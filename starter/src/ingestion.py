"""Read, clean, and normalize PDF source pages while preserving provenance."""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import DocumentPage

_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u00a0": " ",
    "\u200b": "",
    "\ufeff": "",
}

_HEADER_FOOTER_PATTERNS = (
    re.compile(r"^BÁO CÁO ĐIỂM LẠI,?\s*THÁNG\s*\d+/\d{4}$", re.IGNORECASE),
    re.compile(r"^ĐỂ ĐẦU TƯ CÔNG THÚC ĐẨY TĂNG TRƯỞNG$", re.IGNORECASE),
    re.compile(r"^VƯƠN TỚI TẦM CAO MỚI TRÊN THỊ TRƯỜNG VỐN$", re.IGNORECASE),
    re.compile(
        r"^CHUYÊN ĐỀ:\s*BỨT TỐC PHÁT TRIỂN NHÂN TÀI CÔNG NGHỆ CAO CỦA VIỆT NAM(\s+I\s+[ivxlcdm\d]+)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^([ivxlcdm]+|\d+)\s+I\s+ĐIỂM LẠI THÁNG\s*\d+/\d{4}:\s*CẬP NHẬT TÌNH HÌNH KINH TẾ VIỆT NAM$",
        re.IGNORECASE,
    ),
    re.compile(r"^(\d+|[ivxlcdm]+)$", re.IGNORECASE),
)

_BULLET_START = re.compile(r"^(?:[-•●▪▪︎]|z\s+|l\s+|\d+[.)]\s+|\([ivx\d]+\)\s+)")
_HEADING_LIKE = re.compile(
    r"^(?:CHƯƠNG\s+\d+|Phần\s+\d+|Hộp\s+\d+\.\d+|Bảng\s+\d+\.\d+|Hình\s+\d+\.\d+|"
    r"[IVX]+\.\s+|\d+(?:\.\d+)*\.?\s+\S+|TRỤ CỘT\s+\d+|TÓM LƯỢC TỔNG QUAN|Tổng quan)"
)


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFC), ligatures, and whitespace while keeping paragraph breaks."""
    for src_ch, dst_ch in _LIGATURES.items():
        text = text.replace(src_ch, dst_ch)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned_paragraphs: list[str] = []
    for raw_para in re.split(r"\n{2,}", text):
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw_para.splitlines()]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        joined = " ".join(lines)
        joined = re.sub(r"[ \t]+", " ", joined).strip()
        if joined:
            cleaned_paragraphs.append(joined)

    return "\n\n".join(cleaned_paragraphs)


def _is_running_header_footer(line_text: str, y: float) -> bool:
    """Return True when a line lies in header/footer bands and matches banner/page-number text."""
    stripped = re.sub(r"\s+", " ", line_text).strip()
    if not stripped:
        return True
    if y > 730.0 or y < 45.0:
        if any(pat.match(stripped) for pat in _HEADER_FOOTER_PATTERNS):
            return True
        if y < 45.0 and len(stripped) <= 8:
            return True
    return False


def _join_line_parts(parts: list[tuple[float, str]]) -> str:
    """Join horizontally adjacent fragments on the same baseline without inserting spurious gaps."""
    parts_sorted = sorted(parts, key=lambda p: p[0])
    out = ""
    for _, seg in parts_sorted:
        clean = seg.replace("\n", "")
        if not clean.strip():
            continue
        if not out:
            out = clean.lstrip()
        elif out.endswith(" ") or clean.startswith((" ", ",", ".", ";", ":", ")", "%", "”", "’")):
            out += clean
        else:
            out += " " + clean.lstrip()
    return re.sub(r"[ \t]+", " ", out).strip()


def _merge_spans_into_lines(spans: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Group PDF text spans sharing similar y coordinates into ordered visual lines."""
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda item: (-round(item[0], 1), item[1]))
    lines: list[tuple[float, float, str]] = []
    cur_y = spans_sorted[0][0]
    cur_x = spans_sorted[0][1]
    parts: list[tuple[float, str]] = [(spans_sorted[0][1], spans_sorted[0][2])]

    for y, x, txt in spans_sorted[1:]:
        if abs(y - cur_y) <= 3.0:
            parts.append((x, txt))
        else:
            line_str = _join_line_parts(parts)
            if line_str and not _is_running_header_footer(line_str, cur_y):
                lines.append((cur_y, cur_x, line_str))
            cur_y = y
            cur_x = x
            parts = [(x, txt)]

    line_str = _join_line_parts(parts)
    if line_str and not _is_running_header_footer(line_str, cur_y):
        lines.append((cur_y, cur_x, line_str))
    return lines


