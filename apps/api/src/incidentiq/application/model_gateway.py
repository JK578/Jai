"""Provider-independent text inference and process-local cost reservations."""

from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol


class ModelFailure(Exception):
    """Fixed safe code; never include provider exception text."""


@dataclass(frozen=True)
class ModelRequest:
    instructions: str = field(repr=False)
    text: str = field(repr=False)
    max_output_tokens: int = 256

    def __post_init__(self) -> None:
        if not self.instructions.strip() or not self.text.strip():
            raise ValueError("model_input_required")
        if len(self.instructions.encode()) + len(self.text.encode()) > 16000:
            raise ValueError("model_input_too_large")
        if type(self.max_output_tokens) is not int or not 16 <= self.max_output_tokens <= 2048:
            raise ValueError("model_output_limit_invalid")

    @property
    def input_allowance(self) -> int:
        return len(self.instructions.encode()) + len(self.text.encode()) + 256


@dataclass(frozen=True)
class ModelResult:
    text: str = field(repr=False)
    input_tokens: int
    output_tokens: int


class ModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> ModelResult: ...


@dataclass(frozen=True)
class ModelPricing:
    # Integer micro-USD per token; round configured provider rates upward.
    input_microusd: int
    output_microusd: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in (self.input_microusd, self.output_microusd)):
            raise ValueError("model_pricing_invalid")

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        return input_tokens * self.input_microusd + output_tokens * self.output_microusd


class ModelGateway:
    def __init__(self, provider: ModelProvider, pricing: ModelPricing, budget_microusd: int):
        if type(budget_microusd) is not int or budget_microusd <= 0:
            raise ValueError("model_budget_invalid")
        self._provider = provider
        self._pricing = pricing
        self._remaining = budget_microusd
        self._lock = Lock()

    @property
    def remaining_microusd(self) -> int:
        with self._lock:
            return self._remaining

    def generate(self, request: ModelRequest) -> ModelResult:
        reserved = self._pricing.cost(request.input_allowance, request.max_output_tokens)
        with self._lock:
            if reserved > self._remaining:
                raise ModelFailure("model_budget_exceeded")
            self._remaining -= reserved
        # Unknown billing after errors: keep the reservation. Never automatically retry.
        try:
            result = self._provider.generate(request)
            if (
                not isinstance(result.text, str)
                or not result.text.strip()
                or len(result.text.encode()) > 65536
                or type(result.input_tokens) is not int
                or type(result.output_tokens) is not int
                or not 0 <= result.input_tokens <= request.input_allowance
                or not 0 <= result.output_tokens <= request.max_output_tokens
            ):
                raise ModelFailure("model_response_invalid")
        except ModelFailure:
            raise
        except Exception:
            raise ModelFailure("model_unavailable") from None
        actual = self._pricing.cost(result.input_tokens, result.output_tokens)
        with self._lock:
            self._remaining += reserved - actual
        return result
