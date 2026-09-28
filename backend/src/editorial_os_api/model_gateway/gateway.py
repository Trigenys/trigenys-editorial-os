from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from editorial_os_api.model_gateway.budget import BudgetExceededError, BudgetLedger
from editorial_os_api.model_gateway.contracts import (
    BudgetPolicy,
    ModelClient,
    ModelMessage,
    ModelPolicy,
    ModelRequest,
    ModelRole,
)

T = TypeVar("T", bound=BaseModel)


class ModelGatewayError(RuntimeError):
    pass


class StructuredOutputError(ModelGatewayError):
    pass


class ModelGateway:
    def __init__(
        self,
        client: ModelClient,
        *,
        model_policy: ModelPolicy,
        budget_policy: BudgetPolicy,
        budget_ledger: BudgetLedger,
        max_repair_attempts: int = 1,
    ) -> None:
        if max_repair_attempts < 0 or max_repair_attempts > 2:
            raise ValueError("max_repair_attempts must be between 0 and 2.")
        self._client = client
        self._model_policy = model_policy
        self._budget_policy = budget_policy
        self._budget_ledger = budget_ledger
        self._max_repair_attempts = max_repair_attempts

    def generate_structured(
        self,
        request: ModelRequest,
        schema: type[T],
        *,
        call_key: str,
    ) -> T:
        if len(call_key) > 220:
            raise ValueError("call_key must be at most 220 characters.")

        route = self._model_policy.route_for(request.task)
        schema_json = cast(dict[str, object], schema.model_json_schema())
        current_request = request
        last_error: ValidationError | None = None

        for attempt in range(self._max_repair_attempts + 1):
            attempt_key = call_key if attempt == 0 else f"{call_key}:repair:{attempt}"
            response = self._call(
                current_request,
                route_name=route.name,
                call_key=attempt_key,
                json_schema=schema_json,
            )

            try:
                return schema.model_validate_json(response)
            except ValidationError as exc:
                last_error = exc
                if attempt >= self._max_repair_attempts:
                    break
                current_request = self._repair_request(
                    request,
                    invalid_output=response,
                    validation_error=exc,
                    schema_json=schema_json,
                )

        assert last_error is not None
        raise StructuredOutputError(
            "Model output remained invalid after "
            f"{self._max_repair_attempts} repair attempt(s): {last_error}"
        ) from last_error

    def generate_text(
        self,
        request: ModelRequest,
        *,
        call_key: str,
    ) -> str:
        if len(call_key) > 220:
            raise ValueError("call_key must be at most 220 characters.")

        route = self._model_policy.route_for(request.task)
        return self._call(
            request,
            route_name=route.name,
            call_key=call_key,
            json_schema=None,
        )

    def _call(
        self,
        request: ModelRequest,
        *,
        route_name: str,
        call_key: str,
        json_schema: dict[str, object] | None,
    ) -> str:
        route = self._model_policy.route_for(request.task)
        if route.name != route_name:
            raise RuntimeError("Model route changed during one gateway call.")

        self._budget_ledger.reserve(
            request,
            route,
            call_key=call_key,
            policy=self._budget_policy,
        )

        try:
            response = self._client.complete(
                request,
                route,
                json_schema=json_schema,
            )
        except Exception as exc:
            self._budget_ledger.fail(
                request.workflow_run_id,
                call_key=call_key,
                error=exc,
            )
            raise ModelGatewayError(
                f"Model provider call failed for route {route.name!r}."
            ) from exc

        completion = self._budget_ledger.complete(
            request.workflow_run_id,
            call_key=call_key,
            response=response,
            policy=self._budget_policy,
        )
        if not completion.within_budget:
            raise BudgetExceededError(
                "Model call completed above configured budget ceiling; "
                "output was withheld from the caller."
            )
        return response.content

    @staticmethod
    def _repair_request(
        original: ModelRequest,
        *,
        invalid_output: str,
        validation_error: ValidationError,
        schema_json: dict[str, object],
    ) -> ModelRequest:
        repair_messages = [
            *original.messages,
            ModelMessage(role=ModelRole.ASSISTANT, content=invalid_output),
            ModelMessage(
                role=ModelRole.SYSTEM,
                content=(
                    "The previous response did not satisfy the required JSON schema. "
                    "Return corrected JSON only. Do not add prose or markdown."
                ),
            ),
            ModelMessage(
                role=ModelRole.USER,
                content=(
                    f"Schema: {schema_json}\n"
                    f"Validation errors: {validation_error.errors(include_url=False)}"
                ),
            ),
        ]
        return original.model_copy(update={"messages": repair_messages})
