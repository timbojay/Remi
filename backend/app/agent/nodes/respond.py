from app.agent.state import BiographerState
from app.agent.prompts import build_system_prompt
from app.config import settings
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage


async def respond(state: BiographerState) -> dict:
    """Generate the biographical response using Ollama.

    Note: For streaming, the chat router invokes the LLM directly
    with a streaming callback. This node is used for non-streaming
    fallback and testing.
    """
    user_name = state.get("user_name", settings.USER_NAME)
    system_prompt = build_system_prompt(user_name)

    llm = ChatOllama(
        model=settings.MODEL_NAME,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=1024,
        options={"think": False},
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await llm.ainvoke(messages)

    return {
        "messages": [response],
        "response_content": response.content,
    }
