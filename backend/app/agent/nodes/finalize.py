from app.agent.state import BiographerState
from app.db.database import get_db
from app.db import vector_store
import uuid
from datetime import datetime, timezone


async def finalize(state: BiographerState) -> dict:
    """Persist the conversation turn to the database."""
    db = await get_db()
    conversation_id = state["conversation_id"]
    messages = state.get("messages", [])
    now = datetime.now(timezone.utc).isoformat()

    # Ensure conversation exists
    existing = await db.execute(
        "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
    )
    if not await existing.fetchone():
        await db.execute(
            "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
            (conversation_id, now, now),
        )

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
