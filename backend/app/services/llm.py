"""Centralized LLM utilities: retry logic, cost tracking, shared client."""

import asyncio
import time
from dataclasses import dataclass, field
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from app.config import settings

# ── Cost tracking ──────────────────────────────────────────────────────

# Sonnet pricing per 1M tokens (as of 2025)
_INPUT_COST_PER_M = 3.00    # $3 / 1M input tokens
_OUTPUT_COST_PER_M = 15.00  # $15 / 1M output tokens


@dataclass
class UsageStats:
    """Cumulative API usage stats for this server session."""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_errors: int = 0
    total_retries: int = 0
    calls_by_node: dict = field(default_factory=dict)

    @property
    def estimated_cost(self) -> float:
        return (
            self.total_input_tokens * _INPUT_COST_PER_M / 1_000_000
            + self.total_output_tokens * _OUTPUT_COST_PER_M / 1_000_000
        )

    def record(self, node: str, input_tokens: int, output_tokens: int):
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        if node not in self.calls_by_node:
            self.calls_by_node[node] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.calls_by_node[node]["calls"] += 1
        self.calls_by_node[node]["input_tokens"] += input_tokens
        self.calls_by_node[node]["output_tokens"] += output_tokens

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(self.estimated_cost, 4),
            "total_errors": self.total_errors,
            "total_retries": self.total_retries,
            "by_node": dict(self.calls_by_node),
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
    """Invoke Claude with automatic retry on transient errors.

    Returns the response text. Tracks usage and cost automatically.
    """
    llm = ChatAnthropic(
        model=settings.MODEL_NAME,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
    )

    last_error = None
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            response = await llm.ainvoke(messages)
            elapsed = time.time() - t0

            # Extract token usage from response metadata
            meta = getattr(response, "response_metadata", {}) or {}
            token_usage = meta.get("usage", {})
            input_tokens = token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("output_tokens", 0)

            usage.record(node, input_tokens, output_tokens)
            print(
                f"[llm] {node}: {input_tokens}in/{output_tokens}out "
                f"(${usage.estimated_cost:.4f} total) [{elapsed:.1f}s]"
            )

            return response.content if isinstance(response.content, str) else str(response.content)

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Retry on rate limits and server errors
            is_retryable = any(
                keyword in error_str
                for keyword in ["rate_limit", "overloaded", "529", "500", "503", "timeout", "connection"]
            )

            if is_retryable and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                usage.total_retries += 1
                print(f"[llm] {node}: Retry {attempt + 1}/{max_retries} after {delay:.1f}s — {e}")
                await asyncio.sleep(delay)
            else:
                usage.total_errors += 1
                raise

    # Should not reach here, but just in case
    raise last_error  # type: ignore


def get_streaming_llm(**kwargs) -> ChatAnthropic:
    """Get a streaming LLM instance for the RESPOND node."""
    return ChatAnthropic(
        model=settings.MODEL_NAME,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=kwargs.get("max_tokens", 1024),
        streaming=True,
    )
