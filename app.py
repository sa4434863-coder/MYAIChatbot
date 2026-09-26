import os
import time
import sqlite3
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from google import genai
from google.genai import types


# ============================================================
# OPTIONAL PACKAGES
# ============================================================

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


try:
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except Exception:
    WEB_AVAILABLE = False


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="My AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

GEMINI_API_KEY = None

try:
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass

if not GEMINI_API_KEY:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ============================================================
# GEMINI MODELS
# ============================================================

PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"


# ============================================================
# DATABASE
# ============================================================

DB_FILE = "chatbot.db"


def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def column_exists(conn, table_name, column_name):

    columns = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in columns
    )


def add_column_if_missing(
    conn,
    table_name,
    column_name,
    column_definition
):

    if not column_exists(
        conn,
        table_name,
        column_name
    ):

        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )


def init_db():

    conn = get_db()

    # ========================================================
    # SETTINGS
    # ========================================================

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    add_column_if_missing(
        conn,
        "settings",
        "value",
        "TEXT"
    )

    # ========================================================
    # CHATS
    # ========================================================

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    add_column_if_missing(
        conn,
        "chats",
        "title",
        "TEXT"
    )

    add_column_if_missing(
        conn,
        "chats",
        "created_at",
        "TEXT"
    )

    add_column_if_missing(
        conn,
        "chats",
        "updated_at",
        "TEXT"
    )

    # ========================================================
    # MESSAGES
    # ========================================================

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
        """
    )

    add_column_if_missing(
        conn,
        "messages",
        "chat_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "messages",
        "role",
        "TEXT"
    )

    add_column_if_missing(
        conn,
        "messages",
        "content",
        "TEXT"
    )

    add_column_if_missing(
        conn,
        "messages",
        "created_at",
        "TEXT"
    )

    # ========================================================
    # REPAIR OLD DATA
    # ========================================================

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn.execute(
        """
        UPDATE chats
        SET title = 'New Chat'
        WHERE title IS NULL
           OR title = ''
        """
    )

    conn.execute(
        """
        UPDATE chats
        SET created_at = ?
        WHERE created_at IS NULL
           OR created_at = ''
        """,
        (now,)
    )

    conn.execute(
        """
        UPDATE chats
        SET updated_at = ?
        WHERE updated_at IS NULL
           OR updated_at = ''
        """,
        (now,)
    )

    conn.execute(
        """
        UPDATE messages
        SET created_at = ?
        WHERE created_at IS NULL
           OR created_at = ''
        """,
        (now,)
    )

    conn.commit()
    conn.close()


# Run database initialization
init_db()


# ============================================================
# SETTINGS FUNCTIONS
# ============================================================

def get_setting(
    key,
    default=""
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    conn.close()

    if row is None:
        return default

    return row["value"] or default


def set_setting(
    key,
    value
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (
            key,
            value
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# CHAT FUNCTIONS
# ============================================================

def create_chat(
    title="New Chat"
):

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn = get_db()

    cursor = conn.execute(
        """
        INSERT INTO chats(
            title,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?)
        """,
        (
            title,
            now,
            now
        )
    )

    chat_id = cursor.lastrowid

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


def get_chat(
    chat_id
):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM chats
        WHERE id = ?
        """,
        (chat_id,)
    ).fetchone()

    conn.close()

    return row


def rename_chat(
    chat_id,
    title
):

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn = get_db()

    conn.execute(
        """
        UPDATE chats
        SET title = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            title,
            now,
            chat_id
        )
    )

    conn.commit()
    conn.close()


def delete_chat(
    chat_id
):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM messages
        WHERE chat_id = ?
        """,
        (chat_id,)
    )

    conn.execute(
        """
        DELETE FROM chats
        WHERE id = ?
        """,
        (chat_id,)
    )

    conn.commit()
    conn.close()


def save_message(
    chat_id,
    role,
    content
):

    now = datetime.now().isoformat(
        timespec="seconds"
    )

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
            now
        )
    )

    conn.execute(
        """
        UPDATE chats
        SET updated_at = ?
        WHERE id = ?
        """,
        (
            now,
            chat_id
        )
    )

    conn.commit()
    conn.close()


