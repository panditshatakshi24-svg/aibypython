import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from content_agent import generate_draft, load_json, suggest


APP_DIR = Path(__file__).resolve().parent
PROFILE_PATH = APP_DIR / "profile.json"
LIBRARY_PATH = APP_DIR / "library.json"
DRAFTS_PATH = APP_DIR / "drafts.json"
FORMATS = ["Reel script", "Carousel outline", "Caption"]


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_drafts():
    if not DRAFTS_PATH.exists():
        return []
    drafts = load_json(DRAFTS_PATH)
    if not isinstance(drafts, list):
        raise ValueError("drafts.json must contain a JSON array.")
    return drafts


def initialize_state():
    if "profile" not in st.session_state:
        st.session_state.profile = load_json(PROFILE_PATH)
    if "ideas" not in st.session_state:
        st.session_state.ideas = []
    if "selected_idea" not in st.session_state:
        st.session_state.selected_idea = None
    if "draft_text" not in st.session_state:
        st.session_state.draft_text = ""


st.set_page_config(
    page_title="AIBYPYTHON Content Studio",
    page_icon="✦",
    layout="wide",
)
initialize_state()
profile = st.session_state.profile

st.title("✦ AIBYPYTHON Content Studio")
st.caption("Go from a topic to an editable, ready-to-review content draft.")

with st.sidebar:
    st.header("Creator profile")
    profile["name"] = st.text_input("Account name", value=profile.get("name", ""))
    profile["who"] = st.text_area(
        "What do you create?",
        value=profile.get("who", ""),
        height=90,
    )
    audience_text = st.text_input(
        "Audience (comma separated)",
        value=", ".join(profile.get("audience", [])),
    )
    profile["audience"] = [
        item.strip() for item in audience_text.split(",") if item.strip()
    ]
    profile["voice"] = st.text_input("Voice", value=profile.get("voice", ""))
    profile["language"] = st.text_input(
        "Language", value=profile.get("language", "English")
    )
    if st.button("Save profile", use_container_width=True):
        try:
            save_json(PROFILE_PATH, profile)
        except OSError as exc:
            st.error(f"Could not save profile: {exc}")
        else:
            st.success("Profile saved.")

st.subheader("1. Generate ideas")
topic_col, format_col = st.columns([2, 1])
with topic_col:
    topic = st.text_input(
        "What should we create about?",
        placeholder="e.g. embeddings, AI agents, or a Python project",
    )
with format_col:
    format_name = st.selectbox("Draft format", FORMATS)

if st.button("Generate ideas", type="primary", disabled=not topic.strip()):
    try:
        library = load_json(LIBRARY_PATH)
        ideas = suggest(
            profile,
            library,
            [topic.strip()],
            n=5,
            allow_fallback=False,
        )
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        st.error(f"Could not generate ideas: {exc}")
    else:
        st.session_state.ideas = [idea for _, idea in ideas]
        st.session_state.selected_idea = None
        st.session_state.draft_text = ""

if st.session_state.ideas:
    st.subheader("2. Choose an idea")
    idea_labels = [
        f"{index + 1}. {idea.get('title', 'Untitled idea')}"
        for index, idea in enumerate(st.session_state.ideas)
    ]
    selected_index = st.radio(
        "Pick the direction you want to develop",
        range(len(idea_labels)),
        format_func=lambda index: idea_labels[index],
        label_visibility="collapsed",
    )
    selected_idea = st.session_state.ideas[selected_index]
    st.write(selected_idea.get("angle", ""))
    st.caption(f"For: {selected_idea.get('audience', 'your audience')}")
    st.session_state.selected_idea = selected_idea

    if st.button("Create draft", type="primary"):
        try:
            st.session_state.draft_text = generate_draft(
                selected_idea, profile, format_name, topic.strip()
            )
        except RuntimeError as exc:
            st.error(str(exc))

if st.session_state.draft_text:
    st.subheader("3. Edit your draft")
    st.session_state.draft_text = st.text_area(
        "Draft — edit freely before using it",
        value=st.session_state.draft_text,
        height=360,
    )
    selected_title = (st.session_state.selected_idea or {}).get("title", topic)
    st.download_button(
        "Download draft",
        data=st.session_state.draft_text,
        file_name="aibypython-content-draft.txt",
        mime="text/plain",
    )
    if st.button("Save draft"):
        try:
            drafts = load_drafts()
            drafts.insert(
                0,
                {
                    "title": selected_title,
                    "topic": topic.strip(),
                    "format": format_name,
                    "text": st.session_state.draft_text,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            save_json(DRAFTS_PATH, drafts)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            st.error(f"Could not save draft: {exc}")
        else:
            st.success("Draft saved to your local content library.")

st.divider()
st.subheader("Saved drafts")
try:
    saved_drafts = load_drafts()
except (OSError, ValueError, json.JSONDecodeError) as exc:
    st.error(f"Could not load saved drafts: {exc}")
else:
    if not saved_drafts:
        st.caption("Your saved drafts will appear here.")
    else:
        for saved in saved_drafts[:10]:
            with st.expander(
                f"{saved.get('title', 'Untitled')} · {saved.get('format', 'Draft')}"
            ):
                st.caption(saved.get("saved_at", ""))
                st.text(saved.get("text", ""))

if not os.environ.get("CONTENT_AGENT_API_KEY") or not os.environ.get(
    "CONTENT_AGENT_API_URL"
):
    st.info(
        "Running in local demo mode. Add CONTENT_AGENT_API_KEY and "
        "CONTENT_AGENT_API_URL to enable model-generated ideas and drafts."
    )
