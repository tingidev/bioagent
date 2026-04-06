"""AlphaSeq tool — queries antibody binding data from local Postgres."""

from __future__ import annotations

import asyncpg

from bioagent.models import AntibodyBinding

DEFAULT_DATABASE_URL = "postgresql://bioagent:bioagent@localhost:5432/bioagent"


async def get_pool(database_url: str = DEFAULT_DATABASE_URL) -> asyncpg.Pool:
    """Create a connection pool."""
    return await asyncpg.create_pool(database_url, min_size=1, max_size=5)


async def check_connectivity(pool: asyncpg.Pool) -> bool:
    """Check if AlphaSeq table exists and has data."""
    try:
        row = await pool.fetchval("SELECT COUNT(*) FROM alphaseq_bindings")
        return row is not None and row > 0
    except Exception:
        return False


async def get_record_count(pool: asyncpg.Pool) -> int | None:
    """Get total number of binding records."""
    try:
        return await pool.fetchval("SELECT COUNT(*) FROM alphaseq_bindings")
    except Exception:
        return None


async def search_by_binding_score(
    pool: asyncpg.Pool,
    *,
    min_score: float = 0.0,
    max_score: float | None = None,
    target: str | None = None,
    limit: int = 50,
) -> tuple[list[AntibodyBinding], str]:
    """Find antibodies by binding score range.

    Returns (results, reproducible_query).
    """
    conditions = ["binding_score >= $1"]
    params: list[object] = [min_score]
    idx = 2

    if max_score is not None:
        conditions.append(f"binding_score <= ${idx}")
        params.append(max_score)
        idx += 1

    if target is not None:
        conditions.append(f"target = ${idx}")
        params.append(target)
        idx += 1

    where = " AND ".join(conditions)
    query = (
        f"SELECT sequence_id, vh_sequence, vl_sequence, target, binding_score, kd_nm "
        f"FROM alphaseq_bindings WHERE {where} "
        f"ORDER BY binding_score DESC LIMIT ${idx}"
    )
    params.append(limit)

    rows = await pool.fetch(query, *params)
    results = [
        AntibodyBinding(
            sequence_id=r["sequence_id"],
            vh_sequence=r["vh_sequence"],
            vl_sequence=r["vl_sequence"],
            target=r["target"],
            binding_score=r["binding_score"],
            kd_nm=r["kd_nm"],
        )
        for r in rows
    ]

    reproducible = f"SELECT * FROM alphaseq_bindings WHERE {where} ORDER BY binding_score DESC LIMIT {limit}"
    return results, reproducible


async def search_by_sequence(
    pool: asyncpg.Pool,
    *,
    sequence_fragment: str,
    limit: int = 50,
) -> tuple[list[AntibodyBinding], str]:
    """Find antibodies containing a sequence fragment in VH or VL chain."""
    query = (
        "SELECT sequence_id, vh_sequence, vl_sequence, target, binding_score, kd_nm "
        "FROM alphaseq_bindings "
        "WHERE vh_sequence LIKE $1 OR vl_sequence LIKE $1 "
        "ORDER BY binding_score DESC LIMIT $2"
    )
    pattern = f"%{sequence_fragment}%"
    rows = await pool.fetch(query, pattern, limit)
    results = [
        AntibodyBinding(
            sequence_id=r["sequence_id"],
            vh_sequence=r["vh_sequence"],
            vl_sequence=r["vl_sequence"],
            target=r["target"],
            binding_score=r["binding_score"],
            kd_nm=r["kd_nm"],
        )
        for r in rows
    ]

    reproducible = (
        f"SELECT * FROM alphaseq_bindings "
        f"WHERE vh_sequence LIKE '%{sequence_fragment}%' OR vl_sequence LIKE '%{sequence_fragment}%' "
        f"ORDER BY binding_score DESC LIMIT {limit}"
    )
    return results, reproducible


async def get_binding_statistics(
    pool: asyncpg.Pool,
    *,
    target: str | None = None,
) -> tuple[dict, str]:
    """Get summary statistics for binding scores."""
    where = ""
    params: list[object] = []
    if target is not None:
        where = "WHERE target = $1"
        params.append(target)

    query = (
        f"SELECT COUNT(*) as total, "
        f"AVG(binding_score) as mean_score, "
        f"STDDEV(binding_score) as std_score, "
        f"MIN(binding_score) as min_score, "
        f"MAX(binding_score) as max_score, "
        f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY binding_score) as median_score "
        f"FROM alphaseq_bindings {where}"
    )

    row = await pool.fetchrow(query, *params)
    stats = {
        "total": row["total"],
        "mean_score": float(row["mean_score"]) if row["mean_score"] else None,
        "std_score": float(row["std_score"]) if row["std_score"] else None,
        "min_score": float(row["min_score"]) if row["min_score"] else None,
        "max_score": float(row["max_score"]) if row["max_score"] else None,
        "median_score": float(row["median_score"]) if row["median_score"] else None,
    }

    reproducible = f"SELECT COUNT(*), AVG(binding_score), STDDEV(binding_score), MIN(binding_score), MAX(binding_score) FROM alphaseq_bindings {where}"
    return stats, reproducible


async def get_top_binders(
    pool: asyncpg.Pool,
    *,
    target: str | None = None,
    limit: int = 20,
) -> tuple[list[AntibodyBinding], str]:
    """Get the strongest binders by binding score."""
    return await search_by_binding_score(pool, min_score=0.0, target=target, limit=limit)


async def get_targets(pool: asyncpg.Pool) -> tuple[list[dict], str]:
    """List all unique targets and their antibody counts."""
    query = (
        "SELECT target, COUNT(*) as antibody_count, AVG(binding_score) as avg_score "
        "FROM alphaseq_bindings GROUP BY target ORDER BY antibody_count DESC"
    )
    rows = await pool.fetch(query)
    results = [
        {"target": r["target"], "antibody_count": r["antibody_count"], "avg_score": float(r["avg_score"])}
        for r in rows
    ]
    return results, query
