"""ChEMBL tool — queries the EMBL-EBI ChEMBL REST API."""

from __future__ import annotations

import httpx

from bioagent.models import BioactivityRecord

BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
HEADERS = {"Accept": "application/json"}


async def check_connectivity() -> bool:
    """Check if ChEMBL API is reachable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{BASE_URL}/status.json", headers=HEADERS)
            return resp.status_code == 200
    except Exception:
        return False


async def search_target(
    query: str,
    *,
    limit: int = 10,
) -> tuple[list[dict], str]:
    """Search ChEMBL for targets by name or keyword.

    Returns (results, reproducible_query).
    """
    url = f"{BASE_URL}/target/search.json"
    params = {"q": query, "limit": str(limit)}
    reproducible = f"GET {url}?q={query}&limit={limit}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params=params, headers=HEADERS)
        resp.raise_for_status()

    data = resp.json()
    targets = data.get("targets", [])
    results = [
        {
            "target_chembl_id": t["target_chembl_id"],
            "pref_name": t.get("pref_name"),
            "organism": t.get("organism"),
            "target_type": t.get("target_type"),
        }
        for t in targets
    ]
    return results, reproducible


async def get_bioactivities_for_target(
    target_chembl_id: str,
    *,
    activity_type: str | None = None,
    limit: int = 50,
) -> tuple[list[BioactivityRecord], str]:
    """Get bioactivity measurements for a specific ChEMBL target.

    Returns (results, reproducible_query).
    """
    url = f"{BASE_URL}/activity.json"
    params: dict[str, str] = {
        "target_chembl_id": target_chembl_id,
        "limit": str(limit),
    }
    if activity_type:
        params["standard_type"] = activity_type

    reproducible = f"GET {url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers=HEADERS)
        resp.raise_for_status()

    data = resp.json()
    activities = data.get("activities", [])
    results = [
        BioactivityRecord(
            molecule_chembl_id=a["molecule_chembl_id"],
            target_chembl_id=a.get("target_chembl_id", target_chembl_id),
            target_name=a.get("target_pref_name"),
            activity_type=a.get("standard_type", "unknown"),
            value=_float_or_none(a.get("standard_value")),
            units=a.get("standard_units"),
            assay_chembl_id=a.get("assay_chembl_id"),
            assay_description=a.get("assay_description"),
        )
        for a in activities
        if a.get("molecule_chembl_id")
    ]
    return results, reproducible


async def get_molecule(molecule_chembl_id: str) -> tuple[dict | None, str]:
    """Look up a molecule by its ChEMBL ID."""
    url = f"{BASE_URL}/molecule/{molecule_chembl_id}.json"
    reproducible = f"GET {url}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 404:
            return None, reproducible
        resp.raise_for_status()

    data = resp.json()
    return {
        "molecule_chembl_id": data.get("molecule_chembl_id"),
        "pref_name": data.get("pref_name"),
        "molecule_type": data.get("molecule_type"),
        "max_phase": data.get("max_phase"),
        "molecular_formula": data.get("molecule_properties", {}).get("molecular_formula") if data.get("molecule_properties") else None,
    }, reproducible


async def search_molecule(
    query: str,
    *,
    limit: int = 10,
) -> tuple[list[dict], str]:
    """Search ChEMBL for molecules by name."""
    url = f"{BASE_URL}/molecule/search.json"
    params = {"q": query, "limit": str(limit)}
    reproducible = f"GET {url}?q={query}&limit={limit}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params=params, headers=HEADERS)
        resp.raise_for_status()

    data = resp.json()
    molecules = data.get("molecules", [])
    results = [
        {
            "molecule_chembl_id": m["molecule_chembl_id"],
            "pref_name": m.get("pref_name"),
            "molecule_type": m.get("molecule_type"),
            "max_phase": m.get("max_phase"),
        }
        for m in molecules
    ]
    return results, reproducible


async def get_assay(assay_chembl_id: str) -> tuple[dict | None, str]:
    """Look up an assay by its ChEMBL ID."""
    url = f"{BASE_URL}/assay/{assay_chembl_id}.json"
    reproducible = f"GET {url}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 404:
            return None, reproducible
        resp.raise_for_status()

    data = resp.json()
    return {
        "assay_chembl_id": data.get("assay_chembl_id"),
        "description": data.get("description"),
        "assay_type": data.get("assay_type"),
        "assay_organism": data.get("assay_organism"),
        "target_chembl_id": data.get("target_chembl_id"),
    }, reproducible


def _float_or_none(val: object) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None
