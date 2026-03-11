from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class BiographerState(TypedDict):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    conversation_id: str
    user_name: str

    # Classification (set by CLASSIFY node)
    intent: str       # sharing, correcting, asking, greeting, casual
    mood: str         # reflective, enthusiastic, emotional, matter_of_fact, frustrated, curious, neutral
    is_correction: bool
    should_extract: bool

    # Strategy (set by STRATEGIZE node)
    strategy: str           # Brief instruction for how to respond
    biography_summary: str  # Compressed known biography text

    # Flow control
    turn_count: int
    response_content: str   # Full response text after streaming
