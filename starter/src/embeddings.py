"""Real Gemini API embedding adapter with rate-limit pacing, strict failure semantics, and token tracking."""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Protocol

from google import genai
from google.genai import types

_RETRY_IN_RE = re.compile(r"retry in\s+(\d+(?:\.\d+)?)s", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r"retryDelay[\"']?\s*:\s*[\"'](\d+(?:\.\d+)?)s", re.IGNORECASE)


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0 or not math.isfinite(norm):
        raise RuntimeError("Received zero or non-finite embedding vector from provider.")
    return [float(x / norm) for x in vec]


def _parse_retry_seconds(exc: Exception) -> float | None:
    msg = str(exc)
    for pat in (_RETRY_IN_RE, _RETRY_DELAY_RE):
        m = pat.search(msg)
        if m:
            return float(m.group(1))
    return None


class GeminiEmbedder:
    """Google Gemini API embedder using RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY task types."""

    def __init__(
        self,
        model_name: str = "gemini-embedding-001",
        dimensions: int = 768,
        api_key: str | None = None,
        batch_size: int = 20,
        max_items_per_min: int = 70,
        max_tokens_per_min: int = 25000,
        cache_path: Path | None = None,
    ) -> None:
        resolved_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        if not resolved_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Set GEMINI_API_KEY in starter/.env; mock fallback is disabled."
            )
        clean_model = model_name.strip() or "gemini-embedding-001"
        if clean_model.startswith("models/"):
            clean_model = clean_model[len("models/") :]
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")

        self.model_name = clean_model
        self.dimensions = int(dimensions)
        self.batch_size = int(batch_size)
        self.max_items_per_min = int(max_items_per_min)
        self.max_tokens_per_min = int(max_tokens_per_min)
        self.cache_path = cache_path
        self.client = genai.Client(api_key=resolved_key)

        self.api_calls = 0
        self.total_tokens = 0
        self.total_seconds = 0.0
        self._window: deque[tuple[float, int, int]] = deque()
        self._cache: dict[str, dict] = {}
        if self.cache_path and self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def _cache_key(self, task_type: str, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.model_name}|{self.dimensions}|{task_type}|{digest}"

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False),
            encoding="utf-8",
        )

    def _pace_before_request(self, num_items: int, est_tokens: int) -> None:
        """Throttle requests over a rolling 62s window to respect Free Tier RPM/TPM limits."""
        while True:
            now = time.monotonic()
            while self._window and now - self._window[0][0] >= 62.0:
                self._window.popleft()
            used_items = sum(x[1] for x in self._window)
            used_tokens = sum(x[2] for x in self._window)
            if not self._window or (
                used_items + num_items <= self.max_items_per_min
                and used_tokens + est_tokens <= self.max_tokens_per_min
            ):
                return
            oldest_ts = self._window[0][0]
            sleep_sec = max(0.5, 62.5 - (now - oldest_ts))
            time.sleep(sleep_sec)

    def _embed_with_retry(
        self,
        contents: list[str],
        task_type: str,
        max_retries: int = 8,
    ) -> list[list[float]]:
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.dimensions,
        )
        # Estimate tokens (~1 token per 3.0 Vietnamese chars) for pre-flight TPM pacing.
        est_tokens = max(len(contents), sum(max(1, len(c) // 3) for c in contents))
        last_err: Exception | None = None

        for attempt in range(max_retries):
            self._pace_before_request(len(contents), est_tokens)
            try:
                t0 = time.perf_counter()
                resp = self.client.models.embed_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                self.total_seconds += time.perf_counter() - t0
                self.api_calls += 1

                embeddings = getattr(resp, "embeddings", None) or []
                if len(embeddings) != len(contents):
                    raise RuntimeError(
                        f"Expected {len(contents)} embeddings from Gemini, got {len(embeddings)}."
                    )

                vectors: list[list[float]] = []
                for emb in embeddings:
                    vals = list(emb.values)
                    if len(vals) != self.dimensions:
                        raise RuntimeError(
                            f"Expected {self.dimensions}-d vector, got {len(vals)}-d."
                        )
                    vectors.append(_l2_normalize(vals))

                tok_resp = self.client.models.count_tokens(model=self.model_name, contents=contents)
                batch_tokens = int(getattr(tok_resp, "total_tokens", 0) or 0)
                self.total_tokens += batch_tokens
                self._window.append((time.monotonic(), len(contents), max(batch_tokens, est_tokens // 2)))
                return vectors
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                low = msg.lower()
                if "perday" in low or "per_day" in low:
                    raise RuntimeError(
                        f"Gemini daily embedding quota exhausted ({self.model_name}, task={task_type}): {exc}"
                    ) from exc

                is_transient = any(k in low for k in ("429", "503", "500", "rate", "quota", "timeout", "unavailable"))
                if not is_transient or attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Gemini embedding request failed ({self.model_name}, task={task_type}): {exc}"
                    ) from exc

                parsed = _parse_retry_seconds(exc)
                delay = (parsed + 2.0) if parsed is not None else min(15.0 * (attempt + 1), 65.0)
                self._window.clear()
                time.sleep(max(delay, 5.0))

        raise RuntimeError(f"Gemini embedding failed after retries: {last_err}")

    def _embed_batch_cached(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Return cached real Gemini vectors where present, calling Gemini only for cache misses."""
        keys = [self._cache_key(task_type, t) for t in texts]
        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []

        for idx, k in enumerate(keys):
            cached = self._cache.get(k)
            if cached and len(cached.get("vector", [])) == self.dimensions:
                results[idx] = list(cached["vector"])
                self.total_tokens += int(cached.get("tokens", 0))
            else:
                missing_indices.append(idx)

        if missing_indices:
            missing_texts = [texts[i] for i in missing_indices]
            tok_before = self.total_tokens
            new_vecs = self._embed_with_retry(missing_texts, task_type=task_type)
            batch_tokens = self.total_tokens - tok_before
            total_chars = max(1, sum(len(t) for t in missing_texts))
            for idx, vec, txt in zip(missing_indices, new_vecs, missing_texts):
                results[idx] = vec
                est_tok = round(batch_tokens * (len(txt) / total_chars))
                self._cache[keys[idx]] = {"vector": vec, "tokens": est_tok}
            self._save_cache()

        return [v for v in results if v is not None]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        for batch_num, start in enumerate(range(0, len(texts), self.batch_size), start=1):
            batch = texts[start : start + self.batch_size]
            all_vectors.extend(self._embed_batch_cached(batch, task_type="RETRIEVAL_DOCUMENT"))
            if batch_num % 5 == 0 or batch_num == total_batches:
                print(
                    f"[Embed docs] batch {batch_num}/{total_batches} "
                    f"({min(start + len(batch), len(texts))}/{len(texts)} chunks, api_calls={self.api_calls})"
                )
        return all_vectors

    def embed_query(self, question: str) -> list[float]:
        if not question.strip():
            raise ValueError("Cannot embed an empty query.")
        return self._embed_batch_cached([question], task_type="RETRIEVAL_QUERY")[0]

    def embed_queries(self, questions: list[str]) -> list[list[float]]:
        if not questions:
            return []
        if any(not q.strip() for q in questions):
            raise ValueError("Cannot embed an empty query.")
        vectors: list[list[float]] = []
        for start in range(0, len(questions), self.batch_size):
            batch = questions[start : start + self.batch_size]
            vectors.extend(self._embed_batch_cached(batch, task_type="RETRIEVAL_QUERY"))
        return vectors