def get_messages(
    chat_id
):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,)
    ).fetchall()

    conn.close()

    return rows


# ============================================================
# SESSION STATE
# ============================================================

if "chat_id" not in st.session_state:

    existing_chats = get_chats()

    if existing_chats:

        st.session_state.chat_id = (
            existing_chats[0]["id"]
        )

    else:

        st.session_state.chat_id = create_chat()


if "mode" not in st.session_state:

    st.session_state.mode = "General"


if "uploaded_context" not in st.session_state:

    st.session_state.uploaded_context = ""


if "last_model" not in st.session_state:

    st.session_state.last_model = PRIMARY_MODEL


# ============================================================
# GEMINI CLIENT
# ============================================================

client = None

if GEMINI_API_KEY:

    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception:

        client = None


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
}

header {
    visibility: hidden;
}

.stApp {

    background:
        radial-gradient(
            circle at 10% 10%,
            rgba(99, 102, 241, 0.16),
            transparent 35%
        ),
        radial-gradient(
            circle at 90% 10%,
            rgba(14, 165, 233, 0.12),
            transparent 35%
        ),
        #080b12;

    color: #f8fafc;
}

.block-container {

    max-width: 1150px;

    padding-top: 25px;
    padding-bottom: 100px;
}

[data-testid="stSidebar"] {

    background: #0d111b;

    border-right:
        1px solid
        rgba(255,255,255,0.08);
}

[data-testid="stSidebar"] * {
    color: #f8fafc;
}

.hero {

    padding: 28px;

    border-radius: 24px;

    background:
        linear-gradient(
            135deg,
            rgba(79,70,229,0.28),
            rgba(14,165,233,0.16)
        );

    border:
        1px solid
        rgba(255,255,255,0.08);

    margin-bottom: 25px;
}

.hero-title {

    font-size: 36px;

    font-weight: 800;

    letter-spacing: -1px;
}

.hero-subtitle {

    color: #aab4c7;

    margin-top: 5px;

    font-size: 15px;
}

.status {

    padding: 7px 12px;

    border-radius: 999px;

    background:
        rgba(34,197,94,0.12);

    color: #86efac;

    font-size: 12px;

    border:
        1px solid
        rgba(34,197,94,0.18);
}

.card {

    padding: 22px;

    border-radius: 20px;

    background:
        rgba(255,255,255,0.045);

    border:
        1px solid
        rgba(255,255,255,0.07);

    margin-bottom: 15px;
}

.small-text {

    color: #94a3b8;

    font-size: 13px;
}

[data-testid="stChatInput"] {

    border-radius: 18px;
}

div[data-testid="stTextInput"] input {

    background: #111827 !important;

    color: white !important;

    border:
        1px solid
        #263246 !important;

    border-radius: 12px !important;
}

button {

    border-radius: 12px !important;
}

</style>
""",
    unsafe_allow_html=True
)


# ============================================================
# SYSTEM PROMPTS
# ============================================================

def system_prompt(
    mode
):

    base = """
You are My AI, a helpful personal AI assistant.

Always:
- Be accurate.
- Be friendly.
- Explain clearly.
- Do not invent information.
- If the user is a beginner, explain step-by-step.
- Use headings and bullet points when useful.
"""

    if mode == "Study":

        return base + """

You are in Study Mode.

Teach like a patient teacher.
Explain concepts from basic to advanced.
Use examples.
For mathematics, show calculations.
For programming, explain the logic first.
"""

    if mode == "Coding":

        return base + """

You are in Coding Mode.

For coding questions:
1. Identify the problem.
2. Explain why it happens.
3. Give corrected code.
4. Explain the corrected code simply.
5. Show expected output when useful.

Prefer beginner-friendly code.
"""

    if mode == "Web Search":

        return base + """

You are in Web Search Mode.

