"""Agent orchestration — multi-agent handoffs across RPES phases."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import anthropic
import asyncpg

from bioagent.data_map import build_data_map, describe_data_map
from bioagent.models import AgentPhase, Investigation, ToolCall, TraceEvent
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

# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------

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
                "limit": {"type": "integer", "description": "Max results to return (default 20)."},
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
            "Run statistical analysis on data collected from other tools. "
            "Compute descriptive statistics, compare groups with effect size, "
            "test correlations, detect outliers, rank items, cross-tabulate categories, "
            "or build frequency tables. Use this to analyse data, not just summarise it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "describe", "compare_groups", "frequency_table",
                        "correlation", "outlier_detection", "rank_and_filter", "cross_tabulate",
                    ],
                    "description": "The analysis to perform.",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Numeric values (for describe, outlier_detection).",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for each value (for outlier_detection, rank_and_filter). E.g. sequence IDs.",
                },
                "group_a": {"type": "array", "items": {"type": "number"}, "description": "First group for comparison."},
                "group_b": {"type": "array", "items": {"type": "number"}, "description": "Second group for comparison."},
                "label_a": {"type": "string", "description": "Label for first group."},
                "label_b": {"type": "string", "description": "Label for second group."},
                "xs": {"type": "array", "items": {"type": "number"}, "description": "X values for correlation."},
                "ys": {"type": "array", "items": {"type": "number"}, "description": "Y values for correlation."},
                "top_n": {"type": "integer", "description": "Number of top items to return (for rank_and_filter, default 10)."},
                "bottom_n": {"type": "integer", "description": "Number of bottom items to return (for rank_and_filter, default 0)."},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categorical values for frequency table.",
                },
                "row_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Row categories for cross_tabulate.",
                },
                "col_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column categories for cross_tabulate.",
                },
                "row_label": {"type": "string", "description": "Label for row dimension in cross_tabulate."},
                "col_label": {"type": "string", "description": "Label for column dimension in cross_tabulate."},
            },
            "required": ["action"],
        },
    },
]

# ---------------------------------------------------------------------------
# Phase-specific system prompts
# ---------------------------------------------------------------------------

RESEARCH_PROMPT = """You are BioAgent (Research Phase). Your job is to understand the data landscape before any detailed investigation begins.

You have access to these scientific databases:

{data_map}

## Your Task

Given the research question, explore what data is available:

1. Call get_statistics and get_targets on AlphaSeq to understand the dataset shape
2. Run a simple query on SAbDab and ChEMBL to check they are reachable and see what data they hold
3. Note the record counts, available targets, and data types in each source
4. Identify which sources are most relevant to the question

## Rules

- Only run exploratory queries (statistics, targets, basic searches). Do NOT run detailed analytical queries yet.
- Keep it factual. Do not hypothesise or plan yet.

## Output

End your response with a clearly labelled section:

### Research Summary
- What data is available in each source
- Which sources are relevant to this question
- Any connectivity issues encountered
- Key observations about data shape (targets, record counts, score distributions)"""

PLAN_PROMPT = """You are BioAgent (Plan Phase). You receive a research summary and must design an investigation strategy. You have NO access to tools or databases.

## Research Question

{question}

## Research Summary (from previous phase)

{research_summary}

## Your Task

Write a concrete investigation plan. Include:

1. **Hypothesis**: Based on the research summary, what do you expect to find?
2. **Query sequence**: Which databases to query, in what order, and with what parameters. Be specific with tool names, actions, and parameter values.
3. **Cross-references**: Specific connections to attempt between databases. For example: "Take top binders from AlphaSeq (MIT_Target), then search SAbDab for structures targeting SARS-CoV-2 spike protein, then search ChEMBL for bioactivity data against spike protein targets."
4. **Success criteria**: What would a good answer look like? What would surprise you?

Be precise. The Execute phase agent will follow your plan step by step."""

EXECUTE_PROMPT = """You are BioAgent (Execute Phase). You have a research summary and an investigation plan. Your job is to execute the plan by querying databases and cross-referencing findings.

You have access to these scientific databases:

{data_map}

## Research Question

{question}

## Research Summary

{research_summary}

## Investigation Plan (follow this)

{plan}

## Rules

- Follow the plan step by step, but adapt if you discover something unexpected
- Before each tool call, state what you are doing and why
- After each result, briefly reflect: did this match your expectation? Does it change the plan?
- When you find something in one database, use it to query another. Do NOT search databases in isolation.
- Every claim must cite specific data: sequence IDs, PDB codes, ChEMBL IDs, or binding scores
- State what you looked for and didn't find. Negative results matter.

## Cross-Referencing (Critical)

