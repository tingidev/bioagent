"""Domain models for BioAgent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Data Source Models ---


class DataSourceType(str, Enum):
    LOCAL_DB = "local_db"
    REST_API = "rest_api"


class EntityType(str, Enum):
    ANTIBODY = "antibody"
    TARGET = "target"
    STRUCTURE = "structure"
    BIOACTIVITY = "bioactivity"
    ASSAY = "assay"
    COMPOUND = "compound"


class Relationship(BaseModel, frozen=True):
    source: EntityType
    target: EntityType
    label: str


class DataSource(BaseModel, frozen=True):
    name: str
    source_type: DataSourceType
    description: str
    entity_types: tuple[EntityType, ...]
    record_count: int | None = None
    url: str | None = None


class DataMap(BaseModel, frozen=True):
    sources: tuple[DataSource, ...]
    relationships: tuple[Relationship, ...]
    built_at: datetime = Field(default_factory=datetime.now)


# --- AlphaSeq Models ---


class AntibodyBinding(BaseModel, frozen=True):
    """A single antibody-target binding measurement from AlphaSeq."""

    sequence_id: str
    vh_sequence: str
    vl_sequence: str | None = None
    target: str
    binding_score: float
    kd_nm: float | None = None
    dataset: str = "alphaseq"


# --- SAbDab Models ---


class AntibodyStructure(BaseModel, frozen=True):
    """An antibody structure entry from SAbDab."""

    pdb_code: str
    antibody_name: str | None = None
    antigen_name: str | None = None
    antigen_chain: str | None = None
    resolution: float | None = None
    method: str | None = None
    species: str | None = None
    heavy_chain: str | None = None
    light_chain: str | None = None
    cdr_h3_length: int | None = None


# --- ChEMBL Models ---


class BioactivityRecord(BaseModel, frozen=True):
    """A bioactivity measurement from ChEMBL."""

    molecule_chembl_id: str
    target_chembl_id: str
    target_name: str | None = None
    activity_type: str  # IC50, Ki, EC50, etc.
    value: float | None = None
    units: str | None = None
    assay_chembl_id: str | None = None
    assay_description: str | None = None


# --- Agent Trace Models ---


class AgentPhase(str, Enum):
    RESEARCH = "research"
    PLAN = "plan"
    EXECUTE = "execute"
    SYNTHESIZE = "synthesize"


class ToolCall(BaseModel, frozen=True):
    tool_name: str
    input_params: dict
    output_summary: str
    raw_output: dict | list | str
    duration_ms: int
    reproducible_query: str  # The exact API call or SQL query to reproduce this result


class TraceStep(BaseModel, frozen=True):
    step_number: int
    phase: AgentPhase
    description: str
    reasoning: str
    tool_call: ToolCall | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class Investigation(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    question: str
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    steps: tuple[TraceStep, ...] = ()
    report: str | None = None
    data_map: DataMap | None = None


class InvestigationRequest(BaseModel, frozen=True):
    question: str
    api_key: str | None = None


# --- API Response Models ---


class HealthResponse(BaseModel, frozen=True):
    status: str
    sources: dict[str, bool]
    alphaseq_count: int | None = None


class TraceEvent(BaseModel, frozen=True):
    """Server-sent event for streaming agent trace to frontend."""

    event_type: str  # phase_change, tool_call, reasoning, report, error
    data: dict
