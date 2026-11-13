"""Chunking strategies for Vietnamese economic report pages."""

from __future__ import annotations

import re

from .models import Chunk, DocumentPage

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_metadata(
    page: DocumentPage,
    strategy_name: str,
    chunk_index: int,
    text: str,
    extra: dict[str, int] | None = None,
) -> dict:
    """Build chunk metadata inheriting page provenance and filtering fields."""
    meta = dict(page.metadata)
    meta.update(
        {
            "chunking": strategy_name,
            "chunk_index": chunk_index,
            "char_len": len(text),
        }
    )
    if extra:
        meta.update(extra)
    return meta


def fixed_size(page: DocumentPage, size: int = 750, overlap: int = 100) -> list[Chunk]:
    """Split a normalized page into fixed character-window overlapping chunks."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = page.text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    chunk_idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        window = text[start:end].strip()
        if window:
            chunks.append(
                Chunk(
                    chunk_id=f"{page.document_id}::p{page.page:03d}::c{chunk_idx:03d}",
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=window,
                    metadata=_chunk_metadata(
                        page,
                        "fixed_size",
                        chunk_idx,
                        window,
                        {"char_start": start, "char_end": end},
                    ),
                )
            )
            chunk_idx += 1
        if end >= text_len:
            break
        start += step

    return chunks


def _split_by_words(text: str, max_size: int) -> list[str]:
    """Fallback word-level split when a single sentence exceeds max_size."""
    words = text.split()
    if not words:
        return []

    pieces: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_size:
            current = candidate
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


def _split_long_paragraph(paragraph: str, max_size: int) -> list[str]:
    """Split an oversized paragraph along sentence boundaries without cutting words."""
    if len(paragraph) <= max_size:
        return [paragraph]

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]
    pieces: list[str] = []
    current = ""

    for sent in sentences:
        if len(sent) > max_size:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_split_by_words(sent, max_size))
            continue

        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= max_size:
            current = candidate
        else:
            pieces.append(current)
            current = sent

    if current:
        pieces.append(current)
    return pieces


def _is_short_heading(text: str) -> bool:
    """Detect brief section/subsection headings so they stay attached to their body."""
    stripped = text.strip()
    return (
        bool(stripped)
        and len(stripped) <= 110
        and "\n" not in stripped
        and stripped[-1] not in ".!?"
    )


def by_paragraph(page: DocumentPage, max_size: int = 900) -> list[Chunk]:
    """Pack paragraph blocks into semantically coherent chunks bounded by max_size."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    raw_paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]
    if not raw_paragraphs:
        return []

    segments: list[str] = []
    for para in raw_paragraphs:
        segments.extend(_split_long_paragraph(para, max_size))

    chunks_text: list[str] = []
    current = ""

    for seg in segments:
        if not current:
            current = seg
            continue

        candidate = f"{current}\n\n{seg}"
        limit = max_size + 140 if _is_short_heading(current) else max_size
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks_text.append(current)
            current = seg

    if current:
        # Avoid leaving a tiny isolated fragment at page end if attaching stays reasonable.
        if (
            chunks_text
            and len(current) < 100
            and len(chunks_text[-1]) + 2 + len(current) <= max_size + 140
        ):
            chunks_text[-1] = f"{chunks_text[-1]}\n\n{current}"
        else:
            chunks_text.append(current)

    chunks: list[Chunk] = []
    for idx, text in enumerate(chunks_text):
        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}::p{page.page:03d}::c{idx:03d}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=text,
                metadata=_chunk_metadata(page, "by_paragraph", idx, text),
            )
        )
    return chunks
