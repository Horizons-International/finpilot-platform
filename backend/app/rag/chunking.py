from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    if not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0:
        raise ValueError("overlap cannot be negative.")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    normalized_text = " ".join(text.split())

    chunks: list[TextChunk] = []

    start = 0
    chunk_index = 0

    while start < len(normalized_text):
        end = min(
            start + chunk_size,
            len(normalized_text),
        )

        chunk = normalized_text[start:end].strip()

        if chunk:
            chunks.append(
                TextChunk(
                    index=chunk_index,
                    content=chunk,
                )
            )

            chunk_index += 1

        if end >= len(normalized_text):
            break

        start = end - overlap

    return chunks
