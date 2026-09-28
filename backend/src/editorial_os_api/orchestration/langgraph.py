from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from editorial_os_api.orchestration.engine import WorkflowEngine
from editorial_os_api.orchestration.models import GateResume


class GateGraphState(TypedDict, total=False):
    run_id: str
    result: dict[str, object]


def checkpoint_uri_from_sqlalchemy_url(database_url: str) -> str:
    """Convert our SQLAlchemy URL to a psycopg URI isolated in the langgraph schema."""

    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    parts = urlsplit(normalized)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = "-csearch_path=langgraph,public"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


@contextmanager
def postgres_checkpointer(database_url: str) -> Iterator[PostgresSaver]:
    """Open a production-grade checkpointer and reconcile its internal tables."""

    uri = checkpoint_uri_from_sqlalchemy_url(database_url)
    with PostgresSaver.from_conn_string(uri) as saver:
        saver.setup()
        yield saver


class LangGraphGateCoordinator:
    """Thin LangGraph adapter; canonical state remains owned by WorkflowEngine."""

    def __init__(self, engine: WorkflowEngine, checkpointer: Any) -> None:
        self._engine = engine
        builder = StateGraph(GateGraphState)
        builder.add_node("human_gate", self._human_gate)
        builder.add_edge(START, "human_gate")
        builder.add_edge("human_gate", END)
        self._graph: Any = builder.compile(checkpointer=checkpointer)

    @staticmethod
    def _config(workflow_run_id: UUID) -> dict[str, dict[str, str]]:
        return {
            "configurable": {
                "thread_id": f"workflow:{workflow_run_id}",
            }
        }

    def pause_for_gate(self, workflow_run_id: UUID) -> dict[str, Any]:
        return self._graph.invoke(
            {"run_id": str(workflow_run_id)},
            config=self._config(workflow_run_id),
        )

    def resume_gate(
        self,
        workflow_run_id: UUID,
        resume: GateResume,
    ) -> dict[str, Any]:
        return self._graph.invoke(
            Command(resume=resume.model_dump(mode="json")),
            config=self._config(workflow_run_id),
        )

    def _human_gate(self, state: GateGraphState) -> dict[str, object]:
        workflow_run_id = UUID(state["run_id"])
        gate = self._engine.pending_gate(workflow_run_id)

        if gate is None:
            return {
                "result": {
                    "workflow_run_id": str(workflow_run_id),
                    "pending_gate": None,
                }
            }

        raw_resume = interrupt(
            {
                "type": "editorial_gate",
                "workflow_run_id": str(workflow_run_id),
                "gate": gate.value,
            }
        )
        resume = GateResume.model_validate(raw_resume)
        result = self._engine.decide_gate(workflow_run_id, gate, resume)
        result_payload = result.model_dump(mode="json")
        return {"result": result_payload}