Your unique value is connecting findings across databases:
- Take SPECIFIC results from one source and use them to query another
- Compare metrics across sources: AlphaSeq binding scores vs ChEMBL IC50/Ki values measure different aspects of the same biology
- When you find structural data in SAbDab, relate it back to binding data from AlphaSeq
- Always state explicitly what you are cross-referencing and why

## Analysis

Where the data supports it, use statistical tools to strengthen your findings:

- **compare_groups** to test group differences with effect size
- **correlation** to test relationships between variables
- **outlier_detection** to find exceptional data points
- **rank_and_filter** to identify top performers

Pick 1-2 analyses that directly answer the research question. Do not run every possible analysis — be selective and purposeful. State your hypothesis before each analysis, then interpret the result.

## Efficiency

Aim for **8-12 tool calls total**. Budget roughly:
- 4-6 data retrieval queries (the essential ones from the plan)
- 2-3 cross-referencing queries
- 1-2 statistical analyses

When you have enough data to answer the question, STOP and write your findings. Not every result needs a follow-up query — a focused answer with strong cross-references is better than an exhaustive survey of every data point.

## Output

End your response with a clearly labelled section:

### Execution Findings
Organised by theme, with specific data citations, statistical results, and cross-database connections noted."""

SYNTHESISE_PROMPT = """You are BioAgent (Synthesise Phase). You receive the full investigation context and must write the final report. You have NO access to tools or databases.

## Research Question

{question}

## Research Summary

{research_summary}

## Investigation Plan

{plan}

## Execution Findings

{execution_findings}

## Your Task

Write a structured report in markdown:

- **Question**: What was asked
- **Approach**: What was investigated and why
- **Findings**: Organised by theme, with specific data citations
- **Cross-Database Connections**: Insights from combining sources (this is the most important section)
- **Limitations**: What couldn't be answered and why
- **Reproducibility**: Key queries that can be re-run independently

Do not repeat raw data. Interpret, connect, and conclude. Every claim must reference specific data points from the execution findings."""


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


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
        limit = tool_input.get("limit", 20)
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
        elif action == "correlation":
            return statistics.correlation(
                tool_input.get("xs", []),
                tool_input.get("ys", []),
            ), reproducible
        elif action == "outlier_detection":
            return statistics.outlier_detection(
                tool_input.get("values", []),
                labels=tool_input.get("labels"),
            ), reproducible
        elif action == "rank_and_filter":
            return statistics.rank_and_filter(
                tool_input.get("values", []),
                tool_input.get("labels", []),
                top_n=tool_input.get("top_n", 10),
                bottom_n=tool_input.get("bottom_n", 0),
            ), reproducible
        elif action == "cross_tabulate":
            return statistics.cross_tabulate(
                tool_input.get("row_categories", []),
                tool_input.get("col_categories", []),
                row_label=tool_input.get("row_label", "row"),
                col_label=tool_input.get("col_label", "col"),
            ), reproducible

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


def _truncate_value(val: Any, max_len: int = 40) -> Any:
    """Truncate long string values (e.g. amino acid sequences)."""
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "..."
    return val


def _compact_record(record: dict) -> dict:
    """Compact a single record by truncating long string values."""
    return {k: _truncate_value(v) for k, v in record.items()}


def _compact_for_context(result: Any, max_items: int = 20) -> str:
    """Create a compact JSON representation of tool results for the LLM context.

    Full results are kept in the audit trail (ToolCall.raw_output).
    This version goes into the conversation to keep context lean.
    """
    if isinstance(result, list):
        compacted = [_compact_record(r) if isinstance(r, dict) else r for r in result[:max_items]]
        if len(result) > max_items:
            compacted.append({"_note": f"... and {len(result) - max_items} more results (total: {len(result)})"})
        text = json.dumps(compacted, default=str)
    elif isinstance(result, dict):
        text = json.dumps(_compact_record(result), default=str)
    else:
        text = str(result)

    # Hard cap — should rarely hit this after compaction
    if len(text) > 4000:
        return text[:3900] + f'\n... [truncated, {len(text)} chars total]'
    return text


def _trim_messages(messages: list[dict], keep_recent: int = 6) -> list[dict]:
    """Compress older tool exchanges to keep context from growing unbounded.

    Keeps the first message (original question) and the last *keep_recent*
    messages intact. Older assistant reasoning is trimmed and older
    tool_result contents are replaced with a one-line summary.
    """
    # +1 for the initial user question at index 0
    if len(messages) <= keep_recent + 1:
        return messages

    boundary = len(messages) - keep_recent
    trimmed = [messages[0]]

    for i, msg in enumerate(messages[1:], 1):
        if i >= boundary:
            trimmed.append(msg)
            continue

        if msg["role"] == "user":
            content = msg.get("content", [])
            if isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                old_text = content[0].get("content", "")
                trimmed.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": content[0]["tool_use_id"],
                        "content": old_text[:300] + ("..." if len(old_text) > 300 else ""),
                    }],
                })
            else:
                trimmed.append(msg)

        elif msg["role"] == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                compressed = []
                for block in content:
                    if block.get("type") == "text" and len(block.get("text", "")) > 300:
                        compressed.append({"type": "text", "text": block["text"][:300] + "..."})
                    else:
                        compressed.append(block)
                trimmed.append({"role": "assistant", "content": compressed})
            else:
                trimmed.append(msg)
        else:
            trimmed.append(msg)

    return trimmed


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


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


async def _call_llm(
    client,
    model: str,
    *,
    system: str,
    messages: list[dict],
    tools: list | None = None,
    on_retry: Callable[[int, int], None] | None = None,
):
    """Call Claude with retry on rate limit (3 attempts, exponential backoff).

    on_retry(attempt, wait_seconds) is called before each retry sleep,
    so callers can notify the user.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    loop = asyncio.get_event_loop()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return await loop.run_in_executor(
                None,
                partial(client.messages.create, **kwargs),
            )
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            if on_retry:
                on_retry(attempt + 1, wait)
            await asyncio.sleep(wait)
    raise last_err  # type: ignore[misc]


