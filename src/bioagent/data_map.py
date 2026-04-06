"""Data map: source registry and entity/relationship definitions."""

from __future__ import annotations

from bioagent.models import (
    DataMap,
    DataSource,
    DataSourceType,
    EntityType,
    Relationship,
)

ALPHASEQ = DataSource(
    name="AlphaSeq",
    source_type=DataSourceType.LOCAL_DB,
    description=(
        "MIT Lincoln Lab antibody-antigen binding dataset. "
        "104,972 antibody sequences with quantitative binding scores "
        "against SARS-CoV-2 spike protein variants."
    ),
    entity_types=(EntityType.ANTIBODY, EntityType.TARGET),
    record_count=104_972,
)

SABDAB = DataSource(
    name="SAbDab",
    source_type=DataSourceType.REST_API,
    description=(
        "Structural Antibody Database from Oxford Protein Informatics Group. "
        "Curated antibody structures from the PDB with parsed annotations "
        "for CDR regions, species, resolution, and antigen binding."
    ),
    entity_types=(EntityType.ANTIBODY, EntityType.STRUCTURE),
    record_count=18_744,
    url="https://opig.stats.ox.ac.uk/webapps/newsabdab/sabdab",
)

CHEMBL = DataSource(
    name="ChEMBL",
    source_type=DataSourceType.REST_API,
    description=(
        "EMBL-EBI ChEMBL database. 2.4M compounds, 15.5K targets, "
        "and 21.1M bioactivity measurements from medicinal chemistry literature. "
        "Covers IC50, Ki, EC50, and other activity types."
    ),
    entity_types=(EntityType.COMPOUND, EntityType.TARGET, EntityType.BIOACTIVITY, EntityType.ASSAY),
    record_count=21_100_000,
    url="https://www.ebi.ac.uk/chembl/api/data",
)

ALL_SOURCES = (ALPHASEQ, SABDAB, CHEMBL)

RELATIONSHIPS = (
    Relationship(source=EntityType.TARGET, target=EntityType.ANTIBODY, label="binds"),
    Relationship(source=EntityType.ANTIBODY, target=EntityType.STRUCTURE, label="has structure"),
    Relationship(source=EntityType.TARGET, target=EntityType.BIOACTIVITY, label="tested against"),
    Relationship(source=EntityType.COMPOUND, target=EntityType.BIOACTIVITY, label="measured in"),
    Relationship(source=EntityType.BIOACTIVITY, target=EntityType.ASSAY, label="from assay"),
)


def build_data_map() -> DataMap:
    """Build the full data map of all connected sources and relationships."""
    return DataMap(sources=ALL_SOURCES, relationships=RELATIONSHIPS)


def describe_data_map(data_map: DataMap) -> str:
    """Produce a human-readable summary for the agent's context window."""
    lines = ["# Connected Data Sources\n"]

    for source in data_map.sources:
        count = f"{source.record_count:,}" if source.record_count else "unknown"
        lines.append(f"## {source.name} ({source.source_type.value})")
        lines.append(f"{source.description}")
        lines.append(f"Records: {count}")
        entities = ", ".join(e.value for e in source.entity_types)
        lines.append(f"Entity types: {entities}")
        if source.url:
            lines.append(f"Endpoint: {source.url}")
        lines.append("")

    lines.append("## Entity Relationships\n")
    for rel in data_map.relationships:
        lines.append(f"- {rel.source.value} --[{rel.label}]--> {rel.target.value}")

    return "\n".join(lines)
