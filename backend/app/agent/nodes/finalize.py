from app.agent.state import BiographerState
from app.db.database import get_db
from app.db import vector_store
import uuid
from datetime import datetime, timezone


def _make_title(text: str, max_len: int = 60) -> str:
    """Generate a conversation title from the first user message."""
    text = " ".join(text.strip().split())  # normalise whitespace
    if not text:
        return "New conversation"
    if len(text) <= max_len:
        return text
    # Truncate at last word boundary
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated + "…"


async def finalize(state: BiographerState) -> dict:
    """Persist the conversation turn to the database."""
    db = await get_db()
    conversation_id = state["conversation_id"]
    messages = state.get("messages", [])
    now = datetime.now(timezone.utc).isoformat()

    # Ensure conversation exists — generate a title from the first user message
    existing = await db.execute(
        "SELECT id, title FROM conversations WHERE id = ?", (conversation_id,)
    )
    existing_row = await existing.fetchone()
    if not existing_row:
        # New conversation — title from first user message
        first_user_text = ""
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "human":
                first_user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
            # LangChain HumanMessage doesn't always have .type; check class name
            if msg.__class__.__name__ == "HumanMessage":
                first_user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        title = _make_title(first_user_text)
        await db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, title, now, now),
        )
        print(f"[finalize] Created conversation: '{title}'")

    # Find the last user message and last assistant message to save
    from langchain_core.messages import HumanMessage, AIMessage

    last_user = None
    last_assistant = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and last_assistant is None:
            last_assistant = msg
        elif isinstance(msg, HumanMessage) and last_user is None:
            last_user = msg
        if last_user and last_assistant:
            break

    # Check if these messages already exist (avoid double-saving)
    if last_user:
        cursor = await db.execute(
            "SELECT id FROM messages WHERE conversation_id = ? AND role = 'user' AND content = ? ORDER BY timestamp DESC LIMIT 1",
            (conversation_id, last_user.content),
        )
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), conversation_id, "user", last_user.content, now),
            )

    if last_assistant:
        content = last_assistant.content if isinstance(last_assistant.content, str) else str(last_assistant.content)
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), conversation_id, "assistant", content, now),
        )

    # Update conversation timestamp
    await db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )

    await db.commit()

    # Index conversation in vector store for RAG
    try:
        # Build messages list for indexing
        index_messages = []
        if last_user:
            index_messages.append({"role": "user", "content": last_user.content})
        if last_assistant:
            content = last_assistant.content if isinstance(last_assistant.content, str) else str(last_assistant.content)
            index_messages.append({"role": "assistant", "content": content})
        if index_messages:
            await vector_store.index_conversation(conversation_id, index_messages)
    except Exception as e:
        print(f"[finalize] Vector indexing error: {e}")

    return {}
