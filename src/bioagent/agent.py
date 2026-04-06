"""Agent orchestration — research → plan → execute → synthesize."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from functools import partial
from typing import Any

import anthropic
import asyncpg

from bioagent.data_map import build_data_map, describe_data_map
from bioagent.models import AgentPhase, ToolCall, TraceEvent
from bioagent.trace import (
    add_step,
    complete_investigation,
    create_investigation,
    error_event,
    phase_event,
    report_event,
    step_to_event,
    store_investigation,
    thinking_event,
)
from bioagent.tools import alphaseq, chembl, sabdab, statistics

# Tool definitions for Claude
TOOLS = [
    {
        "name": "query_alphaseq_bindings",
        "description": (
            "Search the AlphaSeq antibody binding dataset (104,972 antibodies). "
            "Find antibodies by binding score range, sequence fragment, or get statistics. "
            "Data includes VH/VL sequences, targets, and binding scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_by_score", "search_by_sequence", "get_statistics", "get_top_binders", "get_targets"],
                    "description": "The query action to perform.",
                },
                "min_score": {"type": "number", "description": "Minimum binding score (for search_by_score)."},
                "max_score": {"type": "number", "description": "Maximum binding score (for search_by_score)."},
                "target": {"type": "string", "description": "Target name to filter by."},
                "sequence_fragment": {"type": "string", "description": "Amino acid sequence fragment to search for."},
                "limit": {"type": "integer", "description": "Max results to return (default 50)."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "query_sabdab",
        "description": (
            "Search the Structural Antibody Database (SAbDab, 18,744 structures). "
            "Find antibody crystal structures by antigen, species, method, resolution, or PDB code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_structures", "get_by_pdb", "search_by_antigen", "get_stats"],
                    "description": "The query action to perform.",
                },
                "antigen_name": {"type": "string", "description": "Antigen name to search for."},
                "pdb_code": {"type": "string", "description": "PDB code for direct lookup."},
                "species": {"type": "string", "description": "Species filter (e.g., 'human', 'mouse')."},
                "method": {"type": "string", "description": "Experimental method filter."},
                "max_resolution": {"type": "number", "description": "Maximum resolution in Angstroms."},
                "limit": {"type": "integer", "description": "Max results to return (default 50)."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "query_chembl",
        "description": (
            "Search the ChEMBL database (21.1M bioactivity measurements). "
            "Find targets, molecules, bioactivities, and assay information. "
            "Use this for drug discovery data, IC50/Ki/EC50 values, and target-compound relationships."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_target", "get_bioactivities", "get_molecule", "search_molecule", "get_assay"],
                    "description": "The query action to perform.",
                },
                "query": {"type": "string", "description": "Search query (for search_target, search_molecule)."},
                "target_chembl_id": {"type": "string", "description": "ChEMBL target ID (for get_bioactivities)."},
                "molecule_chembl_id": {"type": "string", "description": "ChEMBL molecule ID (for get_molecule)."},
                "assay_chembl_id": {"type": "string", "description": "ChEMBL assay ID (for get_assay)."},
                "activity_type": {"type": "string", "description": "Filter by activity type (IC50, Ki, EC50, etc.)."},
                "limit": {"type": "integer", "description": "Max results to return (default 50)."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "run_statistics",
        "description": (
            "Run statistical analysis on numeric data. Compute descriptive statistics, "
            "compare groups, or build frequency tables."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["describe", "compare_groups", "frequency_table"],
                    "description": "The analysis to perform.",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Numeric values for describe.",
                },
                "group_a": {"type": "array", "items": {"type": "number"}, "description": "First group for comparison."},
                "group_b": {"type": "array", "items": {"type": "number"}, "description": "Second group for comparison."},
                "label_a": {"type": "string", "description": "Label for first group."},
                "label_b": {"type": "string", "description": "Label for second group."},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categorical values for frequency table.",
                },
            },
            "required": ["action"],
        },
    },
]

SYSTEM_PROMPT = """You are BioAgent, an investigator that reasons across scientific databases to answer research questions about antibodies, drug targets, and bioactivity.