def _detect_two_column_split(spans: list[tuple[float, float, str]]) -> tuple[float, float] | None:
    """Detect two-column prose layouts and return (split_x, dual_top_y), or None."""
    body_spans = [sp for sp in spans if 50.0 <= sp[0] <= 730.0 and len(sp[2].strip()) >= 8]
    left_cands = [sp for sp in body_spans if 50.0 <= sp[1] <= 145.0]
    right_cands = [sp for sp in body_spans if 270.0 <= sp[1] <= 355.0]
    if len(left_cands) < 8 or len(right_cands) < 8:
        return None

    rx_bins: dict[int, int] = {}
    for _, x, _ in right_cands:
        b = round(x / 5.0) * 5
        rx_bins[b] = rx_bins.get(b, 0) + 1
    best_rx = max(rx_bins.items(), key=lambda kv: kv[1])[0]
    aligned_right = [sp for sp in right_cands if abs(sp[1] - best_rx) <= 8.0]

    lx_bins: dict[int, int] = {}
    for _, x, _ in left_cands:
        b = round(x / 5.0) * 5
        lx_bins[b] = lx_bins.get(b, 0) + 1
    best_lx = max(lx_bins.items(), key=lambda kv: kv[1])[0]
    aligned_left = [sp for sp in left_cands if abs(sp[1] - best_lx) <= 10.0]

    if len(aligned_left) < 8 or len(aligned_right) < 8:
        return None

    mean_right_len = statistics.mean(len(sp[2].strip()) for sp in aligned_right)
    if mean_right_len < 22.0:
        return None

    lys = [sp[0] for sp in aligned_left]
    rys = [sp[0] for sp in aligned_right]
    overlap = min(max(lys), max(rys)) - max(min(lys), min(rys))
    if overlap < 120.0:
        return None

    split_x = float(best_rx) - 15.0
    dual_top_y = max(rys) + 12.0
    return split_x, dual_top_y


def _lines_to_paragraphs(lines: list[tuple[float, float, str]]) -> str:
    """Reconstruct paragraph boundaries from vertical gaps, headings, and bullets."""
    if not lines:
        return ""
    lines_sorted = sorted(lines, key=lambda ln: (-ln[0], ln[1]))
    dys = [
        lines_sorted[i - 1][0] - lines_sorted[i][0]
        for i in range(1, len(lines_sorted))
        if 6.0 <= (lines_sorted[i - 1][0] - lines_sorted[i][0]) <= 25.0
    ]
    median_dy = statistics.median(dys) if dys else 14.5
    gap_threshold = max(17.5, median_dy * 1.28)

    paragraphs: list[list[str]] = [[lines_sorted[0][2]]]
    for i in range(1, len(lines_sorted)):
        prev_y, _, prev_txt = lines_sorted[i - 1]
        cur_y, _, cur_txt = lines_sorted[i]
        dy = prev_y - cur_y
        new_para = False
        if dy > gap_threshold or dy < -30.0:
            new_para = True
        elif _BULLET_START.match(cur_txt):
            new_para = True
        elif _HEADING_LIKE.match(cur_txt) and prev_txt.endswith((".", "!", "?", ":")):
            new_para = True
        elif (
            len(prev_txt) < 55
            and prev_txt.endswith((".", "!", "?"))
            and cur_txt[:1].isupper()
            and not prev_txt.endswith(("Tp.", "TS.", "PGS.", "GS."))
        ):
            new_para = True

        if new_para:
            paragraphs.append([cur_txt])
        else:
            paragraphs[-1].append(cur_txt)

    return "\n\n".join(" ".join(p) for p in paragraphs)


def _extract_page_layout_text(pdf_page: Any) -> tuple[int, str]:
    """Extract raw character count and layout-reconstructed text in a single pypdf pass."""
    spans: list[tuple[float, float, str]] = []

    def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
        if text and text.strip():
            spans.append((float(tm[5]), float(tm[4]), text))

    pdf_page.extract_text(visitor_text=visitor)
    raw_chars = sum(len(sp[2].strip()) for sp in spans)
    if raw_chars == 0:
        return 0, ""

    two_col = _detect_two_column_split(spans)
    if two_col is not None:
        split_x, dual_top_y = two_col
        top_spans = [sp for sp in spans if sp[0] > dual_top_y]
        left_spans = [sp for sp in spans if sp[0] <= dual_top_y and sp[1] < split_x]
        right_spans = [sp for sp in spans if sp[0] <= dual_top_y and sp[1] >= split_x]
        ordered_blocks = [
            _lines_to_paragraphs(_merge_spans_into_lines(top_spans)),
            _lines_to_paragraphs(_merge_spans_into_lines(left_spans)),
            _lines_to_paragraphs(_merge_spans_into_lines(right_spans)),
        ]
        reconstructed = "\n\n".join(b for b in ordered_blocks if b)
    else:
        reconstructed = _lines_to_paragraphs(_merge_spans_into_lines(spans))

    return raw_chars, reconstructed


