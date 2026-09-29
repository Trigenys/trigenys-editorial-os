from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import math
import re

from editorial_os_api.domain.enums import TopicDecision
from editorial_os_api.editorial_intelligence.contracts import (
    ScoreBreakdown,
    SignalDocument,
    VerticalIntelligencePolicy,
)

_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "de",
        "des",
        "du",
        "en",
        "et",
        "for",
        "from",
        "in",
        "is",
        "la",
        "le",
        "les",
        "of",
        "on",
        "the",
        "to",
        "un",
        "une",
        "with",
    }
)


def tokenize(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in (match.group(0).casefold() for match in _TOKEN_RE.finditer(text))
        if len(token) >= 3 and token not in _STOPWORDS
    )


def similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def cluster_documents(
    documents: list[SignalDocument],
    *,
    threshold: float,
) -> list[list[SignalDocument]]:
    remaining = {document.id: document for document in documents}
    clusters: list[list[SignalDocument]] = []

    while remaining:
        seed_id = min(remaining, key=str)
        cluster = [remaining.pop(seed_id)]
        expanded = True

        while expanded:
            expanded = False
            cluster_texts = [_document_text(document) for document in cluster]
            for candidate_id, candidate in list(remaining.items()):
                candidate_text = _document_text(candidate)
                if any(
                    similarity(candidate_text, cluster_text) >= threshold
                    for cluster_text in cluster_texts
                ):
                    cluster.append(remaining.pop(candidate_id))
                    expanded = True

        clusters.append(sorted(cluster, key=lambda item: str(item.id)))

    return clusters


def cluster_key(documents: list[SignalDocument]) -> str:
    token_counts: Counter[str] = Counter()
    for document in documents:
        token_counts.update(tokenize(_document_text(document)))

    minimum_occurrences = max(1, math.ceil(len(documents) / 2))
    consensus = sorted(
        token for token, count in token_counts.items() if count >= minimum_occurrences
    )
    if not consensus:
        consensus = sorted(tokenize(_document_text(documents[0])))

    digest = sha256("|".join(consensus).encode("utf-8")).hexdigest()
    return f"topic:{digest}"


def representative_title(documents: list[SignalDocument]) -> str:
    ranked = sorted(
        documents,
        key=lambda item: (-len(tokenize(item.title)), item.title.casefold(), str(item.id)),
    )
    return ranked[0].title.strip()


def score_cluster(
    documents: list[SignalDocument],
    *,
    policy: VerticalIntelligencePolicy,
    recent_topics: list[tuple[str, str]],
    now: datetime,
) -> ScoreBreakdown:
    key = cluster_key(documents)
    title = representative_title(documents)
    reasons: list[str] = []

    novelty = 100
    if any(recent_key == key for recent_key, _ in recent_topics):
        novelty = 15
        reasons.append("DUPLICATE_RECENT_TOPIC")
    else:
        max_recent_similarity = max(
            (similarity(title, recent_title) for _, recent_title in recent_topics),
            default=0.0,
        )
        if max_recent_similarity >= policy.cluster_similarity_threshold:
            novelty = 35
            reasons.append("SIMILAR_RECENT_TOPIC")
        else:
            reasons.append("NOVEL_TOPIC")

    combined_text = " ".join(_document_text(document) for document in documents).casefold()
    blocked = [term for term in policy.blocked_terms if term.casefold() in combined_text]
    if blocked:
        relevance = 0
        reasons.append("BLOCKED_VERTICAL_TERM")
    elif policy.priority_terms:
        matches = [
            term for term in policy.priority_terms if term.casefold() in combined_text
        ]
        if matches:
            relevance = min(
                100,
                round(40 + 60 * (len(matches) / len(policy.priority_terms))),
            )
            reasons.append("VERTICAL_PRIORITY_MATCH")
        else:
            relevance = 20
            reasons.append("LOW_VERTICAL_RELEVANCE")
    else:
        relevance = 70
        reasons.append("VERTICAL_ELIGIBLE")

    source_count = len({document.source_id for document in documents})
    source_diversity = min(100, 50 + 25 * max(0, source_count - 1))
    if source_count > 1:
        reasons.append("CROSS_SOURCE_CLUSTER")
    else:
        reasons.append("SINGLE_SOURCE_CLUSTER")

    newest = max(
        _effective_time(document)
        for document in documents
    )
    stale = (now - newest).total_seconds() > policy.thresholds.stale_after_hours * 3600
    if stale:
        reasons.append("STALE_SIGNAL")

    weights = policy.weights
    total_weight = weights.novelty + weights.relevance + weights.source_diversity
    composite = round(
        (
            novelty * weights.novelty
            + relevance * weights.relevance
            + source_diversity * weights.source_diversity
        )
        / total_weight
    )

    return ScoreBreakdown(
        novelty=novelty,
        relevance=relevance,
        source_diversity=source_diversity,
        composite=composite,
        stale=stale,
        reason_codes=reasons,
    )


def decide(
    score: ScoreBreakdown,
    *,
    policy: VerticalIntelligencePolicy,
) -> TopicDecision:
    if "BLOCKED_VERTICAL_TERM" in score.reason_codes:
        return TopicDecision.IGNORE
    if "DUPLICATE_RECENT_TOPIC" in score.reason_codes:
        return (
            TopicDecision.WATCH
            if score.composite >= policy.thresholds.watch_min
            else TopicDecision.IGNORE
        )
    if score.stale:
        return (
            TopicDecision.WATCH
            if score.composite >= policy.thresholds.watch_min
            else TopicDecision.IGNORE
        )
    if score.composite >= policy.thresholds.propose_min:
        return TopicDecision.PROPOSE
    if score.composite >= policy.thresholds.watch_min:
        return TopicDecision.WATCH
    return TopicDecision.IGNORE


def _document_text(document: SignalDocument) -> str:
    return f"{document.title} {document.summary}".strip()


def _effective_time(document: SignalDocument) -> datetime:
    value = document.published_at_iso or document.observed_at_iso
    return datetime.fromisoformat(value)
