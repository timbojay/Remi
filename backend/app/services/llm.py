"""Centralized LLM utilities: retry logic, usage tracking, shared client."""

import asyncio
import re
import time
from dataclasses import dataclass, field
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage

from app.config import settings


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks produced by reasoning models (e.g. qwen3).

    Some Ollama models output their chain-of-thought inside <think> tags before
    the actual response. We strip them so downstream code only sees the answer.
    """
    # Remove <think>...</think> blocks (greedy=False so we don't eat real content)
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return stripped.strip()


@dataclass
class UsageStats:
    """Cumulative LLM usage stats for this server session."""
    total_calls: int = 0
    total_errors: int = 0
    total_retries: int = 0
    calls_by_node: dict = field(default_factory=dict)

    def record(self, node: str):
        self.total_calls += 1
        if node not in self.calls_by_node:
            self.calls_by_node[node] = {"calls": 0}
        self.calls_by_node[node]["calls"] += 1

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_errors": self.total_errors,
            "total_retries": self.total_retries,
            "by_node": dict(self.calls_by_node),
            "model": settings.MODEL_NAME,
            "ollama_base_url": settings.OLLAMA_BASE_URL,
        }


usage = UsageStats()


# ── Retry-enabled invoke ───────────────────────────────────────────────

async def invoke_with_retry(
    messages: list[BaseMessage],
    *,
    node: str = "unknown",
    max_tokens: int = 1024,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> str:
    """Invoke Ollama LLM with automatic retry on transient errors.

    Returns the response text.
    """
    llm = ChatOllama(
        model=settings.MODEL_NAME,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=max_tokens,
        # Disable thinking mode for qwen3 and other reasoning models.
        # Must be a top-level kwarg, NOT inside options={} — Ollama treats
        # them differently and options={"think":False} is silently ignored.
        think=False,
    )

    last_error = None
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            response = await llm.ainvoke(messages)
            elapsed = time.time() - t0

            usage.record(node)
            print(f"[llm] {node}: completed in {elapsed:.1f}s (model: {settings.MODEL_NAME})")

            raw = response.content if isinstance(response.content, str) else str(response.content)
            return _strip_thinking(raw)

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            is_retryable = any(
                keyword in error_str
                for keyword in ["connection", "timeout", "500", "503", "unavailable"]
            )

            if is_retryable and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                usage.total_retries += 1
                print(f"[llm] {node}: Retry {attempt + 1}/{max_retries} after {delay:.1f}s — {e}")
                await asyncio.sleep(delay)
            else:
                usage.total_errors += 1
                raise

    raise last_error  # type: ignore


def get_streaming_llm(**kwargs) -> ChatOllama:
    """Get a streaming LLM instance for the RESPOND node."""
    return ChatOllama(
        model=settings.MODEL_NAME,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=kwargs.get("max_tokens", 1024),
        think=False,
    )
