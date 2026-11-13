"""Offline unit tests verifying normalization, chunking, manifest, benchmark, and evaluation logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

STARTER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = STARTER_DIR.parent
sys.path.insert(0, str(STARTER_DIR))

from src.chunking import by_paragraph, fixed_size
from src.evaluation import evaluate_query, summarize
from src.ingestion import normalize_text
from src.models import DocumentPage


def test_normalize_text_preserves_paragraphs_and_ligatures() -> None:
    raw = "Tăng \ufb01 trưởng GDP\u00a0năm 2024.\r\nDòng hai.\n\nĐoạn\u200b hai   có nhiều khoảng trắng."
    norm = normalize_text(raw)
    assert norm == "Tăng fi trưởng GDP năm 2024. Dòng hai.\n\nĐoạn hai có nhiều khoảng trắng."


def test_chunking_strategies_and_provenance() -> None:
    text = (
        "Mục tiêu chính sách\n\n"
        + ("Đoạn văn thứ nhất phân tích tình hình vĩ mô và cán cân thương mại của Việt Nam. " * 6).strip()
        + "\n\n"
        + ("Đoạn văn thứ hai đánh giá giải ngân đầu tư công và cải cách thể chế. " * 6).strip()
    )
    page = DocumentPage(
        document_id="wb-diemlai-2024-08",
        source="starter/data/wb_diemlai_2024_08.pdf",
        page=15,
        text=text,
        metadata={"year": 2024, "edition": "2024-08", "section": "tong_luoc", "language": "vi"},
    )
    a = fixed_size(page, size=250, overlap=50)
    b = by_paragraph(page, max_size=500)

    assert len(a) >= 3
    assert all(len(c.text) <= 250 for c in a)
    assert all(c.document_id == "wb-diemlai-2024-08" and c.page == 15 for c in a)
    assert all(c.metadata["year"] == 2024 and c.metadata["section"] == "tong_luoc" for c in a)

    # Heading stays attached to first paragraph in by_paragraph
    assert len(b) >= 2
    assert b[0].text.startswith("Mục tiêu chính sách\n\n")
    assert all(len(c.text) > 0 for c in b)


def test_evaluation_hit1_hit3_and_filter_compliance() -> None:
    q = {
        "id": "q_demo",
        "split": "test",
        "question_type": "metadata_filter",
        "question": "Tỷ lệ lạm phát CPI là bao nhiêu?",
        "expected_answer": "4,3%",
        "gold_source_id": "wb-diemlai-2024-08",
        "gold_page": 15,
        "evidence_quote": "Lạm phát tăng lên 4,3%",
        "filter": {"year": 2024, "section": "tong_luoc"},
    }
    hits = [
        {
            "chunk_id": "c1",
            "document_id": "wb-diemlai-2023-08",
            "source": "s23",
            "page": 12,
            "score": 0.89,
            "text": "Lạm phát giảm.",
            "metadata": {"year": 2023, "section": "tong_luoc"},
        },
        {
            "chunk_id": "c2",
            "document_id": "wb-diemlai-2024-08",
            "source": "s24",
            "page": 15,
            "score": 0.85,
            "text": "Lạm phát tăng lên 4,3% vào tháng 6/2024.",
            "metadata": {"year": 2024, "section": "tong_luoc"},
        },
    ]
    res_unfiltered = evaluate_query(q, hits, applied_filter=None)
    assert res_unfiltered["hit_at_1"] is False
    assert res_unfiltered["evidence_hit_at_3"] is True
    assert res_unfiltered["filter_applicable"] is False
    assert res_unfiltered["filter_compliant"] is None

    res_filtered_fail = evaluate_query(q, hits, applied_filter=q["filter"])
    assert res_filtered_fail["filter_applicable"] is True
    assert res_filtered_fail["filter_compliant"] is False

    res_filtered_ok = evaluate_query(q, [hits[1]], applied_filter=q["filter"])
    assert res_filtered_ok["hit_at_1"] is True
    assert res_filtered_ok["filter_compliant"] is True

    summary = summarize([res_filtered_ok])
    assert summary["test"]["hit1_str"] == "1/1 (100.0%)"
    assert summary["test"]["filter_compliance_str"] == "1/1 (100.0%)"


def test_locked_benchmark_and_manifest_constraints() -> None:
    manifest = json.loads((REPO_ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_valid_content_pages"] >= 30
    assert len(manifest["documents"]) == 3

    questions = json.loads((REPO_ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    assert len(questions) >= 20
    dev = [q for q in questions if q["split"] == "dev"]
    test = [q for q in questions if q["split"] == "test"]
    assert len(dev) >= 15 and len(test) >= 5
    f_all = [q for q in questions if q.get("filter")]
    f_test = [q for q in test if q.get("filter")]
    assert len(f_all) >= 3 and len(f_test) >= 1


if __name__ == "__main__":
    test_normalize_text_preserves_paragraphs_and_ligatures()
    test_chunking_strategies_and_provenance()
    test_evaluation_hit1_hit3_and_filter_compliance()
    test_locked_benchmark_and_manifest_constraints()
    print("ALL OFFLINE TESTS PASSED")