You have access to three connected data sources:

{data_map}

## How You Work

You MUST follow these four phases in strict order. Never skip a phase.

1. **RESEARCH**: Understand the question. Identify which data sources are relevant. Profile what data is available before diving in. Use tool calls to check connectivity and get statistics.
2. **PLAN**: Before executing any detailed queries, write out your investigation strategy. State: which databases you will query, in what order, what you expect to find, and how you will cross-reference results. Begin this section with "## Investigation Strategy" or "Let me plan". Do NOT skip this phase.
3. **EXECUTE**: Now run queries across databases. Cross-reference findings. Follow leads from one source to another.
4. **SYNTHESIZE**: Produce a structured report with findings, citations to actual data, and reproducible queries.

## Rules

- You MUST complete RESEARCH and PLAN before making any EXECUTE queries. No exceptions.
- Every claim must cite specific data: sequence IDs, PDB codes, ChEMBL IDs, or binding scores.
- State what you looked for and didn't find. Negative results matter.
- If a database is unreachable, note it and work with what's available.
- Keep your reasoning visible. Explain why you're querying each source.

## Cross-Referencing (Critical)

Your unique value is connecting findings across databases. Do NOT just search each database independently for the same keyword. Instead:

- Take SPECIFIC results from one source and use them to query another. For example: find the top binders in AlphaSeq, note their target (MIT_Target = SARS-CoV-2 spike protein), then search SAbDab for structures of antibodies targeting spike protein, then search ChEMBL for compounds with bioactivity against spike protein targets.
- Compare metrics across sources: AlphaSeq binding scores vs ChEMBL IC50/Ki values measure different aspects of the same biology. Note similarities and differences.
- When you find structural data in SAbDab (PDB codes, CDR H3 lengths, resolution), relate it back to binding data from AlphaSeq. Do antibodies with known structures show different binding characteristics?
- Always state explicitly what you are cross-referencing and why. "I found X in AlphaSeq. Now I will search SAbDab for Y because Z."

## Adaptive Reasoning

After each tool result, briefly reflect:
- Did you find what you expected? If not, why?
- Does this change your investigation plan? State any pivots explicitly.
- Did you discover something unexpected worth following up?

For example: "I expected multiple targets in AlphaSeq but found that 40K records target MIT_Target (spike protein). This concentration is notable. Let me check whether SAbDab has structural diversity for spike-targeting antibodies, or if they converge on similar binding modes."

## Output Format

