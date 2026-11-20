"""Read one streamed answer from each provider and decide if it really completed.

A request only counts as ok when the stream ended properly, showed visible text, and
reported token usage. In-stream errors, a missing [DONE], an empty answer and a blocked
Gemini answer are failures, not fast successes. Pure functions: tests feed them fake streams.
"""

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

# MAX_TOKENS is fine: the test caps the answer length on purpose.
GEMINI_OK_FINISH = {"STOP", "MAX_TOKENS"}
GEMMA_OK_FINISH = {"stop", "length"}


TAGS = re.compile(r"category:\s*\w+.*urgency:\s*(low|medium|high)\b", re.IGNORECASE | re.DOTALL)


def has_valid_tags(text: str) -> bool:
    """The prompt asks for "Category: <word>. Urgency: <low, medium or high>". Anything else is not a tagged ticket."""
    return TAGS.search(text) is not None


@dataclass
class StreamResult:
    ok: bool = False
    error: str | None = None
    chunk_times: list[float] = field(default_factory=list)
    visible_tokens: int = 0  # tokens the client saw; used for decode speed
    billed_tokens: int = 0  # tokens the provider bills as output; used for cost
    status: str = ""  # HTTP or SDK status code when the call failed, so 429s show in the CSV


def _fail(result: StreamResult, message: str) -> StreamResult:
    result.ok = False
    result.error = message
    return result


def read_gemma_stream(
    lines: Iterable[str], deadline: float, clock: Callable[[], float] = time.perf_counter
) -> StreamResult:
    """Parse OpenAI-style server-sent events from vLLM."""
    result = StreamResult()
    saw_done = False
    finish = None
    text = []
    for line in lines:
        if clock() > deadline:
            return _fail(result, "stream deadline exceeded")
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            saw_done = True
            break
        try:
            payload = json.loads(data)
        except ValueError:
            return _fail(result, "bad JSON in stream")
        if "error" in payload:
            return _fail(result, f"error in stream: {payload['error']}")
        if payload.get("usage"):
            result.visible_tokens = result.billed_tokens = payload["usage"]["completion_tokens"]
        for choice in payload.get("choices", []):
            content = choice.get("delta", {}).get("content")
            if content:
                result.chunk_times.append(clock())
                text.append(content)
            finish = choice.get("finish_reason") or finish
    if not saw_done:
        return _fail(result, "stream ended without [DONE]")
    if finish not in GEMMA_OK_FINISH:
        return _fail(result, f"finish reason {finish}")
    if not result.chunk_times:
        return _fail(result, "no visible text")
    if result.visible_tokens <= 0:
        return _fail(result, "no usage in stream")
    if not has_valid_tags("".join(text)):
        return _fail(result, "answer has no category and urgency")
    result.ok = True
    return result


def read_gemini_stream(
    chunks: Iterable, deadline: float, clock: Callable[[], float] = time.perf_counter
) -> StreamResult:
    """Read google-genai streaming chunks. Billed tokens include thinking tokens."""
    result = StreamResult()
    finish = None
    text = []
    for chunk in chunks:
        if clock() > deadline:
            return _fail(result, "stream deadline exceeded")
        if chunk.text:
            result.chunk_times.append(clock())
            text.append(chunk.text)
        usage = chunk.usage_metadata
        if usage:
            visible = usage.candidates_token_count or 0
            result.visible_tokens = visible
            result.billed_tokens = visible + (usage.thoughts_token_count or 0)
        for candidate in chunk.candidates or []:
            if candidate.finish_reason is not None:
                finish = getattr(candidate.finish_reason, "name", str(candidate.finish_reason))
    if finish not in GEMINI_OK_FINISH:
        return _fail(result, f"finish reason {finish}")
    if not result.chunk_times:
        return _fail(result, "no visible text")
    if result.billed_tokens <= 0:
        return _fail(result, "no usage in stream")
    if not has_valid_tags("".join(text)):
        return _fail(result, "answer has no category and urgency")
    result.ok = True
    return result
