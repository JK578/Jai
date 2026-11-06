import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from incidentiq.application.model_gateway import (
    ModelFailure,
    ModelGateway,
    ModelPricing,
    ModelRequest,
)
from incidentiq.infrastructure.model_provider import MockModelProvider, OpenAIModelProvider
from pydantic import SecretStr


def payload():
    return {
        "status": "completed",
        "usage": {"input_tokens": 1, "output_tokens": 8},
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Mock response: no inference performed."}
                ],
            }
        ],
    }


def adapter(handler):
    return OpenAIModelProvider(
        SecretStr("test-secret"), "configured-model", transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize(
    "provider", [MockModelProvider(), adapter(lambda request: httpx.Response(200, json=payload()))]
)
def test_shared_provider_contract(provider):
    gateway = ModelGateway(provider, ModelPricing(2, 3), 20000)
    result = gateway.generate(ModelRequest("instructions", "evidence"))
    assert result.text == "Mock response: no inference performed."
    assert (result.input_tokens, result.output_tokens) == (1, 8)
    assert gateway.remaining_microusd == 20000 - 26
    assert "evidence" not in repr(ModelRequest("instructions", "evidence"))
    assert result.text not in repr(result)


def test_openai_wire_contract():
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert json.loads(request.content) == {
            "model": "configured-model",
            "input": "evidence",
            "instructions": "instructions",
            "store": False,
            "max_output_tokens": 64,
        }
        return httpx.Response(200, json=payload())

    ModelGateway(adapter(handler), ModelPricing(1, 1), 20000).generate(
        ModelRequest("instructions", "evidence", 64)
    )


def test_explicit_reasoning_effort():
    def handler(request):
        assert json.loads(request.content)["reasoning"] == {"effort": "none"}
        return httpx.Response(200, json=payload())

    provider = OpenAIModelProvider(
        SecretStr("test-secret"),
        "gpt-5.6-luna",
        reasoning_effort="none",
        transport=httpx.MockTransport(handler),
    )
    ModelGateway(provider, ModelPricing(1, 2), 20000).generate(
        ModelRequest("instructions", "evidence")
    )
    with pytest.raises(ValueError, match="model_reasoning_invalid"):
        OpenAIModelProvider(SecretStr("test-secret"), "gpt-5.6-luna", reasoning_effort="invalid")


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "model_authentication_failed"),
        (403, "model_authentication_failed"),
        (429, "model_rate_limited"),
        (500, "model_unavailable"),
        (302, "model_unavailable"),
    ],
)
def test_errors_sanitized_no_retries(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="test-secret private evidence")

    gateway = ModelGateway(adapter(handler), ModelPricing(1, 1), 20000)
    request = ModelRequest("instructions", "evidence")
    with pytest.raises(ModelFailure, match=f"^{code}$"):
        gateway.generate(request)
    assert len(calls) == 1
    assert gateway.remaining_microusd == 20000 - request.input_allowance - 256


def test_timeout_sanitized_and_reservation_retained():
    def handler(request):
        raise httpx.ReadTimeout("test-secret")

    gateway = ModelGateway(adapter(handler), ModelPricing(1, 1), 20000)
    with pytest.raises(ModelFailure, match="^model_timeout$"):
        gateway.generate(ModelRequest("instructions", "evidence"))
    assert gateway.remaining_microusd < 20000


@pytest.mark.parametrize(
    "body,code",
    [
        ({}, "model_response_invalid"),
        ({"status": "incomplete"}, "model_response_incomplete"),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal"}]}],
            },
            "model_refused",
        ),
        (
            {**payload(), "usage": {"input_tokens": 999999, "output_tokens": 1}},
            "model_response_invalid",
        ),
        (
            {**payload(), "usage": {"input_tokens": True, "output_tokens": 1}},
            "model_response_invalid",
        ),
        ({**payload(), "output": []}, "model_response_invalid"),
    ],
)
def test_malformed_incomplete_and_refusal(body, code):
    gateway = ModelGateway(
        adapter(lambda r: httpx.Response(200, json=body)), ModelPricing(1, 1), 20000
    )
    with pytest.raises(ModelFailure, match=f"^{code}$"):
        gateway.generate(ModelRequest("instructions", "evidence"))


def test_oversize_response():
    gateway = ModelGateway(
        adapter(lambda r: httpx.Response(200, content=b"x" * 262145)), ModelPricing(1, 1), 20000
    )
    with pytest.raises(ModelFailure, match="model_response_invalid"):
        gateway.generate(ModelRequest("instructions", "evidence"))


def test_budget_rejected_before_io_and_concurrent_reservations():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private")

    request = ModelRequest("instructions", "evidence")
    reserved = request.input_allowance + request.max_output_tokens
    gateway = ModelGateway(adapter(handler), ModelPricing(1, 1), reserved)

    def invoke(_):
        try:
            gateway.generate(request)
        except ModelFailure as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(invoke, range(2)))
    assert sorted(codes) == ["model_budget_exceeded", "model_timeout"]
    assert len(calls) == 1
    assert gateway.remaining_microusd == 0


@pytest.mark.parametrize(
    "text,limit",
    [("", 256), ("x" * 16001, 256), ("evidence", 0), ("evidence", 2049), ("evidence", True)],
)
def test_invalid_requests(text, limit):
    with pytest.raises(ValueError):
        ModelRequest("instructions", text, limit)


@pytest.mark.parametrize("rate", [0, -1, True, 0.5])
def test_invalid_pricing(rate):
    with pytest.raises(ValueError):
        ModelPricing(rate, 1)
