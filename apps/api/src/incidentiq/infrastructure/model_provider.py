"""Mock and OpenAI text adapters; no credential or provider exception escapes."""

import json
from time import monotonic

import httpx
from pydantic import SecretStr

from incidentiq.application.model_gateway import ModelFailure, ModelRequest, ModelResult


class MockModelProvider:
    def generate(self, request: ModelRequest) -> ModelResult:
        return ModelResult("Mock response: no inference performed.", 1, 8)


class OpenAIModelProvider:
    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 20,
        *,
        reasoning_effort: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key.get_secret_value().strip() or not model.strip():
            raise ValueError("model_configuration_required")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("model_timeout_invalid")
        if reasoning_effort not in (None, "none", "low", "medium", "high"):
            raise ValueError("model_reasoning_invalid")
        self._reasoning_effort = reasoning_effort
        self._key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._transport = transport

    def generate(self, request: ModelRequest) -> ModelResult:
        try:
            started = monotonic()
            with httpx.Client(
                timeout=self._timeout, trust_env=False, transport=self._transport
            ) as client:
                with client.stream(
                    "POST",
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                    json={
                        "model": self._model,
                        "instructions": request.instructions,
                        "input": request.text,
                        "max_output_tokens": request.max_output_tokens,
                        "store": False,
                        **(
                            {"reasoning": {"effort": self._reasoning_effort}}
                            if self._reasoning_effort is not None
                            else {}
                        ),
                    },
                ) as response:
                    if response.status_code != 200:
                        code = {
                            401: "model_authentication_failed",
                            403: "model_authentication_failed",
                            429: "model_rate_limited",
                        }
                        raise ModelFailure(code.get(response.status_code, "model_unavailable"))
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if monotonic() - started > self._timeout:
                            raise ModelFailure("model_timeout")
                        body.extend(chunk)
                        if len(body) > 262144:
                            raise ModelFailure("model_response_invalid")
            data = json.loads(body)
            if data["status"] != "completed":
                raise ModelFailure("model_response_incomplete")
            parts = []
            for item in data["output"]:
                if item["type"] == "message":
                    for content in item["content"]:
                        if content["type"] == "refusal":
                            raise ModelFailure("model_refused")
                        if content["type"] == "output_text":
                            parts.append(content["text"])
            return ModelResult(
                "\n".join(parts), data["usage"]["input_tokens"], data["usage"]["output_tokens"]
            )
        except ModelFailure:
            raise
        except httpx.TimeoutException:
            raise ModelFailure("model_timeout") from None
        except KeyError, TypeError, ValueError:
            raise ModelFailure("model_response_invalid") from None
        except Exception:
            raise ModelFailure("model_unavailable") from None
