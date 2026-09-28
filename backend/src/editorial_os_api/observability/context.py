from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from uuid import UUID


@dataclass(frozen=True)
class CorrelationContext:
    request_id: str | None = None
    workflow_run_id: UUID | None = None
    agent_id: str | None = None
    call_key: str | None = None

    @property
    def correlation_id(self) -> str | None:
        if self.workflow_run_id is not None:
            return str(self.workflow_run_id)
        return self.request_id


_CONTEXT: ContextVar[CorrelationContext] = ContextVar(
    "editorial_os_correlation",
    default=CorrelationContext(),
)


def current_correlation() -> CorrelationContext:
    return _CONTEXT.get()


@contextmanager
def bind_correlation(
    *,
    request_id: str | None = None,
    workflow_run_id: UUID | None = None,
    agent_id: str | None = None,
    call_key: str | None = None,
) -> Iterator[CorrelationContext]:
    current = current_correlation()
    updated = replace(
        current,
        request_id=request_id if request_id is not None else current.request_id,
        workflow_run_id=(
            workflow_run_id if workflow_run_id is not None else current.workflow_run_id
        ),
        agent_id=agent_id if agent_id is not None else current.agent_id,
        call_key=call_key if call_key is not None else current.call_key,
    )
    token = _CONTEXT.set(updated)
    try:
        yield updated
    finally:
        _CONTEXT.reset(token)
