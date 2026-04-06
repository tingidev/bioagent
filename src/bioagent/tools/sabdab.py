"""SAbDab tool — queries the Structural Antibody Database REST API."""

from __future__ import annotations

import httpx

from bioagent.models import AntibodyStructure

BASE_URL = "https://opig.stats.ox.ac.uk/webapps/newsabdab/sabdab"
SUMMARY_URL = f"{BASE_URL}/summary/all/"
SEARCH_URL = f"{BASE_URL}/search/"

# SAbDab provides a bulk CSV download and a search interface.
# We use the search endpoint with query parameters.


async def check_connectivity() -> bool:
    """Check if SAbDab API is reachable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BASE_URL}/about/")
            return resp.status_code == 200
    except Exception:
        return False


async def search_structures(
    *,
    antigen_name: str | None = None,
    species: str | None = None,
    method: str | None = None,
    max_resolution: float | None = None,
    cdr_h3_length_min: int | None = None,
    cdr_h3_length_max: int | None = None,
    limit: int = 50,
) -> tuple[list[AntibodyStructure], str]:
    """Search SAbDab for antibody structures matching criteria.

    Returns (results, reproducible_query).
    """
    # SAbDab search accepts query parameters via its REST-like interface
    # The actual API returns tab-separated data
    params: dict[str, str] = {"output": "json"}

    if antigen_name:
        params["antigen_name"] = antigen_name
    if species:
        params["species"] = species
    if method:
        params["method"] = method
    if max_resolution:
        params["resolution"] = str(max_resolution)

    url = f"{BASE_URL}/search/?"
    reproducible = f"GET {url} params={params}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    # SAbDab returns different formats; parse what we get
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else []

    results = []
    for entry in data[:limit]:
        structure = _parse_structure(entry)
        if structure is not None:
            if cdr_h3_length_min and structure.cdr_h3_length and structure.cdr_h3_length < cdr_h3_length_min:
                continue
            if cdr_h3_length_max and structure.cdr_h3_length and structure.cdr_h3_length > cdr_h3_length_max:
                continue
            results.append(structure)

    return results, reproducible


async def get_structure_by_pdb(pdb_code: str) -> tuple[AntibodyStructure | None, str]:
    """Look up a specific antibody structure by PDB code."""
    url = f"{BASE_URL}/search/?pdb={pdb_code}&output=json"
    reproducible = f"GET {url}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else []
    if not data:
        return None, reproducible

    return _parse_structure(data[0]), reproducible


async def search_by_antigen(
    antigen_query: str,
    *,
    limit: int = 50,
) -> tuple[list[AntibodyStructure], str]:
    """Search for antibody structures targeting a specific antigen."""
    return await search_structures(antigen_name=antigen_query, limit=limit)


async def get_summary_stats() -> tuple[dict, str]:
    """Get summary statistics about the SAbDab database."""
    url = f"{BASE_URL}/about/"
    reproducible = f"GET {url}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{BASE_URL}/stats/?output=json")

    try:
        data = resp.json()
        return data, reproducible
    except Exception:
        return {"note": "Stats endpoint returned non-JSON; database is reachable"}, reproducible


def _parse_structure(entry: dict) -> AntibodyStructure | None:
    """Parse a single SAbDab entry into our model."""
    try:
        pdb = entry.get("pdb") or entry.get("pdb_code") or entry.get("PDB")
        if not pdb:
            return None
        return AntibodyStructure(
            pdb_code=str(pdb).strip().upper(),
            antibody_name=entry.get("antibody_name") or entry.get("ab_name"),
            antigen_name=entry.get("antigen_name") or entry.get("ag_name") or entry.get("antigen"),
            antigen_chain=entry.get("antigen_chain") or entry.get("ag_chain"),
            resolution=_float_or_none(entry.get("resolution")),
            method=entry.get("method") or entry.get("exp_method"),
            species=entry.get("species") or entry.get("organism"),
            heavy_chain=entry.get("heavy_chain") or entry.get("Hchain"),
            light_chain=entry.get("light_chain") or entry.get("Lchain"),
            cdr_h3_length=_int_or_none(entry.get("cdr_h3_length") or entry.get("CDRH3_length")),
        )
    except Exception:
        return None


def _float_or_none(val: object) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _int_or_none(val: object) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None
