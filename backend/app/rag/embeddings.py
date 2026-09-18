from openai import OpenAI

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.core.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class EmbeddingService:
    def __init__(self) -> None:
        if settings.AI_PROVIDER.lower() != "openai":
            raise AIConfigurationError("OpenAI provider is required for embeddings.")

        if not settings.AI_API_KEY:
            raise AIConfigurationError("AI_API_KEY is required for embeddings.")

        self.client = OpenAI(
            api_key=settings.AI_API_KEY,
            timeout=settings.AI_TIMEOUT,
        )

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot generate an embedding for empty text.")

        try:
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
        except Exception as exc:
            raise AIProviderError("Failed to generate text embedding.") from exc

        if not response.data:
            raise AIProviderError("Embedding provider returned no data.")

        embedding = response.data[0].embedding

        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise AIProviderError(
                "Embedding dimension does not match the "
                "configured vector dimension (1536)."
            )

        return embedding

    def embed_many(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        if any(not text.strip() for text in texts):
            raise ValueError("Cannot generate embeddings for empty text.")

        try:
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
        except Exception as exc:
            raise AIProviderError("Failed to generate text embeddings.") from exc

        embeddings = sorted(
            response.data,
            key=lambda item: item.index,
        )

        if len(embeddings) != len(texts):
            raise AIProviderError(
                "Embedding provider returned an unexpected number of embeddings."
            )

        result = [item.embedding for item in embeddings]

        for embedding in result:
            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise AIProviderError(
                    "Embedding dimension does not match the "
                    "configured vector dimension (1536)."
                )

        return result

    def embed_query(self, query: str) -> list[float]:
        """
        Generate an embedding for a user retrieval query.

        This method intentionally uses the same embedding model
        and dimensionality as document indexing.
        """
        if not query.strip():
            raise ValueError("Cannot generate an embedding for an empty query.")

        return self.embed(query)