When you've completed your investigation, write a structured report in markdown with:
- **Question**: what was asked
- **Approach**: what you investigated and why
- **Findings**: organised by theme, with specific data citations
- **Cross-Database Connections**: insights from combining sources (this is the most important section)
- **Limitations**: what couldn't be answered and why
- **Reproducibility**: key queries that can be re-run independently
"""


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    pool: asyncpg.Pool | None,
) -> tuple[Any, str]:
    """Execute a tool call and return (result, reproducible_query)."""
    if tool_name == "query_alphaseq_bindings":
        if pool is None:
            return {"error": "AlphaSeq database not connected"}, "N/A"
        action = tool_input["action"]
        limit = tool_input.get("limit", 50)
        target = tool_input.get("target")

        if action == "search_by_score":
            results, query = await alphaseq.search_by_binding_score(
                pool, min_score=tool_input.get("min_score", 0.0),
                max_score=tool_input.get("max_score"),
                target=target, limit=limit,
            )
            return [r.model_dump() for r in results], query
        elif action == "search_by_sequence":
            results, query = await alphaseq.search_by_sequence(
                pool, sequence_fragment=tool_input["sequence_fragment"], limit=limit,
            )
            return [r.model_dump() for r in results], query
        elif action == "get_statistics":
            return await alphaseq.get_binding_statistics(pool, target=target)
        elif action == "get_top_binders":
            results, query = await alphaseq.get_top_binders(pool, target=target, limit=limit)
            return [r.model_dump() for r in results], query
        elif action == "get_targets":
            return await alphaseq.get_targets(pool)

    elif tool_name == "query_sabdab":
        action = tool_input["action"]
        limit = tool_input.get("limit", 50)

        if action == "search_structures":
            results, query = await sabdab.search_structures(
                antigen_name=tool_input.get("antigen_name"),
                species=tool_input.get("species"),
                method=tool_input.get("method"),
                max_resolution=tool_input.get("max_resolution"),
                limit=limit,
            )
            return [r.model_dump() for r in results], query
        elif action == "get_by_pdb":
            result, query = await sabdab.get_structure_by_pdb(tool_input["pdb_code"])
            return result.model_dump() if result else None, query
        elif action == "search_by_antigen":
            results, query = await sabdab.search_by_antigen(
                tool_input["antigen_name"], limit=limit,
            )
            return [r.model_dump() for r in results], query
        elif action == "get_stats":
            return await sabdab.get_summary_stats()

    elif tool_name == "query_chembl":
        action = tool_input["action"]
        limit = tool_input.get("limit", 50)

        if action == "search_target":
            return await chembl.search_target(tool_input["query"], limit=limit)
        elif action == "get_bioactivities":
            results, query = await chembl.get_bioactivities_for_target(
                tool_input["target_chembl_id"],
                activity_type=tool_input.get("activity_type"),
                limit=limit,
            )
            return [r.model_dump() for r in results], query
        elif action == "get_molecule":
            return await chembl.get_molecule(tool_input["molecule_chembl_id"])
        elif action == "search_molecule":
            return await chembl.search_molecule(tool_input["query"], limit=limit)
        elif action == "get_assay":
            return await chembl.get_assay(tool_input["assay_chembl_id"])

    elif tool_name == "run_statistics":
        action = tool_input["action"]
        reproducible = f"statistics.{action}({json.dumps(tool_input)})"

        if action == "describe":
            return statistics.describe(tool_input.get("values", [])), reproducible
        elif action == "compare_groups":
            return statistics.compare_groups(
                tool_input.get("group_a", []),
                tool_input.get("group_b", []),
                tool_input.get("label_a", "A"),
                tool_input.get("label_b", "B"),
            ), reproducible
        elif action == "frequency_table":
            return statistics.frequency_table(tool_input.get("categories", [])), reproducible

    return {"error": f"Unknown tool/action: {tool_name}/{tool_input.get('action')}"}, "N/A"


def _summarize_output(result: Any) -> str:
    """Create a brief summary of tool output for the trace."""
    if isinstance(result, list):
        return f"Returned {len(result)} results"
    if isinstance(result, dict):
        if "error" in result:
            return f"Error: {result['error']}"
        if "total" in result or "count" in result:
            return f"Stats: {json.dumps(result)}"
        return f"Returned object with keys: {', '.join(result.keys())}"
    return str(result)[:200]


def _create_client(
    api_key: str | None = None,
) -> tuple[anthropic.Anthropic | anthropic.AnthropicBedrock, str]:
    """Create an Anthropic client. Returns (client, model_id).

    Priority: explicit api_key > ANTHROPIC_API_KEY env var > Bedrock (AWS creds).
    """
    import os

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return anthropic.Anthropic(api_key=key), "claude-sonnet-4-20250514"

    return (
        anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
    )


async def investigate(
    question: str,
    pool: asyncpg.Pool | None,
    *,
    api_key: str | None = None,
) -> AsyncGenerator[TraceEvent, None]:
    """Run an investigation and yield trace events via SSE.

    This is the core agent loop.
    """
    data_map = build_data_map()
    investigation = create_investigation(question)

    # Build system prompt with data map context
    system = SYSTEM_PROMPT.format(data_map=describe_data_map(data_map))

    client, model = _create_client(api_key)

    messages: list[dict] = [{"role": "user", "content": question}]
    current_phase = AgentPhase.RESEARCH

    yield phase_event(current_phase)

    max_turns = 50
    for turn in range(max_turns):
        yield thinking_event(turn + 1)
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(
                    client.messages.create,
                    model=model,
                    max_tokens=4096,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                ),
            )
        except anthropic.AuthenticationError:
            yield error_event("API authentication failed. The API key may be invalid or expired.")
            return
        except anthropic.RateLimitError:
            yield error_event("Rate limit reached. Please wait a moment and try again.")
            return
        except anthropic.BadRequestError as e:
            msg = e.message if hasattr(e, "message") else str(e)
            if "credit" in msg.lower() or "billing" in msg.lower():
                yield error_event("The AI service has insufficient credits. The site administrator has been notified.")
            else:
                yield error_event(f"Invalid request to the AI model: {msg}")
            return
        except anthropic.APIStatusError as e:
            # Catch billing/credits errors and other status errors
            msg = e.message if hasattr(e, "message") else str(e)
            if "credit" in msg.lower() or "billing" in msg.lower():
                yield error_event("The AI service has insufficient credits. The site administrator has been notified.")
            elif "overloaded" in msg.lower():
                yield error_event("The AI model is currently overloaded. Please try again in a few minutes.")
            else:
                yield error_event(f"AI service error ({e.status_code}): {msg}")
            return
        except anthropic.APIConnectionError:
            yield error_event("Could not connect to the AI service. Please try again later.")
            return

        # Process response content blocks
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                text = block.text
                assistant_content.append({"type": "text", "text": text})

                # Detect phase transitions from agent text
                new_phase = _detect_phase(text)
                if new_phase and new_phase != current_phase:
                    current_phase = new_phase
                    yield phase_event(current_phase)

                # Add reasoning step to trace
                investigation = add_step(
                    investigation,
                    phase=current_phase,
                    description=f"Agent reasoning (turn {turn + 1})",
                    reasoning=text[:500],
                )
                yield step_to_event(investigation.steps[-1])

            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

                # Execute the tool
                start = time.monotonic()
                try:
                    result, reproducible_query = await execute_tool(block.name, block.input, pool)
                except Exception as e:
                    result = {"error": str(e)}
                    reproducible_query = "N/A (error)"
                duration_ms = int((time.monotonic() - start) * 1000)

                tool_call = ToolCall(
                    tool_name=block.name,
                    input_params=block.input,
                    output_summary=_summarize_output(result),
                    raw_output=result if isinstance(result, (dict, list, str)) else str(result),
                    duration_ms=duration_ms,
                    reproducible_query=reproducible_query,
                )

                investigation = add_step(
                    investigation,
                    phase=current_phase,
                    description=f"Tool call: {block.name}",
                    reasoning=f"Calling {block.name} with {json.dumps(block.input)[:200]}",
                    tool_call=tool_call,
                )
                yield step_to_event(investigation.steps[-1])

                # Add tool result to messages
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str)[:10000],
                    }],
                })
                assistant_content = []

        # If no tool use, add assistant message and check if done
        if response.stop_reason == "end_turn":
            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})

            # Extract report from last text block
            report_text = ""
            for block in response.content:
                if block.type == "text":
                    report_text = block.text

            investigation = complete_investigation(investigation, report_text)
            store_investigation(investigation)

            yield phase_event(AgentPhase.SYNTHESIZE)
            yield report_event(report_text)
            return

        # If we exhausted tool calls for this turn but aren't done, continue
        if not assistant_content:
            continue
        if response.stop_reason != "tool_use":
            messages.append({"role": "assistant", "content": assistant_content})

    # Max turns reached
    yield error_event("Investigation reached maximum number of turns. Partial results may be available.")
    investigation = complete_investigation(investigation, "Investigation incomplete — max turns reached.")
    store_investigation(investigation)


def _detect_phase(text: str) -> AgentPhase | None:
    """Detect phase transitions from agent text."""
    text_lower = text.lower()[:200]
    if any(w in text_lower for w in ["let me plan", "investigation strategy", "my plan", "i'll plan"]):
        return AgentPhase.PLAN
    if any(w in text_lower for w in ["let me query", "let me search", "executing", "i'll now query", "let me check"]):
        return AgentPhase.EXECUTE
    if any(w in text_lower for w in ["## findings", "## report", "synthesiz", "in summary", "## question"]):
        return AgentPhase.SYNTHESIZE
    return None
