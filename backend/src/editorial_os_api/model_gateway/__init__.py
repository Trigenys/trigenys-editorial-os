"""Provider-agnostic model gateway."""

from editorial_os_api.model_gateway.budget import (
    BudgetExceededError,
    BudgetLedger,
    DuplicateModelCallError,
)
from editorial_os_api.model_gateway.contracts import (
    BudgetPolicy,
    ModelClient,
    ModelMessage,
    ModelPolicy,
    ModelRequest,
    ModelRole,
    ModelRoute,
    ModelTask,
    RawModelResponse,
)
from editorial_os_api.model_gateway.gateway import (
    ModelGateway,
    ModelGatewayError,
    StructuredOutputError,
)

__all__ = [
    "BudgetExceededError",
    "BudgetLedger",
    "BudgetPolicy",
    "DuplicateModelCallError",
    "ModelClient",
    "ModelGateway",
    "ModelGatewayError",
    "ModelMessage",
    "ModelPolicy",
    "ModelRequest",
    "ModelRole",
    "ModelRoute",
    "ModelTask",
    "RawModelResponse",
    "StructuredOutputError",
]
