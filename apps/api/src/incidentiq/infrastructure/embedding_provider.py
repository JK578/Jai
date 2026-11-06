"""Bounded OpenAI embeddings; explicit budget, no retries, no raw exception output."""

import json
from threading import Lock
from time import monotonic

import httpx
from pydantic import SecretStr

from incidentiq.domain.retrieval import RetrievalFailure, normalized


class OpenAIEmbeddingProvider:
    model = "text-embedding-3-small"
    dimensions = 512

    def __init__(
        self,
        api_key: SecretStr,
        budget_microusd: int = 20000,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key.get_secret_value().strip():
            raise ValueError("embedding_key_required")
        if type(budget_microusd) is not int or not 0 < budget_microusd <= 100000:
            raise ValueError("embedding_budget_invalid")
        self._key, self._transport = api_key, transport
        self._remaining = budget_microusd
        self._lock = Lock()

    @property
    def remaining_microusd(self) -> int:
        with self._lock:
            return self._remaining

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not 1 <= len(texts) <= 16 or any(
            not text.strip() or len(text.encode()) > 8000 for text in texts
        ):
            raise ValueError("embedding_input_invalid")
        # Conservative 1 micro-USD/token; byte count upper allowance for text tokens.
        reserved = sum(len(text.encode()) for text in texts)
        with self._lock:
            if reserved > self._remaining:
                raise RetrievalFailure("embedding_budget_exceeded")
            self._remaining -= reserved
        try:
            started = monotonic()
            with httpx.Client(timeout=20, trust_env=False, transport=self._transport) as client:
                with client.stream(
                    "POST",
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                    json={
                        "model": self.model,
                        "dimensions": self.dimensions,
                        "input": texts,
                        "encoding_format": "float",
                    },
                ) as response:
                    if response.status_code != 200:
                        codes = {
                            401: "embedding_authentication_failed",
                            403: "embedding_authentication_failed",
                            429: "embedding_rate_limited",
                        }
                        raise RetrievalFailure(
                            codes.get(response.status_code, "embedding_unavailable")
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if monotonic() - started > 20:
                            raise RetrievalFailure("embedding_timeout")
                        body.extend(chunk)
                        if len(body) > 524288:
                            raise RetrievalFailure("embedding_invalid")
            data = json.loads(body)
            if data["model"] != self.model or len(data["data"]) != len(texts):
                raise RetrievalFailure("embedding_invalid")
            indexed = {}
            for item in data["data"]:
                index = item["index"]
                if type(index) is not int or not 0 <= index < len(texts) or index in indexed:
                    raise RetrievalFailure("embedding_invalid")
                indexed[index] = normalized(tuple(item["embedding"]), self.dimensions)
            used = data["usage"]["total_tokens"]
            if type(used) is not int or not 0 <= used <= reserved:
                raise RetrievalFailure("embedding_invalid")
        except RetrievalFailure:
            raise
        except httpx.TimeoutException:
            raise RetrievalFailure("embedding_timeout") from None
        except KeyError, ValueError, TypeError:
            raise RetrievalFailure("embedding_invalid") from None
        except Exception:
            raise RetrievalFailure("embedding_unavailable") from None
        with self._lock:
            self._remaining += reserved - used
        return [indexed[i] for i in range(len(texts))]
