import json
from types import SimpleNamespace as NS

from loadtest.streams import read_gemini_stream, read_gemma_stream


class Clock:
    """Each call returns the next whole second, so chunk times are predictable."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0
        return self.now


def sse(obj):
    return "data: " + json.dumps(obj)


def text_chunk(text):
    return sse({"choices": [{"delta": {"content": text}}]})


USAGE = sse({"choices": [], "usage": {"completion_tokens": 7}})


def test_gemma_success():
    result = read_gemma_stream([text_chunk("a"), text_chunk("b"), USAGE, "data: [DONE]"], 1e9, Clock())
    assert result.ok and result.visible_tokens == 7 and len(result.chunk_times) == 2


def test_gemma_truncated_without_done_is_failure():
    result = read_gemma_stream([text_chunk("a"), USAGE], 1e9, Clock())
    assert not result.ok and "[DONE]" in result.error


def test_gemma_in_stream_error_is_failure_even_with_done():
    lines = [text_chunk("a"), sse({"error": {"message": "boom"}}), "data: [DONE]"]
    result = read_gemma_stream(lines, 1e9, Clock())
    assert not result.ok and "error in stream" in result.error


def test_gemma_no_usage_or_no_text_is_failure():
    assert not read_gemma_stream([text_chunk("a"), "data: [DONE]"], 1e9, Clock()).ok
    assert not read_gemma_stream([USAGE, "data: [DONE]"], 1e9, Clock()).ok


def test_gemma_deadline():
    result = read_gemma_stream([text_chunk("a")], 0.5, Clock())
    assert not result.ok and "deadline" in result.error


def gemini_chunk(text="", finish=None, visible=None, thoughts=None):
    usage = None if visible is None else NS(candidates_token_count=visible, thoughts_token_count=thoughts)
    candidates = [NS(finish_reason=NS(name=finish) if finish else None)]
    return NS(text=text, usage_metadata=usage, candidates=candidates)


def test_gemini_success_counts_thinking_as_billed_not_visible():
    chunks = [gemini_chunk("a"), gemini_chunk("b", "STOP", visible=10, thoughts=30)]
    result = read_gemini_stream(chunks, 1e9, Clock())
    assert result.ok and result.visible_tokens == 10 and result.billed_tokens == 40


def test_gemini_max_tokens_is_ok_but_safety_block_is_not():
    ok = read_gemini_stream([gemini_chunk("a", "MAX_TOKENS", visible=5, thoughts=0)], 1e9, Clock())
    assert ok.ok
    blocked = read_gemini_stream([gemini_chunk("", "SAFETY", visible=0, thoughts=0)], 1e9, Clock())
    assert not blocked.ok


def test_gemini_empty_answer_and_missing_finish_are_failures():
    empty = read_gemini_stream([gemini_chunk("", "STOP", visible=5, thoughts=0)], 1e9, Clock())
    assert not empty.ok and "no visible text" in empty.error
    no_finish = read_gemini_stream([gemini_chunk("a", None, visible=5, thoughts=0)], 1e9, Clock())
    assert not no_finish.ok


def test_gemini_no_candidates_is_failure():
    chunk = NS(text="", usage_metadata=None, candidates=None)
    assert not read_gemini_stream([chunk], 1e9, Clock()).ok
