"""app.py - Streamlit UI for search_bot.py.   Run: streamlit run app.py

Two views of the same app:
  http://<laptop>:8501/                 -> controller: type with the laptop keyboard
  http://<laptop>:8501/?mode=display    -> phone mirror: shows the laptop's search + answer live
"""
import re
import socket
from pathlib import Path

import streamlit as st

from search_bot import NOT_FOUND, SearchBot, split_parts

POLL_SECONDS = 1  # how often the phone mirror checks for a new search

st.set_page_config(page_title="Knowledge Bot", page_icon="🔎",
                   layout="centered", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
      .block-container { padding: 1.2rem 1rem 3rem; max-width: 720px; }
      input { font-size: 16px !important; }   /* prevents iOS zoom-on-focus */
      [data-testid="stMarkdownContainer"] table { display: block; max-width: 100%; overflow-x: auto; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_bot() -> SearchBot:
    return SearchBot()  # index auto-refreshes when files change


@st.cache_resource
def get_shared() -> dict:
    """One dict shared by every open browser tab (laptop controller + phone mirror)."""
    return {"query": None}


bot, shared = get_bot(), get_shared()
TAG_ONLY = re.compile(r"</?[\w-]+>")


def show_answer(result: str) -> None:
    """Render text as copyable code blocks, tables as tables, images as pictures."""
    for kind, value in split_parts(result):
        if kind == "image":
            if value.startswith("http") or Path(value).is_file():
                st.image(value)
            else:
                st.warning(f"Image not found: {Path(value).name}")
        elif kind == "table":
            st.markdown(value)
        elif TAG_ONLY.fullmatch(value.strip()):
            st.markdown(f"`{value.strip()}`")
        else:
            st.code(value, language=None, wrap_lines=True)


def render(query) -> None:
    if not query:
        return
    result = bot.search(query)
    if result == NOT_FOUND:
        st.warning(NOT_FOUND)
    else:
        show_answer(result)


# ------------------------------------------------------------------ phone mirror
if st.query_params.get("mode") == "display":

    @st.fragment(run_every=POLL_SECONDS)
    def mirror() -> None:
        query = shared["query"]
        if query:
            st.caption(f"Search: {query}")
            render(query)
        else:
            st.info("Waiting for a search on the laptop…")

    mirror()
    st.stop()


# ------------------------------------------------------------------ laptop controller
def clear_search() -> None:
    st.session_state["keyword"] = None


def mirror_url() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # no data is sent; just finds this PC's LAN address
            ip = s.getsockname()[0]
    except OSError:
        ip = "your-laptop-ip"
    return f"http://{ip}:{st.get_option('server.port')}/?mode=display"


st.title("🔎 Knowledge Bot")

query = st.selectbox(
    "Search keyword",
    options=bot.all_keywords(),
    index=None,
    accept_new_options=True,
    placeholder="Type a keyword, e.g. play, sel, api",
    label_visibility="collapsed",
    key="keyword",
)
st.button("✕ Clear", on_click=clear_search)

shared["query"] = query  # the phone mirror picks this up within a second
render(query)

st.caption(f"📱 Open on your phone to mirror this screen: {mirror_url()}")
