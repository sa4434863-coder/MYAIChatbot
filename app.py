import os
import textwrap
import re
import time
import sqlite3
import hashlib
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Optional PDF support
try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="My AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv()

# Streamlit Cloud Secrets first, local .env second
try:
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    GEMINI_API_KEY = None

if not GEMINI_API_KEY:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Current stable models + fallback
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

DB_FILE = "chatbot.db"


# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown(
    """
<style>

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.stApp {
    background:
        radial-gradient(circle at top left, rgba(75, 0, 130, 0.18), transparent 35%),
        radial-gradient(circle at top right, rgba(0, 120, 255, 0.12), transparent 35%),
        #080b12;
    color: #f5f7fb;
}

.block-container {
    max-width: 1150px;
    padding-top: 1.2rem;
    padding-bottom: 5rem;
}

[data-testid="stSidebar"] {
    background: #0d111b;
    border-right: 1px solid rgba(255,255,255,0.08);
}

[data-testid="stSidebar"] * {
    color: #eef2ff;
}

.hero {
    padding: 26px;
    border-radius: 24px;
    background:
        linear-gradient(
            135deg,
            rgba(91, 33, 182, 0.32),
            rgba(30, 64, 175, 0.22)
        );
    border: 1px solid rgba(255,255,255,0.09);
    box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    margin-bottom: 20px;
}

.hero-title {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 5px;
}

.hero-subtitle {
    color: #aeb8cc;
    font-size: 15px;
}

.feature-card {
    padding: 20px;
    border-radius: 18px;
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.07);
    min-height: 130px;
}

.feature-icon {
    font-size: 28px;
}

.feature-title {
    font-weight: 700;
    margin-top: 8px;
}

.feature-text {
    color: #9ca8bd;
    font-size: 13px;
}

.chat-user {
    background: linear-gradient(
        135deg,
        rgba(37, 99, 235, 0.24),
        rgba(59, 130, 246, 0.10)
    );
    border: 1px solid rgba(96,165,250,0.18);
    border-radius: 18px;
    padding: 14px 17px;
    margin: 12px 0;
}

.chat-ai {
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    padding: 15px 17px;
    margin: 12px 0;
}

.chat-label {
    font-size: 12px;
    font-weight: 700;
    color: #94a3b8;
    margin-bottom: 7px;
}

.status-pill {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: rgba(34,197,94,0.12);
    border: 1px solid rgba(34,197,94,0.20);
    color: #86efac;
    font-size: 12px;
}

.warning-pill {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: rgba(245,158,11,0.12);
    border: 1px solid rgba(245,158,11,0.20);
    color: #fcd34d;
    font-size: 12px;
}

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background: #111827 !important;
    color: white !important;
    border: 1px solid #273244 !important;
    border-radius: 14px !important;
}

button {
    border-radius: 12px !important;
}

[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.025);
    border-radius: 16px;
    padding: 8px;
}

@media (max-width: 768px) {

    .block-container {
        padding-left: 12px;
        padding-right: 12px;
    }

    .hero {
        padding: 20px;
        border-radius: 18px;
    }

    .hero-title {
        font-size: 27px;
    }

}

</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# =========================================================
# SETTINGS
# =========================================================

def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    ).fetchone()
    conn.close()

    if row:
        return row["value"]

    return default


def set_setting(key, value):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )

    conn.commit()
    conn.close()


# =========================================================
# CHAT FUNCTIONS
# =========================================================

def create_chat(title="New Chat"):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_db()

    cur = conn.execute(
        """
        INSERT INTO chats(title, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        (title, now, now),
    )

    chat_id = cur.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def get_chats():
    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM chats
        ORDER BY updated_at DESC
        """
    ).fetchall()

    conn.close()

    return rows


def get_chat(chat_id):
    conn = get_db()

    row = conn.execute(
        "SELECT * FROM chats WHERE id = ?",
        (chat_id,),
    ).fetchone()

    conn.close()

    return row


def rename_chat(chat_id, title):
    conn = get_db()

    conn.execute(
        """
        UPDATE chats
        SET title = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            datetime.now().isoformat(timespec="seconds"),
            chat_id,
        ),
    )

    conn.commit()
    conn.close()


def delete_chat(chat_id):
    conn = get_db()

    conn.execute(
        "DELETE FROM messages WHERE chat_id = ?",
        (chat_id,),
    )

    conn.execute(
        "DELETE FROM chats WHERE id = ?",
        (chat_id,),
    )

    conn.commit()
    conn.close()