The user may provide search results.
Use those results as supporting information.
Clearly distinguish search information from your own general explanation.
"""

    return base


# ============================================================
# TITLE
# ============================================================

def make_title(
    text
):

    text = text.strip()

    if not text:

        return "New Chat"

    words = text.split()

    title = " ".join(
        words[:8]
    )

    if len(words) > 8:

        title += "..."

    return title[:60]


# ============================================================
# FILE READER
# ============================================================

def read_uploaded_file(
    uploaded_file
):

    if uploaded_file is None:

        return ""

    filename = uploaded_file.name.lower()

    try:

        if filename.endswith(".txt"):

            return uploaded_file.read().decode(
                "utf-8",
                errors="ignore"
            )[:30000]

        if filename.endswith(".pdf"):

            if not PDF_AVAILABLE:

                return (
                    "PDF support is not installed."
                )

            reader = PdfReader(
                uploaded_file
            )

            text = ""

            for page in reader.pages:

                text += (
                    page.extract_text()
                    or ""
                )

                text += "\n"

            return text[:30000]

        return ""

    except Exception as error:

        return (
            f"Could not read file: {error}"
        )


# ============================================================
# WEB SEARCH
# ============================================================

def web_search(
    query
):

    if not WEB_AVAILABLE:

        return (
            "Web search packages are not installed."
        )

    try:

        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={
                "q": query
            },
            headers={
                "User-Agent":
                "Mozilla/5.0"
            },
            timeout=10
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(
            ".result"
        )[:5]:

            title_element = (
                result.select_one(
                    ".result__title"
                )
            )

            snippet_element = (
                result.select_one(
                    ".result__snippet"
                )
            )

            if not title_element:

                continue

            title = (
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

            snippet = ""

            if snippet_element:

                snippet = (
                    snippet_element.get_text(
                        " ",
                        strip=True
                    )
                )

            results.append(
                f"TITLE: {title}\n"
                f"INFO: {snippet}"
            )

        if not results:

            return "No search results found."

        return "\n\n".join(results)

    except Exception as error:

        return (
            "Web search failed: "
            f"{error}"
        )


# ============================================================
# BUILD AI PROMPT
# ============================================================

def build_prompt(
    user_message
):

    history = get_messages(
        st.session_state.chat_id
    )

    recent_history = history[-12:]

    conversation = ""

    for message in recent_history:

        role = message["role"].upper()

        conversation += (
            f"{role}: "
            f"{message['content']}\n\n"
        )

    file_context = ""

    if st.session_state.uploaded_context:

        file_context = f"""
UPLOADED FILE CONTENT:

{st.session_state.uploaded_context}

END FILE CONTENT
"""

    search_context = ""

    if st.session_state.mode == "Web Search":

        with st.spinner(
            "Searching the web..."
        ):

            search_context = web_search(
                user_message
            )

    return f"""
{system_prompt(
    st.session_state.mode
)}

USER NAME:
{get_setting(
    "user_name",
    "User"
)}

CURRENT MODE:
{st.session_state.mode}

{file_context}

WEB SEARCH RESULTS:
{search_context}

CONVERSATION HISTORY:
{conversation}

CURRENT USER MESSAGE:
{user_message}

Answer the user now.
"""


# ============================================================
# GEMINI REQUEST
# ============================================================

def ask_gemini(
    prompt
):

    if client is None:

        return """
🔐 **Gemini API key not found.**

For local use:
Add `GEMINI_API_KEY` to `.env`.

For Streamlit Cloud:
Add `GEMINI_API_KEY` in
App Settings → Secrets.
"""

    models = [
        PRIMARY_MODEL,
        FALLBACK_MODEL
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

                    max_output_tokens=1500
                )
            )

            if response is not None:

                if response.text:

                    return response.text

            return (
                "I received an empty response."
            )

        except Exception as error:

            last_error = error

            error_text = str(
                error
            ).lower()

            # --------------------------------------------
            # RATE LIMIT / QUOTA
            # --------------------------------------------

            if (
                "429" in error_text
                or "quota" in error_text
                or "resource_exhausted"
                in error_text
                or "rate limit"
                in error_text
            ):

                continue

            # --------------------------------------------
            # TEMPORARY SERVER ERROR
            # --------------------------------------------

            if (
                "503" in error_text
                or "unavailable"
                in error_text
                or "overloaded"
                in error_text
            ):

                time.sleep(1)

                continue

            # --------------------------------------------
            # MODEL NOT FOUND
            # --------------------------------------------

            if (
                "404" in error_text
                or "not found"
                in error_text
            ):

                continue

            return (
                "⚠️ Gemini error:\n\n"
                f"`{error}`"
            )

    # ========================================================
    # ALL MODELS FAILED
    # ========================================================

    if last_error:

        error_text = str(
            last_error
        ).lower()

        if (
            "429" in error_text
            or "quota" in error_text
            or "resource_exhausted"
            in error_text
            or "rate limit"
            in error_text
        ):

            return """
