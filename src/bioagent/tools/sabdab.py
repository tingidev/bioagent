"""SAbDab tool — queries the Structural Antibody Database REST API."""

from __future__ import annotations

import csv
import io
import re

import httpx

from bioagent.models import AntibodyStructure

BASE_URL = "https://opig.stats.ox.ac.uk/webapps/sabdab-sabpred/sabdab"
SEARCH_URL = f"{BASE_URL}/search/"
SUMMARY_URL = f"{BASE_URL}/summary"

# Default form values required by SAbDab's advanced search.
_DEFAULT_PARAMS: dict[str, str] = {
    "ABtype": "All",
    "method": "All",
    "species": "All",
    "resolution": "",
    "rfactor": "",
    "antigen": "All",
    "ltype": "All",
    "constantregion": "All",
    "affinity": "All",
    "isin_covabdab": "All",
    "isin_therasabdab": "All",
    "chothiapos": "",
    "restype": "ALA",
}


async def check_connectivity() -> bool:
    """Check if SAbDab API is reachable."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
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
    params = dict(_DEFAULT_PARAMS)

    if species:
        params["species"] = species
    if method:
        params["method"] = method
    if max_resolution:
        params["resolution"] = str(max_resolution)
    if antigen_name:
        params["field_0"] = "Antigens"
        params["keyword_0"] = antigen_name

    reproducible = f"GET {SEARCH_URL} params={params}"

    rows = await _search_and_fetch_tsv(params)

    results = []
    for row in rows[:limit]:
        structure = _parse_structure(row)
        if structure is None:
            continue
        if cdr_h3_length_min and structure.cdr_h3_length and structure.cdr_h3_length < cdr_h3_length_min:
            continue
        if cdr_h3_length_max and structure.cdr_h3_length and structure.cdr_h3_length > cdr_h3_length_max:
            continue
        results.append(structure)

    return results, reproducible


async def get_structure_by_pdb(pdb_code: str) -> tuple[AntibodyStructure | None, str]:
    """Look up a specific antibody structure by PDB code."""
    url = f"{SUMMARY_URL}/{pdb_code.lower()}/"
    reproducible = f"GET {url}"

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    rows = _parse_tsv(resp.text)
    if not rows:
        return None, reproducible

    return _parse_structure(rows[0]), reproducible


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

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)

    if resp.status_code == 200:
        return {"note": "SAbDab database is reachable and operational"}, reproducible
    return {"note": "SAbDab returned non-200 status"}, reproducible


async def _search_and_fetch_tsv(params: dict[str, str]) -> list[dict[str, str]]:
    """Execute a search and fetch the result-set TSV via the summary endpoint.

    SAbDab's search returns an HTML page. We extract the timestamped
    summary URL from it, then fetch that for structured TSV data.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(SEARCH_URL, params=params)
        resp.raise_for_status()

    # Extract the timestamped result-set summary URL
    match = re.search(r'summary/(\d{8}_\d+)/', resp.text)
    if not match:
        return []

    summary_id = match.group(1)
    summary_url = f"{SUMMARY_URL}/{summary_id}/"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(summary_url)
        resp.raise_for_status()

    return _parse_tsv(resp.text)


def _parse_tsv(text: str) -> list[dict[str, str]]:
    """Parse tab-separated values into a list of dicts."""
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    return list(reader)


def _parse_structure(entry: dict) -> AntibodyStructure | None:
    """Parse a single SAbDab TSV row into our model."""
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
            species=entry.get("heavy_species") or entry.get("species") or entry.get("organism"),
            heavy_chain=entry.get("heavy_chain") or entry.get("Hchain"),
            light_chain=entry.get("light_chain") or entry.get("Lchain"),
            cdr_h3_length=_int_or_none(entry.get("cdr_h3_length") or entry.get("CDRH3_length")),
        )
    except Exception:
        return None


def _float_or_none(val: object) -> float | None:
    try:
        return float(val) if val is not None and val != "None" and val != "NA" else None
    except (ValueError, TypeError):
        return None


def _int_or_none(val: object) -> int | None:
    try:
        return int(val) if val is not None and val != "None" and val != "NA" else None
    except (ValueError, TypeError):
        return None
