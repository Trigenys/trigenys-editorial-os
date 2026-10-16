# ruff: noqa: I001
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select

from editorial_os_api.domain.enums import SourceKind
from editorial_os_api.persistence.models import Source
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.scout import ScoutAgent
from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.adapters.listing import ListingPageAdapter
from editorial_os_api.scout.adapters.sitemap import NewsSitemapAdapter
from editorial_os_api.scout.contracts import SourceAdapter
from editorial_os_api.scout.news_registry import NEWS_REGISTRY_ID, seed_news_sources

CANARY_SOURCE_KEYS = (
    "techcabal",
    "techcentral",
    "nairametrics",
    "reuters",
    "bleeping-computer",
)


def _json_default(value: object) -> str:
    return str(value)


def _adapter_for(source: Source) -> SourceAdapter:
    mode = str(source.config.get("collection_mode") or "")
    kind = SourceKind(source.kind)
    if kind in {SourceKind.RSS, SourceKind.ATOM}:
        return RssAtomAdapter()
    if mode == "news-sitemap":
        return NewsSitemapAdapter()
    if mode == "listing-page":
        return ListingPageAdapter()
    raise RuntimeError(
        f"Source {source.config.get('source_key') or source.name} has no supported "
        f"News Scout transport (kind={kind.value}, mode={mode or 'none'})."
    )


def _summarize_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    succeeded = [key for key, item in results.items() if item["status"] == "SUCCEEDED"]
    failed = [key for key, item in results.items() if item["status"] == "FAILED"]
    skipped = [key for key, item in results.items() if item["status"] == "SKIPPED"]

    if failed and not succeeded:
        status = "FAILED"
    elif failed:
        status = "DEGRADED"
    elif succeeded:
        status = "SUCCEEDED"
    else:
        status = "SKIPPED"

    return {
        "status": status,
        "succeeded_sources": len(succeeded),
        "failed_sources": len(failed),
        "skipped_sources": len(skipped),
        "created_items": sum(int(item.get("created_count", 0)) for item in results.values()),
        "updated_items": sum(int(item.get("updated_count", 0)) for item in results.values()),
        "failures": [
            {
                "source": key,
                "kind": results[key].get("failure_kind") or "UNKNOWN",
                "retryable": results[key].get("retryable"),
            }
            for key in failed
        ],
    }


def _write_github_summary(summary: dict[str, Any]) -> None:
    for failure in summary["failures"]:
        print(
            "::warning title=News Scout source failure::"
            f"{failure['source']} failed ({failure['kind']}); "
            f"retryable={failure['retryable']}"
        )

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    lines = [
        "### News Scout collection result",
        "",
        f"- Status: **{summary['status']}**",
        f"- Sources succeeded: {summary['succeeded_sources']}",
        f"- Sources failed: {summary['failed_sources']}",
        f"- Sources skipped (paused/backoff/disabled): {summary['skipped_sources']}",
        f"- Items created: {summary['created_items']}",
        f"- Items updated: {summary['updated_items']}",
    ]
    if summary["failures"]:
        lines.extend(["", "**Source failures**"])
        lines.extend(
            f"- `{failure['source']}`: {failure['kind']} "
            f"(retryable: {failure['retryable']})"
            for failure in summary["failures"]
        )
    with Path(summary_file).open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n\n")


def scan(source_keys: list[str], *, force: bool) -> int:
    session_factory = get_session_factory()
    seed_news_sources(session_factory)

    requested = source_keys or list(CANARY_SOURCE_KEYS)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(Source).where(
                    Source.config["registry_id"].astext == NEWS_REGISTRY_ID,
                    Source.config["source_key"].astext.in_(requested),
                )
            )
        )

    by_key = {str(row.config["source_key"]): row for row in rows}
    missing = sorted(set(requested) - set(by_key))
    if missing:
        raise SystemExit(f"Unknown News Scout source keys: {', '.join(missing)}")

    scout = ScoutAgent(session_factory)
    results: dict[str, dict[str, Any]] = {}
    for key in requested:
        source = by_key[key]
        adapter = _adapter_for(source)
        result = scout.ingest(source.id, adapter, force=force)
        results[key] = result.model_dump(mode="json")

    summary = _summarize_results(results)
    print(
        json.dumps(
            {"results": results, "summary": summary},
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )
    _write_github_summary(summary)
    return 1 if summary["status"] == "FAILED" else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Trigenys Insight News Scout from a network-capable Python runtime."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan the five-source canary set or selected News Scout source keys.",
    )
    scan_parser.add_argument(
        "--source-key",
        action="append",
        default=[],
        help="Registry source key. Repeat to scan more than one source.",
    )
    scan_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore source backoff/next-fetch timing for an explicit canary run.",
    )

    args = parser.parse_args()
    if args.command == "scan":
        return scan(args.source_key, force=args.force)
    raise AssertionError("argparse returned an unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
