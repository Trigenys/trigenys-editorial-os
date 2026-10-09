from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.pilot import (
    PilotMetricsService,
    seed_approved_sources,
)
from editorial_os_api.scout.news_registry import seed_news_sources


def _json_default(value: object) -> str:
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def seed_sources() -> int:
    seeded = seed_approved_sources(get_session_factory())
    print(
        json.dumps(
            {"seeded_sources": {key: str(value) for key, value in seeded.items()}},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def seed_news() -> int:
    seeded = seed_news_sources(get_session_factory())
    print(
        json.dumps(
            {"seeded_news_sources": {key: str(value) for key, value in seeded.items()}},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def report(run_ids: list[str]) -> int:
    if not run_ids:
        raise SystemExit("report requires at least one --run-id")
    parsed = [UUID(value) for value in run_ids]
    metrics = PilotMetricsService(get_session_factory()).summarize_batch(parsed)
    print(
        json.dumps(
            asdict(metrics),
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trigenys Insight staging-pilot utilities."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "seed-sources",
        help="Idempotently reconcile the approved Insight source registry.",
    )
    subparsers.add_parser(
        "seed-news",
        help="Idempotently reconcile the Trigenys Insight News Scout registry.",
    )
    report_parser = subparsers.add_parser(
        "report",
        help="Emit cost, human-touch, retry and factual-defect metrics for pilot runs.",
    )
    report_parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Workflow run UUID. Repeat for the full pilot batch.",
    )

    args = parser.parse_args()
    if args.command == "seed-sources":
        return seed_sources()
    if args.command == "seed-news":
        return seed_news()
    if args.command == "report":
        return report(args.run_id)
    raise AssertionError("argparse returned an unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
