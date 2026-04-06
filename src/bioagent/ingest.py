"""AlphaSeq dataset ingestion — download, extract, and load into Postgres."""

from __future__ import annotations

import asyncio
import csv
import io
import os
import tempfile
import zipfile
from pathlib import Path

import asyncpg
import httpx

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioagent:bioagent@localhost:5432/bioagent")

# MIT AlphaSeq Antibody Dataset — zipped CSV from GitHub
DATASET_URL = (
    "https://raw.githubusercontent.com/mit-ll/AlphaSeq_Antibody_Dataset/"
    "main/antibody_dataset_1/MITLL_AAlphaBio_Ab_Binding_dataset.csv.zip"
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

# CSV columns: POI, Sequence, Target, Assay, Replicate, Pred_affinity, HC, LC, CDRH1-3, CDRL1-3


async def download_dataset(dest_dir: Path) -> Path:
    """Download and extract the AlphaSeq CSV dataset."""
    zip_path = dest_dir / "alphaseq.csv.zip"
    print("Downloading AlphaSeq dataset from GitHub...")
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        resp = await client.get(DATASET_URL)
        resp.raise_for_status()
    zip_path.write_bytes(resp.content)
    size_mb = len(resp.content) / 1024 / 1024
    print(f"Downloaded {size_mb:.1f} MB")

    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV found in zip. Contents: {zf.namelist()}")
        zf.extract(csv_names[0], dest_dir)
        csv_path = dest_dir / csv_names[0]

    print(f"Extracted {csv_path.name}")
    return csv_path


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
            tmp = Path(tempfile.mkdtemp())
            data_path = await download_dataset(tmp)

        print(f"Reading {data_path}...")
        text = data_path.read_text()
        reader = csv.DictReader(io.StringIO(text))

        # Log actual columns for debugging
        fieldnames = reader.fieldnames or []
        print(f"CSV columns: {fieldnames}")

        rows = []
        for i, row in enumerate(reader):
            # Map actual AlphaSeq columns to our schema
            poi = row.get("POI") or f"seq_{i}"
            hc = row.get("HC") or row.get("Sequence") or ""
            lc = row.get("LC") or None
            target = row.get("Target") or "SARS-CoV-2"
            pred_affinity = row.get("Pred_affinity") or row.get("Binding_Score")

            if not hc and not pred_affinity:
                continue

            score = float(pred_affinity) if pred_affinity else 0.0
            lc = lc if lc else None

            rows.append((poi, hc, lc, target, score, None))

        print(f"Inserting {len(rows):,} rows...")

        # Batch insert for performance
        batch_size = 5000
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            await conn.executemany(
                "INSERT INTO alphaseq_bindings (sequence_id, vh_sequence, vl_sequence, target, binding_score, kd_nm) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (sequence_id) DO NOTHING",
                batch,
            )
            if (start + batch_size) % 50000 == 0 or start + batch_size >= len(rows):
                print(f"  Inserted {min(start + batch_size, len(rows)):,} / {len(rows):,}")

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
