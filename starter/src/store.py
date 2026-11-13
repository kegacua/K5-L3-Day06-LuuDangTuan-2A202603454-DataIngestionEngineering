"""Persistent PostgreSQL + pgvector store with idempotent upsert and parameterized SQL filtering."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import Chunk

ALLOWED_FILTER_COLUMNS: dict[str, str] = {
    "document_id": "text",
    "source": "text",
    "page": "int",
    "year": "int",
    "edition": "text",
    "section": "text",
    "language": "text",
}


def _format_vector(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in vec) + "]"


def _validate_vector(vec: list[float], dimensions: int) -> None:
    if len(vec) != dimensions:
        raise ValueError(f"Expected vector of dimension {dimensions}, got {len(vec)}")
    if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in vec):
        raise ValueError("Vector contains non-finite values.")


class PgVectorStore:
    """PostgreSQL + pgvector store supporting multi-strategy isolation and SQL metadata filters."""

    def __init__(self, database_url: str, dimensions: int, table_name: str = "document_chunks") -> None:
        if not database_url or not database_url.strip():
            raise ValueError("DATABASE_URL is empty.")
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        if not table_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid table_name: {table_name}")

        self.database_url = database_url.strip()
        self.dimensions = int(dimensions)
        self.table_name = table_name

        # Fail fast if PostgreSQL or pgvector extension is unavailable.
        with psycopg.connect(self.database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(
                        "Connected to PostgreSQL, but 'vector' (pgvector) extension is not installed."
                    )
                self.pgvector_version = str(row[0])
                cur.execute("SELECT current_setting('server_version')")
                self.postgres_version = str(cur.fetchone()[0])

    def create_schema(self) -> None:
        """Create table with typed metadata columns, JSONB payload, and exact vector column."""
        ddl = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            strategy TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source TEXT NOT NULL,
            page INTEGER NOT NULL,
            year INTEGER NOT NULL,
            edition TEXT NOT NULL,
            section TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'vi',
            text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            metadata JSONB NOT NULL,
            embedding vector({self.dimensions}) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (strategy, chunk_id)
        );
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_strat_doc
            ON {self.table_name} (strategy, document_id);
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_strat_year_sec
            ON {self.table_name} (strategy, year, section);
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_strat_edition
            ON {self.table_name} (strategy, edition);
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_metadata_gin
            ON {self.table_name} USING GIN (metadata);
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
                # Verify existing table embedding dimension matches the configured model.
                cur.execute(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON a.attrelid = c.oid
                    WHERE c.relname = %s AND a.attname = 'embedding'
                    """,
                    (self.table_name,),
                )
                dim_row = cur.fetchone()
                expected_type = f"vector({self.dimensions})"
                if dim_row and dim_row[0] != expected_type:
                    raise RuntimeError(
                        f"Schema mismatch on {self.table_name}.embedding: "
                        f"expected {expected_type}, found {dim_row[0]}."
                    )
            conn.commit()

    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> dict[str, int]:
        """Validate lengths/dimensions, idempotently upsert chunks, and prune obsolete chunks."""
        if len(chunks) != len(vectors):
            raise ValueError(f"Length mismatch: {len(chunks)} chunks vs {len(vectors)} vectors")
        if not chunks:
            return {"upserted": 0, "deleted_obsolete": 0, "total_strategy_rows": self.count_chunks(strategy)}

        rows_to_upsert: list[tuple[Any, ...]] = []
        doc_ids: set[str] = set()
        active_chunk_ids: list[str] = []

        for chunk, vec in zip(chunks, vectors):
            _validate_vector(vec, self.dimensions)
            meta = dict(chunk.metadata)
            year = int(meta.get("year", 0))
            edition = str(meta.get("edition", ""))
            section = str(meta.get("section", ""))
            language = str(meta.get("language", "vi"))
            content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()

            doc_ids.add(chunk.document_id)
            active_chunk_ids.append(chunk.chunk_id)
            rows_to_upsert.append(
                (
                    strategy,
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.source,
                    int(chunk.page),
                    year,
                    edition,
                    section,
                    language,
                    chunk.text,
                    len(chunk.text),
                    content_hash,
                    json.dumps(meta, ensure_ascii=False),
                    _format_vector(vec),
                )
            )

        upsert_sql = f"""
        INSERT INTO {self.table_name} (
            strategy, chunk_id, document_id, source, page, year, edition, section, language,
            text, char_count, content_hash, metadata, embedding, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, NOW())
        ON CONFLICT (strategy, chunk_id) DO UPDATE SET
            document_id = EXCLUDED.document_id,
            source = EXCLUDED.source,
            page = EXCLUDED.page,
            year = EXCLUDED.year,
            edition = EXCLUDED.edition,
            section = EXCLUDED.section,
            language = EXCLUDED.language,
            text = EXCLUDED.text,
            char_count = EXCLUDED.char_count,
            content_hash = EXCLUDED.content_hash,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """
        prune_sql = f"""
        DELETE FROM {self.table_name}
        WHERE strategy = %s
          AND document_id = ANY(%s)
          AND NOT (chunk_id = ANY(%s))
        """

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.executemany(upsert_sql, rows_to_upsert)
                cur.execute(prune_sql, (strategy, sorted(doc_ids), active_chunk_ids))
                deleted_obsolete = cur.rowcount or 0
                cur.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE strategy = %s", (strategy,))
                total_rows = int(cur.fetchone()[0])
            conn.commit()

        return {
            "upserted": len(rows_to_upsert),
            "deleted_obsolete": deleted_obsolete,
            "total_strategy_rows": total_rows,
        }

    def prune_missing_documents(self, strategy: str, active_document_ids: list[str]) -> int:
        """Remove chunks belonging to documents removed from the active manifest."""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                if not active_document_ids:
                    cur.execute(f"DELETE FROM {self.table_name} WHERE strategy = %s", (strategy,))
                else:
                    cur.execute(
                        f"DELETE FROM {self.table_name} WHERE strategy = %s AND NOT (document_id = ANY(%s))",
                        (strategy, active_document_ids),
                    )
                deleted = cur.rowcount or 0
            conn.commit()
        return deleted

    def count_chunks(self, strategy: str | None = None) -> int:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                if strategy is None:
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                else:
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE strategy = %s", (strategy,))
                return int(cur.fetchone()[0])

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata via parameterized SQL and rank by exact cosine distance."""
        _validate_vector(query_vector, self.dimensions)
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")

        where_clauses = ["strategy = %s"]
        filter_params: list[Any] = [strategy]

        if filters:
            for key, raw_val in filters.items():
                col_type = ALLOWED_FILTER_COLUMNS.get(key)
                if col_type is None:
                    raise ValueError(
                        f"Unsupported metadata filter '{key}'. Allowed: {sorted(ALLOWED_FILTER_COLUMNS)}"
                    )
                if isinstance(raw_val, (list, tuple, set)):
                    vals = [int(v) if col_type == "int" else str(v) for v in raw_val]
                    if not vals:
                        raise ValueError(f"Filter '{key}' cannot be an empty list.")
                    where_clauses.append(f"{key} = ANY(%s)")
                    filter_params.append(vals)
                else:
                    val = int(raw_val) if col_type == "int" else str(raw_val)
                    where_clauses.append(f"{key} = %s")
                    filter_params.append(val)

        vec_literal = _format_vector(query_vector)
        sql = f"""
        SELECT
            chunk_id,
            document_id,
            source,
            page,
            text,
            metadata,
            (embedding <=> %s::vector) AS cosine_distance,
            (1.0 - (embedding <=> %s::vector)) AS cosine_similarity
        FROM {self.table_name}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY embedding <=> %s::vector ASC, chunk_id ASC
        LIMIT %s
        """
        params: list[Any] = [vec_literal, vec_literal, *filter_params, vec_literal, int(top_k)]

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        results: list[dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            meta = dict(row["metadata"])
            meta.setdefault("document_id", row["document_id"])
            meta.setdefault("source", row["source"])
            meta.setdefault("page", int(row["page"]))
            results.append(
                {
                    "rank": rank,
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "source": row["source"],
                    "page": int(row["page"]),
                    "score": round(float(row["cosine_similarity"]), 6),
                    "cosine_distance": round(float(row["cosine_distance"]), 6),
                    "text": row["text"],
                    "metadata": meta,
                }
            )
        return results
