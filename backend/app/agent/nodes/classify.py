"""CLASSIFY node: Fast intent + mood classification of the user's message."""

import json
import re
from app.agent.state import BiographerState
from app.agent.prompts import CLASSIFY_PROMPT
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage


async def classify(state: BiographerState) -> dict:
    """Classify the user's message intent and mood with a single fast Claude call."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    # Get the last user message
    last_user = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user = msg
            break

    if not last_user:
        return {}

    user_text = last_user.content if isinstance(last_user.content, str) else str(last_user.content)

    result_text = await invoke_with_retry(
        [
            SystemMessage(content=CLASSIFY_PROMPT),
            HumanMessage(content=user_text),
        ],
        node="classify",
        max_tokens=256,
    )

    # Parse JSON result
    data = _parse_classify_json(result_text)
    if not data:
        print(f"[classify] Failed to parse, using defaults")
        return {
            "intent": "sharing",
            "mood": "neutral",
            "is_correction": False,
            "should_extract": True,
        }

    intent = data.get("intent", "sharing")
    mood = data.get("mood", "neutral")
    is_correction = intent == "correcting"
    should_extract = intent in ("sharing", "correcting")

    print(f"[classify] intent={intent} mood={mood} is_correction={is_correction} should_extract={should_extract}")

    return {
        "intent": intent,
        "mood": mood,
        "is_correction": is_correction,
        "should_extract": should_extract,
    }


def _parse_classify_json(text: str) -> dict | None:
    """Parse JSON from classification response."""
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None
