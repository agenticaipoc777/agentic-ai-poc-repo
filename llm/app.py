"""
Local LLM chat app -- fully offline inference (no external API calls
at runtime), served as a Streamlit chat UI.

MODEL_ID is configurable via env var so you can iterate fast locally
with a small model, then deploy with the real 7B model for
production -- swapping is a one-line env var change, no code change.
"""
import os
import re
import threading

import streamlit as st
import torch
from transformers import (
    AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, BitsAndBytesConfig
)

import rag

# Default to a small, fast model for local dev/testing. Override with
# MODEL_ID=Qwen/Qwen2.5-7B-Instruct (or similar) for the real
# production deployment -- see the Dockerfile, which bakes the model
# into the image at build time for that case.
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")

# Optional: load in 4-bit quantized mode -- shrinks VRAM needs
# dramatically (roughly a 4x reduction vs full fp16), letting a
# bigger/more capable model (e.g. a 14B or 32B model) fit on a single
# L4 GPU's 24GB, at a small quality/speed cost vs full precision.
# Not needed for 7B-and-under models on an L4 -- those fit at full
# precision already.
USE_4BIT = os.environ.get("USE_4BIT_QUANTIZATION", "false").lower() == "true"

st.set_page_config(page_title="Local LLM Chat", page_icon="🤖", layout="wide")

# ==============================================================================
# MODEL LOADING (cached -- runs once per process, not on every rerun)
# ==============================================================================

@st.cache_resource(show_spinner="Loading model...")
def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    quantization_config = None
    if USE_4BIT:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype="auto",
        device_map="auto",
        quantization_config=quantization_config,
    )
    return tokenizer, model


tokenizer, model = load_model()
device = next(model.parameters()).device

# ==============================================================================
# TOOLS (unchanged from the original script)
# ==============================================================================

def calculate_square_foot(radius: str) -> str:
    """Calculates area of a circle given radius."""
    try:
        r = float(radius)
        return str(3.14159 * (r ** 2))
    except Exception as e:
        return f"Error: {str(e)}"


TOOLS = {"calculate_square_foot": calculate_square_foot}

SYSTEM_PROMPT = """You are an advanced AI Agent operating completely OFFLINE.
You must answer questions using your deep internal knowledge parameters.

Available tools:
- calculate_square_foot: ONLY use this tool if the user explicitly asks to calculate a circle's area.

Your responses must strictly follow one of these two formats:

Format A (If calculating a circle area):
Thought: Reflect on what to do.
Action: calculate_square_foot[radius]

Format B (For all other general knowledge questions):
Thought: Reflect on the answer using your internal memory.
Final Answer: <your final response to the user>

CRITICAL: Never try to use the calculate_square_foot tool for general questions. Use your internal knowledge base to provide maximum detail.
"""

# ==============================================================================
# STREAMING GENERATION
# ==============================================================================

def generate_streaming(messages: list, placeholder):
    """
    Streams tokens into the given Streamlit placeholder as they're
    generated, instead of blocking until the full response is done --
    a 7B model on a single GPU is not instant, and a live-updating
    response is a meaningfully better experience than a frozen UI.
    """
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    generation_kwargs = dict(
        **inputs,
        streamer=streamer,
        max_new_tokens=256,
        do_sample=False,
    )
    thread = threading.Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()

    full_text = ""
    for token_text in streamer:
        full_text += token_text
        placeholder.markdown(full_text + "▌")
    placeholder.markdown(full_text)
    thread.join()
    return full_text


def run_agent(user_query: str, placeholder, use_rag: bool = True):
    effective_query = user_query
    if use_rag:
        retrieved_chunks = rag.retrieve(user_query, k=3)
        if retrieved_chunks:
            context_block = "\n\n".join(retrieved_chunks)
            effective_query = (
                f"Use the following context from the knowledge repository "
                f"if relevant to answer accurately:\n\n{context_block}\n\n"
                f"Question: {user_query}"
            )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": effective_query},
    ]

    for step in range(3):
        response_text = generate_streaming(messages, placeholder)

        if "Final Answer:" in response_text:
            return response_text.split("Final Answer:")[-1].strip()

        action_match = re.search(r"Action:\s*(\w+)\[(.*?)\]", response_text)
        if action_match:
            tool_name, tool_arg = action_match.group(1), action_match.group(2)
            if tool_name in TOOLS:
                observation = TOOLS[tool_name](tool_arg)
                messages.append({"role": "assistant", "content": response_text})
                messages.append(
                    {"role": "user", "content": f"Observation: {observation}"}
                )
                placeholder.markdown(f"_Running {tool_name}({tool_arg})..._")
                continue

        return response_text

    return "Agent loop timed out."

# ==============================================================================
# CHAT UI
# ==============================================================================

st.title("🤖 Local LLM Chat")
st.caption(f"Model: `{MODEL_ID}` — fully offline inference, no external API calls.")

with st.sidebar:
    st.header("📚 Knowledge Repository")
    st.caption(
        "This is how you 'feed the model more information' -- no "
        "retraining involved. Documents here are searched at query "
        "time and given to the model as context."
    )
    stats = rag.index_stats()
    st.metric("Documents", stats["documents"])
    st.metric("Chunks indexed", stats["chunks_indexed"])

    uploaded = st.file_uploader(
        "Add a document (.txt or .md)", type=["txt", "md"]
    )
    if uploaded is not None:
        dest = rag.DOCS_DIR / uploaded.name
        rag.DOCS_DIR.mkdir(exist_ok=True)
        dest.write_bytes(uploaded.getvalue())
        st.success(f"Saved {uploaded.name} to the repository.")

    if st.button("🔄 Rebuild index", type="primary"):
        with st.spinner("Indexing documents..."):
            count = rag.build_index()
        st.success(f"Indexed {count} chunks from your documents.")
        st.rerun()

    use_rag = st.checkbox("Use knowledge repository for answers", value=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask something...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        answer = run_agent(prompt, placeholder, use_rag=use_rag)
        st.session_state.messages.append({"role": "assistant", "content": answer})