def _handle_api_error(e: Exception) -> TraceEvent | None:
    """Convert Anthropic API exceptions to error events."""
    if isinstance(e, anthropic.AuthenticationError):
        return error_event("API authentication failed. The API key may be invalid or expired.")
    if isinstance(e, anthropic.RateLimitError):
        return error_event("Rate limit reached. Please wait a moment and try again.")
    if isinstance(e, anthropic.BadRequestError):
        msg = e.message if hasattr(e, "message") else str(e)
        if "credit" in msg.lower() or "billing" in msg.lower():
            return error_event("The AI service has insufficient credits. The site administrator has been notified.")
        return error_event(f"Invalid request to the AI model: {msg}")
    if isinstance(e, anthropic.APIStatusError):
        msg = e.message if hasattr(e, "message") else str(e)
        if "credit" in msg.lower() or "billing" in msg.lower():
            return error_event("The AI service has insufficient credits. The site administrator has been notified.")
        if "overloaded" in msg.lower():
            return error_event("The AI model is currently overloaded. Please try again in a few minutes.")
        return error_event(f"AI service error ({e.status_code}): {msg}")
    if isinstance(e, anthropic.APIConnectionError):
        return error_event("Could not connect to the AI service. Please try again later.")
    return None


# ---------------------------------------------------------------------------
# Mutable state container for phase handoffs
# ---------------------------------------------------------------------------


@dataclass
class _PhaseState:
    """Mutable container passed through phase functions.

    Investigation itself stays immutable (new object per add_step),
    but we need a shared reference the orchestrator can read after each phase.
    """
    investigation: Investigation
    output: str = ""


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------


async def _run_tool_phase(
    *,
    phase: AgentPhase,
    system: str,
    user_message: str,
    pool: asyncpg.Pool | None,
    client,
    model: str,
    state: _PhaseState,
    max_turns: int = 25,
) -> AsyncGenerator[TraceEvent, None]:
    """Run a phase that has tool access (Research, Execute).

    Yields TraceEvents as they happen. Updates state.investigation
    and sets state.output to the agent's final text.
    """
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        yield thinking_event(turn + 1)

        retry_events: list[TraceEvent] = []

        def _on_retry(attempt: int, wait: int) -> None:
            retry_events.append(
                thinking_event(0)  # keep spinner alive
            )
            retry_events.append(
                TraceEvent(event_type="retry", data={"attempt": attempt, "wait_seconds": wait})
            )

        try:
            response = await _call_llm(client, model, system=system, messages=_trim_messages(messages), tools=TOOLS, on_retry=_on_retry)
        except Exception as e:
            err = _handle_api_error(e)
            if err:
                yield err
            else:
                yield error_event(f"Unexpected error: {type(e).__name__}")
            return
        finally:
            for evt in retry_events:
                yield evt

        assistant_content: list[dict] = []
        last_text = ""

        for block in response.content:
            if block.type == "text":
                last_text = block.text
                assistant_content.append({"type": "text", "text": block.text})

                state.investigation = add_step(
                    state.investigation,
                    phase=phase,
                    description=f"Agent reasoning (turn {turn + 1})",
                    reasoning=block.text,
                )
                yield step_to_event(state.investigation.steps[-1])

            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

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

                state.investigation = add_step(
                    state.investigation,
                    phase=phase,
                    description=f"Tool call: {block.name}",
                    reasoning=f"Calling {block.name} with {json.dumps(block.input)[:200]}",
                    tool_call=tool_call,
                )
                yield step_to_event(state.investigation.steps[-1])

                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _compact_for_context(result),
                    }],
                })
                assistant_content = []

        if response.stop_reason == "end_turn":
            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})
            state.output = last_text
            return

        if not assistant_content:
            continue
        if response.stop_reason != "tool_use":
            messages.append({"role": "assistant", "content": assistant_content})

    # Max turns for this phase
    state.output = last_text
    yield error_event(f"{phase.value.title()} phase reached maximum turns ({max_turns}).")


