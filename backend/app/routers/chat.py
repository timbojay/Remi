import asyncio
import json
import re
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel

from app.agent.nodes.receive import receive
from app.agent.nodes.classify import classify
from app.agent.nodes.correct import correct
from app.agent.nodes.strategize import strategize
from app.agent.nodes.retrieve import retrieve_focused_context
from app.agent.nodes.finalize import finalize
from app.agent.nodes.extract import extract
from app.agent.nodes.greet import greet
from app.agent.prompts import build_system_prompt
from app.services.llm import get_streaming_llm, invoke_with_retry, usage
from app.services.maintenance import notify_chat_start, notify_chat_end
from app.config import settings

router = APIRouter(prefix="/api")

# Keep references to background tasks so they aren't garbage collected
_background_tasks: set[asyncio.Task] = set()

# ── Response validation ────────────────────────────────────────────────────
# Phrases that signal the model is guessing rather than interviewing
_HALLUCINATION_RE = re.compile(
    r"\b("
    r"i (can |could )imagine|"
    r"(she|he) must have|"
    r"i (can |could )picture|"
    r"i('ve| have) heard|"
    r"i remember (reading|hearing|being told)|"
    r"(she|he) probably|"
    r"it must have been|"
    r"i would imagine|"
    r"sounds like (she|he|they)"
    r")\b",
    re.IGNORECASE,
)

_RETRY_SUFFIX = (
    "\n\nREMINDER: Reply in 1-2 sentences maximum, then ask exactly ONE question. "
    "Do not invent or assume anything not listed above. Be brief and direct."
)


def _validate_response(text: str) -> tuple[bool, str]:
    """Returns (is_valid, reason_if_invalid)."""
    if not text or len(text.split()) < 4:
        return False, f"response too short or empty"
    if _HALLUCINATION_RE.search(text):
        return False, "hallucination phrase detected"
    word_count = len(text.split())
    if word_count > 80:
        return False, f"too long ({word_count} words)"
    if text.count("?") > 2:
        return False, f"too many questions ({text.count('?')})"
    return True, ""


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


async def _post_stream_tasks(state: dict):
    """Run finalization and extraction after the stream completes."""
    print("[post-stream] Starting finalize...")
    await finalize(state)
    print("[post-stream] Finalize complete.")

    if state.get("should_extract", True) and not state.get("skip_extraction", False):
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

    notify_chat_end()


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Biographical conversation with validate+retry respond step.

    Pipeline:
      RECEIVE → CLASSIFY → STRATEGIZE → RETRIEVE → RESPOND (validate+retry) →
      fake-stream to client → FINALIZE + EXTRACT (background)
    """
    t0 = time.time()
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
        "focused_context": "",
        "turn_count": 0,
        "response_content": "",
        "skip_extraction": False,
    }
    state = await receive(initial_state)
    for k, v in state.items():
        initial_state[k] = v
    state = initial_state
    conversation_id = state["conversation_id"]
    t1 = time.time()
    print(f"[timing] RECEIVE: {t1-t0:.2f}s")

    # -- CLASSIFY (instant, rule-based) --
    classify_result = await classify(state)
    state.update(classify_result)
    t1b = time.time()
    print(f"[timing] CLASSIFY: {t1b-t1:.4f}s (rule-based)")

    # -- STRATEGIZE --
    strategy_result = await strategize(state)
    state.update(strategy_result)
    t2 = time.time()
    print(f"[timing] STRATEGIZE: {t2-t1b:.2f}s")

    # -- CORRECT --
    if state.get("is_correction"):
        try:
            correct_result = await correct(state)
            state.update(correct_result)
        except Exception as e:
            print(f"[correct] Error: {e}")
        t2b = time.time()
        print(f"[timing] CORRECT: {t2b-t2:.2f}s")
        t2 = t2b

    # -- RETRIEVE: focused context for this specific message --
    focused_context = await retrieve_focused_context(state)
    state["focused_context"] = focused_context
    t3 = time.time()
    print(f"[timing] RETRIEVE: {t3-t2:.2f}s")

    # Build system prompt using focused context instead of full biography dump
    system_prompt = build_system_prompt(
        state["user_name"],
        biography_summary=focused_context,   # targeted, not full dump
        strategy=state.get("strategy", ""),
        mood=state.get("mood", ""),
    )
    llm_messages = state["messages"]

    async def generate():
        # -- RESPOND: generate full response, validate, retry once if needed --
        llm = get_streaming_llm(max_tokens=200)
        messages_for_llm = [SystemMessage(content=system_prompt)] + llm_messages

        # First attempt — non-streaming so we can validate before sending
        full_response = await invoke_with_retry(
            messages_for_llm,
            node="respond",
            max_tokens=200,
        )
        t4 = time.time()
        print(f"[timing] RESPOND attempt 1: {t4-t3:.2f}s")

        valid, reason = _validate_response(full_response)
        if not valid:
            print(f"[respond] Validation failed ({reason}), retrying...")
            retry_messages = [
                SystemMessage(content=system_prompt + _RETRY_SUFFIX)
            ] + llm_messages
            full_response = await invoke_with_retry(
                retry_messages,
                node="respond-retry",
                max_tokens=150,
            )
            t4b = time.time()
            print(f"[timing] RESPOND retry: {t4b-t4:.2f}s")
            valid2, reason2 = _validate_response(full_response)
            if not valid2:
                print(f"[respond] Retry still invalid ({reason2}), using anyway")

        # Emergency fallback — never send a blank response to the client
        if not full_response or not full_response.strip():
            full_response = "Tell me more — I'm listening. What happened next?"
            print("[respond] Emergency fallback used — LLM returned empty response")

        total_pre = t4 - t0
        print(f"[timing] Total pre-response: {total_pre:.2f}s | response: {len(full_response.split())} words")

        # Fake-stream: yield word by word so the UI still feels alive
        words = full_response.split()
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            yield json.dumps({
                "content": token,
                "done": False,
                "conversation_id": conversation_id,
            }) + "\n"
            # No artificial delay — yield immediately for responsive streaming

        yield json.dumps({
            "content": "",
            "done": True,
            "conversation_id": conversation_id,
        }) + "\n"

        # Update state for post-stream background tasks
        state["messages"] = llm_messages + [AIMessage(content=full_response)]
        state["response_content"] = full_response

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
        if not greeting or not greeting.strip():
            greeting = f"Hello {settings.USER_NAME}! What would you like to share today?"
        return {"greeting": greeting}
    except Exception as e:
        print(f"[greet] Error: {e}")
        return {"greeting": f"Hello {settings.USER_NAME}! What would you like to talk about today?"}
