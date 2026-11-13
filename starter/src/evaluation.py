"""Retrieval evaluation helpers for benchmark Hit@1, Evidence Hit@3, and filter compliance."""

from __future__ import annotations

from typing import Any


def _norm_ws(text: str) -> str:
    """Collapse arbitrary whitespace to single spaces for stable verbatim matching."""
    return " ".join(text.split())


def _gold_candidates(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect the primary gold location/quote plus any pre-locked alternatives."""
    candidates = [
        {
            "source_id": question["gold_source_id"],
            "page": int(question["gold_page"]),
            "evidence_quote": question["evidence_quote"],
        }
    ]
    for alt in question.get("alternative_golds") or []:
        candidates.append(
            {
                "source_id": alt["source_id"],
                "page": int(alt["page"]),
                "evidence_quote": alt["evidence_quote"],
            }
        )
    return candidates


def _hit_matches_filter(hit: dict[str, Any], expected_filter: dict[str, Any]) -> bool:
    """Verify whether a single retrieved hit satisfies every key-value filter predicate."""
    meta = hit.get("metadata") or {}
    for key, expected in expected_filter.items():
        if key in ("document_id", "source", "page"):
            actual = hit.get(key)
        else:
            actual = meta.get(key)
        if actual != expected:
            return False
    return True


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    applied_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate top-k hits for a single benchmark query without altering hit ordering."""
    golds = _gold_candidates(question)
    hit_evals: list[dict[str, Any]] = []
    first_evidence_rank: int | None = None
    first_page_rank: int | None = None

    for idx, hit in enumerate(hits, start=1):
        norm_text = _norm_ws(hit.get("text", ""))
        hit_doc = hit.get("document_id")
        hit_page = int(hit.get("page", -1))

        page_match = False
        evidence_match = False
        matched_quote = None

        for gold in golds:
            if hit_doc == gold["source_id"] and hit_page == gold["page"]:
                page_match = True
                norm_quote = _norm_ws(gold["evidence_quote"])
                if norm_quote and norm_quote in norm_text:
                    evidence_match = True
                    matched_quote = gold["evidence_quote"]
                    break

        if page_match and first_page_rank is None:
            first_page_rank = idx
        if evidence_match and first_evidence_rank is None:
            first_evidence_rank = idx

        filter_match = (
            _hit_matches_filter(hit, applied_filter) if applied_filter else None
        )
        hit_evals.append(
            {
                "rank": idx,
                "chunk_id": hit.get("chunk_id"),
                "document_id": hit_doc,
                "source": hit.get("source"),
                "page": hit_page,
                "score": hit.get("score"),
                "metadata": hit.get("metadata") or {},
                "text": hit.get("text", ""),
                "page_match": page_match,
                "evidence_match": evidence_match,
                "matched_quote": matched_quote,
                "filter_match": filter_match,
            }
        )

    filter_applicable = bool(applied_filter)
    filter_compliant: bool | None = None
    if filter_applicable:
        filter_compliant = all(bool(h["filter_match"]) for h in hit_evals)

    return {
        "id": question["id"],
        "split": question["split"],
        "question_type": question.get("question_type", "direct"),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_id": question["gold_source_id"],
        "gold_page": int(question["gold_page"]),
        "evidence_quote": question["evidence_quote"],
        "question_filter": question.get("filter"),
        "applied_filter": applied_filter,
        "filter_applicable": filter_applicable,
        "filter_compliant": filter_compliant,
        "hit_at_1": first_evidence_rank == 1,
        "evidence_hit_at_3": first_evidence_rank is not None and first_evidence_rank <= 3,
        "page_hit_at_1": first_page_rank == 1,
        "page_hit_at_3": first_page_rank is not None and first_page_rank <= 3,
        "first_evidence_rank": first_evidence_rank,
        "reciprocal_rank": (1.0 / first_evidence_rank) if first_evidence_rank else 0.0,
        "hits": hit_evals,
    }


def _summarize_group(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute counts and rates for a list of evaluated query traces."""
    n = len(traces)
    if n == 0:
        return {
            "n": 0,
            "hit1_count": 0,
            "hit1_rate": 0.0,
            "hit1_str": "0/0 (0.0%)",
            "hit3_count": 0,
            "hit3_rate": 0.0,
            "hit3_str": "0/0 (0.0%)",
            "page_hit1_count": 0,
            "page_hit3_count": 0,
            "mrr3": 0.0,
            "filter_applicable": 0,
            "filter_compliant": 0,
            "filter_compliance_str": "N/A",
        }

    hit1 = sum(1 for t in traces if t["hit_at_1"])
    hit3 = sum(1 for t in traces if t["evidence_hit_at_3"])
    page1 = sum(1 for t in traces if t["page_hit_at_1"])
    page3 = sum(1 for t in traces if t["page_hit_at_3"])
    mrr3 = sum(float(t.get("reciprocal_rank", 0.0)) for t in traces) / n

    filter_traces = [t for t in traces if t.get("filter_applicable")]
    f_total = len(filter_traces)
    f_ok = sum(1 for t in filter_traces if t.get("filter_compliant"))
    f_str = f"{f_ok}/{f_total} ({(100.0 * f_ok / f_total):.1f}%)" if f_total else "N/A"

    return {
        "n": n,
        "hit1_count": hit1,
        "hit1_rate": hit1 / n,
        "hit1_str": f"{hit1}/{n} ({100.0 * hit1 / n:.1f}%)",
        "hit3_count": hit3,
        "hit3_rate": hit3 / n,
        "hit3_str": f"{hit3}/{n} ({100.0 * hit3 / n:.1f}%)",
        "page_hit1_count": page1,
        "page_hit3_count": page3,
        "mrr3": mrr3,
        "filter_applicable": f_total,
        "filter_compliant": f_ok,
        "filter_compliance_str": f_str,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize retrieval accuracy across dev, test, and overall splits."""
    dev_traces = [t for t in traces if t.get("split") == "dev"]
    test_traces = [t for t in traces if t.get("split") == "test"]
    return {
        "dev": _summarize_group(dev_traces),
        "test": _summarize_group(test_traces),
        "all": _summarize_group(traces),
    }
