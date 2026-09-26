import streamlit as st
from google import genai
from dotenv import load_dotenv
import sqlite3
import os
import time
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

load_dotenv()

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

DB_FILE = "chatbot.db"


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="My AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return sqlite3.connect(DB_FILE)


def init_database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            user_name TEXT DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute(
        "SELECT id FROM settings WHERE id = 1"
    )

    if cursor.fetchone() is None:

        cursor.execute(
            "INSERT INTO settings (id, user_name) VALUES (1, '')"
        )

    conn.commit()
    conn.close()


init_database()


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def get_user_name():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_name FROM settings WHERE id = 1"
    )

    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]

    return ""


def save_user_name(name):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE settings SET user_name = ? WHERE id = 1",
        (name,)
    )

    conn.commit()
    conn.close()


def create_chat(title="New Chat"):

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO chats (title, created_at)
        VALUES (?, ?)
        """,
        (title, now)
    )

    chat_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def get_chats():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, created_at
        FROM chats
        ORDER BY id DESC
        """
    )

    chats = cursor.fetchall()

    conn.close()

    return chats


def rename_chat(chat_id, new_title):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chats
        SET title = ?
        WHERE id = ?
        """,
        (new_title, chat_id)
    )

    conn.commit()
    conn.close()


def delete_chat(chat_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM messages WHERE chat_id = ?",
        (chat_id,)
    )

    cursor.execute(
        "DELETE FROM chats WHERE id = ?",
        (chat_id,)
    )

    conn.commit()
    conn.close()


def save_message(chat_id, role, content):

    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO messages
        (chat_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, role, content, now)
    )

    conn.commit()
    conn.close()


def get_messages(chat_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,)
    )

    messages = cursor.fetchall()

    conn.close()

    return messages


# ============================================================
# SESSION STATE
# ============================================================

if "current_chat_id" not in st.session_state:

    chats = get_chats()

    if chats:

        st.session_state.current_chat_id = chats[0][0]

    else:

        st.session_state.current_chat_id = create_chat()


if "mode" not in st.session_state:

    st.session_state.mode = "General"


# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>

.block-container {
    max-width: 1100px;
    padding-top: 1.5rem;
    padding-bottom: 5rem;
}

.main-title {
    text-align: center;
    font-size: 42px;
    font-weight: 700;
    margin-bottom: 0;
}

.subtitle {
    text-align: center;
    color: #777;
    margin-bottom: 25px;
}

.chat-card {
    padding: 15px;
    border-radius: 15px;
    background: #f5f7fb;
    margin-bottom: 15px;
}

.small-text {
    color: #777;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# CURRENT USER
# ============================================================

user_name = get_user_name()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 My AI")

    st.caption("Your personal AI assistant")

    st.divider()


    # USER NAME

    st.subheader("👤 Profile")

    new_name = st.text_input(
        "Your name",
        value=user_name,
        placeholder="Enter your name"
    )

    if new_name != user_name:

        save_user_name(new_name)

        user_name = new_name


    st.divider()


    # MODE

    st.subheader("🎯 Mode")

    mode = st.selectbox(
        "Choose mode",
        [
            "General",
            "📚 Study Mode",
            "💻 Coding Mode"
        ]
    )

    st.session_state.mode = mode


    st.divider()


    # NEW CHAT

    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        new_chat_id = create_chat()

        st.session_state.current_chat_id = new_chat_id

        st.rerun()


    st.divider()


    # CHAT HISTORY

    st.subheader("🗂️ Chat History")

    chats = get_chats()

    if not chats:

        st.caption("No conversations yet.")

    else:

        for chat_id, title, created_at in chats:

            col1, col2 = st.columns([4, 1])

            with col1:

                if st.button(
                    title[:28],
                    key=f"open_{chat_id}",
                    use_container_width=True
                ):

                    st.session_state.current_chat_id = chat_id

                    st.rerun()

            with col2:

                if st.button(
                    "🗑️",
                    key=f"delete_{chat_id}"
                ):

                    delete_chat(chat_id)

                    remaining = get_chats()

                    if remaining:

                        st.session_state.current_chat_id = remaining[0][0]

                    else:

                        st.session_state.current_chat_id = create_chat()

                    st.rerun()


    st.divider()


    # RENAME

    st.subheader("✏️ Rename Chat")

    new_title = st.text_input(
        "New chat name",
        placeholder="Example: Python Practice"
    )

    if st.button(
        "Rename",
        use_container_width=True
    ):

        if new_title.strip():

            rename_chat(
                st.session_state.current_chat_id,
                new_title.strip()
            )

            st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🤖 My AI</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Your intelligent personal AI assistant'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# CURRENT CHAT
# ============================================================

current_messages = get_messages(
    st.session_state.current_chat_id
)


# ============================================================
# WELCOME
# ============================================================

if not current_messages:

    greeting = "👋 Hello!"

    if user_name:

        greeting = f"👋 Hello {user_name}!"

    st.markdown(
        f"""
        <div class="chat-card">

        <h3>{greeting}</h3>

        <p>
        Welcome to My AI. Ask me anything about:
        </p>

        <ul>
            <li>📚 Study</li>
            <li>💻 Coding</li>
            <li>➗ Mathematics</li>
            <li>🧠 Concepts</li>
            <li>✍️ Writing</li>
            <li>🔍 Problem solving</li>
        </ul>

        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# DISPLAY MESSAGES
