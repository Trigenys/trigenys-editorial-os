from __future__ import annotations

import argparse
import json

from editorial_os_api.editorial_intelligence.news_radar import NewsRadarService
from editorial_os_api.persistence.session import get_session_factory


def promote(*, lookback_hours: int, max_clusters: int) -> int:
    result = NewsRadarService(get_session_factory()).promote_recent(
        lookback_hours=lookback_hours,
        max_clusters=max_clusters,
    )
    print(json.dumps(result, indent=2, sort_keys=True))

    proposed = [
        item for item in result["results"] if item.get("decision") == "PROPOSE"
    ]
    print(
        json.dumps(
            {
                "signals": result["signals"],
                "clusters": result["clusters"],
                "created_runs": result["created_runs"],
                "proposed": len(proposed),
                "gate_a_pending": sum(
                    1 for item in proposed if item.get("pending_gate") == "A"
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cluster recent News Scout signals and promote them into "
            "Trigenys Insight editorial candidates."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    promote_parser = subparsers.add_parser(
        "promote",
        help="Cluster, score and create recent editorial candidates.",
    )
    promote_parser.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="Only consider News Scout signals observed within this window.",
    )
    promote_parser.add_argument(
        "--max-clusters",
        type=int,
        default=8,
        help="Maximum number of recent clusters to evaluate.",
    )

    args = parser.parse_args()
    if args.command == "promote":
        return promote(
            lookback_hours=args.lookback_hours,
            max_clusters=args.max_clusters,
        )
    raise AssertionError("argparse returned an unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
