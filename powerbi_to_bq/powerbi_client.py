"""
Power BI semantic model client -- authenticates as YOU (an
interactive user) via MSAL's device code flow, and runs DAX queries
against a dataset through the Execute Queries REST API.

Device code flow instead of a client secret / service principal:
opens a real Microsoft sign-in page (correctly handles MFA and
Conditional Access, unlike the username/password ROPC flow, which
typically fails outright once MFA is enforced -- true for essentially
any real corporate tenant), and never has your password touch this
code at all.

STILL REQUIRES, regardless of which auth method is used:
1. An Entra ID app registration -- a PUBLIC client this time (no
   secret needed), with the "Power BI Service" API permission
   (delegated, not application) added. If you don't have permission
   to create app registrations in this tenant, someone with Entra ID
   admin/Application Administrator rights needs to create one and
   give you the Client ID.
2. Power BI Admin Portal -> Tenant settings -> Integration settings ->
   "Dataset Execute Queries REST API" enabled. This is a SEPARATE,
   unconditional requirement -- it applies no matter which auth
   method (service principal or interactive user) is used. Your
   earlier screenshot showed only "Capacity settings" in the Admin
   Portal sidebar, which means you likely have Capacity Administrator
   rights, not full Power BI/Fabric Administrator -- meaning you
   probably cannot see or change this setting yourself. Switching
   auth methods does not get around this; if it's not already
   enabled, someone with full tenant admin rights needs to enable it
   before ANY of this works, for either auth approach.
3. Your own account needs Build permission on the target dataset
   (workspace -> dataset -> Manage permissions), and at least Viewer
   role on the workspace.
"""
import os
import re
from pathlib import Path
import requests
import msal
import pandas as pd

SCOPE = ["https://analysis.windows.net/powerbi/api/Dataset.Read.All"]

# Persistent, file-backed token cache. Without this, a fresh
# msal.PublicClientApplication() with no cache would have zero
# accounts on every call -- meaning get_access_token() would trigger
# a BRAND NEW device-code sign-in prompt for every single API call
# (table discovery, then one more per table synced). With this, you
# sign in once via device code, and every subsequent call in this
# process -- or even a later run of the script, until the refresh
# token itself expires per your tenant's policy -- reuses it silently
# with no prompt.
_CACHE_FILE = Path(__file__).parent / ".msal_token_cache.bin"
_token_cache = msal.SerializableTokenCache()
if _CACHE_FILE.exists():
    _token_cache.deserialize(_CACHE_FILE.read_text())

# FIX: previously TENANT_ID/CLIENT_ID were read ONCE at module import
# time and _get_msal_app() cached a single app instance forever after.
# In a Streamlit UI, the module is imported once for the life of the
# server process, but the tenant/client ID fields can change on every
# rerun -- so the old code kept using whatever values (often empty
# strings, on the very first import before the UI had rendered any
# fields yet) were present the first time, no matter what you typed
# afterward. Now both are read fresh from the environment on every
# call, and the cached app is rebuilt if the tenant/client actually
# changed since the last call.
_msal_app = None
_msal_app_key = None  # (tenant_id, client_id) the cached app was built for


def _save_cache():
    if _token_cache.has_state_changed:
        _CACHE_FILE.write_text(_token_cache.serialize())


def _get_msal_app():
    global _msal_app, _msal_app_key
    tenant_id = os.environ.get("PBI_TENANT_ID", "")
    client_id = os.environ.get("PBI_CLIENT_ID", "")
    if not (tenant_id and client_id):
        raise RuntimeError("PBI_TENANT_ID / PBI_CLIENT_ID must both be set.")

    current_key = (tenant_id, client_id)
    if _msal_app is None or _msal_app_key != current_key:
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        _msal_app = msal.PublicClientApplication(
            client_id, authority=authority, token_cache=_token_cache
        )
        _msal_app_key = current_key
    return _msal_app


def get_access_token(on_device_code=None) -> str:
    """
    on_device_code: optional callback(message: str) -- called with the
    device-code sign-in instructions instead of printing to stdout,
    so a UI (e.g. Streamlit) can display it on-screen. If not given,
    prints to the console as before.
    """
    app = _get_msal_app()

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPE, account=accounts[0])
        if result and "access_token" in result:
            _save_cache()
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=SCOPE)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")

    if on_device_code:
        on_device_code(flow["message"])
    else:
        print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)  # blocks until sign-in completes
    _save_cache()

    if "access_token" not in result:
        raise RuntimeError(
            f"Failed to acquire Power BI token: "
            f"{result.get('error')}: {result.get('error_description')}"
        )
    return result["access_token"]


def execute_dax_query(
    workspace_id: str, dataset_id: str, dax_query: str, on_device_code=None
) -> pd.DataFrame:
    """
    Runs a single DAX query (e.g. "EVALUATE 'Sales'" or
    "EVALUATE SUMMARIZECOLUMNS(...)") against the given dataset and
    returns the single result table as a DataFrame.

    Column names come back fully qualified (e.g. "Sales[OrderDate]")
    for plain table references, or bracketed (e.g. "[TotalRevenue]")
    for computed/renamed columns -- this strips the table-qualifier
    prefix so downstream BigQuery column names are clean, since
    "Sales[OrderDate]" isn't a valid-looking column name to carry
    through unchanged.
    """
    token = get_access_token(on_device_code=on_device_code)
    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}"
        f"/datasets/{dataset_id}/executeQueries"
    )
    body = {
        "queries": [{"query": dax_query}],
        "serializerSettings": {"includeNulls": True},
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Execute Queries failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    tables = data["results"][0]["tables"]
    if not tables:
        return pd.DataFrame()
    rows = tables[0]["rows"]
    df = pd.DataFrame(rows)

    # Strip "TableName[Column]" -> "Column" for clean BigQuery-bound
    # column names; leave "[ComputedCol]"-style names as "ComputedCol".
    df.columns = [
        re.sub(r"^.*\[(.+)\]$", r"\1", col) for col in df.columns
    ]
    return df


def list_model_tables(workspace_id: str, dataset_id: str, on_device_code=None) -> list[str]:
    """
    Discovers every table name in the semantic model, so a sync run
    doesn't require hardcoding one table name -- uses DAX's built-in
    INFO.TABLES() function, which the Execute Queries API explicitly
    supports (INFO functions are allowed even though general MDX/DMV
    queries are not).
    """
    df = execute_dax_query(
        workspace_id, dataset_id,
        "EVALUATE SELECTCOLUMNS(INFO.TABLES(), \"Name\", [Name])",
        on_device_code=on_device_code,
    )
    if df.empty or "Name" not in df.columns:
        return []
    return df["Name"].tolist()