⚠️ **Gemini free-tier limit reached.**

The application is working, but Google's
Gemini API has temporarily limited requests
for this API project.

Please try again after the quota resets.
"""

        return (
            "⚠️ Gemini is temporarily unavailable.\n\n"
            f"`{last_error}`"
        )

    return (
        "⚠️ No response was received."
    )


# ============================================================
# EXPORT
# ============================================================

def export_chat(
    chat_id
):

    chat = get_chat(
        chat_id
    )

    messages = get_messages(
        chat_id
    )

    if not chat:

        return ""

    output = []

    output.append(
        f"# {chat['title']}\n"
    )

    output.append(
        f"Created: "
        f"{chat['created_at']}\n"
    )

    output.append(
        "\n---\n"
    )

    for message in messages:

        role = (
            "You"
            if message["role"] == "user"
            else "My AI"
        )

        output.append(
            f"\n## {role}\n\n"
        )

        output.append(
            message["content"]
        )

        output.append(
            "\n"
        )

    return "\n".join(output)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        """
        <div style="
            font-size:27px;
            font-weight:800;
            margin-bottom:20px;
        ">
        🤖 My AI
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # NEW CHAT
    # --------------------------------------------------------

    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        st.session_state.chat_id = (
            create_chat()
        )

        st.session_state.uploaded_context = ""

        st.rerun()

    st.divider()

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    st.markdown(
        "### 🧠 AI Mode"
    )

    selected_mode = st.selectbox(
        "Mode",
        [
            "General",
            "Study",
            "Coding",
            "Web Search"
        ],
        index=[
            "General",
            "Study",
            "Coding",
            "Web Search"
        ].index(
            st.session_state.mode
        ),
        label_visibility="collapsed"
    )

    st.session_state.mode = (
        selected_mode
    )

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    st.markdown(
        "### 👤 Your Name"
    )

    current_name = get_setting(
        "user_name",
        ""
    )

    new_name = st.text_input(
        "Name",
        value=current_name,
        placeholder="Enter your name",
        label_visibility="collapsed"
    )

    if new_name != current_name:

        set_setting(
            "user_name",
            new_name
        )

    # --------------------------------------------------------
    # FILE UPLOAD
    # --------------------------------------------------------

    st.markdown(
        "### 📎 File"
    )

    uploaded_file = st.file_uploader(
        "Upload PDF or TXT",
        type=[
            "pdf",
            "txt"
        ],
        label_visibility="collapsed"
    )

    if uploaded_file:

        file_text = read_uploaded_file(
            uploaded_file
        )

        st.session_state.uploaded_context = (
            file_text
        )

        if file_text:

            st.success(
                f"Loaded: "
                f"{uploaded_file.name}"
            )

    # --------------------------------------------------------
    # CHAT HISTORY
    # --------------------------------------------------------

    st.markdown(
        "### 💬 Chats"
    )

    chats = get_chats()

    for chat in chats:

        chat_id = chat["id"]

        is_active = (
            chat_id ==
            st.session_state.chat_id
        )

        label = chat["title"]

        if is_active:

            label = (
                "🟣 "
                + label
            )

        if st.button(
            label,
            key=f"chat_{chat_id}",
            use_container_width=True
        ):

            st.session_state.chat_id = (
                chat_id
            )

            st.session_state.uploaded_context = ""

            st.rerun()

    # --------------------------------------------------------
    # CHAT MANAGEMENT
    # --------------------------------------------------------

    st.divider()

    st.markdown(
        "### ⚙️ Chat Settings"
    )

    current_chat = get_chat(
        st.session_state.chat_id
    )

    if current_chat:

        new_title = st.text_input(
            "Chat name",
            value=current_chat["title"],
            key="rename_current_chat"
        )

        if st.button(
            "✏️ Rename",
            use_container_width=True
        ):

            if new_title.strip():

                rename_chat(
                    st.session_state.chat_id,
                    new_title.strip()
                )

                st.rerun()

        if st.button(
            "🗑️ Delete Chat",
            use_container_width=True
        ):

            delete_chat(
                st.session_state.chat_id
            )

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

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    st.divider()

    st.markdown(
        "### 📥 Export"
    )

    export_data = export_chat(
        st.session_state.chat_id
    )

    st.download_button(
        "Download Chat",
        data=export_data,
        file_name="my_ai_chat.md",
        mime="text/markdown",
        use_container_width=True
    )

    # --------------------------------------------------------
    # API STATUS
    # --------------------------------------------------------

    st.divider()

    if client:

        st.success(
            "● Gemini API Connected"
        )

    else:

        st.warning(
            "● Gemini API Key Missing"
        )

    st.caption(
        "Model: "
        + st.session_state.last_model
    )


