"""Pure timing maths for one streamed response. No network, so tests need no mocks."""


def ttft_from_stream_timestamps(request_start: float, chunk_times: list[float]) -> float | None:
    """Seconds from sending the request to the first streamed chunk, or None if none came."""
    if not chunk_times:
        return None
    return chunk_times[0] - request_start


def output_tokens_per_second(output_tokens: int, chunk_times: list[float]) -> float | None:
    """Decode speed: tokens divided by the time between first and last chunk.

    The wait for the first token is left out on purpose; it is the TTFT metric. This is an
    APPROXIMATE streaming rate: a chunk can hold several tokens and the tokens of the first
    chunk are counted although the span starts after it. Compare sides with that in mind.
    Returns None when the stream had fewer than two chunks or took no time.
    """
    if len(chunk_times) < 2:
        return None
    span = chunk_times[-1] - chunk_times[0]
    if span <= 0:
        return None
    return output_tokens / span
