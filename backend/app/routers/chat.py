import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel

from app.agent.nodes.receive import receive
from app.agent.nodes.classify import classify
from app.agent.nodes.correct import correct
from app.agent.nodes.strategize import strategize
from app.agent.nodes.finalize import finalize
from app.agent.nodes.extract import extract
from app.agent.nodes.greet import greet
from app.agent.prompts import build_system_prompt
from app.services.llm import get_streaming_llm, usage
from app.services.maintenance import notify_chat_start, notify_chat_end
from app.config import settings

router = APIRouter(prefix="/api")

# Keep references to background tasks so they aren't garbage collected
_background_tasks: set[asyncio.Task] = set()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


async def _post_stream_tasks(state: dict):
    """Run finalization and extraction after the stream completes."""
    # -- FINALIZE: persist conversation --
    print("[post-stream] Starting finalize...")
    await finalize(state)
    print("[post-stream] Finalize complete.")

    # -- EXTRACT: record facts/entities (only if should_extract) --
    if state.get("should_extract", True):
        print("[post-stream] Starting extraction...")
        try:
            await extract(state)
            print("[post-stream] Extraction complete.")
        except Exception as e:
            import traceback
            print(f"[extract] Error: {e}")
            traceback.print_exc()
    else:
        print("[post-stream] Skipping extraction (no biographical content)")

    # Signal chat complete — maintenance can resume
    notify_chat_end()


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a biographical conversation response.

    Pipeline: RECEIVE → CLASSIFY → STRATEGIZE → RESPOND (stream) → FINALIZE + EXTRACT (background)
    """
    import time
    t0 = time.time()

    # Signal that chat is active (pauses background maintenance)
    notify_chat_start()

    # -- RECEIVE --
    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "conversation_id": request.conversation_id or "",
        "user_name": settings.USER_NAME,
        "intent": "",
        "mood": "",
        "is_correction": False,
        "should_extract": True,
        "strategy": "",
        "biography_summary": "",
        "turn_count": 0,
        "response_content": "",
    }
    state = await receive(initial_state)
    for k, v in state.items():
        initial_state[k] = v
    state = initial_state
    conversation_id = state["conversation_id"]
    t1 = time.time()
    print(f"[timing] RECEIVE: {t1-t0:.2f}s")

    # -- CLASSIFY (instant, rule-based) then STRATEGIZE --
    # Classify runs first (microseconds — no LLM call) so strategize gets the
    # correct intent + mood and can choose the right conversational strategy.
    classify_result = await classify(state)
    state.update(classify_result)
    t1b = time.time()
    print(f"[timing] CLASSIFY: {t1b-t1:.4f}s (rule-based)")

    strategy_result = await strategize(state)
    state.update(strategy_result)
    t2 = time.time()
    print(f"[timing] STRATEGIZE: {t2-t1b:.2f}s")

    # -- CORRECT: if user is correcting data, fix it before responding --
    if state.get("is_correction"):
        try:
            await correct(state)
        except Exception as e:
            print(f"[correct] Error: {e}")
        t2b = time.time()
        print(f"[timing] CORRECT: {t2b-t2:.2f}s")
        t2 = t2b

    # Build system prompt with strategy and mood
    system_prompt = build_system_prompt(
        state["user_name"],
        biography_summary=state.get("biography_summary", ""),
        strategy=state.get("strategy", ""),
        mood=state.get("mood", ""),
    )
    llm_messages = state["messages"]
    pre_stream_time = t2 - t0

    async def generate():
        collected_content = []

        # -- RESPOND (streaming) --
        llm = get_streaming_llm(max_tokens=1024)

        messages_for_llm = [SystemMessage(content=system_prompt)] + llm_messages

        async for chunk in llm.astream(messages_for_llm):
            token = chunk.content if isinstance(chunk.content, str) else ""
            if token:
                collected_content.append(token)
                yield json.dumps({
                    "content": token,
                    "done": False,
                    "conversation_id": conversation_id,
                }) + "\n"

        full_response = "".join(collected_content)
        t4 = time.time()
        print(f"[timing] RESPOND: {t4-t2:.2f}s (total pre-stream: {pre_stream_time:.2f}s)")

        # Send done signal
        yield json.dumps({
            "content": "",
            "done": True,
            "conversation_id": conversation_id,
        }) + "\n"

        # Update state with full response for post-stream tasks
        state["messages"] = llm_messages + [AIMessage(content=full_response)]
        state["response_content"] = full_response

        # Run finalize + extract in background with a kept reference
        task = asyncio.create_task(_post_stream_tasks(state))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
    )


@router.get("/greet")
async def get_greeting():
    """Generate a personalized greeting for a new session."""
    try:
        greeting = await greet()
        return {"greeting": greeting}
    except Exception as e:
        print(f"[greet] Error: {e}")
        return {"greeting": f"Hello {settings.USER_NAME}! What would you like to talk about today?"}