def save_message(chat_id, role, content):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO messages(
            chat_id,
            role,
            content,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            chat_id,
            role,
            content,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    conn.execute(
        """
        UPDATE chats
        SET updated_at = ?
        WHERE id = ?
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            chat_id,
        ),
    )

    conn.commit()
    conn.close()


def get_messages(chat_id):
    conn = get_db()

    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# SESSION STATE
# =========================================================

if "chat_id" not in st.session_state:
    chats = get_chats()

    if chats:
        st.session_state.chat_id = chats[0]["id"]
    else:
        st.session_state.chat_id = create_chat()

if "mode" not in st.session_state:
    st.session_state.mode = "General"

if "uploaded_context" not in st.session_state:
    st.session_state.uploaded_context = ""

if "last_model" not in st.session_state:
    st.session_state.last_model = PRIMARY_MODEL


# =========================================================
# GEMINI CLIENT
# =========================================================

client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        client = None


# =========================================================
# PROMPTS
# =========================================================

def get_system_prompt(mode):

    base = """
You are My AI, a helpful, intelligent and friendly AI assistant.

Rules:
- Give clear and useful answers.
- Use simple language when the user is a beginner.
- Do not invent facts.
- If information is uncertain, say so.
- For programming questions, explain errors and provide corrected code.
- Format answers with headings and bullet points when useful.
"""

    if mode == "Study":
        return base + """
You are now in STUDY MODE.

Teach step-by-step.
Use beginner-friendly explanations.
Give examples.
For mathematics, show calculations.
For programming, explain the logic before the code.
If the user asks a direct exam question, provide an exam-ready answer.
"""

    if mode == "Coding":
        return base + """
You are now in CODING MODE.

Focus on programming.
Explain:
1. What is wrong
2. Why it is wrong
3. Correct code
4. Output/example
5. Simple explanation

Prefer beginner-friendly code.
"""

    return base


# =========================================================
# TITLE GENERATOR
# =========================================================

def make_title(text):

    text = text.strip()

    if not text:
        return "New Chat"

    words = text.split()

    title = " ".join(words[:7])

    if len(words) > 7:
        title += "..."

    return title[:60]


# =========================================================
# PDF / TEXT FILE EXTRACTION
# =========================================================

def extract_uploaded_file(uploaded_file):

    if uploaded_file is None:
        return ""

    filename = uploaded_file.name.lower()

    try:

        if filename.endswith(".txt"):
            return uploaded_file.read().decode(
                "utf-8",
                errors="ignore"
            )

        if filename.endswith(".pdf"):

            if not PDF_AVAILABLE:
                return "PDF support is not installed."

            reader = PdfReader(uploaded_file)

            text = ""

            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            return text[:30000]

        return ""

    except Exception as e:
        return f"Could not read file: {e}"


# =========================================================
# WEB SEARCH
# =========================================================

def simple_web_search(query):

    """
    Lightweight DuckDuckGo HTML search.

    This is intentionally simple.
    If the search service blocks the request,
    the chatbot will continue normally.
    """

    try:

        import requests
        from bs4 import BeautifulSoup

        url = "https://html.duckduckgo.com/html/"

        response = requests.post(
            url,
            data={"q": query},
            headers={
                "User-Agent":
                "Mozilla/5.0"
            },
            timeout=10,
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(".result")[:5]:

            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")

            if not title_el:
                continue

            title = title_el.get_text(
                " ",
                strip=True
            )

            snippet = ""

            if snippet_el:
                snippet = snippet_el.get_text(
                    " ",
                    strip=True
                )

            results.append(
                f"TITLE: {title}\n"
                f"INFO: {snippet}"
            )

        return "\n\n".join(results)

    except Exception as e:
        return f"Web search unavailable: {e}"


# =========================================================
# BUILD PROMPT
# =========================================================

def build_prompt(user_message):

    system_prompt = get_system_prompt(
        st.session_state.mode
    )

    history = get_messages(
        st.session_state.chat_id
    )

    recent_history = history[-12:]

    conversation = ""

    for msg in recent_history:
        conversation += (
            f"{msg['role'].upper()}: "
            f"{msg['content']}\n\n"
        )

    extra_context = ""

    if st.session_state.uploaded_context:

        extra_context += """
USER UPLOADED FILE:

{file}

END OF FILE
""".format(
            file=st.session_state.uploaded_context
        )

    return f"""
{system_prompt}

USER NAME:
{get_setting("user_name", "User")}

CURRENT MODE:
{st.session_state.mode}

{extra_context}

CONVERSATION:
{conversation}

USER:
{user_message}

ASSISTANT:
"""


# =========================================================
# GEMINI CALL
# =========================================================

def ask_gemini(prompt):

    if not client:
        return (
            "🔐 Gemini API key is not available.\n\n"
            "Please add `GEMINI_API_KEY` to "
            "Streamlit Secrets or your `.env` file."
        )

    models = [
        PRIMARY_MODEL,
        FALLBACK_MODEL,
    ]

    last_error = None

    for model in models:

        try:

            st.session_state.last_model = model

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1200,
                ),
            )

            if response and response.text:
                return response.text

            return "I received an empty response."

        except Exception as e:

            last_error = e

            error_text = str(e).lower()

            # Rate limit
            if (
                "429" in error_text
                or "resource_exhausted" in error_text
                or "rate limit" in error_text
                or "quota" in error_text
            ):
                # Try fallback model
                continue

            # Temporary server overload
            if (
                "503" in error_text
                or "unavailable" in error_text
                or "overloaded" in error_text
            ):
                time.sleep(1)
                continue

            # Model unavailable
            if (
                "404" in error_text
                or "not found" in error_text
            ):
                continue

            return (
                "⚠️ Gemini error:\n\n"
                f"`{str(e)}`"
            )

    # Both models failed
    error_text = str(last_error).lower()

    if (
        "429" in error_text
        or "resource_exhausted" in error_text
        or "quota" in error_text
        or "rate" in error_text
    ):
        return """
⚠️ **Gemini free-tier limit reached.**

I tried both available models:

- Gemini 3.8 Flash
- Gemini 3.5 Flash-Lite

Please wait for the quota to reset and try again.

Your API key is being detected correctly.
"""

    return (
        "⚠️ Gemini is temporarily unavailable.\n\n"
        f"Error: `{str(last_error)}`"
    )


# =========================================================
# EXPORT CHAT
# =========================================================

def make_export_text(chat_id):

    chat = get_chat(chat_id)
    messages = get_messages(chat_id)

    output = []

    output.append(
        f"# {chat['title']}\n"
    )

    output.append(
        f"Created: {chat['created_at']}\n"
    )

    output.append("\n---\n")

    for message in messages:

        role = (
            "You"
            if message["role"] == "user"
            else "My AI"
        )

        output.append(
            f"\n## {role}\n\n"
            f"{message['content']}\n"
        )

    return "\n".join(output)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        """
        <div style="
            font-size:25px;
            font-weight:800;
            margin-bottom:15px;
        ">
        🤖 My AI
        </div>
        """,
        unsafe_allow_html=True,
    )

    # New Chat
    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        st.session_state.chat_id = create_chat(
            "New Chat"
        )

        st.session_state.uploaded_context = ""

        st.rerun()

    st.markdown("### 💬 Conversations")

    chats = get_chats()

    for chat in chats:

        col1, col2 = st.columns(
            [5, 1],
            gap="small"
        )

        with col1:

            label = chat["title"]

            if chat["id"] == st.session_state.chat_id:
                label = "🟣 " + label

            if st.button(
                label,
                key=f"open_{chat['id']}",
                use_container_width=True,
            ):
                st.session_state.chat_id = chat["id"]
                st.session_state.uploaded_context = ""
                st.rerun()

        with col2:

            if st.button(
                "⋮",
                key=f"menu_{chat['id']}"
            ):
                st.session_state[
                    f"show_menu_{chat['id']}"
                ] = not st.session_state.get(
                    f"show_menu_{chat['id']}",
                    False
                )

        if st.session_state.get(
            f"show_menu_{chat['id']}",
            False
        ):

            rename = st.text_input(
                "Rename",
                value=chat["title"],
                key=f"rename_{chat['id']}",
            )

            c1, c2 = st.columns(2)

            with c1:

                if st.button(
                    "Save",
                    key=f"save_{chat['id']}"
                ):

                    rename_chat(
                        chat["id"],
                        rename.strip()
                        or "New Chat"
                    )

                    st.rerun()

            with c2:

                if st.button(
                    "Delete",
                    key=f"delete_{chat['id']}"
                ):

                    delete_chat(chat["id"])

                    remaining = get_chats()

                    if remaining:
                        st.session_state.chat_id = (
                            remaining[0]["id"]
                        )
                    else:
                        st.session_state.chat_id = (
                            create_chat()
                        )

                    st.rerun()

    st.divider()

    # Mode
    st.markdown("### 🧠 AI Mode")

    mode = st.selectbox(
        "Choose mode",
        [
            "General",
            "Study",
            "Coding",
        ],
        index=[
            "General",
            "Study",
            "Coding",
        ].index(st.session_state.mode),
        label_visibility="collapsed",
    )

    st.session_state.mode = mode

    # User name
    st.markdown("### 👤 Your Name")

    user_name = st.text_input(
        "Name",
        value=get_setting(
            "user_name",
            ""
        ),
        label_visibility="collapsed",
        placeholder="Enter your name",
    )

    if user_name != get_setting(
        "user_name",
        ""
    ):
        set_setting(
            "user_name",
            user_name
        )

    # File
    st.markdown("### 📎 Upload File")

    uploaded_file = st.file_uploader(
        "PDF or TXT",
        type=["pdf", "txt"],
        label_visibility="collapsed",
    )

    if uploaded_file:

        text = extract_uploaded_file(
            uploaded_file
        )

        st.session_state.uploaded_context = text

        if text:
            st.success(
                f"Loaded: {uploaded_file.name}"
            )

    # Export
    st.markdown("### 📥 Export")

    export_text = make_export_text(
        st.session_state.chat_id
    )

    st.download_button(
        "Download Chat",
        data=export_text,
        file_name="my_ai_chat.md",
        mime="text/markdown",
        use_container_width=True,
    )

    st.divider()

    # API status
    if client:

        st.markdown(
            '<span class="status-pill">'
            '● API Connected'
            '</span>',
            unsafe_allow_html=True,
        )

    else:

        st.markdown(
            '<span class="warning-pill">'
            '● API Key Missing'
            '</span>',
            unsafe_allow_html=True,
        )

    st.caption(
        f"Model: {st.session_state.last_model}"
    )


# =========================================================
# MAIN HEADER
# =========================================================

chat = get_chat(
    st.session_state.chat_id
)

st.markdown(
    f"""
    <div class="hero">

        <div class="hero-title">
            🤖 My AI
        </div>

        <div class="hero-subtitle">
            Your personal AI assistant —
            {st.session_state.mode} Mode
        </div>

    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# WELCOME SCREEN
# =========================================================

messages = get_messages(
    st.session_state.chat_id
)

if not messages:

    st.markdown(
        """
        <div style="
            text-align:center;
            padding:25px 10px 20px;
        ">

            <div style="
                font-size:50px;
            ">
                ✨
            </div>

            <h2>
                Welcome to My AI
            </h2>

            <p style="
                color:#9ca8bd;
            ">
                Ask anything, learn something,
                or build something.
            </p>

        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">📚</div>
                <div class="feature-title">
                    Study
                </div>
                <div class="feature-text">
                    Learn concepts step-by-step.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">💻</div>
                <div class="feature-title">
                    Coding
                </div>
                <div class="feature-text">
                    Debug and understand code.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-icon">🧠</div>
                <div class="feature-title">
                    General AI
                </div>
                <div class="feature-text">
                    Ask questions and explore ideas.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =========================================================
# DISPLAY CHAT
# =========================================================

for message in messages:

    if message["role"] == "user":

        st.markdown(
            f"""
            <div class="chat-user">

                <div class="chat-label">
                    YOU
                </div>

                <div>
                    {message["content"]}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )

    else:

        st.markdown(
            """
            <div class="chat-ai">

                <div class="chat-label">
                    MY AI
                </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            message["content"]
        )

        st.markdown(
            "</div>",
            unsafe_allow_html=True,
        )


# =========================================================
# CHAT INPUT
# =========================================================

user_message = st.chat_input(
    "Message My AI..."
)


if user_message:

    user_message = user_message.strip()

    if not user_message:
        st.stop()

    # First message -> auto title
    if len(messages) == 0:

        rename_chat(
            st.session_state.chat_id,
            make_title(user_message),
        )

    # Save user message
    save_message(
        st.session_state.chat_id,
        "user",
        user_message,
    )

    # Display immediately
    with st.chat_message("user"):
        st.markdown(user_message)

    # Build prompt
    prompt = build_prompt(
        user_message
    )

    # AI response
    with st.chat_message("assistant"):

        with st.spinner(
            "My AI is thinking..."
        ):

            answer = ask_gemini(
                prompt
            )

        st.markdown(answer)

    # Save response
    save_message(
        st.session_state.chat_id,
        "assistant",
        answer,
    )

    st.rerun()