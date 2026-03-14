from app.agent.state import BiographerState
from app.agent.prompts import build_system_prompt
from app.config import settings
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage


async def respond(state: BiographerState) -> dict:
    """Generate the biographical response using Ollama.

    Note: For streaming, the chat router invokes the LLM directly
    with a streaming callback. This node is used for non-streaming
    fallback and testing.
    """
    user_name = state.get("user_name", settings.USER_NAME)
    system_prompt = build_system_prompt(user_name)

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    content = await invoke_with_retry(messages, node="respond-fallback", max_tokens=500)

    from langchain_core.messages import AIMessage
    return {
        "messages": [AIMessage(content=content)],
        "response_content": content,
    }
