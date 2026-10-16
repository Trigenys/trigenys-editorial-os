from pathlib import Path
from typing import Any

import pytest

from scripts.news_scout import _summarize_results, _write_github_summary


def test_partial_source_timeout_keeps_radar_unblocked() -> None:
    results: dict[str, dict[str, Any]] = {
        "reuters": {"status": "SUCCEEDED", "created_count": 53, "updated_count": 7},
        "techcabal": {"status": "SUCCEEDED", "created_count": 5, "updated_count": 5},
        "bleeping-computer": {
            "status": "SUCCEEDED",
            "created_count": 3,
            "updated_count": 12,
        },
        "techcentral": {"status": "SUCCEEDED", "created_count": 2, "updated_count": 18},
        "nairametrics": {
            "status": "FAILED",
            "failure_kind": "TIMEOUT",
            "retryable": True,
        },
    }

    summary = _summarize_results(results)

    assert summary["status"] == "DEGRADED"
    assert summary["succeeded_sources"] == 4
    assert summary["failed_sources"] == 1
    assert summary["created_items"] == 63
    assert summary["updated_items"] == 42
    assert summary["failures"] == [
        {"source": "nairametrics", "kind": "TIMEOUT", "retryable": True}
    ]


def test_all_attempted_sources_failing_is_fatal_even_with_skips() -> None:
    summary = _summarize_results(
        {
            "nairametrics": {"status": "FAILED", "failure_kind": "TIMEOUT"},
            "reuters": {"status": "SKIPPED", "skipped_reason": "backoff"},
        }
    )

    assert summary["status"] == "FAILED"
    assert summary["succeeded_sources"] == 0
    assert summary["failed_sources"] == 1
    assert summary["skipped_sources"] == 1


def test_all_skipped_sources_are_not_an_error() -> None:
    summary = _summarize_results(
        {
            "reuters": {"status": "SKIPPED", "skipped_reason": "backoff"},
            "techcabal": {"status": "SKIPPED", "skipped_reason": "paused"},
        }
    )

    assert summary["status"] == "SKIPPED"


def test_success_with_zero_new_items_is_still_success() -> None:
    summary = _summarize_results({"reuters": {"status": "SUCCEEDED", "created_count": 0}})

    assert summary["status"] == "SUCCEEDED"
    assert summary["created_items"] == 0


def test_github_summary_reports_partial_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    summary = _summarize_results(
        {
            "techcabal": {"status": "SUCCEEDED", "created_count": 2},
            "nairametrics": {
                "status": "FAILED",
                "failure_kind": "TIMEOUT",
                "retryable": True,
            },
        }
    )

    _write_github_summary(summary)

    markdown = summary_file.read_text(encoding="utf-8")
    assert "**DEGRADED**" in markdown
    assert "Items created: 2" in markdown
    assert "nairametrics" in markdown
    assert "TIMEOUT" in markdown
    assert "::warning title=News Scout source failure::" in capsys.readouterr().out
