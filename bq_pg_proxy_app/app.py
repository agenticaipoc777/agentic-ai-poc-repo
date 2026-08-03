import os
import asyncio
import struct
import time
import traceback
import re
from google.cloud import bigquery


def _load_dotenv_if_present(path=".env"):
    """
    Minimal zero-dependency .env loader. Reads KEY=VALUE lines from a
    local .env file (if present) and applies them via os.environ.setdefault
    so real shell/OS environment variables always take priority over the
    file. This exists purely so you don't have to remember to
    $env:VAR = "..." every time you open a new terminal -- create a
    .env file once next to app.py and it's picked up automatically.
    Lines starting with # are treated as comments and skipped.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


_load_dotenv_if_present()

# Core project configuration. These have working hardcoded defaults so
# `python app.py` runs immediately with no setup -- but any of them can
# still be overridden via a real environment variable or a .env file
# (see _load_dotenv_if_present above) without touching this file, e.g.
# for pointing the same code at a different project/dataset later.
PROJECT_ID = os.environ.get("PG_PROXY_PROJECT_ID", "agentic-ai-502518")
BQ_LOCATION = os.environ.get("PG_PROXY_LOCATION", "EU")
LISTEN_HOST = os.environ.get("PG_PROXY_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PG_PROXY_LISTEN_PORT", "5432"))
# Safety cap on bytes scanned per query, in bytes. Raised from the
# original 100GB default to 500GB: some real tables in this project
# (e.g. fact_sales_transactions_daily) legitimately need to scan more
# than 100GB even for a normal, partition-filtered query, and the old
# default was rejecting those outright (SQLSTATE 57014). 500GB is
# still a real ceiling -- it stops a genuinely runaway/malformed query
# (e.g. a Navigator preview with no filter at all) from silently
# scanning multi-terabyte tables and racking up cost, while giving
# legitimate large queries room to run. Tune via
# PG_PROXY_MAX_BYTES_BILLED (bytes); set to "0" to disable the cap
# entirely (not recommended -- this removes your only protection
# against an accidental full-table scan on a huge table).
MAX_BYTES_BILLED = int(
    os.environ.get("PG_PROXY_MAX_BYTES_BILLED", str(500 * 1024**3))
)

# Safety cap on ROWS returned per query -- separate from the bytes-
# billed cap above, and protecting a different resource. Bytes billed
# caps what BigQuery charges you; this caps how many rows this Python
# process itself pulls into memory as a plain list
# (d_rows = [list(row.values()) for row in res]) before handing them
# back to Power BI. A query that's cheap to bill (e.g. it hits
# BigQuery's own query-result cache) can still return millions of rows
# and blow up this process's own RAM if nothing bounds it, especially
# since a copy of that same row list also sits in self.result_cache
# briefly. Set to "0" to disable the cap entirely.
MAX_RESULT_ROWS = int(
    os.environ.get("PG_PROXY_MAX_RESULT_ROWS", "500000")
)

os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = BQ_LOCATION

GLOBAL_QUERY_REGISTRY = {}

# Postgres type OIDs we actually need
OID_BOOL = 16
OID_INT8 = 20
OID_INT4 = 23
OID_INT2 = 21
OID_TEXT = 25
OID_FLOAT4 = 700
OID_FLOAT8 = 701
OID_NUMERIC = 1700
OID_DATE = 1082
OID_TIMESTAMP = 1114
OID_TIMESTAMPTZ = 1184
OID_VARCHAR = 1043

# Map BigQuery field_type -> (postgres OID, typlen, information_schema
# data_type string). The data_type string matters just as much as the
# OID: Power BI's connector reads information_schema.columns.data_type
# to help decide default aggregation/format (measure vs dimension, date
# formatting), and BigQuery's raw type names ("integer", "float",
# "numeric") are NOT valid Postgres data_type strings -- a real Postgres
# server reports "bigint", "double precision", "numeric", "date", etc.
# Sending BigQuery's own names through unchanged left every column
# looking like an unrecognized/text type to Power BI.
BQ_TO_PG_TYPE = {
    "STRING":     (OID_TEXT,      -1, "text"),
    "BYTES":      (OID_TEXT,      -1, "bytea"),
    "INTEGER":    (OID_INT8,       8, "bigint"),
    "INT64":      (OID_INT8,       8, "bigint"),
    "FLOAT":      (OID_FLOAT8,     8, "double precision"),
    "FLOAT64":    (OID_FLOAT8,     8, "double precision"),
    "NUMERIC":    (OID_NUMERIC,   -1, "numeric"),
    "BIGNUMERIC": (OID_NUMERIC,   -1, "numeric"),
    "BOOLEAN":    (OID_BOOL,       1, "boolean"),
    "BOOL":       (OID_BOOL,       1, "boolean"),
    "DATE":       (OID_DATE,       4, "date"),
    "DATETIME":   (OID_TIMESTAMP,  8, "timestamp without time zone"),
    "TIMESTAMP":  (OID_TIMESTAMPTZ, 8, "timestamp with time zone"),
}
# Kept for backward compatibility with existing call sites that only
# need (oid, typlen).
BQ_TO_PG_OID = {k: (v[0], v[1]) for k, v in BQ_TO_PG_TYPE.items()}


def get_at(array_list, position_index):
    """Safe index extractor that completely avoids bracket literal text."""
    return array_list[position_index]


class ServerlessPGProxy:
    def __init__(self):
        self.bq_client = bigquery.Client(
            project=PROJECT_ID,
            location=BQ_LOCATION
        )
        self.project_id = PROJECT_ID

        # Multi-user credential allowlist. Defaults to root/pass123 if
        # PG_PROXY_ALLOWED_USERS isn't set, so this runs out of the box
        # -- override it (env var or .env) with real credentials for
        # anything beyond local dev. Format: "user1:pass1,user2:pass2"
        self.allowed_users = {}
        raw_users = os.environ.get(
            "PG_PROXY_ALLOWED_USERS", "root:pass123"
        )
        for pair in raw_users.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            u, p = pair.split(":", 1)
            self.allowed_users[u] = p

        # PERF FIX: was hardcoded to 60s. Table/column schemas for a
        # dashboard dataset rarely change minute-to-minute, so a short
        # TTL just forces frequent, expensive re-harvests
        # (list_datasets + parallel list_tables + parallel get_table)
        # for no real benefit. Default raised to 5 minutes; override
        # via PG_PROXY_SCHEMA_CACHE_TTL (seconds) if your schema
        # changes more often and you need fresher metadata.
        self.cache_ttl = int(
            os.environ.get("PG_PROXY_SCHEMA_CACHE_TTL", "300")
        )
        self.schema_cache = None
        self.cache_timestamp = 0
        # Bridges the extended-protocol Describe/Execute split so the
        # same query only hits BigQuery once. See process_respond_sql.
        self.result_cache = {}
        # Simple concurrency guard: cap concurrent in-flight BigQuery
        # jobs so a Power BI report refresh firing many visuals at once
        # can't blow through your BigQuery concurrent-query quota or
        # spike cost unbounded. Tune via PG_PROXY_MAX_CONCURRENT_QUERIES.
        max_concurrent = int(
            os.environ.get("PG_PROXY_MAX_CONCURRENT_QUERIES", "8")
        )
        self.query_semaphore = asyncio.Semaphore(max_concurrent)

        # PERF FIX: guards get_cached_metadata() against a thundering
        # herd. Without this lock, if Power BI fires several visuals at
        # once right when the 60s cache expires, EACH request
        # independently kicks off its own full list_datasets +
        # parallel list_tables + parallel get_table harvest --
        # N redundant full harvests hitting the BigQuery API at the
        # same moment instead of 1. The log showing repeated
        # "Connected user: 'root'" / "Harvesting metadata (parallel)..."
        # lines back-to-back is exactly this happening. With the lock,
        # only the first caller on a cache miss actually harvests;
        # everyone else waits for it and then reads the now-warm cache.
        self.metadata_lock = asyncio.Lock()

    @staticmethod
    def extract_select_columns(sql):
        """
        Best-effort extraction of the projected column/alias names from a
        SELECT statement. Used for queries we intercept and answer
        locally (pg_catalog, information_schema constraint views) so the
        RowDescription we send always matches what the client actually
        asked for -- Postgres always describes the real column list even
        for a query that returns zero rows, and sending a mismatched or
        empty shape is what causes Npgsql/Mashup to null-ref downstream.
        Falls back to a single generic column if parsing fails.
        """
        m = re.search(
            r'select\s+(.*?)\s+from\s', sql, re.IGNORECASE | re.DOTALL
        )
        if not m:
            return [("col", "STRING")]
        col_list = m.group(1)
        if col_list.strip() == "*":
            return [("col", "STRING")]

        # naive split on top-level commas (ignores commas inside parens)
        parts = []
        depth = 0
        current = ""
        for ch in col_list:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
        if current.strip():
            parts.append(current)

        names = []
        for p in parts:
            p = p.strip()
            alias_match = re.search(
                r'\bas\s+"?([A-Za-z_][\w$]*)"?\s*$', p, re.IGNORECASE
            )
            if alias_match:
                names.append(alias_match.group(1))
                continue
            # no explicit AS -- take the last dotted/quoted token
            tok = re.split(r'[\s.]', p.strip().strip('"'))
            tok = [t for t in tok if t]
            names.append(tok[-1].strip('"') if tok else "col")
        return [(n or f"col{i}", "STRING") for i, n in enumerate(names)]

    @staticmethod
    def rewrite_postgres_dialect(sql):
        """
        Rewrites common Postgres SQL dialect constructs into their
        BigQuery Standard SQL equivalents. This is the real gap behind
        most "DAX translation" failures: Power BI's engine folds DAX
        into Postgres-flavored SQL (because it thinks it's talking to
        a real Postgres server) BEFORE it ever reaches this proxy --
        DAX/MDX itself never crosses the wire. What actually breaks at
        scale, with real joins and aggregates, is Postgres syntax that
        has no BigQuery equivalent or a differently-named one. This
        function is a living rule table: extend it as new BadRequest
        errors surface a new construct, the same way every fix this
        session traced back to one specific unsupported pattern.

        Ordering matters -- more specific patterns are rewritten before
        more general ones so a later rule doesn't clobber text a
        rewrite already produced.
        """
        out = sql

        # ILIKE (case-insensitive LIKE) -> BigQuery has no ILIKE.
        # Standard SQL equivalent: wrap both sides in UPPER(...) LIKE.
        # Operands must be matched as a whole quoted identifier (which
        # commonly contains spaces in Power BI-generated column names
        # like "Material Name") OR a bare token -- a naive \S+ match
        # incorrectly splits on the space inside a quoted identifier.
        ident_or_token = r'(?:"[^"]+"\.)?"[^"]+"|\S+'
        out = re.sub(
            rf'({ident_or_token})\s+ILIKE\s+({ident_or_token})',
            r'UPPER(\1) LIKE UPPER(\2)',
            out, flags=re.IGNORECASE
        )

        # ::type casts (Postgres shorthand) -> CAST(... AS type)
        # e.g. price::numeric -> CAST(price AS numeric)
        # e.g. "$Table".amount::float8 -> CAST(...AS FLOAT64)
        pg_to_bq_cast_type = {
            "character varying": "STRING",
            "double precision": "FLOAT64",
            "text": "STRING", "varchar": "STRING",
            "int": "INT64", "int4": "INT64", "integer": "INT64",
            "int8": "INT64", "bigint": "INT64",
            "float4": "FLOAT64", "float8": "FLOAT64",
            "real": "FLOAT64",
            "numeric": "NUMERIC", "decimal": "NUMERIC",
            "bool": "BOOL", "boolean": "BOOL",
            "date": "DATE", "timestamp": "TIMESTAMP",
            "timestamptz": "TIMESTAMP",
        }
        # Match only against the known type names (longest first, so
        # "double precision" wins over a stray partial match), never a
        # generic word-run -- a generic capture over-matches into
        # whatever SQL keyword follows (e.g. "numeric FROM t" being
        # read as the type "numeric from").
        type_alt = "|".join(
            re.escape(t) for t in
            sorted(pg_to_bq_cast_type, key=len, reverse=True)
        )

        def cast_repl(m):
            expr, pg_type = m.group(1), m.group(2).lower().strip()
            bq_type = pg_to_bq_cast_type.get(pg_type, pg_type.upper())
            return f'CAST({expr} AS {bq_type})'

        out = re.sub(
            rf'([\w.`"\)\]]+)::({type_alt})\b',
            cast_repl, out, flags=re.IGNORECASE
        )

        # date_trunc('unit', col) -> DATE_TRUNC(col, UNIT) -- BigQuery
        # swaps argument order and wants the unit as a bare keyword,
        # not a string literal.
        def date_trunc_repl(m):
            unit, col = m.group(1), m.group(2)
            return f'DATE_TRUNC({col}, {unit.upper()})'
        out = re.sub(
            r"date_trunc\(\s*'(\w+)'\s*,\s*([^)]+)\)",
            date_trunc_repl, out, flags=re.IGNORECASE
        )

        # EXTRACT(field FROM col) is valid in both dialects as-is --
        # no rewrite needed, listed here as a documented non-issue so
        # it isn't mistakenly "fixed" by a future edit.

        # NOW() -> CURRENT_TIMESTAMP() (Postgres allows both; BigQuery
        # only accepts the function-call form for current timestamp)
        out = re.sub(r'\bNOW\(\)', 'CURRENT_TIMESTAMP()', out, flags=re.IGNORECASE)

        # Postgres string concatenation with || works identically in
        # BigQuery Standard SQL -- no rewrite needed, documented for
        # the same reason as EXTRACT above.

        # LIMIT x OFFSET y is valid in both -- no rewrite needed.

        # TRUE/FALSE literals are valid in both -- no rewrite needed.

        return out

    def translate_sql_to_bigquery(self, sql, known_tables=None):
        """
        Translates identifiers from Postgres to BigQuery standard syntax.

        known_tables: optional set of (dataset_id_lower, table_id_lower)
        tuples from real BigQuery metadata. Only a "X"."Y" pair that
        matches a REAL dataset/table is qualified with the project id.
        Guessing by pattern alone is not reliable: Npgsql/Mashup uses
        the identical "X"."Y" quoting for alias-qualified columns too,
        and the alias name varies by query shape -- we've seen both
        "$Table"."email_id" and "rows"."Base Quantity" incorrectly
        merged into one bogus identifier
        (`agentic-ai-502518.rows.Base Quantity`) by a purely
        pattern-based approach, which BigQuery then rejects as
        "Unrecognized name". Checking against real metadata is the only
        reliable way to tell a dataset.table reference apart from an
        alias.column reference.
        """
        clean_sql = sql.replace('\n', ' ').replace('\r', ' ')
        clean_sql = self.rewrite_postgres_dialect(clean_sql)
        known_tables = known_tables or set()

        def qualify_if_real_table(m):
            left, right = m.group(1), m.group(2)
            if (left.lower(), right.lower()) in known_tables:
                return f'`{self.project_id}.{left}.{right}`'
            # Not a known dataset.table -- leave as-is, the generic
            # backtick pass below will quote it as alias.column instead.
            return m.group(0)

        tp = r'"([^"]+)"\."([^"]+)"'
        clean_sql = re.sub(tp, qualify_if_real_table, clean_sql)

        # Any remaining double-quoted identifiers (aliases, quoted
        # column names) must become backtick-quoted BigQuery identifiers
        # -- NOT have their quotes simply stripped, which turns e.g.
        # "$Table" into the bare token $Table (BigQuery rejects an
        # unquoted identifier starting with '$').
        clean_sql = re.sub(r'"([^"]+)"', r'`\1`', clean_sql)
        return clean_sql

    async def get_cached_metadata(self):
        """
        Public entry point. Fast-path: if the cache is warm, return it
        immediately with no locking at all -- this is the common case
        for every query once the cache has been populated once.

        PERF FIX: only acquires self.metadata_lock on a cache miss, and
        re-checks freshness *inside* the lock before harvesting. Without
        this, several concurrent requests hitting a cold/expired cache
        at the same instant (e.g. Power BI firing multiple visuals on
        report open) would each independently call the full BigQuery
        harvest below -- N redundant list_datasets/list_tables/get_table
        sweeps racing each other instead of 1. With the lock, only the
        first caller actually harvests; every other concurrent caller
        waits for that single harvest to finish and then reads the
        now-warm cache instead of starting its own.
        """
        now = time.time()
        if self.schema_cache and (
            now - self.cache_timestamp < self.cache_ttl
        ):
            return self.schema_cache

        async with self.metadata_lock:
            # Re-check: another coroutine may have already refreshed
            # the cache while we were waiting for the lock.
            now = time.time()
            if self.schema_cache and (
                now - self.cache_timestamp < self.cache_ttl
            ):
                return self.schema_cache
            return await self._harvest_metadata()

    async def _harvest_metadata(self):
        """
        Fetches and caches metadata maps directly from the BigQuery API.
        Only ever called from get_cached_metadata() while holding
        self.metadata_lock -- never call this directly.

        Table and column enumeration is parallelized (list_tables per
        dataset, then get_table per table, all concurrently) instead of
        one at a time in a sequential loop. With many datasets/tables
        this was previously the slowest part of the whole request path
        -- and it now runs on every real query too, since
        translate_sql_to_bigquery needs it to correctly distinguish a
        genuine dataset.table reference from an alias.column reference.
        A slow sequential harvest here directly delayed every query.
        """
        now = time.time()

        print("Harvesting metadata (parallel)...")
        loop = asyncio.get_event_loop()
        try:
            datasets = await loop.run_in_executor(
                None,
                lambda: list(self.bq_client.list_datasets())
            )
        except Exception as e:
            print(f"API Error: {e}")
            return {"datasets": [], "tables": [], "columns": []}

        dataset_rows = [[ds.dataset_id] for ds in datasets]

        async def list_tables_for(ds):
            tables = await loop.run_in_executor(
                None,
                lambda: list(self.bq_client.list_tables(ds.dataset_id))
            )
            return ds, tables

        ds_table_results = await asyncio.gather(
            *(list_tables_for(ds) for ds in datasets)
        )

        async def get_table_schema(ds, t):
            t_full = await loop.run_in_executor(
                None,
                lambda: self.bq_client.get_table(
                    f"{self.bq_client.project}."
                    f"{ds.dataset_id}.{t.table_id}"
                )
            )
            cols = []
            for idx, field in enumerate(t_full.schema, start=1):
                _, _, pg_type_name = BQ_TO_PG_TYPE.get(
                    field.field_type.upper(), (OID_TEXT, -1, "text")
                )
                cols.append([
                    ds.dataset_id, t.table_id, field.name,
                    pg_type_name, str(idx)
                ])
            return ds.dataset_id, t.table_id, cols

        table_rows = []
        schema_fetch_tasks = []
        for ds, tables in ds_table_results:
            for t in tables:
                table_rows.append([ds.dataset_id, t.table_id, "BASE TABLE"])
                schema_fetch_tasks.append(get_table_schema(ds, t))

        column_rows = []
        if schema_fetch_tasks:
            results = await asyncio.gather(
                *schema_fetch_tasks, return_exceptions=True
            )
            for r in results:
                if isinstance(r, Exception):
                    print(f"Schema fetch error: {r}")
                    continue
                _, _, cols = r
                column_rows.extend(cols)

        self.schema_cache = {
            "datasets": dataset_rows,
            "tables": table_rows,
            "columns": column_rows
        }
        self.cache_timestamp = now
        return self.schema_cache

    async def handle_client(self, reader, writer):
        """Processes initial connection checks and setup tokens safely."""
        try:
            length_buf = await reader.readexactly(4)
            packet_len, = struct.unpack('!I', length_buf)
            st_payload = await reader.readexactly(packet_len - 4)

            if struct.unpack('!I', st_payload[:4]) == (80877103,):
                writer.write(b'N')
                await writer.drain()
                length_buf = await reader.readexactly(4)
                packet_len, = struct.unpack('!I', length_buf)
                st_payload = await reader.readexactly(packet_len - 4)

            payload_str = st_payload[4:].decode('utf-8', errors='ignore')
            parts = payload_str.split('\x00')
            client_user = ""
            for i in range(len(parts)):
                if get_at(parts, i) == 'user' and i + 1 < len(parts):
                    client_user = get_at(parts, i + 1)
                    break

            print(f"Connected user: '{client_user}'")
            writer.write(b'R' + struct.pack('!II', 8, 3))
            await writer.drain()

            msg_type = await reader.readexactly(1)
            if msg_type != b'p':
                return

            len_buf = await reader.readexactly(4)
            msg_len, = struct.unpack('!I', len_buf)
            pass_payload = await reader.readexactly(msg_len - 4)
            client_pass = pass_payload.decode('utf-8').rstrip('\x00')

            if self.allowed_users.get(client_user) != client_pass:
                err = b"SFATAL\x00C28P01\x00MInvalid credentials.\x00\x00"
                writer.write(b'E' + struct.pack('!I', len(err) + 4) + err)
                await writer.drain()
                return

            writer.write(b'R' + struct.pack('!II', 8, 0))
            params = [
                ("server_version", "15.0"),
                ("client_encoding", "UTF8"),
                ("DateStyle", "ISO, YMD")
            ]
            for key, val in params:
                p_bytes = f"{key}\x00{val}\x00".encode('utf-8')
                writer.write(
                    b'S' + struct.pack('!I', len(p_bytes) + 4) + p_bytes
                )

            writer.write(b'K' + struct.pack('!III', 12, 12345, 67890))
            writer.write(b'Z' + struct.pack('!I', 5) + b'I')
            await writer.drain()
            await self.parse_extended_pipeline(reader, writer)
        except (ConnectionResetError, OSError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            print(f"Handler Error: {str(e)}")
            traceback.print_exc()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def parse_extended_pipeline(self, reader, writer):
        """
        Buffers incoming bytes across reads and only parses complete
        messages. The previous version parsed within a single `data`
        chunk and dropped/misaligned partial messages that spanned
        two TCP reads -- this is what corrupted Bind/Execute/Data
        flow for actual query results once payloads got larger than
        a single read() call (which is exactly what happens once you
        go from schema/table introspection to real BigQuery rows).
        """
        buffer = b""
        local_stmt = ""
        portal_to_stmt = {}
        while True:
            data = await reader.read(65536)
            if not data:
                break
            buffer += data

            while True:
                if len(buffer) < 5:
                    break
                msg_type = buffer[0:1]
                msg_len, = struct.unpack('!I', buffer[1:5])
                total_len = 1 + msg_len
                if len(buffer) < total_len:
                    break  # wait for more bytes, do not desync

                payload = buffer[5:total_len]
                buffer = buffer[total_len:]

                if msg_type == b'Q':
                    sql_str = payload.decode(
                        'utf-8', errors='ignore'
                    ).rstrip('\x00')
                    GLOBAL_QUERY_REGISTRY[""] = sql_str
                    await self.process_respond_sql(
                        sql_str, writer, extended_mode=False
                    )
                elif msg_type == b'P':
                    p_parts = payload.split(b'\x00')
                    if len(p_parts) > 1:
                        stmt_bytes = get_at(p_parts, 0)
                        query_bytes = get_at(p_parts, 1)
                        stmt = stmt_bytes.decode('utf-8', errors='ignore')
                        sql_q = query_bytes.decode('utf-8', errors='ignore')
                        local_stmt = stmt
                        GLOBAL_QUERY_REGISTRY[stmt] = sql_q
                    writer.write(b'1' + struct.pack('!I', 4))
                    await writer.drain()
                elif msg_type == b'B':
                    # Bind payload: portal_name\0 stmt_name\0 ...
                    # Record which prepared statement THIS PORTAL binds
                    # to, keyed by portal name -- not a single shared
                    # variable. Multiple portals can be open at once
                    # (e.g. an interleaved metadata probe + the real
                    # aggregate query), and overwriting one shared
                    # local_stmt caused a later Execute to run against
                    # whichever statement was bound most recently
                    # instead of the one its own portal actually points
                    # to -- producing a schema/data mismatch that
                    # surfaces as "failed to move the data reader to
                    # the next row".
                    b_parts = payload.split(b'\x00')
                    if len(b_parts) > 1:
                        portal_name = get_at(b_parts, 0).decode(
                            'utf-8', errors='ignore'
                        )
                        stmt_name = get_at(b_parts, 1).decode(
                            'utf-8', errors='ignore'
                        )
                        portal_to_stmt[portal_name] = stmt_name
                        if stmt_name in GLOBAL_QUERY_REGISTRY:
                            local_stmt = stmt_name
                    writer.write(b'2' + struct.pack('!I', 4))
                    await writer.drain()
                elif msg_type == b'D':
                    # Describe payload: 'S' or 'P' (1 byte) + name
                    target_stmt = local_stmt
                    if len(payload) > 1:
                        kind = payload[0:1]
                        name = payload[1:].split(b'\x00')[0].decode(
                            'utf-8', errors='ignore'
                        )
                        if kind == b'P' and name in portal_to_stmt:
                            target_stmt = portal_to_stmt[name]
                        elif kind == b'S' and name in GLOBAL_QUERY_REGISTRY:
                            target_stmt = name
                    sql_run = GLOBAL_QUERY_REGISTRY.get(
                        target_stmt, GLOBAL_QUERY_REGISTRY.get("", "")
                    )
                    await self.process_respond_sql(
                        sql_run, writer, extended_mode=True,
                        describe_phase=True
                    )
                elif msg_type == b'E':
                    # Execute payload: portal_name\0 + max_rows(4 bytes)
                    target_stmt = local_stmt
                    if b'\x00' in payload:
                        portal_name = payload.split(b'\x00')[0].decode(
                            'utf-8', errors='ignore'
                        )
                        if portal_name in portal_to_stmt:
                            target_stmt = portal_to_stmt[portal_name]
                    sql_run = GLOBAL_QUERY_REGISTRY.get(
                        target_stmt, GLOBAL_QUERY_REGISTRY.get("", "")
                    )
                    await self.process_respond_sql(
                        sql_run, writer, extended_mode=True,
                        describe_phase=False
                    )
                elif msg_type == b'C':
                    # Close (statement or portal) -- ack and drop it
                    if len(payload) > 1:
                        kind = payload[0:1]
                        name = payload[1:].split(b'\x00')[0].decode(
                            'utf-8', errors='ignore'
                        )
                        if kind == b'P':
                            portal_to_stmt.pop(name, None)
                        elif kind == b'S':
                            GLOBAL_QUERY_REGISTRY.pop(name, None)
                    writer.write(b'3' + struct.pack('!I', 4))
                    await writer.drain()
                elif msg_type == b'S':
                    writer.write(b'Z' + struct.pack('!I', 5) + b'I')
                    await writer.drain()
                elif msg_type == b'H':
                    await writer.drain()
                elif msg_type == b'X':
                    return
                # else: ignore unknown/unhandled message types safely

    async def process_respond_sql(
        self, sql, writer, extended_mode=False, describe_phase=False
    ):
        """Intercepts internal engine schemas and routes columns safely."""
        try:
            if not sql:
                if describe_phase:
                    await self.send_custom_desc(writer, [("status", "STRING")])
                else:
                    await self.send_custom_rows(
                        writer, [["OK"]], extended_mode, cmd_tag=b"SELECT 1\x00"
                    )
                return
            sl = sql.lower().strip()

            # Postgres session/administrative commands that Npgsql (and
            # therefore Power BI) sends automatically. These are not valid
            # BigQuery SQL and must never be forwarded -- just ack them.
            session_noops = (
                "discard", "set ", "set session", "set local",
                "begin", "start transaction", "commit", "rollback",
                "reset", "listen", "unlisten", "notify", "close ",
                "deallocate", "show transaction_isolation",
                "show standard_conforming_strings",
            )
            if sl.startswith(session_noops):
                cmd_word = sl.split()[0].upper() if sl.split() else "OK"
                # Postgres' real tag for DISCARD ALL is literally "DISCARD ALL"
                if sl.startswith("discard"):
                    tag = b"DISCARD ALL\x00"
                elif sl.startswith(("begin", "start transaction")):
                    tag = b"BEGIN\x00"
                else:
                    tag = f"{cmd_word}\x00".encode("utf-8")
                if describe_phase:
                    writer.write(b'n' + struct.pack('!I', 4))
                    await writer.drain()
                else:
                    await self.send_custom_rows(
                        writer, [], extended_mode, cmd_tag=tag
                    )
                return

            cat = [
                "pg_type", "pg_enum", "pg_attribute", "pg_namespace",
                "pg_am", "pg_class", "pg_constraint", "pg_index",
                "conrelid", "confrelid", "conkey", "confkey",
                "pg_get_constraintdef", "pg_depend", "pg_trigger"
            ]
            if any(x in sl for x in cat):
                # A zero-row SELECT still has a real, well-defined column
                # list in Postgres -- NoData is only valid for statements
                # with no output at all. Sending NoData here made
                # Npgsql/Mashup treat the column list as null instead of
                # empty, which is what crashed GetPrimaryKey() /
                # get_KeyColumnNames(). Describe the columns the query
                # actually asked for, with zero rows.
                desc_cols = self.extract_select_columns(sql)
                if describe_phase:
                    await self.send_custom_desc(writer, desc_cols)
                else:
                    await self.send_custom_rows(
                        writer, [], extended_mode, cmd_tag=b"SELECT 0\x00"
                    )
                return
            metadata = await self.get_cached_metadata()
            if "information_schema.schemata" in sl:
                rows = metadata["datasets"]
                if describe_phase:
                    await self.send_custom_desc(writer, [("name", "STRING")])
                else:
                    await self.send_custom_rows(
                        writer, rows, extended_mode,
                        cmd_tag=f"SELECT {len(rows)}\x00".encode('utf-8')
                    )
                return
            if "information_schema.tables" in sl:
                rows = metadata["tables"]
                if describe_phase:
                    await self.send_custom_desc(
                        writer, [("table_schema", "STRING"),
                                 ("table_name", "STRING"),
                                 ("table_type", "STRING")]
                    )
                else:
                    await self.send_custom_rows(
                        writer, rows, extended_mode,
                        cmd_tag=f"SELECT {len(rows)}\x00".encode('utf-8')
                    )
                return
            if "information_schema.columns" in sl:
                sm = re.search(r"table_schema\s*=\s*'([^']+)'", sl)
                tm = re.search(r"table_name\s*=\s*'([^']+)'", sl)
                if sm and tm:
                    ts, tt = sm.group(1).lower(), tm.group(1).lower()
                    fc = []
                    for c in metadata["columns"]:
                        if len(c) >= 5:
                            c_schema = get_at(c, 0)
                            c_table = get_at(c, 1)
                            c_name = get_at(c, 2)
                            c_type = get_at(c, 3)
                            c_pos = get_at(c, 4)
                            if (str(c_schema).lower() == ts and
                                    str(c_table).lower() == tt):
                                fc.append([
                                    str(c_name), str(c_pos),
                                    "YES", str(c_type)
                                ])
                    if describe_phase:
                        await self.send_custom_desc(
                            writer, [("column_name", "STRING"),
                                     ("ordinal_position", "INTEGER"),
                                     ("is_nullable", "STRING"),
                                     ("data_type", "STRING")]
                        )
                    else:
                        await self.send_custom_rows(
                            writer, fc, extended_mode,
                            cmd_tag=f"SELECT {len(fc)}\x00".encode('utf-8')
                        )
                return

            # Npgsql queries these unqualified, global information_schema
            # views to discover primary/foreign keys and constraints.
            # BigQuery requires every INFORMATION_SCHEMA reference to be
            # dataset-qualified, so these would always fail if forwarded.
            # BigQuery has no equivalent concept exposed this way, so we
            # just tell the client "no constraints/keys exist" -- which
            # is effectively true and lets Power BI move on.
            constraint_views = (
                "key_column_usage", "table_constraints",
                "referential_constraints", "check_constraints",
                "constraint_column_usage", "views",
                "sequences", "triggers", "routines",
            )
            if any(v in sl for v in constraint_views) and "information_schema" in sl:
                desc_cols = self.extract_select_columns(sql)
                if describe_phase:
                    await self.send_custom_desc(writer, desc_cols)
                else:
                    await self.send_custom_rows(
                        writer, [], extended_mode, cmd_tag=b"SELECT 0\x00"
                    )
                return
            if "character_sets" in sl or "version()" in sl:
                if describe_phase:
                    await self.send_custom_desc(writer, [("val", "STRING")])
                else:
                    await self.send_custom_rows(
                        writer, [["UTF8"]], extended_mode, cmd_tag=b"SELECT 1\x00"
                    )
                return

            # --- Real BigQuery execution path ---
            # FIX: reuse the `metadata` fetched earlier in this same
            # function call (used above for the information_schema
            # interception checks) instead of calling
            # get_cached_metadata() a second time. Previously this ran
            # TWICE per query on every real (non-intercepted) SELECT.
            # get_cached_metadata() is cheap when the 60s cache is warm,
            # but on a cache miss it does list_datasets + parallel
            # list_tables + parallel get_table for every table --
            # running that full harvest twice back-to-back inside a
            # single request is what can push total response time past
            # Npgsql's client-side command timeout, causing the client
            # to abandon the connection before Describe/Execute ever
            # gets a reply -- which is exactly the
            # ConnectionResetError seen in send_custom_desc's
            # writer.drain() in the traceback for this bug.
            known_tables = {
                (str(row[0]).lower(), str(row[1]).lower())
                for row in metadata.get("tables", [])
            }
            bq_sql = self.translate_sql_to_bigquery(sql, known_tables)

            # Extended-protocol Describe ('D') and Execute ('E') are two
            # separate calls into this function for the SAME query.
            # Previously each one ran its own BigQuery job independently
            # -- meaning every real chart/table query hit BigQuery
            # TWICE. Besides being wasteful, this is what was causing
            # "Failed to move the data reader to the next row" on
            # anything non-trivial (aggregates, larger tables): the
            # Describe response came from one job run and the actual
            # row stream from a different one, so Npgsql's reader could
            # desync against a schema that doesn't reliably match the
            # data it's iterating. Cache the single job result and serve
            # both phases from it.
            now = time.time()
            cached = self.result_cache.get(bq_sql)
            if cached and (now - cached[0] < 30):
                fields, d_rows = cached[1], cached[2]
            else:
                loop = asyncio.get_event_loop()
                # use_query_cache=True (BigQuery's own 24h result cache,
                # on by default but made explicit here) plus a
                # maximum_bytes_billed safety cap -- at billions-of-rows
                # scale, an unexpected DAX-folded query shape (e.g. a
                # join that fans out) scanning far more data than
                # intended is a real cost risk, not just a latency one.
                # Tune the cap via PG_PROXY_MAX_BYTES_BILLED (bytes);
                # unset/0 disables the cap.
                job_config = bigquery.QueryJobConfig(
                    use_query_cache=True,
                    maximum_bytes_billed=(
                        MAX_BYTES_BILLED if MAX_BYTES_BILLED > 0 else None
                    ),
                )
                # PERF: query_and_wait() (added in newer
                # google-cloud-bigquery versions) uses BigQuery's
                # synchronous jobs.query REST path instead of the
                # older query()+job.result() flow, which creates an
                # async job and then polls for completion. For the
                # short, dashboard-sized queries Power BI issues, the
                # synchronous path avoids that extra
                # create-then-poll round trip and is meaningfully
                # faster. Not every installed client version has this
                # method, so we check for it and fall back to the
                # original job-based path if it's unavailable rather
                # than hard-depending on a version bump.
                # COST VISIBILITY: dry-run this exact query first.
                # dry_run=True never scans data and is NOT billed --
                # BigQuery just returns how many bytes the real query
                # WOULD process. This runs on every real query so the
                # console log shows the actual cost of each dashboard
                # query as it happens, instead of only finding out via
                # a bytes-billed rejection (or, worse, a monthly bill)
                # that a query is unexpectedly scanning terabytes.
                # Tune the assumed on-demand price via
                # PG_PROXY_BQ_PRICE_PER_TB (USD) if your project uses
                # a different pricing tier/region rate.
                try:
                    dry_run_config = bigquery.QueryJobConfig(
                        dry_run=True, use_query_cache=False
                    )
                    dry_run_job = await loop.run_in_executor(
                        None,
                        lambda: self.bq_client.query(
                            bq_sql, job_config=dry_run_config
                        )
                    )
                    est_bytes = dry_run_job.total_bytes_processed or 0
                    price_per_tb = float(
                        os.environ.get("PG_PROXY_BQ_PRICE_PER_TB", "6.25")
                    )
                    est_cost = (est_bytes / (1024 ** 4)) * price_per_tb
                    print(
                        f"Estimated scan: {est_bytes:,} bytes "
                        f"(~${est_cost:.2f} at ${price_per_tb}/TB) "
                        f"for query: {bq_sql[:120]}..."
                    )
                except Exception as dry_run_err:
                    # Never let a dry-run failure block the real
                    # query -- this is a logging aid, not a gate.
                    print(f"Dry-run estimate failed (non-fatal): {dry_run_err}")

                async with self.query_semaphore:
                    if hasattr(self.bq_client, "query_and_wait"):
                        res = await loop.run_in_executor(
                            None,
                            lambda: self.bq_client.query_and_wait(
                                bq_sql, job_config=job_config
                            )
                        )
                    else:
                        job = await loop.run_in_executor(
                            None,
                            lambda: self.bq_client.query(
                                bq_sql, job_config=job_config
                            )
                        )
                        res = await loop.run_in_executor(None, job.result)
                # FIX: normalize to uppercase here, once, at the source.
                # BQ_TO_PG_OID / BQ_TO_PG_TYPE are keyed on uppercase
                # strings ("BOOL", "BOOLEAN"). f.field_type from the
                # BigQuery client is normally already uppercase, but
                # relying on that implicitly is what let a
                # differently-cased or unexpected value silently fall
                # through to the OID_TEXT/-1 default in send_custom_desc
                # -- which is exactly the kind of declared-type mismatch
                # that produces a client-side DISP_E_TYPEMISMATCH /
                # "Typekonflikt" error in Power BI/OLE DB, since the
                # Describe phase told Npgsql to expect one wire type
                # (e.g. text) while the row data underneath is a real
                # BigQuery BOOLEAN. Normalizing once here keeps
                # send_custom_desc's lookup and send_custom_rows'
                # boolean check both working off the same guaranteed
                # uppercase value.
                fields = [(f.name, f.field_type.upper()) for f in res.schema]

                # MEMORY FIX: enforce PG_PROXY_MAX_RESULT_ROWS before
                # this process commits to holding the full result set
                # in memory. Two checks, because BigQuery doesn't
                # always know total_rows up front (it depends on which
                # execution path was used above):
                #   1. If res.total_rows IS known, fail immediately --
                #      no need to iterate anything.
                #   2. Otherwise, fail as soon as we cross the cap
                #      while iterating, so a huge unbounded result
                #      still can't be fully materialized before we
                #      notice.
                total_rows = getattr(res, "total_rows", None)
                if (
                    MAX_RESULT_ROWS > 0
                    and total_rows is not None
                    and total_rows > MAX_RESULT_ROWS
                ):
                    raise MemoryError(
                        f"Query would return {total_rows} rows, "
                        f"exceeding the configured "
                        f"PG_PROXY_MAX_RESULT_ROWS cap of "
                        f"{MAX_RESULT_ROWS}. Add a filter or "
                        f"aggregation to reduce the result size, or "
                        f"raise PG_PROXY_MAX_RESULT_ROWS if this many "
                        f"rows is genuinely expected."
                    )

                d_rows = []
                for i, row in enumerate(res):
                    if MAX_RESULT_ROWS > 0 and i >= MAX_RESULT_ROWS:
                        raise MemoryError(
                            f"Query exceeded the configured "
                            f"PG_PROXY_MAX_RESULT_ROWS cap of "
                            f"{MAX_RESULT_ROWS} rows while streaming "
                            f"results. Add a filter or aggregation to "
                            f"reduce the result size, or raise "
                            f"PG_PROXY_MAX_RESULT_ROWS if this many "
                            f"rows is genuinely expected."
                        )
                    d_rows.append(list(row.values()))

                # keep the cache small -- this is just to bridge the
                # Describe -> Execute gap for the same statement, not a
                # general-purpose result cache
                if len(self.result_cache) > 20:
                    self.result_cache.clear()
                self.result_cache[bq_sql] = (now, fields, d_rows)

            if describe_phase:
                await self.send_custom_desc(writer, fields)
            else:
                await self.send_custom_rows(
                    writer, d_rows, extended_mode,
                    cmd_tag=f"SELECT {len(d_rows)}\x00".encode('utf-8'),
                    field_types=[ft for _, ft in fields]
                )
                # Once served to Execute, drop it -- a fresh Describe
                # for the same SQL text later should re-run rather than
                # serve increasingly stale cached data.
                self.result_cache.pop(bq_sql, None)
        except Exception as e:
            err_text = str(e)
            print(f"Query Error: {err_text}")
            traceback.print_exc()

            # Give the BigQuery MAX_BYTES_BILLED safety-cap rejection
            # its own recognizable identity instead of burying it under
            # the same generic 42601 (syntax error) SQLSTATE as every
            # other failure. "Query exceeded limit for bytes billed" is
            # BigQuery's own wording for this specific rejection --
            # matching on it lets us report Postgres SQLSTATE 57014
            # (query_canceled / resource limit exceeded) with a message
            # that names the actual cause (the PG_PROXY_MAX_BYTES_BILLED
            # cap) instead of leaving it looking like a SQL syntax
            # problem, which is what the generic path made it look like
            # in the Power BI error dialog.
            if isinstance(e, MemoryError):
                # This proxy's own PG_PROXY_MAX_RESULT_ROWS cap firing
                # -- distinct from BigQuery's bytes-billed rejection
                # above. SQLSTATE 54000 (program_limit_exceeded) is the
                # closest real Postgres code for "this result is too
                # large for the receiving side to handle," which is
                # accurate here: BigQuery was willing to run the
                # query, but this proxy declined to hold the full
                # result set in memory.
                sqlstate = "54000"
                friendly = err_text
            elif "bytes billed" in err_text.lower():
                sqlstate = "57014"
                friendly = (
                    "Query rejected: it would scan more data than the "
                    "configured PG_PROXY_MAX_BYTES_BILLED safety cap "
                    f"allows. Underlying BigQuery error: {err_text}"
                )
            else:
                sqlstate = "42601"
                friendly = err_text

            ep = f"SERROR\x00C{sqlstate}\x00M{friendly}\x00\x00".encode('utf-8')
            writer.write(b'E' + struct.pack('!I', len(ep) + 4) + ep)
            if not extended_mode:
                writer.write(b'Z' + struct.pack('!I', 5) + b'I')
            await writer.drain()

    async def send_custom_desc(self, writer, fields):
        """
        fields: list of (name, bq_type_or_STRING) tuples.
        Sends correct-ish OIDs per column instead of hardcoding text (1043)
        for everything, which is a common cause of the Power BI provider
        choking while reading real data rows.
        """
        fp = b""
        for name, bq_type in fields:
            oid, typlen = BQ_TO_PG_OID.get(bq_type.upper(), (OID_TEXT, -1))
            fp += name.encode('utf-8') + b'\x00'
            fp += struct.pack('!IHIhiH', 0, 0, oid, typlen, -1, 0)
        writer.write(
            b'T' + struct.pack('!IH', len(fp) + 6, len(fields)) + fp
        )
        await writer.drain()

    @staticmethod
    def format_pg_value(val, bq_type):
        """
        Formats a Python value returned by the BigQuery client into the
        Postgres wire *text* representation expected for the OID we
        declared for this column in send_custom_desc. A plain str(val)
        works for STRING/INTEGER/FLOAT, but DATE/TIMESTAMP/NUMERIC/BOOL
        values need an exact format or Npgsql's type parser throws
        client-side (which is what surfaces in Power BI as a generic
        "Object reference not set to an instance of an object" with no
        underlying BigQuery error -- the query already succeeded).
        """
        bt = (bq_type or "").upper()
        if bt in ("BOOL", "BOOLEAN"):
            # BigQuery can hand back Python bool True/False, but also
            # int 0/1 or string "true"/"false" depending on how the
            # row values were materialized. Postgres wire text format
            # for a boolean-typed column MUST be exactly 't' or 'f' --
            # anything else (e.g. "1", "0", "True") makes Npgsql's
            # type parser throw client-side, which is the boolean
            # fetch error. Normalize every truthy/falsy representation
            # explicitly rather than relying on Python's isinstance(bool).
            if isinstance(val, str):
                return "t" if val.strip().lower() in ("true", "t", "1") else "f"
            return "t" if val else "f"
        if bt == "DATE":
            # datetime.date -> 'YYYY-MM-DD'
            try:
                return val.isoformat()
            except AttributeError:
                return str(val)
        if bt in ("TIMESTAMP", "DATETIME"):
            # datetime.datetime -> 'YYYY-MM-DD HH:MM:SS[.ffffff][+HH:MM]'
            # Postgres text format uses a space, not Python's 'T' separator.
            try:
                iso = val.isoformat(sep=' ')
            except AttributeError:
                return str(val)
            return iso
        if bt in ("NUMERIC", "BIGNUMERIC"):
            # decimal.Decimal -> plain string, never scientific notation
            try:
                return format(val, 'f')
            except (ValueError, TypeError):
                return str(val)
        if bt == "BYTES":
            # bytea hex format Postgres expects: \x followed by hex
            try:
                return '\\x' + val.hex()
            except AttributeError:
                return str(val)
        if bt in ("FLOAT", "FLOAT64"):
            # Python's str()/repr() give 'nan'/'inf', but Postgres text
            # format expects 'NaN'/'Infinity' -- a real risk with
            # SUM()/AVG() aggregate chart queries over real data.
            try:
                fv = float(val)
                if fv != fv:  # NaN check
                    return "NaN"
                if fv == float("inf"):
                    return "Infinity"
                if fv == float("-inf"):
                    return "-Infinity"
                return repr(fv)
            except (ValueError, TypeError):
                return str(val)
        return str(val)

    async def send_custom_rows(
        self, writer, rows, extended_mode=False, cmd_tag=b"SELECT 0\x00",
        field_types=None
    ):
        for r in rows:
            rp = b""
            for i, val in enumerate(r):
                if val is None:
                    # Proper SQL NULL: length -1, no bytes.
                    rp += struct.pack('!i', -1)
                    continue

                bq_type = (
                    field_types[i]
                    if field_types and i < len(field_types)
                    else None
                )

                # FIX: boolean handling now goes through format_pg_value,
                # keyed off the DECLARED BigQuery column type -- not off
                # Python's isinstance(val, bool). Previously, if a BOOL
                # column ever came back as a Python int (0/1) or string
                # instead of a native True/False, isinstance(val, bool)
                # silently failed, fell through to a plain str(val), and
                # sent "1"/"0" as the row text for a column declared as
                # Postgres OID 16 (boolean) -- Npgsql then throws trying
                # to parse "1"/"0" as a boolean, since it only accepts
                # 't'/'f'. Checking the declared type is authoritative
                # and catches every representation BigQuery might hand
                # back for a BOOL/BOOLEAN field.
                if (bq_type or "").upper() in ("BOOL", "BOOLEAN") or isinstance(val, bool):
                    bv = self.format_pg_value(val, "BOOL").encode('utf-8')
                else:
                    try:
                        text_val = self.format_pg_value(val, bq_type)
                    except Exception:
                        text_val = str(val)
                    bv = text_val.encode('utf-8')

                rp += struct.pack('!I', len(bv)) + bv
            writer.write(
                b'D' + struct.pack('!IH', len(rp) + 6, len(r)) + rp
            )
        writer.write(b'C' + struct.pack('!I', len(cmd_tag) + 4) + cmd_tag)
        if not extended_mode:
            writer.write(b'Z' + struct.pack('!I', 5) + b'I')
        await writer.drain()


async def main():
    proxy = ServerlessPGProxy()
    server = await asyncio.start_server(
        proxy.handle_client, LISTEN_HOST, LISTEN_PORT
    )
    print(f"Proxy listening on {LISTEN_HOST}:{LISTEN_PORT} "
          f"(project={PROJECT_ID}, location={BQ_LOCATION}) ...")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())