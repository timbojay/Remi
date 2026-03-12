"""CLASSIFY node: Fast rule-based intent + mood classification.

Replaces the previous LLM call with regex/keyword rules — saves ~1s of pre-stream latency
with no meaningful quality loss (classification is simple and deterministic enough).
"""

import re
from app.agent.state import BiographerState
from langchain_core.messages import HumanMessage

# ── Intent patterns ──────────────────────────────────────────────────

_CORRECTION_RE = re.compile(
    r'\b(actually|no,|wait,|that\'s\s+(wrong|not\s+right|incorrect)|not\s+quite|'
    r'correction|incorrect|mistake|meant\s+to\s+say|meant\s+\w+|wrong|'
    r'fix\s+that|update\s+that|change\s+that|that\s+should\s+be|i\s+said\s+\w+\s+not)\b',
    re.IGNORECASE,
)
_CORRECTION_START_RE = re.compile(r'^(no\b|nope\b|wrong\b|actually\b)', re.IGNORECASE)

_GREETING_RE = re.compile(
    r'^(hi|hello|hey|good\s+(morning|afternoon|evening|night)|howdy|sup|yo|greetings)\b',
    re.IGNORECASE,
)
_GREETING_PHRASES = re.compile(
    r'^(how are you|how\'s it going|what\'s up|how\'s everything)',
    re.IGNORECASE,
)

_ASKING_START_RE = re.compile(
    r'^(what|when|where|who|how|why|do you|can you|could you|would you|'
    r'did you|have you|is there|are there|tell me)',
    re.IGNORECASE,
)

_CASUAL_WORDS = {
    'ok', 'okay', 'thanks', 'thank you', 'cool', 'nice', 'great', 'sure',
    'lol', 'haha', 'hehe', 'yep', 'yup', 'nope', 'gotcha', 'got it',
    'sounds good', 'alright', 'right', 'fair enough', 'interesting',
}

# ── Mood patterns ────────────────────────────────────────────────────

_FRUSTRATED_RE = re.compile(
    r'\b(wrong|incorrect|no,|actually|that\'s\s+not|fix|ugh|argh|frustrated|annoying)\b',
    re.IGNORECASE,
)

_EMOTIONAL_RE = re.compile(
    r'\b(miss|missed|missing|died|passed\s+away|heartbreak|heartbroken|'
    r'devastated|grief|mourning|so\s+(sad|happy)|can\'t\s+believe|'
    r'changed\s+my\s+life|meant\s+everything|love\s+them|loved\s+them)\b',
    re.IGNORECASE,
)

_REFLECTIVE_RE = re.compile(
    r'\b(remember|looking\s+back|used\s+to|back\s+then|those\s+days|'
    r'when\s+i\s+was|as\s+a\s+kid|growing\s+up|childhood|in\s+those\s+days|'
    r'i\s+still\s+recall|fond\s+memories)\b',
    re.IGNORECASE,
)

_ENTHUSIASTIC_RE = re.compile(
    r'(!!|amazing|incredible|love\s+it|loved\s+it|so\s+excited|fantastic|brilliant|awesome)',
    re.IGNORECASE,
)


def _classify_intent(text: str) -> str:
    """Rule-based intent classification."""
    stripped = text.strip()
    lower = stripped.lower()

    # Greeting
    if _GREETING_RE.match(stripped) or _GREETING_PHRASES.match(stripped):
        return "greeting"

    # Very short or pure casual filler
    if len(stripped) < 20 and lower.rstrip('!.,?') in _CASUAL_WORDS:
        return "casual"
    if lower.rstrip('!.,?') in _CASUAL_WORDS:
        return "casual"

    # Correction
    if _CORRECTION_START_RE.match(stripped) or _CORRECTION_RE.search(stripped):
        return "correcting"

    # Question
    if _ASKING_START_RE.match(stripped) or stripped.endswith('?'):
        return "asking"

    # Default: assume biographical sharing
    return "sharing"


def _classify_mood(text: str, intent: str) -> str:
    """Rule-based mood classification."""
    if intent == "correcting" or _FRUSTRATED_RE.search(text):
        return "frustrated"

    if _EMOTIONAL_RE.search(text):
        return "emotional"

    if _REFLECTIVE_RE.search(text):
        return "reflective"

    if _ENTHUSIASTIC_RE.search(text):
        return "enthusiastic"

    if intent == "asking":
        return "curious"

    # Short declarative — matter of fact
    if len(text.strip()) < 60 and not text.strip().endswith('?') and intent == "sharing":
        return "matter_of_fact"

    return "neutral"


async def classify(state: BiographerState) -> dict:
    """Classify the user's message intent and mood — rule-based, no LLM call."""
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

    intent = _classify_intent(user_text)
    mood = _classify_mood(user_text, intent)
    is_correction = intent == "correcting"
    should_extract = intent in ("sharing", "correcting")

    print(f"[classify] intent={intent} mood={mood} is_correction={is_correction} (rule-based)")

    return {
        "intent": intent,
        "mood": mood,
        "is_correction": is_correction,
        "should_extract": should_extract,
    }
