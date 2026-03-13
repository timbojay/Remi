"""ChromaDB vector store for conversation memory and semantic search."""

import asyncio
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from app.config import settings

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None
_fact_collection: chromadb.Collection | None = None

COLLECTION_NAME = "conversation_memory"
FACT_COLLECTION_NAME = "fact_embeddings"
OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_BASE_URL = "http://localhost:11434"


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        import os
        persist_dir = os.path.join(os.path.dirname(settings.DB_PATH), "chroma")
        os.makedirs(persist_dir, exist_ok=True)
        _client = chromadb.PersistentClient(path=persist_dir)
    return _client


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = _get_client()
        embed_fn = OllamaEmbeddingFunction(
            url=OLLAMA_BASE_URL,
            model_name=OLLAMA_EMBED_MODEL,
        )
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


async def index_conversation(
    conversation_id: str,
    messages: list[dict],
    title: str = "",
):
    """Index a conversation's messages for semantic search.

    Each message pair (user + assistant) becomes one document.
    """
    collection = _get_collection()

    documents = []
    metadatas = []
    ids = []

    # Build document from message pairs
    for i in range(0, len(messages) - 1, 2):
        user_msg = messages[i] if messages[i].get("role") == "user" else None
        assist_msg = messages[i + 1] if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant" else None

        if not user_msg:
            continue

        doc_parts = [f"User: {user_msg['content']}"]
        if assist_msg:
            doc_parts.append(f"Assistant: {assist_msg['content']}")

        doc_id = f"{conversation_id}_{i // 2}"

        documents.append("\n".join(doc_parts))
        metadatas.append({
            "conversation_id": conversation_id,
            "pair_index": i // 2,
            "title": title or "",
        })
        ids.append(doc_id)

    if not documents:
        return

    # Upsert to handle re-indexing
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )
    print(f"[vector] Indexed {len(documents)} exchanges from conversation {conversation_id[:8]}")


async def search_conversations(query: str, limit: int = 5) -> list[dict]:
    """Search for conversations similar to the query."""
    collection = _get_collection()

    try:
        results = collection.query(
            query_texts=[query],
            n_results=limit,
        )
    except Exception as e:
        print(f"[vector] Search error: {e}")
        return []

    if not results["documents"] or not results["documents"][0]:
        return []

    hits = []
    for doc, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "content": doc,
            "conversation_id": metadata.get("conversation_id", ""),
            "title": metadata.get("title", ""),
            "similarity": 1 - distance,  # Convert distance to similarity
        })

    return hits


async def get_collection_count() -> int:
    """Get the number of indexed documents."""
    try:
        collection = _get_collection()
        return collection.count()
    except Exception:
        return 0


# ─── FACT EMBEDDINGS ──────────────────────────────────────────────────

def _get_fact_collection() -> chromadb.Collection:
    global _fact_collection
    if _fact_collection is None:
        client = _get_client()
        embed_fn = OllamaEmbeddingFunction(
            url=OLLAMA_BASE_URL,
            model_name=OLLAMA_EMBED_MODEL,
        )
        _fact_collection = client.get_or_create_collection(
            name=FACT_COLLECTION_NAME,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _fact_collection


async def index_fact(fact_id: str, fact_value: str) -> None:
    """Index a fact's text for semantic dedup. Runs embedding in a thread to avoid blocking."""
    def _do():
        collection = _get_fact_collection()
        collection.upsert(
            documents=[fact_value],
            ids=[fact_id],
            metadatas=[{"fact_id": fact_id}],
        )
    try:
        await asyncio.to_thread(_do)
    except Exception as e:
        print(f"[vector] Failed to index fact: {e}")


async def find_similar_facts(text: str, threshold: float = 0.85, limit: int = 5) -> list[dict]:
    """Find facts semantically similar to the given text. Returns matches above threshold."""
    def _do():
        collection = _get_fact_collection()
        if collection.count() == 0:
            return []
        results = collection.query(
            query_texts=[text],
            n_results=min(limit, collection.count()),
        )
        return results

    try:
        results = await asyncio.to_thread(_do)
    except Exception as e:
        print(f"[vector] Fact similarity search error: {e}")
        return []

    if not results or not results["documents"] or not results["documents"][0]:
        return []

    hits = []
    for doc, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1 - distance
        if similarity >= threshold:
            hits.append({
                "fact_id": metadata.get("fact_id", ""),
                "text": doc,
                "similarity": similarity,
            })

    return hits