# ============================================================
# MAIN HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">

        <div class="hero-title">
            🤖 My AI
        </div>

        <div class="hero-subtitle">
            Your intelligent personal AI assistant
        </div>

    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CURRENT CHAT
# ============================================================

messages = get_messages(
    st.session_state.chat_id
)


# ============================================================
# WELCOME
# ============================================================

if not messages:

    st.markdown(
        """
        <div style="
            text-align:center;
            padding:35px 10px;
        ">

            <div style="
                font-size:55px;
            ">
                ✨
            </div>

            <h2>
                Welcome to My AI
            </h2>

            <p style="
                color:#94a3b8;
            ">
                Ask anything. Learn anything.
                Build anything.
            </p>

        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.markdown(
            """
            <div class="card">

                <div style="font-size:30px">
                    📚
                </div>

                <b>
                    Study Mode
                </b>

                <div class="small-text">
                    Learn concepts step-by-step.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            """
            <div class="card">

                <div style="font-size:30px">
                    💻
                </div>

                <b>
                    Coding Mode
                </b>

                <div class="small-text">
                    Write, debug and learn code.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:

        st.markdown(
            """
            <div class="card">

                <div style="font-size:30px">
                    🔎
                </div>

                <b>
                    Web Search
                </b>

                <div class="small-text">
                    Search the web for information.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )


# ============================================================
# DISPLAY MESSAGES
# ============================================================

for message in messages:

    role = message["role"]

    if role == "user":

        with st.chat_message(
            "user"
        ):

            st.markdown(
                message["content"]
            )

    else:

        with st.chat_message(
            "assistant"
        ):

            st.markdown(
                message["content"]
            )


# ============================================================
# CHAT INPUT
# ============================================================

user_message = st.chat_input(
    "Ask me anything..."
)


if user_message:

    user_message = (
        user_message.strip()
    )

    if not user_message:

        st.stop()

    # --------------------------------------------------------
    # AUTO TITLE
    # --------------------------------------------------------

    if len(messages) == 0:

        rename_chat(
            st.session_state.chat_id,
            make_title(
                user_message
            )
        )

    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    save_message(
        st.session_state.chat_id,
        "user",
        user_message
    )

    # --------------------------------------------------------
    # SHOW USER MESSAGE
    # --------------------------------------------------------

    with st.chat_message(
        "user"
    ):

        st.markdown(
            user_message
        )

    # --------------------------------------------------------
    # CREATE PROMPT
    # --------------------------------------------------------

    prompt = build_prompt(
        user_message
    )

    # --------------------------------------------------------
    # AI RESPONSE
    # --------------------------------------------------------

    with st.chat_message(
        "assistant"
    ):

        with st.spinner(
            "My AI is thinking..."
        ):

            answer = ask_gemini(
                prompt
            )

        st.markdown(
            answer
        )

    # --------------------------------------------------------
    # SAVE AI RESPONSE
    # --------------------------------------------------------

    save_message(
        st.session_state.chat_id,
        "assistant",
        answer
    )

    # Refresh UI
    st.rerun()