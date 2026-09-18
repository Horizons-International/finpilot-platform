import pytest

from app.rag.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    TextChunk,
    chunk_text,
)


def test_chunk_text_returns_empty_list_for_empty_text():
    assert chunk_text("") == []


def test_chunk_text_returns_empty_list_for_whitespace():
    assert chunk_text("   \n\t   ") == []


def test_chunk_text_normalizes_whitespace():
    result = chunk_text(
        "First   sentence.\n\nSecond\t sentence.",
        chunk_size=100,
        overlap=10,
    )

    assert result == [
        TextChunk(
            index=0,
            content="First sentence. Second sentence.",
        )
    ]


def test_chunk_text_creates_single_chunk_for_short_text():
    text = "This is a short document."

    result = chunk_text(
        text,
        chunk_size=100,
        overlap=20,
    )

    assert len(result) == 1
    assert result[0].index == 0
    assert result[0].content == text


def test_chunk_text_splits_long_text():
    text = "abcdefghijklmnopqrstuvwxyz"

    result = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert len(result) == 3

    assert result[0].index == 0
    assert result[0].content == "abcdefghij"

    assert result[1].index == 1
    assert result[1].content == "ijklmnopqr"

    assert result[2].index == 2
    assert result[2].content == "qrstuvwxyz"


def test_chunk_text_preserves_chunk_indexes():
    text = "abcdefghijklmnopqrstuvwxyz"

    result = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert [chunk.index for chunk in result] == [0, 1, 2]


def test_chunk_text_applies_overlap():
    text = "abcdefghijklmnopqrstuvwxyz"

    result = chunk_text(
        text,
        chunk_size=10,
        overlap=3,
    )

    assert result[0].content[-3:] == result[1].content[:3]
    assert result[1].content[-3:] == result[2].content[:3]


def test_chunk_text_handles_exact_chunk_size():
    text = "abcdefghij"

    result = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert result == [
        TextChunk(
            index=0,
            content="abcdefghij",
        )
    ]


def test_chunk_text_handles_text_just_over_chunk_size():
    text = "abcdefghijk"

    result = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert len(result) == 2
    assert result[0].content == "abcdefghij"
    assert result[1].content == "ijk"


def test_chunk_text_rejects_zero_chunk_size():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text(
            "Some text",
            chunk_size=0,
            overlap=0,
        )


def test_chunk_text_rejects_negative_chunk_size():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text(
            "Some text",
            chunk_size=-1,
            overlap=0,
        )


def test_chunk_text_rejects_negative_overlap():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text(
            "Some text",
            chunk_size=100,
            overlap=-1,
        )


def test_chunk_text_rejects_overlap_equal_to_chunk_size():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text(
            "Some text",
            chunk_size=100,
            overlap=100,
        )


def test_chunk_text_rejects_overlap_greater_than_chunk_size():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text(
            "Some text",
            chunk_size=100,
            overlap=101,
        )


def test_default_chunk_configuration_is_valid():
    assert DEFAULT_CHUNK_SIZE > 0
    assert DEFAULT_CHUNK_OVERLAP >= 0
    assert DEFAULT_CHUNK_OVERLAP < DEFAULT_CHUNK_SIZE