# ============================================================

for role, content in current_messages:

    with st.chat_message(role):

        st.markdown(content)


# ============================================================
# CREATE AI PROMPT
# ============================================================

def create_prompt(messages, question):

    conversation = ""

    # Keep recent context
    recent_messages = messages[-20:]

    for role, content in recent_messages:

        conversation += (
            f"{role}: {content}\n"
        )


    prompt = f"""
You are My AI, a helpful intelligent personal AI assistant.

User name:
{user_name or "User"}

Current mode:
{st.session_state.mode}

Instructions:

- Answer clearly and accurately.
- Remember the conversation context.
- Explain difficult concepts simply.
- Help with Python, C, C++, Java and DSA.
- Help with mathematics and college studies.
- Give step-by-step explanations for beginners.
- Debug code when asked.
- Be friendly and helpful.
- Do not unnecessarily repeat the question.

Previous conversation:

{conversation}

Latest user question:

{question}

Answer the latest question.
"""

    return prompt


# ============================================================
# GEMINI
# ============================================================

def ask_gemini(prompt):

    if client is None:

        return (
            "🔐 Gemini API key was not found.\n\n"
            "Please check your `.env` file."
        )


    for attempt in range(3):

        try:

            response = client.models.generate_content(

                model="gemini-3.8-flash",

                contents=prompt
            )

            if response and response.text:

                return response.text

            return "⚠️ Empty response received."

        except Exception as error:

            error_text = str(error).lower()


            # Temporary overload

            if (
                "503" in error_text
                or "unavailable" in error_text
                or "high demand" in error_text
            ):

                if attempt < 2:

                    time.sleep(2)

                    continue

                return (
                    "⚠️ Gemini is temporarily busy.\n\n"
                    "Please try again in a few seconds."
                )


            # Rate limit

            if (
                "429" in error_text
                or "rate limit" in error_text
            ):

                return (
                    "⚠️ Rate limit reached.\n\n"
                    "Please wait a little and try again."
                )


            # API key

            if (
                "401" in error_text
                or "403" in error_text
                or "api key" in error_text
            ):

                return (
                    "🔐 API key problem.\n\n"
                    "Please check your Gemini API key."
                )


            return (
                "⚠️ Something went wrong.\n\n"
                f"`{str(error)}`"
            )


# ============================================================
# CHAT INPUT
# ============================================================

user_message = st.chat_input(
    "💬 Ask me anything..."
)


if user_message:

    # Current messages before new message
    old_messages = get_messages(
        st.session_state.current_chat_id
    )


    # Save user message

    save_message(
        st.session_state.current_chat_id,
        "user",
        user_message
    )


    # Automatically name first chat

    if len(old_messages) == 0:

        title = user_message[:35]

        if len(user_message) > 35:

            title += "..."

        rename_chat(
            st.session_state.current_chat_id,
            title
        )


    # Show user

    with st.chat_message("user"):

        st.markdown(user_message)


    # Create prompt

    prompt = create_prompt(
        old_messages,
        user_message
    )


    # AI

    with st.chat_message("assistant"):

        with st.spinner("🤔 Thinking..."):

            answer = ask_gemini(prompt)

        st.markdown(answer)


    # Save AI response

    save_message(
        st.session_state.current_chat_id,
        "assistant",
        answer
    )


    # Refresh

    st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "✨ My AI • Persistent Chat History • Study • Coding"
)