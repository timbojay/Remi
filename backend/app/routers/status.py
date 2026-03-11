from fastapi import APIRouter
from app.db.database import get_db
from app.db import vector_store
from app.services.llm import usage

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as count FROM conversations")
    row = await cursor.fetchone()
    conversation_count = row["count"] if row else 0

    cursor = await db.execute("SELECT COUNT(*) as count FROM messages")
    row = await cursor.fetchone()
    message_count = row["count"] if row else 0

    cursor = await db.execute("SELECT COUNT(*) as count FROM facts WHERE is_suppressed = 0")
    row = await cursor.fetchone()
    fact_count = row["count"] if row else 0

    cursor = await db.execute("SELECT COUNT(*) as count FROM entities WHERE is_suppressed = 0")
    row = await cursor.fetchone()
    entity_count = row["count"] if row else 0

    cursor = await db.execute("SELECT COUNT(*) as count FROM relationships")
    row = await cursor.fetchone()
    relationship_count = row["count"] if row else 0

    vector_count = await vector_store.get_collection_count()

    return {
        "status": "ok",
        "conversations": conversation_count,
        "messages": message_count,
        "facts": fact_count,
        "entities": entity_count,
        "relationships": relationship_count,
        "vectors": vector_count,
        "api_usage": usage.to_dict(),
    }


@router.get("/conversations")
async def list_conversations():
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
        (conversation_id,),
    )
    conv = await cursor.fetchone()
    if not conv:
        return {"error": "not found"}

    cursor = await db.execute(
        "SELECT id, role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp",
        (conversation_id,),
    )
    messages = await cursor.fetchall()

    return {
        **dict(conv),
        "messages": [dict(m) for m in messages],
    }
