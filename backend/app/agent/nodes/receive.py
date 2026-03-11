from app.agent.state import BiographerState
from app.db.database import get_db
from langchain_core.messages import HumanMessage, AIMessage
import uuid


async def receive(state: BiographerState) -> dict:
    """Load conversation history from DB if resuming, count turns."""
    conversation_id = state.get("conversation_id", "")
    messages = state.get("messages", [])

    # If we have a conversation_id, load prior messages from DB
    if conversation_id:
        db = await get_db()
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conversation_id,),
        )
        rows = await cursor.fetchall()

        if rows:
            # Build message history from DB, excluding the latest user message
            # (which is already in state.messages)
            db_messages = []
            for row in rows:
                if row["role"] == "user":
                    db_messages.append(HumanMessage(content=row["content"]))
                elif row["role"] == "assistant":
                    db_messages.append(AIMessage(content=row["content"]))

            # The last message in state is the new user message
            new_user_msg = messages[-1] if messages else None
            if new_user_msg and db_messages:
                messages = db_messages + [new_user_msg]

            turn_count = sum(1 for m in messages if isinstance(m, HumanMessage))
        else:
            turn_count = 1
    else:
        # New conversation
        conversation_id = str(uuid.uuid4())
        turn_count = 1

    return {
        "conversation_id": conversation_id,
        "turn_count": turn_count,
        "messages": messages,
    }