def _section_for_page(page_num: int, section_ranges: list[dict[str, Any]] | None) -> tuple[str, str]:
    """Resolve section code and title from documented TOC page ranges."""
    if not section_ranges:
        return "body", ""
    for sec in section_ranges:
        if sec["start_page"] <= page_num <= sec["end_page"]:
            return str(sec["section"]), str(sec.get("section_title", ""))
    return "body", ""


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    doc_metadata: dict[str, Any] | None = None,
    section_ranges: list[dict[str, Any]] | None = None,
    exclude_pages: dict[int, str] | None = None,
    diagnostics_out: list[dict[str, Any]] | None = None,
) -> list[DocumentPage]:
    """Extract each physical page, normalize text, record empty/excluded/error pages."""
    if not path.exists():
        raise FileNotFoundError(f"Source PDF not found: {path}")

    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    base_meta = dict(doc_metadata or {})
    exclude_map = exclude_pages or {}

    for page_idx, pdf_page in enumerate(reader.pages, start=1):
        try:
            raw_len, reconstructed = _extract_page_layout_text(pdf_page)
        except Exception as exc:
            if diagnostics_out is not None:
                diagnostics_out.append(
                    {
                        "document_id": document_id,
                        "source": source,
                        "page": page_idx,
                        "status": "error",
                        "reason": str(exc),
                        "raw_chars": 0,
                        "normalized_chars": 0,
                    }
                )
            raise RuntimeError(f"Failed extracting {source} page {page_idx}: {exc}") from exc

        if raw_len == 0:
            if diagnostics_out is not None:
                diagnostics_out.append(
                    {
                        "document_id": document_id,
                        "source": source,
                        "page": page_idx,
                        "status": "empty_no_text",
                        "reason": exclude_map.get(page_idx, "Page contains zero extractable characters (blank/graphic)"),
                        "raw_chars": 0,
                        "normalized_chars": 0,
                    }
                )
            continue

        if page_idx in exclude_map:
            if diagnostics_out is not None:
                diagnostics_out.append(
                    {
                        "document_id": document_id,
                        "source": source,
                        "page": page_idx,
                        "status": "excluded_non_content",
                        "reason": exclude_map[page_idx],
                        "raw_chars": raw_len,
                        "normalized_chars": 0,
                    }
                )
            continue

        normalized = normalize_text(reconstructed)
        if not normalized:
            if diagnostics_out is not None:
                diagnostics_out.append(
                    {
                        "document_id": document_id,
                        "source": source,
                        "page": page_idx,
                        "status": "empty_after_normalization",
                        "reason": "No remaining content after removing headers/footers",
                        "raw_chars": raw_len,
                        "normalized_chars": 0,
                    }
                )
            continue

        section_code, section_title = _section_for_page(page_idx, section_ranges)
        page_meta = {
            **base_meta,
            "section": section_code,
            "section_title": section_title,
        }
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_idx,
                text=normalized,
                metadata=page_meta,
            )
        )
        if diagnostics_out is not None:
            diagnostics_out.append(
                {
                    "document_id": document_id,
                    "source": source,
                    "page": page_idx,
                    "status": "included",
                    "section": section_code,
                    "raw_chars": raw_len,
                    "normalized_chars": len(normalized),
                }
            )

    return pages


def load_corpus_from_manifest(
    manifest_path: Path,
    repo_root: Path,
) -> tuple[list[DocumentPage], dict[str, Any], list[dict[str, Any]]]:
    """Load and validate all corpus documents declared in data/manifest.json."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_pages: list[DocumentPage] = []
    diagnostics: list[dict[str, Any]] = []

    for doc in manifest["documents"]:
        pdf_path = repo_root / doc["local_path"]
        exclude_pages = {int(k): v for k, v in doc.get("excluded_pages", {}).items()}
        doc_meta = {
            "year": int(doc["year"]),
            "edition": str(doc["edition"]),
            "language": str(doc.get("language", "vi")),
            "doc_title": str(doc["title"]),
        }
        doc_pages = load_pdf(
            path=pdf_path,
            document_id=doc["source_id"],
            source=doc["local_path"],
            doc_metadata=doc_meta,
            section_ranges=doc.get("section_ranges", []),
            exclude_pages=exclude_pages,
            diagnostics_out=diagnostics,
        )
        all_pages.extend(doc_pages)

    min_pages = int(manifest.get("minimum_required_content_pages", 30))
    if len(all_pages) < min_pages:
        raise ValueError(
            f"Corpus validation failed: extracted {len(all_pages)} content pages, minimum is {min_pages}."
        )

    return all_pages, manifest, diagnostics
