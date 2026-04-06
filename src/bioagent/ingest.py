"""AlphaSeq dataset ingestion — download and load into Postgres."""

from __future__ import annotations

import asyncio
import csv
import io
import os
import tempfile
from pathlib import Path

import asyncpg
import httpx

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioagent:bioagent@localhost:5432/bioagent")

# MIT AlphaSeq Antibody Dataset — raw CSV from GitHub
DATASET_URL = (
    "https://raw.githubusercontent.com/mit-ll/AlphaSeq_Antibody_Dataset/"
    "main/data/antibody_dataset.csv"
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS alphaseq_bindings (
    sequence_id TEXT PRIMARY KEY,
    vh_sequence TEXT NOT NULL,
    vl_sequence TEXT,
    target TEXT NOT NULL,
    binding_score REAL NOT NULL,
    kd_nm REAL
);
CREATE INDEX IF NOT EXISTS idx_alphaseq_target ON alphaseq_bindings(target);
CREATE INDEX IF NOT EXISTS idx_alphaseq_score ON alphaseq_bindings(binding_score);
"""


async def download_dataset(dest: Path) -> Path:
    """Download the AlphaSeq CSV dataset."""
    print(f"Downloading AlphaSeq dataset from GitHub...")
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(DATASET_URL)
        resp.raise_for_status()
    dest.write_bytes(resp.content)
    size_mb = len(resp.content) / 1024 / 1024
    print(f"Downloaded {size_mb:.1f} MB to {dest}")
    return dest


async def ingest(database_url: str = DATABASE_URL, data_path: Path | None = None) -> int:
    """Ingest AlphaSeq data into Postgres. Returns number of rows inserted."""
    conn = await asyncpg.connect(database_url)

    try:
        await conn.execute(CREATE_TABLE)

        # Check if already ingested
        count = await conn.fetchval("SELECT COUNT(*) FROM alphaseq_bindings")
        if count and count > 0:
            print(f"AlphaSeq already loaded: {count:,} rows. Skipping.")
            return count

        # Download if no local file
        if data_path is None or not data_path.exists():
            tmp = Path(tempfile.mkdtemp()) / "alphaseq.csv"
            data_path = await download_dataset(tmp)

        print(f"Reading {data_path}...")
        text = data_path.read_text()
        reader = csv.DictReader(io.StringIO(text))

        rows = []
        for i, row in enumerate(reader):
            # Adapt to actual CSV column names
            seq_id = row.get("Sequence_ID") or row.get("sequence_id") or f"seq_{i}"
            vh = row.get("VH") or row.get("vh_sequence") or row.get("Heavy_Chain") or ""
            vl = row.get("VL") or row.get("vl_sequence") or row.get("Light_Chain")
            target = row.get("Target") or row.get("target") or row.get("Antigen") or "SARS-CoV-2"
            score_raw = row.get("Binding_Score") or row.get("binding_score") or row.get("Score")
            kd_raw = row.get("Kd_nM") or row.get("kd_nm") or row.get("Kd")

            if not vh and not score_raw:
                continue

            score = float(score_raw) if score_raw else 0.0
            kd = float(kd_raw) if kd_raw else None
            vl = vl if vl else None

            rows.append((seq_id, vh, vl, target, score, kd))

        print(f"Inserting {len(rows):,} rows...")
        await conn.executemany(
            "INSERT INTO alphaseq_bindings (sequence_id, vh_sequence, vl_sequence, target, binding_score, kd_nm) "
            "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (sequence_id) DO NOTHING",
            rows,
        )

        final_count = await conn.fetchval("SELECT COUNT(*) FROM alphaseq_bindings")
        print(f"Ingestion complete: {final_count:,} rows in alphaseq_bindings.")
        return final_count

    finally:
        await conn.close()


async def main():
    count = await ingest()
    print(f"Done. {count:,} antibody binding records available.")


if __name__ == "__main__":
    asyncio.run(main())
