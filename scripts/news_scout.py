from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import select

from editorial_os_api.domain.enums import SourceKind
from editorial_os_api.persistence.models import Source
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.scout import ScoutAgent
from editorial_os_api.scout.adapters.feed import RssAtomAdapter
from editorial_os_api.scout.adapters.sitemap import NewsSitemapAdapter
from editorial_os_api.scout.news_registry import NEWS_REGISTRY_ID, seed_news_sources

CANARY_SOURCE_KEYS = (
    "digital-business-africa",
    "ecomatin",
    "techcabal",
    "reuters",
    "bleeping-computer",
)


def _json_default(value: object) -> str:
    return str(value)


def _adapter_for(source: Source):
    mode = str(source.config.get("collection_mode") or "")
    kind = SourceKind(source.kind)
    if kind in {SourceKind.RSS, SourceKind.ATOM}:
        return RssAtomAdapter()
    if mode == "news-sitemap":
        return NewsSitemapAdapter()
    raise RuntimeError(
        f"Source {source.config.get('source_key') or source.name} has no supported "
        f"News Scout transport (kind={kind.value}, mode={mode or 'none'})."
    )


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

    print(json.dumps({"results": results}, indent=2, sort_keys=True, default=_json_default))
    failed = [key for key, result in results.items() if result["status"] == "FAILED"]
    return 1 if failed else 0


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
