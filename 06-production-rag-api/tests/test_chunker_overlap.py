import pytest
from rag.chunk import chunk


def words(n):
    return " ".join(f"w{i}" for i in range(n))


def test_chunks_overlap_by_the_requested_words():
    parts = chunk(words(2000), size=800, overlap=120)
    first, second = parts[0].split(), parts[1].split()
    assert len(first) == 800
    assert first[-120:] == second[:120]


def test_every_word_is_covered():
    text = words(1000)
    joined = chunk(text, size=300, overlap=50)
    assert joined[-1].split()[-1] == "w999"


def test_short_text_is_one_chunk():
    assert chunk("a b c", size=800, overlap=120) == ["a b c"]


def test_empty_text_has_no_chunks():
    assert chunk("   ") == []


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk("a b c", size=10, overlap=10)
