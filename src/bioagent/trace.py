"""Trace module — audit trail for agent investigations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from bioagent.models import (
    AgentPhase,
    Investigation,
    ToolCall,
    TraceEvent,
    TraceStep,
)


def create_investigation(question: str) -> Investigation:
    """Start a new investigation."""
    return Investigation(question=question)


def add_step(
    investigation: Investigation,
    *,
    phase: AgentPhase,
    description: str,
    reasoning: str,
    tool_call: ToolCall | None = None,
) -> Investigation:
    """Add a trace step to the investigation (returns new Investigation)."""
    step = TraceStep(
        step_number=len(investigation.steps) + 1,
        phase=phase,
        description=description,
        reasoning=reasoning,
        tool_call=tool_call,
    )
    return Investigation(
        id=investigation.id,
        question=investigation.question,
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        steps=(*investigation.steps, step),
        report=investigation.report,
        data_map=investigation.data_map,
    )


def complete_investigation(investigation: Investigation, report: str) -> Investigation:
    """Mark investigation as complete with final report."""
    return Investigation(
        id=investigation.id,
        question=investigation.question,
        started_at=investigation.started_at,
        completed_at=datetime.now(),
        steps=investigation.steps,
        report=report,
        data_map=investigation.data_map,
    )


def step_to_event(step: TraceStep) -> TraceEvent:
    """Convert a trace step into an SSE event."""
    data: dict = {
        "step_number": step.step_number,
        "phase": step.phase.value,
        "description": step.description,
        "reasoning": step.reasoning,
        "timestamp": step.timestamp.isoformat(),
    }
    if step.tool_call:
        data["tool_call"] = {
            "tool_name": step.tool_call.tool_name,
            "input_params": step.tool_call.input_params,
            "output_summary": step.tool_call.output_summary,
            "duration_ms": step.tool_call.duration_ms,
            "reproducible_query": step.tool_call.reproducible_query,
        }
    return TraceEvent(event_type="trace_step", data=data)


def phase_event(phase: AgentPhase) -> TraceEvent:
    """Create a phase change event."""
    return TraceEvent(event_type="phase_change", data={"phase": phase.value})


def report_event(report: str) -> TraceEvent:
    """Create a report event."""
    return TraceEvent(event_type="report", data={"report": report})


def thinking_event(turn: int) -> TraceEvent:
    """Create a thinking event — tells the frontend the LLM is processing."""
    return TraceEvent(event_type="thinking", data={"turn": turn})


def error_event(message: str) -> TraceEvent:
    """Create an error event."""
    return TraceEvent(event_type="error", data={"message": message})


# In-memory store for completed investigations
_investigations: dict[UUID, Investigation] = {}


def store_investigation(investigation: Investigation) -> None:
    """Store a completed investigation."""
    _investigations[investigation.id] = investigation


def get_investigation(investigation_id: UUID) -> Investigation | None:
    """Retrieve a stored investigation."""
    return _investigations.get(investigation_id)
