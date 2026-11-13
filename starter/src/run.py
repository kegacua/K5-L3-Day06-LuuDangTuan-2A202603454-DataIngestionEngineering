"""End-to-end controlled ingestion, pgvector indexing, retrieval, and evaluation runner."""

from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import GeminiEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus_from_manifest
from .models import Chunk, DocumentPage
from .store import PgVectorStore


FIXED_CHUNK_SIZE = 1400
FIXED_OVERLAP = 150
PARAGRAPH_MAX_SIZE = 1650
TOP_K = 3


def _norm_ws(text: str) -> str:
    return " ".join(text.split())


def _chunk_distribution(chunks: list[Chunk]) -> dict[str, Any]:
    lens = sorted(len(c.text) for c in chunks)
    n = len(lens)
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "total_chars": sum(lens),
        "min_chars": lens[0],
        "p25_chars": lens[n // 4],
        "median_chars": round(float(statistics.median(lens)), 1),
        "mean_chars": round(float(statistics.mean(lens)), 1),
        "p75_chars": lens[(3 * n) // 4],
        "p95_chars": lens[min(n - 1, int(0.95 * n))],
        "max_chars": lens[-1],
        "short_under_120": sum(1 for x in lens if x < 120),
    }


def _find_chunks_at_location(
    chunks: list[Chunk],
    document_id: str,
    page: int,
    anchor_phrase: str,
) -> dict[str, Any]:
    """Locate chunks matching a pre-selected anchor phrase on (document_id, page)."""
    page_chunks = [c for c in chunks if c.document_id == document_id and c.page == page]
    norm_anchor = _norm_ws(anchor_phrase)
    matched = [
        {
            "chunk_id": c.chunk_id,
            "chunk_index": c.metadata.get("chunk_index"),
            "char_len": len(c.text),
            "text": c.text,
            "metadata": c.metadata,
        }
        for c in page_chunks
        if norm_anchor in _norm_ws(c.text)
    ]

    # If fixed-size windowing split the anchor phrase itself across adjacent chunks, expose both.
    partial_split_context: list[dict[str, Any]] = []
    if not matched:
        tokens = [w for w in norm_anchor.split() if len(w) >= 3][:4]
        for idx, c in enumerate(page_chunks):
            nt = _norm_ws(c.text)
            if any(tok in nt for tok in tokens):
                partial_split_context.append(
                    {
                        "chunk_id": c.chunk_id,
                        "chunk_index": idx,
                        "char_len": len(c.text),
                        "text": c.text,
                    }
                )

    return {
        "page_chunk_count": len(page_chunks),
        "matched_chunks": matched,
        "partial_split_context": partial_split_context,
    }


def _run_reingestion_check(
    store: PgVectorStore,
    chunks_a: list[Chunk],
    vectors_a: list[list[float]],
    dims: int,
) -> dict[str, Any]:
    """Verify idempotent upsert, stale chunk removal, and real-strategy invariant row counts."""
    unit_vec_1 = [1.0] + [0.0] * (dims - 1)
    unit_vec_2 = [0.0, 1.0] + [0.0] * (dims - 2)
    unit_vec_3 = [0.0, 0.0, 1.0] + [0.0] * (dims - 3)
    ns = "_reingest_verify"
    base_meta = {
        "document_id": "doc-reingest-test",
        "source": "synthetic/test.pdf",
        "page": 1,
        "year": 2025,
        "edition": "test",
        "section": "tong_luoc",
        "language": "vi",
    }

    c1 = Chunk("doc-reingest-test::p001::c000", "doc-reingest-test", "synthetic/test.pdf", 1, "Đoạn 1 ban đầu", dict(base_meta))
    c2 = Chunk("doc-reingest-test::p001::c001", "doc-reingest-test", "synthetic/test.pdf", 1, "Đoạn 2 ban đầu", dict(base_meta))
    c3 = Chunk("doc-reingest-test::p001::c002", "doc-reingest-test", "synthetic/test.pdf", 1, "Đoạn 3 sẽ bị xóa", dict(base_meta))

    r1 = store.upsert(ns, [c1, c2, c3], [unit_vec_1, unit_vec_2, unit_vec_3])
    r2 = store.upsert(ns, [c1, c2, c3], [unit_vec_1, unit_vec_2, unit_vec_3])  # idempotent repeat

    c2_updated = Chunk("doc-reingest-test::p001::c001", "doc-reingest-test", "synthetic/test.pdf", 1, "Đoạn 2 đã cập nhật", dict(base_meta))
    r3 = store.upsert(ns, [c1, c2_updated], [unit_vec_1, unit_vec_2])  # shrinks 3 -> 2; c3 must be deleted
    pruned_docs = store.prune_missing_documents(ns, [])  # full cleanup

    # Real strategy idempotency: re-upsert one full existing document in Strategy A and assert invariant count.
    before_a = store.count_chunks("A")
    target_doc = chunks_a[0].document_id
    doc_pairs = [(c, v) for c, v in zip(chunks_a, vectors_a) if c.document_id == target_doc]
    reupsert_real = store.upsert("A", [p[0] for p in doc_pairs], [p[1] for p in doc_pairs])
    after_a = store.count_chunks("A")

    return {
        "synthetic_initial_insert": r1,
        "synthetic_idempotent_repeat": r2,
        "synthetic_shrink_prune_obsolete": r3,
        "synthetic_cleanup_pruned": pruned_docs,
        "real_strategy_a_count_before": before_a,
        "real_strategy_a_reupsert_doc": target_doc,
        "real_strategy_a_reupsert_result": reupsert_real,
        "real_strategy_a_count_after": after_a,
        "passed": (
            r1["total_strategy_rows"] == 3
            and r2["total_strategy_rows"] == 3
            and r2["deleted_obsolete"] == 0
            and r3["total_strategy_rows"] == 2
            and r3["deleted_obsolete"] == 1
            and store.count_chunks(ns) == 0
            and before_a == after_a
        ),
    }


def main() -> None:
    starter_dir = Path(__file__).resolve().parent.parent
    repo_root = starter_dir.parent
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    load_dotenv(starter_dir / ".env")
    database_url = os.getenv("DATABASE_URL", "").strip()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()
    dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    t_start = time.perf_counter()

    # 1. Ingestion & Normalization
    manifest_path = repo_root / "data" / "manifest.json"
    pages, manifest, ingestion_logs = load_corpus_from_manifest(manifest_path, repo_root)
    pages_by_key = {(p.document_id, p.page): p for p in pages}

    ingestion_summary = {
        "corpus_name": manifest.get("corpus_name"),
        "documents": len(manifest.get("documents", [])),
        "included_pages": len(pages),
        "total_normalized_chars": sum(len(p.text) for p in pages),
        "excluded_non_content": sum(1 for x in ingestion_logs if x["status"] == "excluded_non_content"),
        "empty_no_text": sum(1 for x in ingestion_logs if x["status"] == "empty_no_text"),
        "errors": sum(1 for x in ingestion_logs if x["status"] == "error"),
    }
    (results_dir / "ingestion_log.json").write_text(
        json.dumps({"summary": ingestion_summary, "page_logs": ingestion_logs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Ingestion] {ingestion_summary}")

    # 2. Controlled Chunk Generation (A = fixed_size, B = by_paragraph, C = identical chunks to B)
    chunks_a = [c for p in pages for c in fixed_size(p, size=FIXED_CHUNK_SIZE, overlap=FIXED_OVERLAP)]
    chunks_b = [c for p in pages for c in by_paragraph(p, max_size=PARAGRAPH_MAX_SIZE)]
    chunks_c = list(chunks_b)

    assert [c.chunk_id for c in chunks_b] == [c.chunk_id for c in chunks_c]
    assert [c.text for c in chunks_b] == [c.text for c in chunks_c]

    chunk_stats = {
        "A": {"chunking": "fixed_size", "chunk_size": FIXED_CHUNK_SIZE, "overlap": FIXED_OVERLAP, **_chunk_distribution(chunks_a)},
        "B": {"chunking": "by_paragraph", "max_size": PARAGRAPH_MAX_SIZE, **_chunk_distribution(chunks_b)},
        "C": {"chunking": "by_paragraph (identical to B)", "max_size": PARAGRAPH_MAX_SIZE, **_chunk_distribution(chunks_c)},
    }
    (results_dir / "chunk_stats.json").write_text(
        json.dumps(chunk_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Chunks] A={chunk_stats['A']['count']} (mean={chunk_stats['A']['mean_chars']}), B/C={chunk_stats['B']['count']} (mean={chunk_stats['B']['mean_chars']})")

    # 3. Connect Vector Store & Real Embedding
    cache_path = Path(tempfile.gettempdir()) / "day6_pgvector_embed_cache.json"
    embedder = GeminiEmbedder(
        model_name=model_name,
        dimensions=dimensions,
        api_key=api_key,
        cache_path=cache_path,
    )
    store = PgVectorStore(database_url=database_url, dimensions=dimensions)
    store.create_schema()

    print(f"[Store] PostgreSQL {store.postgres_version} | pgvector {store.pgvector_version} | metric=cosine (<=> exact)")

    vectors_a = embedder.embed_documents([c.text for c in chunks_a])
    doc_tokens_after_a = embedder.total_tokens
    doc_calls_after_a = embedder.api_calls

    # B and C share exact chunks, so we embed B ONCE and write the exact same vectors to B & C.
    vectors_b = embedder.embed_documents([c.text for c in chunks_b])
    doc_tokens_b = embedder.total_tokens - doc_tokens_after_a
    doc_calls_b = embedder.api_calls - doc_calls_after_a

    active_doc_ids = sorted({p.document_id for p in pages})
    upsert_results = {}
    for strat, chs, vecs in [("A", chunks_a, vectors_a), ("B", chunks_b, vectors_b), ("C", chunks_c, vectors_b)]:
        res = store.upsert(strat, chs, vecs)
        pruned_docs = store.prune_missing_documents(strat, active_doc_ids)
        res["pruned_missing_doc_rows"] = pruned_docs
        upsert_results[strat] = res
        print(f"[Upsert {strat}] {res}")

    # 4. Re-ingestion Idempotency & Obsolete Chunk Removal Verification
    reingestion_check = _run_reingestion_check(store, chunks_a, vectors_a, dimensions)
    (results_dir / "reingestion_check.json").write_text(
        json.dumps(reingestion_check, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Reingestion check] passed={reingestion_check['passed']}")

    # 5. Load Locked Benchmark & Run Retrieval Across A, B, C
    questions = json.loads((repo_root / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    coherence_locs = json.loads((repo_root / "benchmark" / "coherence_locations.json").read_text(encoding="utf-8"))

    tokens_before_queries = embedder.total_tokens
    calls_before_queries = embedder.api_calls
    query_vectors = embedder.embed_queries([q["question"] for q in questions])
    query_tokens = embedder.total_tokens - tokens_before_queries
    query_calls = embedder.api_calls - calls_before_queries

    all_traces: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}
    metrics_summary: dict[str, Any] = {}

    for strat, use_filters in [("A", False), ("B", False), ("C", True)]:
        traces: list[dict[str, Any]] = []
        for q, qvec in zip(questions, query_vectors):
            q_filter = (q.get("filter") or None) if use_filters else None
            hits = store.search(strat, qvec, top_k=TOP_K, filters=q_filter)
            traces.append(evaluate_query(q, hits, applied_filter=q_filter))
        all_traces[strat] = traces
        metrics_summary[strat] = summarize(traces)
        dev_m = metrics_summary[strat]["dev"]
        test_m = metrics_summary[strat]["test"]
        print(
            f"[Metrics {strat}] DEV Hit@1={dev_m['hit1_str']} Hit@3={dev_m['hit3_str']} Filter={dev_m['filter_compliance_str']} | "
            f"TEST Hit@1={test_m['hit1_str']} Hit@3={test_m['hit3_str']} Filter={test_m['filter_compliance_str']}"
        )

    total_seconds = round(time.perf_counter() - t_start, 2)
    embedding_stats = {
        "model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "l2_normalized": True,
        "postgres_version": store.postgres_version,
        "pgvector_version": store.pgvector_version,
        "search_mode": "exact_cosine_distance (<=>)",
        "total_api_calls": embedder.api_calls,
        "total_tokens": embedder.total_tokens,
        "tokens_A_documents": doc_tokens_after_a,
        "calls_A_documents": doc_calls_after_a,
        "tokens_BC_shared_documents": doc_tokens_b,
        "calls_BC_shared_documents": doc_calls_b,
        "tokens_queries": query_tokens,
        "calls_queries": query_calls,
        "embed_seconds": round(embedder.total_seconds, 2),
        "total_pipeline_seconds": total_seconds,
        "upsert_results": upsert_results,
    }
    (results_dir / "embedding_stats.json").write_text(
        json.dumps(embedding_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (results_dir / "traces.json").write_text(
        json.dumps({"summary": metrics_summary, "traces": all_traces}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (results_dir / "metrics_summary.json").write_text(
        json.dumps(metrics_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 6. Export Pre-Locked Coherence Samples & Test Audit Sheet for Manual Labeling
    coherence_samples: list[dict[str, Any]] = []
    for loc in coherence_locs:
        src_page = pages_by_key[(loc["document_id"], loc["page"])]
        coherence_samples.append(
            {
                "loc_id": loc["loc_id"],
                "document_id": loc["document_id"],
                "page": loc["page"],
                "section": loc["section"],
                "layout_type": loc["layout_type"],
                "description": loc["description"],
                "anchor_phrase": loc["anchor_phrase"],
                "A": _find_chunks_at_location(chunks_a, loc["document_id"], loc["page"], loc["anchor_phrase"]),
                "B": _find_chunks_at_location(chunks_b, loc["document_id"], loc["page"], loc["anchor_phrase"]),
                "C": _find_chunks_at_location(chunks_c, loc["document_id"], loc["page"], loc["anchor_phrase"]),
                "source_page_excerpt": src_page.text,
            }
        )
    (results_dir / "coherence_samples.json").write_text(
        json.dumps(coherence_samples, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    test_questions = [q for q in questions if q["split"] == "test"]
    test_audit_sheet: list[dict[str, Any]] = []
    for q in test_questions:
        qid = q["id"]
        gold_page_obj = pages_by_key[(q["gold_source_id"], q["gold_page"])]
        per_strat: dict[str, Any] = {}
        for strat in ("A", "B", "C"):
            trace = next(t for t in all_traces[strat] if t["id"] == qid)
            per_strat[strat] = {
                "applied_filter": trace["applied_filter"],
                "filter_compliant": trace["filter_compliant"],
                "hit_at_1": trace["hit_at_1"],
                "evidence_hit_at_3": trace["evidence_hit_at_3"],
                "hits": trace["hits"],
            }
        test_audit_sheet.append(
            {
                "id": qid,
                "question_type": q["question_type"],
                "question": q["question"],
                "expected_answer": q["expected_answer"],
                "gold_source_id": q["gold_source_id"],
                "gold_page": q["gold_page"],
                "evidence_quote": q["evidence_quote"],
                "filter": q.get("filter"),
                "gold_page_text": gold_page_obj.text,
                "strategies": per_strat,
            }
        )
    (results_dir / "test_audit_sheet.json").write_text(
        json.dumps(test_audit_sheet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Done] Saved all outputs to {results_dir} in {total_seconds}s")


if __name__ == "__main__":
    main()