async def _run_reasoning_phase(
    *,
    phase: AgentPhase,
    system: str,
    user_message: str,
    client,
    model: str,
    state: _PhaseState,
) -> AsyncGenerator[TraceEvent, None]:
    """Run a reasoning-only phase with no tools (Plan, Synthesise).

    Single LLM call. Yields TraceEvents and sets state.output.
    """
    yield thinking_event(1)

    retry_events: list[TraceEvent] = []

    def _on_retry(attempt: int, wait: int) -> None:
        retry_events.append(
            TraceEvent(event_type="retry", data={"attempt": attempt, "wait_seconds": wait})
        )

    try:
        response = await _call_llm(client, model, system=system, messages=[{"role": "user", "content": user_message}], on_retry=_on_retry)
    except Exception as e:
        err = _handle_api_error(e)
        if err:
            yield err
        else:
            yield error_event(f"Unexpected error: {type(e).__name__}")
        return
    finally:
        for evt in retry_events:
            yield evt

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text

    state.investigation = add_step(
        state.investigation,
        phase=phase,
        description=f"{phase.value.title()} phase",
        reasoning=text,
    )
    yield step_to_event(state.investigation.steps[-1])
    state.output = text


# ---------------------------------------------------------------------------
# Orchestrator — chains the 4 phases with handoffs
# ---------------------------------------------------------------------------


async def investigate(
    question: str,
    pool: asyncpg.Pool | None,
    *,
    api_key: str | None = None,
) -> AsyncGenerator[TraceEvent, None]:
    """Run a 4-phase RPES investigation with agent handoffs.

    Each phase is a separate Claude conversation with a focused prompt.
    Research and Execute have tool access; Plan and Synthesise do not.
    Phase transitions are architectural, not keyword-detected.
    """
    data_map = build_data_map()
    data_map_text = describe_data_map(data_map)
    client, model = _create_client(api_key)
    state = _PhaseState(investigation=create_investigation(question))

    # ── Phase 1: Research ──────────────────────────────────────────────
    yield phase_event(AgentPhase.RESEARCH)
    async for event in _run_tool_phase(
        phase=AgentPhase.RESEARCH,
        system=RESEARCH_PROMPT.format(data_map=data_map_text),
        user_message=question,
        pool=pool,
        client=client,
        model=model,
        state=state,
        max_turns=15,
    ):
        yield event
        if event.event_type == "error":
            return
    research_summary = state.output

    # ── Phase 2: Plan ──────────────────────────────────────────────────
    yield phase_event(AgentPhase.PLAN)
    async for event in _run_reasoning_phase(
        phase=AgentPhase.PLAN,
        system=PLAN_PROMPT.format(
            question=question,
            research_summary=research_summary,
        ),
        user_message=question,
        client=client,
        model=model,
        state=state,
    ):
        yield event
        if event.event_type == "error":
            return
    plan = state.output

    # ── Phase 3: Execute ───────────────────────────────────────────────
    yield phase_event(AgentPhase.EXECUTE)
    async for event in _run_tool_phase(
        phase=AgentPhase.EXECUTE,
        system=EXECUTE_PROMPT.format(
            data_map=data_map_text,
            question=question,
            research_summary=research_summary,
            plan=plan,
        ),
        user_message=f"Execute the investigation plan for: {question}",
        pool=pool,
        client=client,
        model=model,
        state=state,
        max_turns=20,
    ):
        yield event
        if event.event_type == "error":
            return
    execution_findings = state.output

    # ── Phase 4: Synthesise ────────────────────────────────────────────
    yield phase_event(AgentPhase.SYNTHESIZE)
    async for event in _run_reasoning_phase(
        phase=AgentPhase.SYNTHESIZE,
        system=SYNTHESISE_PROMPT.format(
            question=question,
            research_summary=research_summary,
            plan=plan,
            execution_findings=execution_findings,
        ),
        user_message=f"Write the final investigation report for: {question}",
        client=client,
        model=model,
        state=state,
    ):
        yield event
        if event.event_type == "error":
            return
    report_text = state.output

    # ── Done ───────────────────────────────────────────────────────────
    state.investigation = complete_investigation(state.investigation, report_text)
    store_investigation(state.investigation)
    yield report_event(report_text)
