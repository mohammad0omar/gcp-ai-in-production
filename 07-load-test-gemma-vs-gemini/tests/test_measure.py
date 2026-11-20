import pytest
from loadtest.measure import output_tokens_per_second, ttft_from_stream_timestamps


def test_ttft_from_stream_timestamps():
    # Request sent at t=10.0, chunks arrive at 10.4, 10.5, 11.4.
    assert ttft_from_stream_timestamps(10.0, [10.4, 10.5, 11.4]) == pytest.approx(0.4)


def test_ttft_is_none_when_no_chunk_arrived():
    assert ttft_from_stream_timestamps(10.0, []) is None


def test_tokens_per_second_ignores_the_wait_for_first_token():
    # 100 tokens between the first chunk (10.4) and the last (11.4) is 100 per second.
    assert output_tokens_per_second(100, [10.4, 10.5, 11.4]) == pytest.approx(100.0)


def test_tokens_per_second_none_for_single_chunk():
    assert output_tokens_per_second(5, [10.4]) is None
