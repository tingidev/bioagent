# BioAgent — Technical Learnings & Architecture Decisions

> Built in one day (5 sessions, ~14 hours) on Easter Monday 2026-04-06.
> Deployed at [bioagent.eu](https://bioagent.eu).
> Deep-dive context per component. Each section covers: what it is, why it works that way, what goes wrong, what changes at scale, and key interview talking points.

---

## Table of Contents

1. [Multi-Agent Architecture (RPES)](#1-multi-agent-architecture-rpes)
2. [Context Engineering](#2-context-engineering)
3. [Agent Instructions & Prompt Design](#3-agent-instructions--prompt-design)
4. [Tool Schema Design](#4-tool-schema-design)
5. [Tool Implementation & Execution](#5-tool-implementation--execution)
6. [Data Map Pattern](#6-data-map-pattern)
7. [SSE Streaming Architecture](#7-sse-streaming-architecture)
8. [Immutable Data Models](#8-immutable-data-models)
9. [LLM Integration & Error Handling](#9-llm-integration--error-handling)
10. [Frontend Architecture](#10-frontend-architecture)
11. [Infrastructure & Deployment](#11-infrastructure--deployment)
12. [Database & Ingestion](#12-database--ingestion)
13. [The Development Journey](#13-the-development-journey)
14. [Security & GxP Considerations](#14-security--gxp-considerations)
15. [What We Chose NOT To Do (YAGNI)](#15-what-we-chose-not-to-do-yagni)

---

## 1. Multi-Agent Architecture (RPES)

### What we're building

BioAgent needs to answer complex research questions that span three different scientific databases. A question like "compare the top-scoring antibodies against MIT_Target with the negative controls — are the best binders statistically different?" requires at least four distinct cognitive tasks:

1. Explore what data is available and confirm connectivity
2. Design a structured investigation strategy given what was found
3. Execute that strategy by querying databases and cross-referencing results
4. Synthesise the raw findings into a coherent scientific report

These are not the same task. Research is exploratory. Planning is strategic. Execution is operational. Synthesis is interpretive. Giving all four tasks to a single agent in a single prompt produces muddled output — the agent hedges between exploration and analysis, writes its plan into the investigation output, and produces reports that read like stream-of-consciousness rather than structured findings.

RPES (Research, Plan, Execute, Synthesise) is an agentic methodology that separates these concerns. Each phase runs as a distinct Claude conversation with its own system prompt, its own turn budget, and specific rules about what it can and cannot do.

### Why 4 agents instead of 1

The single-agent alternative looks like this: one system prompt, one conversation, a keyword like "PLANNING:" or "SYNTHESIZING:" to signal phase changes, and an instruction like "first explore the data, then make a plan, then execute, then write a report."

This approach fails for three reasons.

**Context contamination.** In a single conversation, the model's attention is split across everything it has seen. Research observations bleed into planning reasoning. Planning language appears in the execution phase. Synthesis is influenced by intermediate tool outputs that should have been abstracted away. Each phase agent starts with a clean slate.

**Keyword detection is unreliable.** If you rely on the model detecting "I am now in the EXECUTE phase" in its own output, the model can drift. It may skip phases, re-enter phases, or detect a phase change that wasn't intended. In RPES, phase transitions are architectural: the orchestrator calls a different function with a different system prompt. The model cannot influence when a transition happens.

**Turn budget waste.** A single agent doing research, planning, execution, and synthesis in 25 turns will use many of those turns on research exploration and planning, leaving less room for the multi-step execute phase. Separate turn budgets (15 for research, 20 for execute) let each phase use what it needs.

```
Single-agent approach:
  One conversation → all phases mixed → unclear responsibility → inconsistent quality

RPES approach:
  Research (15 turns, tools) → Plan (1 call, no tools) → Execute (20 turns, tools) → Synthesise (1 call, no tools)
     ↓                              ↓                          ↓                           ↓
  state.output               state.output               state.output               final report
  (research_summary)         (plan)                     (execution_findings)
```

### How phase transitions work architecturally

The orchestrator function `investigate()` in `agent.py` is a Python async generator. It runs four sequential async generators, one per phase, chaining their outputs. When Research finishes, its final text is extracted from `state.output` and passed as a formatted string into the Plan phase's system prompt. Plan's output becomes the `plan` variable, which is injected into Execute's system prompt. Execute's findings feed Synthesise.

```python
# Phase 1: Research
async for event in _run_tool_phase(phase=AgentPhase.RESEARCH, ...):
    yield event
    if event.event_type == "error":
        return
research_summary = state.output   # Extract the agent's final text

# Phase 2: Plan — receives research_summary as context
async for event in _run_reasoning_phase(
    system=PLAN_PROMPT.format(question=question, research_summary=research_summary),
    ...
):
    yield event
plan = state.output
```

The model has no visibility into the transition. From its perspective, each phase is a fresh conversation. The only continuity is the structured text passed between phases — not conversation history.

### `_PhaseState` for state management

The `Investigation` object is immutable — every call to `add_step()` returns a new `Investigation`. But the orchestrator needs a reference that gets updated across steps within a phase, and that it can read after the phase completes.

`_PhaseState` is the solution. It is a plain Python dataclass (mutable, not frozen) that wraps the current `Investigation` reference and the phase's final text output:

```python
@dataclass
class _PhaseState:
    investigation: Investigation
    output: str = ""
```

Each phase function receives `state` by reference. When it calls `add_step()`, it reassigns `state.investigation` to the new immutable `Investigation`. When it finishes, it assigns `state.output` to the agent's final text. The orchestrator reads both after the phase generator completes.

This is a deliberate design choice: keep the domain model (`Investigation`) immutable for safety and auditability, but use a thin mutable wrapper for the within-phase accumulation that the orchestrator needs to coordinate handoffs.

### `_run_tool_phase()` vs `_run_reasoning_phase()`

Two different phase runners handle the two types of agents.

`_run_tool_phase()` runs a multi-turn conversation with tool access. It maintains a `messages` list that grows as the agent calls tools and receives results. Each turn: send messages → get response → parse tool calls → execute tools → append results → repeat. It calls `_trim_messages()` before each LLM call to prevent context overflow. It yields `TraceEvent` objects for every reasoning step and every tool call. This is used for Research and Execute.

`_run_reasoning_phase()` makes a single LLM call with no tools. It sends one user message, gets one response, records it as a trace step, and sets `state.output`. This is used for Plan and Synthesise. The model has everything it needs in the system prompt (the prior phases' outputs) and has no need to loop.

Why no tools for Plan and Synthesise? Planning with tool access creates scope creep — the model starts running queries during planning, skipping the Execute phase. Synthesis with tool access creates double-work — the model re-queries databases instead of interpreting existing findings. Restricting tool access enforces the phase boundary and produces better output.

### Turn limits per phase

Research is capped at 15 turns. The research phase only needs to run exploratory queries — statistics, target lists, connectivity checks. 15 turns is generous for 3 databases. If the model hits 15 turns, it likely ran into an unexpected issue (slow database, confusing data shape) that would benefit from a fresh start anyway.

Execute is capped at 20 turns. This is the analytical workhorse: 4-6 retrieval queries, 2-3 cross-referencing queries, 1-2 statistical analyses. The prompt instructs the model to aim for 8-12 tool calls total and stop when it has enough to answer the question. 20 turns gives headroom without letting the agent spiral. The prompt explicitly says "a focused answer with strong cross-references is better than an exhaustive survey."

### Context trimming via `_trim_messages()`

Each turn in a tool phase adds two messages to the conversation history: an assistant message (reasoning + tool call) and a user message (tool result). Over 15-20 turns, this becomes a very large context window.

`_trim_messages()` keeps the first message (the original question) and the last 6 messages intact. Older messages are compressed: tool results are truncated to 300 characters, assistant reasoning blocks are truncated to 300 characters. The model retains full detail for recent context and a brief summary of older context.

```
messages = [
  [0] original question (always kept)
  [1] assistant reasoning (compressed if old)
  [2] tool result (compressed if old)
  ...
  [n-6] start of preserved window
  [n-5] full
  [n-4] full
  [n-3] full
  [n-2] full
  [n-1] full
  [n]   full
]
```

This is a practical approximation of a sliding window. It is not perfect — the model loses detail about earlier tool results — but it is transparent (no hidden summarisation) and deterministic (the trimming logic is pure Python, not another LLM call).

### The evolution: from single-agent to multi-agent

BioAgent was originally implemented as a single agent with keyword-detected phase changes. The system prompt said "first explore the data, then write a plan, then execute it, then synthesise." Phase labels in the output ("PLANNING:", "EXECUTING:") were detected by the streaming parser to update the UI.

This worked, but had clear quality problems. The agent often skipped the planning section or merged it with execution. The synthesis was messy because it happened in the same conversation that contained all the raw tool outputs. Cross-referencing was weaker because the agent had not explicitly planned what to cross-reference.

The refactor to multi-agent handoffs (Session 5/6) was the biggest quality improvement of the entire project. The separation forced each phase to do exactly one thing. The Plan phase, given only the research summary and no tool access, produced crisp, specific investigation plans with explicit cross-reference steps. The Execute phase, given the plan, followed it methodically. The Synthesis phase, given structured findings rather than raw conversation history, wrote cleaner reports.

The RPES acronym itself came from Joeri's Aizon RDPI methodology (Research, Design, Plan, Implement) — the agent adaptation replaces Design with Synthesise because agents synthesise findings rather than design solutions.

### GxP relevance: phase separation for auditability

In regulated pharmaceutical environments, you cannot have a black-box "AI did something" answer. You need to show what was investigated, what was found, what was concluded, and how each conclusion relates to specific data points.

RPES maps directly to this requirement. The Research phase produces a documented data landscape. The Plan phase produces a documented investigation strategy. The Execute phase produces a documented series of tool calls with reproducible queries. The Synthesis phase produces a structured report with citations back to execution findings. Every step is recorded in the audit trail, which ships in the exported report.

This is not an accident. The phase structure was designed with pharma reviewers in mind.

### Key interview talking points

- "Phase transitions in RPES are architectural, not keyword-detected. The model cannot accidentally skip a phase or drift between them — the orchestrator controls the flow."
- "Plan and Synthesise have no tool access by design. If Plan could query databases, it would start executing. If Synthesis could query databases, it would re-do the work instead of interpreting it."
- "This is the same separation of concerns I used in Aizon's RDPI methodology — agents need explicit phase boundaries, not just hints in a prompt."
- "The move from single-agent to multi-agent was the biggest quality jump of the entire project. Plans got more specific. Execution got more focused. Reports got more readable."
- "The audit trail is not an afterthought — every agent step produces a `TraceStep` with phase, reasoning, tool call, and reproducible query. That's the kind of traceability pharma workflows require."

### Decisions made

| What | Why |
|------|-----|
| 4 distinct agents (RPES) | Each phase has different cognitive demands and different tool requirements |
| Plan and Synthesise have no tools | Enforces phase boundary; prevents scope creep and double-work |
| 15 turns for Research | Enough for exploratory queries across 3 sources; caps waste if something goes wrong |
| 20 turns for Execute | Headroom for full investigation without allowing spiralling |
| `_PhaseState` mutable wrapper | Need a shared reference for orchestrator coordination; Investigation itself stays immutable |
| `_trim_messages()` keeps first + last 6 | Original question is always in context; recent tool calls get full detail; older ones get compressed |

---

## 2. Context Engineering

### What we're building

Context engineering is the discipline of controlling exactly what information the LLM sees, when it sees it, and in what form. In a multi-agent system, this is not prompt writing — it is system design. Every token in the context window either helps the agent reason about the current task or dilutes its attention. The goal is maximum signal density.

BioAgent's context engineering operates at three levels: **what enters the context** (data map, prior phase outputs, tool results), **how it is structured** (system prompt sections, output format instructions, labelled handoff text), and **what gets removed** (message trimming, phase isolation).

### Level 1: What enters the context

Each RPES phase receives a carefully curated context window:

```
Research Agent sees:
  System prompt: role + data map + task instructions + output format
  User message:  the research question
  (grows with): tool results + own reasoning over 15 turns

Plan Agent sees:
  System prompt: role + research question + research summary + task instructions + output format
  User message:  "Create the investigation plan"
  (single turn — no growth)

Execute Agent sees:
  System prompt: role + data map + research question + research summary + plan + task instructions + output format
  User message:  "Execute the investigation plan"
  (grows with): tool results + own reasoning over 20 turns

Synthesis Agent sees:
  System prompt: role + research question + research summary + plan + execution findings + task instructions + output format
  User message:  "Write the final report"
  (single turn — no growth)
```

Notice what is NOT in these contexts:
- The Execute agent does not see Research's raw tool outputs — only the Research Summary (a curated text block the Research agent was instructed to produce)
- The Synthesis agent does not see Execute's raw tool outputs — only the Execution Findings
- Plan and Synthesis never see tool schemas (they have no tools)
- No agent sees another agent's conversation history

This is the core principle: **each agent sees the minimum context required for its specific task, in a pre-digested form**. Raw tool results from Research don't help the Plan agent — the Research Summary does. Raw conversation history from Execute doesn't help Synthesis — the Execution Findings section does.

### Level 2: How it is structured

The context is structured so the LLM can parse it without ambiguity. Every system prompt follows the same layout:

```
1. Role statement (one sentence: "You are BioAgent (Research Phase).")
2. Data access (data map text, if the phase has tools)
3. Task framing (what was asked, what prior phases found)
4. Instructions (specific steps and rules)
5. Output format (exact section header the agent must produce)
```

This ordering matters. Role first sets the frame. Data access before task framing prevents the agent from reasoning about the question before it knows what data is available. Instructions after framing prevents the agent from starting work before understanding the context. Output format last anchors what "done" looks like.

The handoff text between phases uses markdown headers that are explicitly named in the receiving prompt. Research's output has a `### Research Summary` section. The Plan prompt says `## Research Summary (from previous phase)` and pastes the text. This labelling is not decorative — it tells the model the provenance of the text (another agent wrote it) and its purpose (context, not instructions).

### Level 3: What gets removed

The `_trim_messages()` function is context engineering at the conversation level. In a 20-turn Execute phase, messages accumulate: 20 assistant responses (reasoning + tool calls) + 20 user messages (tool results). At ~2K tokens per exchange, that is 80K tokens of conversation — more than most models' effective attention window.

Trimming keeps:
- Message 0 (original question) — always in context, prevents goal drift
- Last 6 messages — full fidelity for the current chain of thought
- Older messages — compressed to 300 chars each (enough to remember "I queried AlphaSeq for targets" but not the full result)

This is a **lossy compression** that trades detail for focus. The agent loses the ability to reference exact numbers from early tool calls but retains awareness of what it already tried. In practice, this trade-off is invisible — the agent's recent context (last 3 tool calls) is where its active reasoning happens.

### Why not use a summarisation agent for trimming?

An LLM could summarise older messages more intelligently than truncation. But that means an extra LLM call per turn in the Execute phase (20 calls × 20 turns = 400 summarisation calls). The latency and cost are prohibitive. Truncation is deterministic, instant, and free. The quality difference is marginal because the trimmed messages are context, not instructions — the agent doesn't need to recall exact values from turn 3 when it is on turn 18.

### The data map as context engineering

The data map (`describe_data_map()`) is the most important piece of context engineering in BioAgent. It is not a simple list of database descriptions — it encodes:

1. **What each source contains** — record counts, entity types, data shapes
2. **How sources connect** — explicit cross-reference instructions with search terms
3. **Target name mappings** — "MIT_Target = SARS-CoV-2 spike protein"
4. **What to search for** — "search SAbDab with antigen_name='spike' or 'SARS-CoV-2'"

Without the cross-reference strategy section, the agent has to infer that AlphaSeq's "MIT_Target" is the same antigen that SAbDab calls "spike" and ChEMBL calls "SARS-CoV-2 spike glycoprotein." With it, the agent has explicit instructions for bridging sources. This is the difference between an agent that searches in isolation and one that cross-references.

The data map is injected into Research and Execute system prompts (the phases with tool access). Plan and Synthesis don't need it — they work from the curated text summaries produced by the tool phases.

### What goes wrong

**Context overflow in long Execute phases.** Even with trimming, a 20-turn Execute phase with large tool results (ChEMBL returns verbose JSON) can push the context window. The model starts losing coherence on early findings. The mitigation is the trim function + the Execute prompt's efficiency instructions ("aim for 8-12 tool calls").

**Handoff text too long.** If the Research agent produces a 3-page Research Summary, it consumes space in every subsequent prompt (Plan, Execute, Synthesis all receive it). The Research prompt instructs a concise summary format, but the model occasionally overproduces. A hard character limit on handoff text would be the production fix.

**Handoff text too sparse.** If Research finishes early (connectivity issue, limited data), the Plan agent gets a thin summary and produces a generic plan. The quality of each phase depends on the quality of the previous phase's output. Garbage in, garbage out — except the garbage is curated text, not raw data.

### At scale

At production scale with dozens of data sources:
- The data map becomes too large to fit in every prompt. You would need **selective data map injection** — only include sources relevant to the question, determined by a pre-processing step.
- Handoff text between phases would need compression or structured summaries (JSON schemas instead of free text) to prevent context bloat.
- Context trimming would shift from truncation to **RAG over conversation history** — embed and retrieve relevant prior exchanges instead of keeping the last 6.
- Model context windows will grow (Claude already supports 200K), but attention degradation at long contexts means smaller, focused contexts will always outperform token-stuffed ones.

### Key interview talking points

- "Context engineering is system design, not prompt tweaking. Each agent sees the minimum context for its task — no raw conversation history from prior phases, no tool schemas for reasoning-only agents."
- "The data map encodes cross-reference strategy as text in the system prompt. Without it, the agent searches databases in isolation. With it, the agent knows that MIT_Target is the same protein SAbDab calls 'spike' — that mapping is context engineering, not prompt engineering."
- "Phase isolation is context engineering: the Synthesis agent never sees raw tool results. It sees curated Execution Findings. This is why its reports are clean — it synthesises conclusions, not JSON blobs."
- "`_trim_messages()` is a lossy compression: keep the question, keep recent context, truncate the rest. No extra LLM calls, deterministic, instant. The quality trade-off is invisible in practice."
- "At scale, you would selectively inject relevant portions of the data map rather than the whole thing. Context window management is the core scaling challenge for multi-agent systems."

### Decisions made

| What | Why |
|------|-----|
| Phase isolation (no shared conversation history) | Prevents context contamination; each agent reasons from curated summaries |
| Data map as system prompt text | Agent reads it as instructions; no special parsing needed; encodes domain knowledge |
| `_trim_messages()` truncation over LLM summarisation | Deterministic, free, instant; quality difference is marginal for context messages |
| Output format anchors (`### Research Summary`, etc.) | Forces agent to produce structured output that becomes clean handoff text |
| Data map only in tool phases | Plan and Synthesis don't need source details; they work from summaries |
| Cross-reference strategy as explicit text | Agent cannot infer that MIT_Target = spike protein without being told |

---

## 3. Agent Instructions & Prompt Design

### What we're building

Four system prompts that each produce a different cognitive behaviour from the same LLM. The Research prompt produces exploratory behaviour. The Plan prompt produces strategic behaviour. The Execute prompt produces analytical behaviour. The Synthesis prompt produces interpretive behaviour. Same model, same weights, different outputs — entirely from prompt design.

### The anatomy of a phase prompt

Every RPES prompt follows a consistent structure, but the content varies dramatically between phases:

**Research Prompt:**
```
Role:    "You are BioAgent (Research Phase)"
Context: {data_map}
Task:    "Given the research question, explore what data is available"
Steps:   4 numbered steps (get statistics, check connectivity, note counts, identify relevance)
Rules:   "Only run exploratory queries... Do NOT run detailed analytical queries yet"
Output:  "End your response with a clearly labelled section: ### Research Summary"
```

**Plan Prompt:**
```
Role:    "You are BioAgent (Plan Phase). You have NO access to tools or databases."
Context: {question} + {research_summary}
Task:    "Write a concrete investigation plan"
Steps:   4 items (hypothesis, query sequence, cross-references, success criteria)
Rules:   (implicit — no tools available, so no tool-related rules needed)
Output:  (implicit — the entire response is the plan)
```

**Execute Prompt:**
```
Role:    "You are BioAgent (Execute Phase)"
Context: {data_map} + {question} + {research_summary} + {plan}
Task:    "Execute the plan by querying databases and cross-referencing findings"
Rules:   6 bullet rules + cross-referencing section + analysis section + efficiency section
Output:  "End your response with a clearly labelled section: ### Execution Findings"
```

**Synthesis Prompt:**
```
Role:    "You are BioAgent (Synthesise Phase). You have NO access to tools or databases."
Context: {question} + {research_summary} + {plan} + {execution_findings}
Task:    "Write a structured report in markdown"
Format:  6 sections (Question, Approach, Findings, Cross-Database Connections, Limitations, Reproducibility)
Rules:   "Do not repeat raw data. Interpret, connect, and conclude."
Output:  (the report IS the output)
```

### Why each prompt is different

**Research is constrained to exploration.** The critical line: "Only run exploratory queries (statistics, targets, basic searches). Do NOT run detailed analytical queries yet." Without this constraint, the Research agent starts doing the Execute agent's job — running deep queries, computing statistics, attempting cross-references. The constraint keeps it focused on reconnaissance.

**Plan is explicitly told it has no tools.** "You have NO access to tools or databases." This is stated even though the orchestrator never passes tools to the Plan phase. Why? Because the model doesn't know it has no tools until it tries to use them (or reads that it doesn't). Stating it in the prompt prevents wasted reasoning about which tools to call.

**Execute has the most structured instructions.** Six rule bullets, a dedicated cross-referencing section, an analysis section, and an efficiency section. This is because Execute is the phase most likely to go wrong — it can spiral (querying endlessly), be shallow (one query per database, no cross-references), or be unfocused (running every possible analysis). The prompt constrains all three failure modes:
- "Aim for 8-12 tool calls total" prevents spiralling
- "Take SPECIFIC results from one source and use them to query another" prevents shallow isolation
- "Pick 1-2 analyses that directly answer the research question" prevents unfocused analysis

**Synthesis is told what NOT to do.** "Do not repeat raw data. Interpret, connect, and conclude." Without this, the Synthesis agent copies tool results verbatim into the report. The most important section instruction: "Cross-Database Connections: Insights from combining sources (this is the most important section)." Labelling it as "most important" biases the model's attention toward the cross-referencing conclusions — which is the whole point of BioAgent.

### The evolution of prompts across sessions

The prompts went through four major iterations:

**v1 (Session 2):** Single prompt, single agent. "You are a scientific investigator. You have access to three databases..." No phase separation, no output format constraints, no cross-referencing instructions. Result: stream-of-consciousness investigations that mixed exploration with analysis.

**v2 (Session 4):** Single prompt with phase detection keywords. Added "RESEARCH:", "PLANNING:", "EXECUTING:", "SYNTHESIZING:" labels. Added cross-referencing instructions. Result: better structure, but the model frequently merged phases or skipped planning entirely.

**v3 (Session 5):** Prompt rewritten with RPES methodology sections, adaptive reasoning guidelines, and deep cross-referencing instructions. Still single-agent. Result: improved cross-referencing, but phase boundaries still drifted.

**v4 (Session 6):** Four separate prompts. Each prompt is focused, constrained, and has explicit output format requirements. Result: dramatic quality improvement. Plans became specific (tool names, parameter values). Execution followed plans. Reports cited specific data. This version is what is deployed.

The key insight: **you cannot fix agent behaviour with better instructions in a single prompt**. At some point, the only solution is architectural — separate the prompts, separate the conversations, separate the tool access.

### Instruction patterns that work

**Numbered steps produce better compliance than prose.** "1. Call get_statistics... 2. Run a simple query on SAbDab..." is followed more reliably than "explore the data by looking at statistics and checking connectivity." The model treats numbered lists as a checklist.

**Negative instructions prevent specific failure modes.** "Do NOT run detailed analytical queries yet" is more effective than "keep it exploratory." Negative instructions name the specific unwanted behaviour. The model recognises what it should avoid.

**Budget constraints prevent spiralling.** "Aim for 8-12 tool calls total" with a breakdown (4-6 retrieval, 2-3 cross-ref, 1-2 analysis) gives the model a concrete efficiency target. Without this, Execute phases routinely used all 20 turns running every possible query combination.

**"Most important section" labels direct attention.** In the Synthesis prompt, labelling Cross-Database Connections as "the most important section" produces noticeably longer and more detailed cross-referencing analysis. The model allocates more reasoning tokens to sections flagged as important.

**Output format anchors with exact headers.** "End your response with a clearly labelled section: ### Research Summary" is precise. It gives the orchestrator a reliable extraction point (grep for `### Research Summary`) and gives the model an unambiguous signal for "you're done when you've written this section."

### What goes wrong

**Instruction following degrades with context length.** At turn 15 in an Execute phase, the model has seen thousands of tokens of tool results. The system prompt's instructions (aim for 8-12 calls, stop when you have enough) get less weight as the context grows. This is why `_trim_messages()` exists — it keeps the context manageable so the system prompt retains influence.

**Over-constraining kills creativity.** Early versions of the Execute prompt specified exact query sequences. The model followed them mechanically, even when intermediate results suggested a different path. The current prompt says "follow the plan step by step, but adapt if you discover something unexpected" — a balance between structure and flexibility.

**Under-constraining produces meandering.** Without the efficiency budget, the Execute agent would happily use all 20 turns exploring tangential queries. "More tool calls" is not "better investigation."

### At scale

At production scale:
- Prompts become **templates with runtime injection** — the data map, question, and handoff text are already parameterised; at scale you would also parameterise instruction intensity (more constraints for complex questions, fewer for simple ones).
- **Prompt versioning** becomes critical. Each prompt version produces different output quality. You need A/B testing infrastructure to compare prompt versions against evaluation criteria.
- **Evaluation-driven prompt development.** At 14 hours, prompts are tuned by human judgment. At scale, you need automated evaluation: does the Research summary contain all relevant sources? Does the Plan include cross-references? Does the report cite specific data? These become scored metrics.
- **Few-shot examples** in prompts can improve quality for specific question types but consume context. The trade-off is example quality vs. context budget.

### Key interview talking points

- "Each RPES prompt produces a different cognitive behaviour from the same model. Research explores, Plan strategises, Execute analyses, Synthesis interprets. The prompts are the primary lever for agent quality."
- "The Execute prompt has three failure-mode constraints: budget (8-12 calls) prevents spiralling, cross-referencing rules prevent shallow isolation, selective analysis prevents unfocused computation."
- "I learned that you cannot fix agent behaviour with better instructions in a single prompt. Past a complexity threshold, the only fix is architectural — separate prompts, separate conversations, separate tool access."
- "Prompt engineering was iterative — four major rewrites across five sessions. Each version fixed specific failure modes I observed in the output."
- "The 'most important section' label in the Synthesis prompt measurably improves cross-referencing quality. It is a simple attention-direction technique that works because LLMs allocate reasoning proportional to perceived importance."

### Decisions made

| What | Why |
|------|-----|
| Separate prompts per phase | Cannot fix phase drift with instructions alone; architecture > prompting |
| "Do NOT" negative constraints | Names the specific unwanted behaviour; more effective than positive-only framing |
| Budget constraints in Execute | "Aim for 8-12 tool calls" prevents spiralling while allowing flexibility |
| "Most important section" label | Directs model attention to cross-database connections — the key differentiator |
| Output anchors with exact headers | Reliable extraction points for orchestrator; unambiguous completion signal |
| "Adapt if you discover something unexpected" | Balances plan-following with flexibility; avoids mechanical execution of stale plans |

---

## 4. Tool Schema Design

### What we're building

When you give an LLM access to tools, the tool schema IS the interface. The model reads the tool name, description, and input schema to decide when to call it, what parameters to provide, and how to interpret the results. A poorly designed schema produces poor tool usage — wrong parameters, wrong tool for the task, or tools that never get called.

BioAgent has four tools, each with a different design challenge. The schema design choices directly affect investigation quality.

### Naming: compound verbs that signal intent

```
query_alphaseq_bindings    — "query" signals data retrieval, "bindings" signals the data type
query_sabdab               — consistent "query_" prefix for all database tools
query_chembl               — same pattern; the model learns "query_* = get data from a source"
run_statistics             — "run_" prefix signals computation, not retrieval
```

The naming convention creates a mental model for the LLM: `query_*` tools retrieve data from external sources, `run_*` tools compute over data already obtained. This distinction matters in the Execute phase — the model naturally calls query tools first (to get data) and statistics tools second (to analyse it).

### The action-based pattern: one tool, many actions

Each tool uses an `action` enum instead of separate tools per operation:

```json
{
  "name": "query_alphaseq_bindings",
  "input_schema": {
    "properties": {
      "action": {
        "type": "string",
        "enum": ["search_by_score", "search_by_sequence", "get_statistics", "get_top_binders", "get_targets"]
      },
      "min_score": { ... },
      "target": { ... },
      ...
    },
    "required": ["action"]
  }
}
```

**Why not 20 separate tools?** AlphaSeq has 5 actions, SAbDab has 4, ChEMBL has 5, Statistics has 7 — that is 21 operations. Exposing them as 21 tools floods the tool selection space. The model has to read 21 tool descriptions to decide which to call. With 4 tools, the model first decides which source to query (a high-level decision), then which action to take within that source (a focused decision). Two-level decision-making is faster and more reliable than flat 21-way selection.

**The trade-off:** all action-specific parameters exist on every tool call. When calling `get_statistics`, the `min_score` and `sequence_fragment` parameters are irrelevant but present in the schema. This is a known imperfection — the descriptions clarify which parameters apply to which actions ("for search_by_score", "for get_molecule"). In practice, the model handles this well; it rarely sends irrelevant parameters.

### Description as documentation

Tool descriptions are not labels — they are the model's only documentation for what the tool does:

```python
"Search the AlphaSeq antibody binding dataset (104,972 antibodies). "
"Find antibodies by binding score range, sequence fragment, or get statistics. "
"Data includes VH/VL sequences, targets, and binding scores."
```

Three elements in every description:
1. **What it is** — "AlphaSeq antibody binding dataset" (names the source)
2. **Scale** — "(104,972 antibodies)" (the model knows the data volume)
3. **What you can do** — "Find antibodies by binding score range, sequence fragment, or get statistics" (summarises the actions)

The ChEMBL description adds domain-specific terms: "IC50/Ki/EC50 values, and target-compound relationships." This primes the model to use correct terminology in its tool calls and reasoning. If the description said "bioactivity data," the model might search for vague terms. "IC50/Ki/EC50" teaches it the exact measurement types available.

The statistics tool description ends with: "Use this to analyse data, not just summarise it." This is an instruction embedded in a tool description. It nudges the model toward analytical usage (compare_groups, correlation) rather than just calling `describe` repeatedly.

### Parameter descriptions as usage guides

Each parameter description includes the action context:

```python
"min_score": {"description": "Minimum binding score (for search_by_score)."}
"target_chembl_id": {"description": "ChEMBL target ID (for get_bioactivities)."}
```

The "(for action_name)" suffix tells the model which action the parameter belongs to. Without this, the model might pass `min_score` to `get_targets` — syntactically valid, but semantically wrong. The backend would ignore the parameter, but the model's reasoning would be confused about what it asked for.

### Only `action` is required

```json
"required": ["action"]
```

All other parameters are optional. This is deliberate: different actions need different parameters, and the model determines which to provide based on the action it chose. Making parameters required would either force the model to provide dummy values or would require separate input schemas per action (defeating the purpose of the action pattern).

### The statistics tool: teaching the model analytical methods

The statistics tool schema is the most complex because it teaches the model what analyses are possible:

```python
"action": {
    "enum": ["describe", "compare_groups", "frequency_table",
             "correlation", "outlier_detection", "rank_and_filter", "cross_tabulate"]
}
```

Each action name is self-documenting. But the key design choice is in the parameters:

```python
"group_a": {"description": "First group for comparison."}
"group_b": {"description": "Second group for comparison."}
"label_a": {"description": "Label for first group."}
"label_b": {"description": "Label for second group."}
```

`group_a`/`group_b` with `label_a`/`label_b` teaches the model that `compare_groups` needs two named groups. The model naturally fills this with meaningful data: group_a = binding scores for MIT_Target, label_a = "MIT_Target binders", group_b = scores for AlphaNeg1, label_b = "Negative control."

The `labels` parameter for `outlier_detection` and `rank_and_filter` accepts string identifiers: "E.g. sequence IDs." This hint tells the model to pass identifiable labels (not generic indices) so the results are interpretable: "Outlier: SEQ_4827 (score: 0.98)" instead of "Outlier: item 4827 (score: 0.98)."

### What goes wrong

**The model invents parameters.** Occasionally, the model sends a parameter not in the schema (e.g., `sort_by` for AlphaSeq). The backend ignores unknown parameters via `tool_input.get("sort_by")` returning None. This is a graceful failure — the query runs without sorting, which is close enough.

**The model picks the wrong action.** When the model wants "what targets exist in AlphaSeq," it sometimes calls `get_statistics` instead of `get_targets`. Both return useful information, but `get_targets` is more specific. The action descriptions could be more distinctive. In practice, the Research prompt's numbered steps ("1. Call get_statistics and get_targets") compensate for schema ambiguity.

**Over-parameterisation of statistics.** The model occasionally calls `compare_groups` with small sample sizes (3-5 values per group) where the results are not statistically meaningful. The statistics tool returns the results anyway, and the model sometimes draws conclusions from them. A production fix would include sample size warnings in the tool output.

### At scale

At production scale with dozens of data sources:
- The action pattern scales poorly beyond ~10 actions per tool. At that point, split into multiple tools (one per domain) or use a hierarchical tool selection pattern.
- **Tool descriptions become a prompt engineering surface.** Wording changes in descriptions measurably affect tool usage patterns. You would need evaluation metrics for tool selection quality.
- **Dynamic tool injection** — only expose tools relevant to the current phase/question, reducing the selection space. BioAgent already does this (Plan and Synthesis get no tools).
- **Schema versioning** — tool schema changes affect model behaviour. Track which schema version was used for each investigation for reproducibility.

### Key interview talking points

- "The action-based pattern reduces 21 operations to 4 tools. Two-level decision-making (which source, then which action) is more reliable than flat 21-way tool selection."
- "Tool descriptions are documentation for the LLM. Including scale ('104,972 antibodies') and domain terms ('IC50/Ki/EC50') teaches the model what to expect and what terms to use."
- "The statistics tool description says 'Use this to analyse data, not just summarise it.' Instructions embedded in tool descriptions steer usage patterns."
- "Only the `action` parameter is required because different actions need different parameters. The model determines which to provide based on context — enforcing all parameters would force dummy values."

### Decisions made

| What | Why |
|------|-----|
| Action-based pattern (4 tools with action enums) | Reduces decision space; 2-level selection beats 21-way flat selection |
| Scale in descriptions ("104,972 antibodies") | Model knows data volume; affects query strategy and expectations |
| Domain terms in descriptions ("IC50/Ki/EC50") | Primes model to use correct terminology in queries and reasoning |
| Only `action` required | Different actions need different params; model determines which to provide |
| "(for action_name)" in param descriptions | Prevents cross-action parameter confusion |
| `query_*` / `run_*` naming convention | Signals retrieval vs computation; model calls query tools before run tools |

---

## 5. Tool Implementation & Execution

### What we're building

The agent needs to query three fundamentally different data sources: a local Postgres database (AlphaSeq), a REST API that returns structured JSON (SAbDab), and another REST API (ChEMBL). From the agent's perspective, all three look the same — they are named tools with a JSON schema describing their inputs.

The agent also needs analytical capabilities. Raw database results are not enough. An agent that can ask "are the best binders statistically different from the negative controls?" needs a statistics tool, not just a query tool.

### 4 tools: alphaseq, sabdab, chembl, statistics

**`query_alphaseq_bindings`** wraps a local Postgres database. Actions: `search_by_score`, `search_by_sequence`, `get_statistics`, `get_top_binders`, `get_targets`. The database contains 104,972 rows with VH/VL sequences, target names, and binding scores.

**`query_sabdab`** wraps the Oxford OPIG SAbDab REST API. Actions: `search_structures`, `get_by_pdb`, `search_by_antigen`, `get_stats`. Returns PDB codes, resolution, CDR H3 length, antigen name, and species for antibody crystal structures.

**`query_chembl`** wraps the EMBL-EBI ChEMBL REST API. Actions: `search_target`, `get_bioactivities`, `get_molecule`, `search_molecule`, `get_assay`. Returns IC50, Ki, EC50, and other bioactivity measurements from medicinal chemistry literature.

**`run_statistics`** is pure Python, no external dependencies. Actions: `describe`, `compare_groups`, `frequency_table`, `correlation`, `outlier_detection`, `rank_and_filter`, `cross_tabulate`. The agent feeds it data extracted from other tool calls.

The tools are listed in `TOOLS` as Anthropic tool-use JSON schemas. The agent selects which tool to call and what inputs to provide. The `execute_tool()` function in `agent.py` dispatches to the appropriate implementation.

### Unified return signature: `(result, reproducible_query)` tuple

Every tool function returns a tuple: `(result, reproducible_query)`. The `result` is the actual data — a list of Pydantic models, a dict of stats, etc. The `reproducible_query` is a string that describes exactly how to reproduce that result independently.

For SQL tools:
```python
reproducible = "SELECT * FROM alphaseq_bindings WHERE binding_score >= 0.8 ORDER BY binding_score DESC LIMIT 20"
```

For REST tools:
```python
reproducible = "GET https://www.ebi.ac.uk/chembl/api/data/activity.json?target_chembl_id=CHEMBL3559560&limit=50"
```

For the statistics tool:
```python
reproducible = 'statistics.compare_groups({"group_a": [...], "group_b": [...], "label_a": "MIT_Target", "label_b": "AlphaNeg1"})'
```

This reproducible query string is stored on the `ToolCall` model and surfaced in the audit trail panel and exported reports. Anyone reading the report can reproduce any data point independently.

### Why reproducible queries matter

In pharma and drug discovery, data provenance is not optional. If a report claims "the top binders have a mean binding score of 0.91 (SD 0.03)", a scientist needs to be able to verify that claim by re-running the exact query. The reproducible query makes that possible.

This is also what separates BioAgent from a chatbot that "looks things up." A chatbot might summarise data without any way to verify the source. BioAgent's every claim has a verifiable query attached.

### Database-agnostic tool interface

From the agent's perspective, all data comes from "tools." It does not know or care whether the data comes from a local Postgres database, a REST API in Oxford, or a REST API at EMBL-EBI. The tool schema describes what the tool can do; the dispatch layer in `execute_tool()` handles the implementation.

This matters because it keeps the agent's reasoning clean. It does not need to think "I should query the database" vs "I should call the API." It thinks "I need binding data, I'll call `query_alphaseq_bindings`."

### Parameterized queries for SQL injection safety

The AlphaSeq tool builds SQL queries with positional parameters (`$1`, `$2`, etc.) and passes values as separate arguments to `asyncpg`. The SQL statement itself never includes user input:

```python
conditions = ["binding_score >= $1"]
params: list[object] = [min_score]
if target is not None:
    conditions.append(f"target = ${idx}")
    params.append(target)
rows = await pool.fetch(query, *params)
```

The agent controls the `target` field via the tool input. If a malicious input contained SQL injection characters, asyncpg would treat it as a literal string value, not as SQL.

### Statistics tool: pure Python, no scipy

The statistics tool implements six analyses using only Python's standard library: `math`, `collections.Counter`, and `itertools`. No numpy, no scipy, no pandas.

Why? Three reasons.

**Minimal dependencies.** The Docker image is smaller and builds faster. Adding scipy would pull in ~50MB of compiled C extensions for a production image that runs on a 4GB server.

**Transparent implementations.** Every formula is visible in the source. Cohen's d is computed as `mean_diff / pooled_std`. Pearson correlation is computed from the covariance formula. An auditor or scientist can read the code and verify the statistics.

**Sufficient precision.** The analyses needed — descriptive stats, group comparison, correlation, outlier detection, ranking — do not require scipy's advanced tests. Implementing the IQR method for outlier detection from scratch is 20 lines. The result is identical to scipy's implementation.

What each statistic measures and when the agent uses it:

- **`describe`**: mean, median, std, min, max, IQR. Used to profile binding score distributions.
- **`compare_groups`**: descriptive stats for two groups plus Cohen's d effect size. Cohen's d > 0.8 is "large" — used to assess whether top binders are meaningfully different from negative controls.
- **`correlation`**: Pearson r between two numeric series. Used to test relationships — e.g., does CDR H3 length correlate with binding score?
- **`outlier_detection`**: IQR method (1.5x fence). Used to find antibody sequences with exceptional binding scores worth investigating further.
- **`rank_and_filter`**: sort values with labels, return top/bottom N with percentile context. Used to identify top-performing sequences by ID.
- **`cross_tabulate`**: count and percentage breakdown of two categorical variables. Used when multiple targets or assay types are present.
- **`frequency_table`**: count and percentage per category. Used for categorical distributions like target breakdown.

### Error handling: return error dict so agent can adapt

Tool errors are caught at the execution layer and returned as error dicts rather than raised as exceptions (except for truly unexpected failures which are caught at the phase runner level):

```python
try:
    result, reproducible_query = await execute_tool(block.name, block.input, pool)
except Exception as e:
    result = {"error": str(e)}
    reproducible_query = "N/A (error)"
```

The agent receives the error as a tool result and can adapt its plan. If SAbDab returns a 503, the agent's next turn might say "SAbDab returned an error, I'll note this as a limitation and focus on AlphaSeq and ChEMBL." This is better than terminating the investigation.

### httpx for REST clients with configurable timeouts

Both SAbDab and ChEMBL clients use `httpx.AsyncClient` with explicit timeouts:
- SAbDab: 30s for searches, 15s for point lookups, 10s for connectivity checks
- ChEMBL: 30s for bioactivity queries, 20s for searches, 15s for point lookups

These are one-request-per-call (not pooled). The tool phase loops call tools sequentially, so there is no concurrent request pressure. The `async with` context manager ensures clean connection teardown after each call.

### Key interview talking points

- "Every tool returns `(result, reproducible_query)`. That tuple is the mechanism for scientific reproducibility — every claim in the report can be independently verified."
- "The statistics tool is pure Python by design: minimal dependencies, transparent implementations, faster container builds. scipy is overkill for the analyses we need."
- "The agent doesn't know whether data comes from Postgres or a REST API. That's intentional — it keeps reasoning clean and makes it easy to add new data sources."
- "Errors are returned as dicts, not raised as exceptions. The agent adapts its plan when a source fails, rather than terminating the investigation."

### Decisions made

| What | Why |
|------|-----|
| Unified `(result, reproducible_query)` return | Reproducibility for audit trail; every claim citable |
| No scipy in statistics tool | Minimal deps, transparent formulas, faster image builds |
| Errors return dicts, not exceptions | Agent can adapt plan; investigation survives source failures |
| asyncpg parameterized queries | SQL injection safety; standard practice |
| httpx with explicit timeouts | Prevents hanging on slow APIs; appropriate per-action granularity |

---

## 6. Data Map Pattern

### What we're building

BioAgent needs to tell the agent what data is available before it starts investigating. Without a data map, the agent would have to discover the data landscape through trial-and-error, wasting turns and producing inconsistent results.

The data map is a structured registry of:
- Which data sources exist, what they contain, and how many records they have
- What entity types each source holds (antibodies, structures, bioactivity measurements)
- How entities relate across sources
- Crucially: how to cross-reference between sources when there are no shared identifiers

### How it's used

The data map is serialised to human-readable text by `describe_data_map()` and injected into the Research and Execute system prompts. The agent reads it as part of its instructions.

```
# Connected Data Sources

## AlphaSeq (local_db)
MIT Lincoln Lab antibody-antigen binding dataset. 104,972 antibody sequences with
quantitative binding scores against SARS-CoV-2 spike protein variants...
Records: 104,972
Entity types: antibody, target

## SAbDab (rest_api)
Structural Antibody Database from Oxford Protein Informatics Group...
Records: 18,744
...

## Cross-Reference Strategy

1. AlphaSeq target → SAbDab antigen: AlphaSeq MIT_Target = SARS-CoV-2 spike protein.
   Search SAbDab with antigen_name='spike' to find crystal structures targeting the same protein.
2. AlphaSeq target → ChEMBL target: Search ChEMBL for 'SARS-CoV-2 spike' to find compounds
   with measured bioactivity. Compare ChEMBL IC50/Ki with AlphaSeq binding scores.
```

The agent uses this to plan its investigation. When it sees "MIT_Target = SARS-CoV-2 spike protein," it knows to search SAbDab with `antigen_name='spike'` — not with `antigen_name='MIT_Target'`, which would return nothing.

### Cross-referencing is semantic, not ID-based

This is the core challenge of multi-database investigation in biology: databases rarely share identifiers. AlphaSeq uses internal sequence IDs. SAbDab uses PDB codes. ChEMBL uses ChEMBL IDs. There is no foreign key from an AlphaSeq record to a SAbDab record.

The connection happens through shared biology. The target in AlphaSeq called `MIT_Target` is the SARS-CoV-2 spike protein. In SAbDab, you search for structures targeting "spike" or "SARS-CoV-2." In ChEMBL, you search for targets matching "SARS-CoV-2 spike" or "coronavirus." The databases are linked by the protein identity, not by a shared ID.

```
AlphaSeq MIT_Target (104,972 antibodies against SARS-CoV-2 spike)
       ↓ semantic link: same biology
SAbDab structures with antigen_name='spike' (crystal structures of SARS-CoV-2 antibodies)
       ↓ semantic link: same protein target
ChEMBL CHEMBL3559560 (SARS-CoV-2 spike protein target, bioactivity data)
```

This requires domain knowledge to set up. The data map encodes that knowledge explicitly, so the agent does not have to infer it. The cross-reference strategy section of `describe_data_map()` gives the agent the exact search terms to use for each connection.

### Why this is more impressive than simple joins

A simple JOIN works when two tables share a foreign key. Connecting AlphaSeq to SAbDab requires knowing that:
1. `MIT_Target` is a dataset-specific name, not a standard identifier
2. It refers to SARS-CoV-2 spike protein
3. SAbDab calls this antigen "spike" or "SARS-CoV-2" (not "MIT_Target")
4. ChEMBL has a different taxonomy but the same biological target

This is the kind of cross-database reasoning that takes a domain expert to set up. The data map makes that expertise available to the agent at query time.

This directly connects to Joeri's work on Data Maps at Aizon — the concept that manufacturing data is valuable not in individual siloes but in how they connect. In pharma manufacturing, you might connect batch records to in-process quality data to final product testing to adverse event reports. The entity types and relationships differ, but the pattern is the same: encode the cross-reference strategy explicitly so automated agents (or analysts) can use it.

### `describe_data_map()` function

`describe_data_map()` takes a `DataMap` model and generates a multi-section text document. It is pure text generation — no templating engine, just string concatenation. The output is consumed by the LLM as part of the system prompt.

The format was designed for LLM consumption: clear section headers, explicit record counts, example search terms, and a dedicated "Cross-Reference Strategy" section that lists the exact relationships with specific parameter examples.

### Key interview talking points

- "There are no shared identifiers between AlphaSeq, SAbDab, and ChEMBL. Cross-referencing works through shared biology — the same protein target has different names in each database."
- "The data map is not just a schema description. It encodes the domain knowledge of how to connect the sources — something that normally lives in an expert's head."
- "This is the same pattern I used in Aizon's Data Maps work: encode the cross-reference strategy explicitly so it can be used by automated systems, not just by people who already know the domain."
- "The agent's unique value is not querying databases individually — any search box can do that. The value is knowing that AlphaSeq's MIT_Target and ChEMBL's SARS-CoV-2 spike are the same biology."

### Decisions made

| What | Why |
|------|-----|
| Data map as text injected into system prompt | Agent reads it as instructions; no special parsing needed |
| Cross-reference strategy as explicit text | Encodes domain knowledge; prevents agent from guessing wrong search terms |
| Semantic cross-referencing, not ID matching | No shared IDs exist between these databases; biological identity is the link |
| `describe_data_map()` output section per source | Clear structure for LLM parsing; includes record counts and entity types |

---

## 7. SSE Streaming Architecture

### What we're building

An investigation takes 2-5 minutes to complete. Showing nothing until it's done is terrible user experience. The user needs to see the agent's progress in real-time: which phase it's in, what tool calls it's making, what it's reasoning about.

Server-Sent Events (SSE) is the mechanism for streaming this live data from the FastAPI backend to the React frontend.

### Why SSE over WebSockets or polling

**WebSockets** are bidirectional. BioAgent only needs one direction: server pushes events to client. WebSockets add complexity (connection upgrade, heartbeats, reconnection logic) for a use case that is inherently one-directional.

**Polling** (client requests `/progress` every N seconds) introduces latency equal to the polling interval and wastes requests when nothing has changed. For a stream of events that happens continuously over 2-5 minutes, polling is the wrong tool.

**SSE** is a standard HTTP response with `Content-Type: text/event-stream`. The connection stays open; the server writes events as they happen. The browser handles reconnection automatically if the connection drops. It works over HTTP/1.1 and HTTP/2. It is simpler than WebSockets for one-directional streaming.

The one catch: native browser `EventSource` only supports GET requests. Since the investigation request includes a `question` parameter (and optionally an API key), it needs to be a POST. The frontend works around this with a custom ReadableStream implementation (see frontend section).

### Full proxy chain: FastAPI → nginx → Caddy → browser

In production, an SSE event travels through:

```
FastAPI (port 8000, inside Docker)
    → nginx (inside web Docker container, port 80)
    → Caddy (shared reverse proxy, port 443)
    → Browser
```

Each proxy in this chain has its own response buffering. Buffering is what breaks SSE: the proxy holds response bytes in a buffer until the buffer is full or the connection closes, rather than forwarding each event immediately.

Disabling buffering at each layer was required:

**nginx** (`web/nginx.conf`):
```nginx
location /api/ {
    proxy_pass http://api:8000/;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    proxy_read_timeout 300s;
}
```

`proxy_buffering off` disables nginx's response buffer. `proxy_read_timeout 300s` prevents nginx from terminating long-running investigations. The `Connection ''` header is needed for HTTP/1.1 keep-alive.

**Caddy** (`Caddyfile`):
```
flush_interval -1
```

`flush_interval -1` tells Caddy to flush the response immediately for every write, disabling Caddy's default response buffering.

Both were needed. Fixing only nginx still showed buffered output at the Caddy layer.

### `EventSourceResponse` from sse-starlette

FastAPI does not have built-in SSE support. `sse-starlette` provides `EventSourceResponse`, which takes an async generator and streams each `yield`ed dict as an SSE event.

```python
@app.post("/investigate")
async def start_investigation(request: InvestigationRequest):
    async def event_stream() -> AsyncGenerator[dict, None]:
        async for event in investigate(request.question, _pool, api_key=request.api_key):
            yield {
                "event": event.event_type,
                "data": event.model_dump_json(),
            }
    return EventSourceResponse(event_stream())
```

The `event` field sets the SSE event type. The `data` field is the JSON-serialised `TraceEvent`. The frontend parses both.

### Frontend parsing: ReadableStream, manual line-by-line

The frontend cannot use the browser's native `EventSource` API because `EventSource` only supports GET requests. The investigation endpoint is a POST (it needs to send the question in the request body).

The solution is to use the `fetch()` API to make the POST request and then read the response body as a `ReadableStream`. The stream is decoded UTF-8 line by line. SSE events are formatted as:

```
event: phase_change
data: {"event_type": "phase_change", "data": {"phase": "execute"}}

event: trace_step
data: {"event_type": "trace_step", "data": {...}}

```

The frontend parser accumulates lines, splits on the blank line that separates events, extracts the `event:` and `data:` values, parses the JSON data, and dispatches to the appropriate state update. This is ~30 lines of TypeScript in `api.ts`.

### AbortController for stop button

When the user clicks "Stop," the frontend calls `controller.abort()` on the `AbortController` attached to the `fetch()` call. The browser terminates the HTTP connection. The FastAPI generator raises `asyncio.CancelledError` (or the response simply stops being read), and the investigation stops.

The stop button stores a cancel function in a React ref (`cancelRef`), which the `handleCancel` callback invokes. The ref avoids stale-closure issues with the investigating state.

### Event types

| Event type | When emitted | Data |
|------------|--------------|------|
| `phase_change` | Agent enters a new phase | `{phase: "research"\|"plan"\|"execute"\|"synthesize"}` |
| `thinking` | LLM call is in progress (turn N) | `{turn: N}` |
| `trace_step` | Agent reasoning or tool call completes | step data including optional tool call |
| `report` | Final synthesis completes | `{report: "...markdown..."}` |
| `error` | Any error in the pipeline | `{message: "..."}` |
| `retry` | Rate limit hit, retrying | `{attempt: N, wait_seconds: N}` |

### The bug: SSE didn't work through the proxy chain

When BioAgent was first deployed, the investigation UI appeared to hang. The spinner ran for 2-5 minutes and then the entire investigation appeared at once, rather than streaming.

The cause was nginx's response buffering. nginx was holding all SSE events in its buffer and flushing them when the response completed (the connection closed). Adding `proxy_buffering off` to the nginx location block fixed partial streaming. Then Caddy's own buffering caused the same issue at the next layer. Adding `flush_interval -1` to the Caddy config fixed it fully.

The lesson: in a proxy chain, every proxy that handles the response can buffer it. SSE streaming requires disabling buffering at every layer.

### Key interview talking points

- "SSE over WebSockets because the communication is one-directional. WebSockets are for bidirectional real-time, which is more than we need."
- "The native `EventSource` API only supports GET. We use `fetch()` with `ReadableStream` and manual line parsing to support POST. About 30 lines of TypeScript."
- "The buffering bug took an hour to debug. Every proxy in the chain — nginx inside the web container, Caddy as the reverse proxy — had its own response buffer. Both had to be disabled."
- "AbortController gives you a clean stop: the browser terminates the connection, the Python generator stops yielding, the investigation halts."

### Decisions made

| What | Why |
|------|-----|
| SSE over WebSockets | One-directional streaming; simpler protocol; native browser reconnection |
| Manual `fetch()` + `ReadableStream` | `EventSource` doesn't support POST requests |
| `proxy_buffering off` in nginx | Prevents buffering at the web container proxy layer |
| `flush_interval -1` in Caddy | Prevents buffering at the reverse proxy layer |
| `proxy_read_timeout 300s` in nginx | Prevents nginx from terminating long investigations |
| `EventSourceResponse` from sse-starlette | FastAPI has no built-in SSE; sse-starlette is the standard solution |

---

## 8. Immutable Data Models

### What we're building

BioAgent needs to track the state of an investigation as it progresses: which steps have been completed, what each step found, what tool calls were made, and the final report. This state is accumulated over 30-50 steps across 4 agent phases.

The design choice is to make all domain models immutable (`frozen=True` in Pydantic), and to return new objects on every state change rather than mutating existing ones.

### All Pydantic models `frozen=True`

Every Pydantic model in `models.py` is declared with `frozen=True`:

```python
class Investigation(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    question: str
    steps: tuple[TraceStep, ...] = ()
    report: str | None = None
    ...

class TraceStep(BaseModel, frozen=True):
    step_number: int
    phase: AgentPhase
    tool_call: ToolCall | None = None
    ...
```

`frozen=True` means the model instances are hashable and cannot be modified after creation. Attempting to assign to a field raises a `ValidationError`.

Note the use of `tuple` rather than `list` for `steps`. Lists are mutable. A frozen Pydantic model with a list field can have the list contents modified (even if the list reference itself is frozen). Using `tuple` enforces true immutability of the collection.

### `add_step()` returns new Investigation

```python
def add_step(investigation: Investigation, *, phase, description, reasoning, tool_call=None) -> Investigation:
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
        steps=(*investigation.steps, step),  # new tuple with appended step
        report=investigation.report,
        data_map=investigation.data_map,
    )
```

The spread `(*investigation.steps, step)` creates a new tuple. The returned `Investigation` is a completely new object. The original `investigation` is unchanged.

`complete_investigation()` works the same way: returns a new `Investigation` with `completed_at` set and `report` populated.

### Why immutability

**Prevents bugs.** Mutable shared state is the source of a large class of bugs: a function modifies an object thinking it's safe, a second reference to that object now has unexpected data. With frozen models, this is impossible. The compiler (Pydantic's validation) prevents it.

**Makes handoffs explicit.** In the RPES architecture, each phase receives `state.investigation` and must assign `state.investigation = add_step(...)` to update it. The assignment is visible and intentional. There is no way to accidentally update the investigation without an explicit reassignment.

**Thread-safe.** Immutable objects can be shared across threads without locks. While BioAgent is currently single-threaded per investigation, this matters for future parallelisation.

**Debuggable.** At any point, you can inspect the `investigation` object and know it accurately represents the state at that moment. There is no risk of it being modified by a concurrent branch of code.

### Trade-off: memory vs safety

Creating a new `Investigation` object for every step means ~50 object allocations per investigation. Each allocation copies the `steps` tuple (which grows by one element each time), so the total memory cost is roughly O(n²) where n is the number of steps.

For 50 steps, this is ~1,250 object-tuple allocations. Each `Investigation` object is small (a few kilobytes). The total memory cost per investigation is well under 1MB. On a 4GB server, this is irrelevant.

The trade-off is explicitly the right one: pay a small memory cost for the correctness guarantees that immutability provides. At 100x scale, you might introduce a cursor-based approach (append to a mutable list, snapshot immutably on read), but this is premature optimisation for a demo.

### Domain models: AntibodyBinding, AntibodyStructure, BioactivityRecord

The three data source models are also frozen:

```python
class AntibodyBinding(BaseModel, frozen=True):
    sequence_id: str
    vh_sequence: str
    vl_sequence: str | None = None
    target: str
    binding_score: float
    kd_nm: float | None = None
    dataset: str = "alphaseq"
```

These are the typed representations of external data. Making them frozen means a tool function cannot accidentally modify a record after parsing it. The records are parsed once, passed to the agent, and never modified.

### Key interview talking points

- "Every model is `frozen=True`. You cannot accidentally modify an investigation state — the only way to change it is to call `add_step()`, which returns a new object."
- "We use `tuple` for the steps collection, not `list`. A frozen Pydantic model with a mutable list field can still have its list contents modified. Tuple prevents that."
- "The memory cost of immutability is O(n²) in allocations, but we're talking kilobytes at 50 steps. The correctness guarantees are worth it."
- "Immutability also makes debugging trivial: any state snapshot is accurate and stable. There's no question of 'was this modified after I captured it.'"

### Decisions made

| What | Why |
|------|-----|
| `frozen=True` on all Pydantic models | Correctness guarantees; prevents accidental mutation |
| `tuple` for `steps` collection | Lists are mutable even in frozen models; tuple enforces collection immutability |
| `add_step()` / `complete_investigation()` return new objects | Explicit handoffs; no shared mutable state |
| `_PhaseState` as mutable wrapper | Orchestrator needs a mutable reference for within-phase accumulation; domain model stays immutable |

---

## 9. LLM Integration & Error Handling

### What we're building

BioAgent calls Claude for every phase of every investigation. That means 4 Claude calls per investigation minimum (one per phase), plus additional calls for each turn within the tool phases. A complete investigation makes 25-35 LLM calls. Each one needs to be reliable, non-blocking, and graceful on failure.

### Anthropic API primary, Bedrock fallback

The `_create_client()` function checks for an `ANTHROPIC_API_KEY` environment variable. If present, it uses the direct Anthropic API (`anthropic.Anthropic`). If absent, it falls back to AWS Bedrock (`anthropic.AnthropicBedrock`) using ambient AWS credentials.

```python
def _create_client(api_key=None) -> tuple[client, model_id]:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return anthropic.Anthropic(api_key=key), "claude-sonnet-4-20250514"
    return (
        anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
    )
```

The model ID differs between direct API and Bedrock — this is an Anthropic/AWS platform detail that the function handles transparently.

Why Bedrock as fallback? During development, Joeri had AWS Bedrock access via Aizon's account before adding Anthropic API credits. Bedrock support cost little to maintain and provides a fallback if Anthropic's service is unavailable.

### Model: Claude Sonnet 4

Sonnet 4 (`claude-sonnet-4-20250514`) was chosen over Haiku and Opus.

**vs Haiku**: Haiku is faster and cheaper, but the quality of reasoning for multi-step scientific investigation is noticeably lower. A research question involving cross-database antibody analysis requires the model to hold multiple hypotheses, track data from different sources, and draw conclusions across domains. Haiku handles this poorly — it misses cross-references and produces shallower analyses.

**vs Opus**: Opus produces the best reasoning but is 3-5x more expensive and significantly slower (10-15s per call vs 3-5s for Sonnet). For a demo running 30+ LLM calls per investigation, Opus would make the user-facing experience too slow and the API costs too high. Sonnet 4 represents the right cost/quality tradeoff.

### `_call_llm()` — shared function across all phases

All four phase runners use the same `_call_llm()` function. It handles:
- Building the `kwargs` dict (model, max_tokens, system, messages, optional tools)
- Running the synchronous Anthropic SDK call in a thread executor (non-blocking)
- Retry loop with exponential backoff
- Firing the `on_retry` callback before each sleep

```python
async def _call_llm(client, model, *, system, messages, tools=None, on_retry=None):
    kwargs = {"model": model, "max_tokens": 4096, "system": system, "messages": messages}
    if tools:
        kwargs["tools"] = tools

    loop = asyncio.get_event_loop()
    for attempt in range(3):
        try:
            return await loop.run_in_executor(None, partial(client.messages.create, **kwargs))
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            if on_retry:
                on_retry(attempt + 1, wait)
            await asyncio.sleep(wait)
    raise last_err
```

### Rate limit retry: exponential backoff (5s, 10s, 20s)

Rate limit errors from the Anthropic API are retried up to 3 times with waits of 5, 10, and 20 seconds. The `on_retry` callback fires before each sleep — the phase runner uses it to yield a `retry` TraceEvent, which the frontend displays as a status message ("Rate limited — retrying in 10s (attempt 2/3)").

If all 3 attempts fail, the last `RateLimitError` is re-raised and caught by `_handle_api_error()`, which produces an `error` TraceEvent.

### API error mapping

`_handle_api_error()` maps Anthropic SDK exceptions to user-friendly messages:

| Exception | User message |
|-----------|-------------|
| `AuthenticationError` | "API key may be invalid or expired" |
| `RateLimitError` (after retries) | "Rate limit reached. Please wait a moment and try again." |
| `BadRequestError` with "credit" | "The AI service has insufficient credits." |
| `APIStatusError` with "overloaded" | "The AI model is currently overloaded." |
| `APIConnectionError` | "Could not connect to the AI service." |

Billing errors are detected by checking for "credit" or "billing" in the error message — these surface when the Anthropic account has no credits, a real-world scenario that happened during development.

### `run_in_executor` for non-blocking LLM calls

The Anthropic Python SDK is synchronous (`client.messages.create(...)` is a blocking call). BioAgent uses FastAPI's async event loop. A blocking SDK call in an async function would block the entire event loop, preventing the server from handling other requests or yielding SSE events during the wait.

The solution is `loop.run_in_executor(None, partial(client.messages.create, **kwargs))`. This runs the synchronous SDK call in a thread pool executor, leaving the event loop free to handle other work. The `await` suspends the coroutine until the thread finishes.

### Key interview talking points

- "The Anthropic SDK is synchronous. Calling it directly in an async function blocks the event loop. `run_in_executor` moves it to a thread pool — the event loop stays free for SSE event delivery and other requests."
- "Retry logic uses exponential backoff with a callback. The callback lets the frontend show 'retrying in 10s' rather than a silent hang."
- "Sonnet 4 over Haiku because the quality of cross-database reasoning matters. Haiku misses cross-references. Sonnet 4 over Opus because 30+ LLM calls per investigation at Opus latency and cost is prohibitive for a demo."
- "Billing errors are detected by string matching on the error message body. That is not elegant, but it is practical — the Anthropic SDK does not expose a specific billing error type."

### Decisions made

| What | Why |
|------|-----|
| Direct Anthropic API primary | Simpler auth, no AWS dependency |
| Bedrock fallback | Was available during early development; low cost to keep |
| Claude Sonnet 4 | Best cost/quality/speed tradeoff for multi-step scientific reasoning |
| `run_in_executor` | Anthropic SDK is sync; keeps FastAPI event loop non-blocking |
| Exponential backoff (5s, 10s, 20s) | Standard pattern for rate limit handling; 3 attempts covers transient spikes |
| 4096 max tokens | Sufficient for phase outputs; Synthesis and Plan may produce long markdown |

---

## 10. Frontend Architecture

### What we're building

The frontend is a single-page React app that shows:
1. The live investigation stream (phase progress, agent steps, tool calls)
2. The final report when synthesis completes
3. An audit trail panel with every trace step and reproducible query
4. A "How It Works" panel that explains the system to non-technical visitors

The app is designed to tell its own story. The default view is "How It Works" — when a visitor opens the URL, they see an explanation of the system before touching the investigation feature.

### React 19 + TypeScript + Vite + Tailwind

Standard modern stack for a TypeScript React app. React 19 is the latest stable version; no unusual features are used. TypeScript provides type safety for the event parsing and state management. Vite provides fast development builds. Tailwind provides utility-class styling with a custom dark theme (`bio-*` color tokens).

The `web/.npmrc` file overrides the global npm registry. Joeri's global `~/.npmrc` points to Aizon's private CodeArtifact registry (with auth tokens). The project-level `.npmrc` overrides this to use the public registry, preventing build failures when deploying on servers that don't have those tokens.

### State management: React hooks only

No Redux, no Zustand, no context. The investigation state lives in `App.tsx` as plain `useState` hooks:

```typescript
const [currentPhase, setCurrentPhase] = useState<string | null>(null);
const [steps, setSteps] = useState<TraceStep[]>([]);
const [report, setReport] = useState<string | null>(null);
const [isThinking, setIsThinking] = useState(false);
const cancelRef = useRef<(() => void) | null>(null);
```

Why no state management library? The app has a single investigation in flight at a time, a linear flow (pre-investigation → investigating → done), and all state is read by components that are direct children of `App`. There is no cross-cutting state that needs a store. Adding Redux for this would be structural complexity with no benefit.

### Phase pipeline visualization

The `PhasePipeline` component renders a horizontal bar showing the four RPES phases. Each phase card has three states:
- **Future** (not yet reached): dim, muted
- **Active** (currently running): colored border + gradient background + animated pulse dot
- **Done** (completed): checkmark, softer color

Phase colors:
- Research: blue
- Plan: amber
- Execute: emerald (green)
- Synthesise: purple

The color associations are not arbitrary. Blue for research (exploration), amber for planning (caution/deliberation), green for execution (action), purple for synthesis (insight). These are consistent throughout the UI — step cards in the investigation panel use the same color per phase.

### Thinking indicator with cycling messages

While waiting for the LLM to respond (between tool calls, or before the first response in a phase), the frontend shows a `ThinkingCard`. It displays a spinner ring and a cycling text message. Messages are phase-specific:

```typescript
const THINKING_MESSAGES: Record<string, string[]> = {
  research: ["Research agent exploring data landscape", "Checking database connectivity", ...],
  execute: ["Execute agent running queries", "Cross-referencing findings between databases", ...],
  synthesize: ["Synthesis agent compiling report", "Connecting evidence across sources", ...],
};
```

Messages cycle every 2.8 seconds. This prevents the UI from feeling frozen during long LLM calls. The messages set accurate expectations about what the agent is doing.

### Report export: .md and .docx with audit trail appendix

When synthesis completes, the user can export the full report as a Markdown file or a Word document. Both formats include:
- The original question
- Research summary (from the Research phase's final text)
- Investigation plan (from the Plan phase's final text)
- The synthesis report
- Appendix: every tool call with phase, duration, result summary, and reproducible query
- Appendix: data source usage table derived from actual tool calls

The `.docx` export uses the `docx` library in the browser. `markdownToParagraphs()` converts the markdown to `docx` `Paragraph` objects, handling headings (1-3), bullet points, thematic breaks, bold/code inline formatting, and table rows.

Why .docx? Pharma stakeholders work in Word. If a scientist wants to share an investigation report with a colleague or include it in a regulatory filing, they need a Word-compatible format. A plain markdown file is insufficient in that context.

### Three-column layout

The investigate view has three columns:
- **Left (320px)**: Data Map panel showing source connectivity, entity types, and relationships
- **Center (flex-1)**: Investigation stream, question input, report
- **Right (320px)**: Audit trail panel, visible once steps exist

The right column is always visible once investigation starts — users should not have to discover the audit trail. It auto-scrolls to show new steps as they arrive.

### "How It Works" as default tab

The app opens on "How It Works," not "Investigate." This is a deliberate UX choice for a demo:
1. Visitors may not know what BioAgent does
2. The explanation panel builds credibility before the user touches the system
3. If the investigation fails for any reason (rate limit, source unavailable), the visitor has already understood what the system is supposed to do

The panel covers: RPES methodology, the three data sources, the data map concept, GxP design patterns, and sample questions.

### Source health indicators in header

The header shows a colored dot and label for each data source (AlphaSeq, SAbDab, ChEMBL). Green = connected, yellow = unavailable. Hovering shows a tooltip explaining that if a source is unavailable, the agent will use the remaining sources.

This is loaded via a `/health` call on page load. SAbDab has historically returned 503 on their servers — this indicator gives users and demos confidence that BioAgent handles degraded connectivity gracefully.

### Dark theme design language

The color tokens (`bio-bg`, `bio-card`, `bio-border`, `bio-accent`, `bio-muted`) are defined in `tailwind.config.ts`. The same dark theme was used in the clinical-trial-rag project. Reusing it saved significant design time and creates visual consistency across portfolio projects.

### Key interview talking points

- "No Redux. The app is a linear flow with one investigation in flight. useState is sufficient; adding a state management library would be complexity for no benefit."
- "Export to .docx because pharma stakeholders live in Word. The audit trail appendix in the export is how a scientist would share findings with a regulator."
- "The default view is 'How It Works.' This is deliberate — when the CEO opens the URL, he sees an explanation of the system. The investigation feature is the second thing he encounters."
- "The thinking indicator cycles through phase-specific messages. It's not decorative — it sets accurate expectations about what the agent is doing between tool calls."

### Decisions made

| What | Why |
|------|-----|
| React hooks only, no state library | Single-investigation linear flow; no cross-cutting state; Redux is overhead |
| "How It Works" as default view | Demo UX: visitors understand the system before using it |
| .docx export | Pharma audience works in Word; regulatory filing compatibility |
| Three-column layout | Data map + investigation stream + audit trail always visible |
| Phase-specific colors and messages | Communicates agent structure visually; reinforces RPES separation |
| Source health indicators | Sets expectations for degraded connectivity; SAbDab frequently returns 503 |

---

## 11. Infrastructure & Deployment

### What we're building

BioAgent runs on a single Hetzner VPS, shared with another project (datavoorelkaar). The deployment stack is: Caddy (HTTPS reverse proxy, shared) → Docker containers (web nginx, FastAPI API, PostgreSQL). Everything runs via Docker Compose.

### Docker Compose: local dev vs production configs

**Local** (`docker-compose.yml`): Simple. No resource limits. API port exposed on 8000. Postgres password is `bioagent` (hardcoded, fine for local). Bedrock credentials passed through for fallback.

**Production** (`deploy/docker-compose.yml`): Credentials from `.env` file (`ANTHROPIC_API_KEY`, `POSTGRES_PASSWORD`). Resource limits enforced. API port 8001 (not 8000 — avoids conflict with datavoorelkaar on the same host). Health checks on all services. Log rotation via json-file driver.

Resource limits in production:
- `db`: 256MB RAM, 0.25 CPU
- `api`: 512MB RAM, 0.5 CPU

These are tight for a 4GB server shared with another project. They prevent BioAgent from starving the other services.

### Multi-stage frontend build

The web Dockerfile uses two stages:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

The final image contains only nginx and the compiled static assets — no Node.js runtime, no `node_modules`. The resulting image is ~30MB. The build stage (which includes all node_modules) is discarded.

This is the standard pattern for production React deployments. The small final image means faster pulls on deploy and less attack surface.

### Hetzner CX22 (2 vCPU, 4GB RAM)

The server is a shared VPS at €3.79/month. It runs BioAgent and datavoorelkaar simultaneously. This is aggressive resource sharing — an investigation doing 30 LLM calls will not OOM the server, but it will use significant CPU during the AI processing and database queries.

The resource limits on the Docker containers prevent one project from taking down the other.

### Caddy reverse proxy: auto HTTPS via Let's Encrypt

Caddy's killer feature is automatic TLS certificate provisioning and renewal via Let's Encrypt. Zero configuration: point a domain at the server, add the domain to the Caddyfile, and Caddy handles the rest.

BioAgent routes in the Caddy config:
```
bioagent.eu {
    reverse_proxy 172.17.0.1:3001
    flush_interval -1
}
```

`172.17.0.1` is the Docker bridge network's host-facing IP. This is how containers reach the host machine. Port 3001 is where the web Docker container listens.

### IPv6 gotcha: `host.docker.internal` resolves to IPv6

On Linux, `host.docker.internal` resolves to an IPv6 address. Docker's containers bind to IPv4 by default. So `host.docker.internal:3001` fails — there is a listener on `0.0.0.0:3001` (IPv4) but nothing on the IPv6 address.

The fix: use `172.17.0.1` (the Docker bridge network's IPv4 gateway) instead of `host.docker.internal`. This is not documented prominently; it took an hour of debugging on the production server to discover.

This is macOS-specific in reverse: on macOS, `host.docker.internal` works reliably for local development. On Linux servers, it does not.

### OOM on ingest: streaming CSV fix

During the first production deploy, the ingest service OOM-killed. The original implementation loaded the entire CSV into memory:

```python
df = pd.read_csv(csv_path)  # 50MB CSV → ~300MB DataFrame in memory
```

On a 4GB server with Docker resource limits and other containers running, loading a 300MB object at ingest time caused an OOM kill.

The fix was to stream the CSV row by row using Python's `csv.DictReader` and batch-insert every 5,000 rows:

```python
with open(data_path, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        batch.append(...)
        if len(batch) >= 5000:
            await conn.executemany(INSERT_SQL, batch)
            batch = []
```

Peak memory usage dropped from ~300MB to ~5MB (the batch). This is the correct pattern for any dataset ingestion that cannot fit in available RAM.

### Hatch package discovery for src layout

The project uses a `src/` layout (source code lives in `src/bioagent/`, not `bioagent/`). Python's package discovery does not automatically handle src layouts — it looks for packages in the project root.

`pyproject.toml` requires:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/bioagent"]
```

Without this, `pip install .` would succeed but `import bioagent` inside the Docker container would fail with `ModuleNotFoundError`. This cost an hour of debugging early in deployment.

### Deploy script

`deploy/deploy.sh` is a bash script that:
1. Checks for uncommitted changes (refuses to deploy dirty working tree)
2. Records the current commit hash
3. SSHs to the server
4. Pulls the latest code from GitHub
5. Runs `docker compose up -d --build`
6. Waits 15 seconds for containers to start
7. Runs a health check against the API
8. Checks if the database is empty and runs ingest if needed

The ingest step is idempotent: the ingest function checks `SELECT COUNT(*) FROM alphaseq_bindings` before doing anything. If records exist, it skips. This prevents re-ingesting 104,972 rows on every deploy.

### Log rotation

Both `db` and `api` containers use the `json-file` log driver with rotation:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "20m"
    max-file: "3"
```

A long-running production service without log rotation will fill the disk. The API generates significant log output during investigations (uvicorn access logs, any print statements from debugging that accidentally got left in). 3 files × 20MB = 60MB max for the API, 30MB for the database.

### Key interview talking points

- "Multi-stage Docker build: the production web image is ~30MB. The build stage is discarded. No node_modules in production."
- "The OOM bug on ingest is a lesson in the difference between development (32GB laptop) and production (4GB VPS). We fixed it by switching from pandas to streaming CSV parsing."
- "`host.docker.internal` works on macOS but resolves to IPv6 on Linux. Caddy binds to IPv4. Using `172.17.0.1` (the Docker bridge gateway IP) fixed the routing."
- "Resource limits in production Docker Compose prevent BioAgent from starving the co-hosted project. 512MB for the API is tight but sufficient."

### Decisions made

| What | Why |
|------|-----|
| Caddy as reverse proxy | Auto HTTPS via Let's Encrypt; zero certificate management |
| `172.17.0.1` instead of `host.docker.internal` | IPv6 resolution issue on Linux; Docker bridge is reliably IPv4 |
| Multi-stage frontend build | ~30MB final image; no Node.js runtime in production |
| Streaming CSV ingest (5,000-row batches) | 50MB CSV → OOM on 4GB server; streaming keeps peak memory at ~5MB |
| Resource limits in production compose | Shared server; prevents one service from starving the other |
| Log rotation (json-file, 20MB × 3) | Prevents disk fill on long-running service |
| `packages = ["src/bioagent"]` in pyproject.toml | src layout requires explicit package discovery for pip install |

---

## 12. Database & Ingestion

### What we're building

The AlphaSeq dataset is a 50MB CSV of 104,972 antibody-target binding measurements from MIT Lincoln Lab. It needs to live in a local PostgreSQL database so the agent can query it with sub-second latency. REST APIs (SAbDab, ChEMBL) are too slow for the exploratory phase; a local database supports the fast, repeated queries that the research and execute phases require.

### PostgreSQL 16 for AlphaSeq data

PostgreSQL 16 in a Docker container, using the `postgres:16-alpine` image (~80MB). Alpine base keeps the image small.

Schema:
```sql
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
```

Two indices: one on `target` (for filtering by target name in research queries), one on `binding_score` (for `ORDER BY binding_score DESC` in top-binders queries). Both are used in the hot paths. Without the `binding_score` index, `get_top_binders` would require a full table scan of 104,972 rows.

### 104,972 antibody binding records

The dataset covers:
- `MIT_Target`: ~40,000 records — antibodies against SARS-CoV-2 spike protein
- `AlphaNeg1`, `AlphaNeg2`, `AlphaNeg3`: negative controls (antibodies not targeting the spike protein, used to validate that high binding scores are specific to MIT_Target)

Binding scores are predicted affinities (not measured Kd), ranging from approximately 0.0 to ~1.0. Higher scores indicate stronger predicted binding.

### Streaming ingestion: row-by-row CSV reading, batch insert every 5,000 rows

As described in the Infrastructure section, the ingestion reads the CSV file row by row with `csv.DictReader`, accumulates rows into a batch, and inserts when the batch reaches 5,000 rows:

```python
batch_size = 5000
batch: list[tuple] = []
total_inserted = 0

with open(data_path, newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        # parse row...
        batch.append((poi, hc, lc, target, score, None))
        if len(batch) >= batch_size:
            await conn.executemany(INSERT_SQL, batch)
            total_inserted += len(batch)
            batch = []
```

`executemany` with asyncpg batches the 5,000-row insert into a single network round trip with PostgreSQL. This is ~20x faster than individual row inserts.

On first run: ingests 104,972 rows in approximately 45-60 seconds. On subsequent runs: detects existing data and skips. The check is `SELECT COUNT(*) FROM alphaseq_bindings` — idempotent.

### asyncpg connection pooling (min=1, max=5)

```python
_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
```

The connection pool is created at FastAPI startup (via the `lifespan` context manager) and closed at shutdown. Min=1 keeps one connection warm. Max=5 prevents too many connections on the 256MB-limited Postgres container.

The pool is passed to the investigation function as `pool: asyncpg.Pool | None`. If the pool failed to connect at startup (Postgres not ready), `pool` is `None` and the alphaseq tool returns a graceful error dict.

### Why asyncpg over psycopg

asyncpg is the native async PostgreSQL driver for Python. It uses PostgreSQL's binary protocol and avoids the GIL by implementing critical paths in C. Compared to psycopg3 (which has async support), asyncpg is generally faster for high-throughput async workloads and has a simpler async API.

psycopg3 has better Django/SQLAlchemy ORM integration. BioAgent uses raw SQL — no ORM — so asyncpg's simpler async interface is preferred.

### In-memory investigation store

Completed investigations are stored in a Python dict:
```python
_investigations: dict[UUID, Investigation] = {}
```

The `/trace/{investigation_id}` endpoint retrieves them. This is an in-memory store — if the API restarts, investigations are lost.

This is a deliberate trade-off for a demo. Persistent investigation storage would require another database table (or a document store), migration management, TTL logic to prevent unbounded growth, and backup/restore concerns. For a demo with one or two simultaneous users and occasional investigations, an in-memory dict is sufficient. The valuable output (the exported report) is client-side anyway.

### Key interview talking points

- "Streaming ingestion was forced by an OOM bug on the production server. The pattern — stream row by row, batch insert every N rows — is the correct approach for any dataset that might not fit in RAM."
- "asyncpg over psycopg because we use raw SQL (no ORM) and asyncpg's native async protocol is simpler and faster in that context."
- "The in-memory investigation store is a deliberate YAGNI call. The export functionality is client-side, so server-side persistence is not necessary for the demo use case."
- "Two indices: target for filtering, binding_score for ordering. Both are on the hot paths. Without them, research phase queries would full-scan 100K rows repeatedly."

### Decisions made

| What | Why |
|------|-----|
| PostgreSQL 16 | Reliable, known behavior for structured tabular data; asyncpg native support |
| Indices on `target` and `binding_score` | Both used in hot-path queries; essential for sub-second research phase performance |
| asyncpg over psycopg | Native async protocol; simpler API for raw SQL without ORM |
| 5,000-row batch inserts | Balance between memory (small batch) and insert performance (not one row at a time) |
| In-memory investigation store | YAGNI for demo; export is client-side; persistence adds complexity without value |
| Pool min=1, max=5 | One warm connection for latency; small max for 256MB Postgres memory limit |

---

## 13. The Development Journey

### Overview

BioAgent was built in 5 work sessions (labelled Sessions 1-6 in the commit history due to session numbering) over Easter Monday 2026-04-06. Total: 22 commits, ~14 hours of active development, from blank project to live production at bioagent.eu.

This is not a toy. The codebase is ~2,000 lines of Python and ~2,000 lines of TypeScript/React. It connects to real scientific databases, runs a genuine multi-agent investigation architecture, and is deployed on production infrastructure.

### Session 1 — Afternoon: Direction & Design

The starting point was a decision: what kind of system to build for a Head of AI interview at a pharma AI company?

Two directions were considered:
- **Direction A**: Multi-database agentic investigator (AlphaSeq + SAbDab + ChEMBL)
- **Direction B**: Single-database batch analytics system

Direction A was chosen because it is more directly relevant to pharma AI platforms that connect disparate data sources, it demonstrates multi-agent orchestration rather than just data engineering, and it gives an interviewer with a deep biology background something to engage with technically.

Session 1 output:
- Full design document covering architecture, data sources, agent design, and deployment plan
- Project scaffolded with pyproject.toml, src layout, Docker Compose
- Three data sources selected: AlphaSeq (MIT Lincoln Lab antibody dataset, Postgres), SAbDab (Oxford OPIG structural database, REST), ChEMBL (EMBL-EBI bioactivity database, REST). MaveDB was considered and rejected — MaveDB is a variant effect database, harder to cross-reference with the antibody binding focus.

### Session 2 — Evening 1: Full Stack Build

The entire backend was implemented in one session:
- `agent.py`: single-agent loop with keyword phase detection (the version later replaced)
- `models.py`: Pydantic domain models
- `data_map.py`: data source registry
- `tools/alphaseq.py`, `tools/sabdab.py`, `tools/chembl.py`
- `api.py`: FastAPI endpoints with SSE
- `ingest.py`: initial implementation (pandas, later OOM-killed)
- Frontend: React with How It Works panel, investigation view, trace/audit panel
- Docker Compose for local dev
- End-to-end test via AWS Bedrock: the agent ran a complete investigation, cross-referenced all three databases, and produced a coherent report

4 commits. The system was working end-to-end before any deployment work started.

### Session 3 — Evening 2: Deployment & Bugs

Session 3 focused on getting the system live:
- Switched from Bedrock-only to direct Anthropic API support
- Registered bioagent.eu domain via Gandi
- Created GitHub repo (tingidev/bioagent)
- Deployed to Hetzner CX22 server

Three bugs were encountered and fixed:

**OOM on ingest**: The ingest service loaded the full 50MB CSV into a pandas DataFrame (~300MB in memory) and OOM-killed. Fixed by switching to streaming CSV with `csv.DictReader` and batch inserts.

**IPv6 Caddy routing**: Caddy config used `host.docker.internal:3001`. On Linux, this resolves to IPv6. Docker containers listen on IPv4. Fixed by using `172.17.0.1:3001` (Docker bridge gateway IP).

**SSE proxy buffering**: The investigation stream appeared to hang for 2-5 minutes then dump all events at once. Fixed by adding `proxy_buffering off` to nginx and `flush_interval -1` to Caddy.

10 commits. Site live (pending Anthropic API credits being added).

### Session 4 — Evening 3: UI Polish & Backend Hardening

The investigation was working but the UI felt like a development prototype. Session 4 focused on production-quality UX:

**UI improvements**:
- Phase colours (blue/amber/emerald/purple) replacing a flat list
- Horizontal phase progress pipeline replacing a text label
- Favicon
- Markdown rendering in step cards (using `react-markdown`)
- Collapsible reasoning cards (long reasoning blocks collapsed to preview, click to expand)
- Redesigned findings panel
- Three-column layout (data map | investigation | audit trail)
- Always-visible audit trail panel once investigation starts
- Thinking indicator: spinner ring + cycling phase-specific messages
- Per-source health tooltips in header
- "New investigation" button

**Backend improvements**:
- Full API error handling (`_handle_api_error()`)
- Non-blocking LLM calls (`run_in_executor`)
- Thinking events streamed to frontend

### Session 5 — Evening 4: Stop Button, Export & Methodology Rewrite

Session 5 added the features that make BioAgent usable rather than just demonstrable:

**Stop button**: AbortController attached to the SSE connection. The cancel function stored in a React ref and invoked on click. Investigation terminates cleanly.

**Report export**: `.md` and `.docx` formats. `buildFullReport()` assembles research summary, plan, synthesis report, audit trail appendix, and data source usage table. `exportDocx()` uses the `docx` browser library.

**Methodology rewrite**: The system prompt was overhauled to explicitly describe RPES, deep cross-referencing instructions, and adaptive reasoning guidelines. This was a significant prompt engineering step — the previous prompt was a single paragraph; the new one was a detailed multi-section document.

**Data map enrichment**: The `data_map.py` cross-reference strategy section was added, giving the agent explicit search terms for connecting AlphaSeq targets to SAbDab antigens and ChEMBL targets.

**Multi-agent architecture designed** (not yet implemented): The multi-agent handoff design was drafted at the end of this session.

### Session 6 — Evening 5: Multi-Agent Handoffs

The most technically significant session. The single-agent loop was replaced with the 4-agent RPES architecture.

**Changes made**:
- `RESEARCH_PROMPT`, `PLAN_PROMPT`, `EXECUTE_PROMPT`, `SYNTHESISE_PROMPT` written as distinct prompts
- `_run_tool_phase()` and `_run_reasoning_phase()` implemented
- `_PhaseState` dataclass for shared mutable state
- `investigate()` orchestrator rewritten as 4 sequential phase calls
- Statistics tool expanded: added `correlation`, `outlier_detection`, `rank_and_filter`, `cross_tabulate`
- GxP section added to "How It Works" panel
- Retry with exponential backoff implemented
- Rate limit handling added
- Execute phase capped at 20 turns and prompt tuned for efficiency ("aim for 8-12 tool calls")
- Sample questions rewritten for demo resilience (SAbDab was frequently returning 503; new questions work with just AlphaSeq + ChEMBL)
- README updated and repo made public
- 22 commits total on main

The quality jump from single-agent to multi-agent was immediately visible. Investigation reports became more structured, cross-references became more explicit, and plans became more actionable.

### Key lessons from the journey

**Start with the simplest thing that works, then iterate.** Session 2 implemented a single-agent loop with keyword detection. It worked. The multi-agent architecture (Session 6) was built on top of a working foundation, not designed from scratch. This is always the right order.

**Deployment bugs take more time than expected.** OOM, IPv6, and SSE buffering together consumed most of Session 3 — a session planned for polish. Budget more time for deployment than you think you need.

**Prompt engineering is iterative.** The system prompt went through 4 major rewrites across the sessions. Each rewrite made the agent more focused, more specific about cross-referencing, and more likely to produce useful output. Prompt quality is a first-class engineering concern, not an afterthought.

**The move from single-agent to multi-agent was the biggest quality improvement.** More than UI polish, more than infrastructure work, the architectural separation of Research, Plan, Execute, and Synthesise produced the most visible improvement in output quality.

**Building for a specific audience focuses every decision.** Every feature was evaluated by asking "does this help pharma AI leadership understand and evaluate this system?" The "How It Works" default view, the GxP section, the DOCX export, the audit trail — all of these exist because the target audience is pharma AI professionals who expect rigour.

---

## 14. Security & GxP Considerations

### What we're building

BioAgent touches regulated territory: it is being demonstrated to a company that sells AI to pharmaceutical manufacturers. Even as a portfolio demo, the security and compliance design choices signal whether the builder understands pharma requirements.

### Parameterized SQL queries

All Postgres queries use positional parameters with asyncpg. User input (target names, score thresholds) from the LLM is never concatenated into SQL strings. SQL injection through the agent's tool calls is not possible.

```python
# Safe: user/agent input in params, not in the query string
conditions.append(f"target = ${idx}")
params.append(target)  # "MIT_Target" or any string; treated as value, not SQL
rows = await pool.fetch(query, *params)
```

### API key management

- `ANTHROPIC_API_KEY` and `POSTGRES_PASSWORD` are set via environment variables on the server
- They live in `/opt/bioagent/deploy/.env` on the Hetzner server, excluded from version control via `.gitignore`
- No secrets are committed to the GitHub repository
- The `.env.example` file provides a template with placeholder values

### CORS: open for development

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open — demo only
    allow_methods=["*"],
    allow_headers=["*"],
)
```

CORS is open (`*`) because the demo is single-user (there is no auth, no multi-tenancy, no user data). In production, this should be restricted to the specific frontend origin.

This is an acknowledged trade-off, not an oversight. The system has no user data to protect; open CORS does not create a meaningful attack surface for a public demo.

### Database: no external port in production

In the local `docker-compose.yml`, Postgres is exposed on `5432:5432` for development convenience. In `deploy/docker-compose.yml`, the port mapping is absent — Postgres is only accessible within the Docker network (service name `db`). External connections to Postgres are not possible.

### GxP design patterns

BioAgent is not GxP-qualified software. It is a portfolio demo. However, it is designed with patterns that pharma workflows expect.

**Reproducible queries**: Every tool call produces a `reproducible_query` string — the exact SQL or API call that produced the result. Any claim in the report can be independently verified by re-running that query. This is data traceability.

**Phase separation and audit trail**: The RPES architecture produces a step-by-step audit trail with timestamps, phase labels, reasoning text, and tool call details. You can reconstruct exactly what the agent investigated and in what order. This is an audit trail.

**Source attribution**: The synthesised report cites specific data points (sequence IDs, PDB codes, ChEMBL IDs, binding scores). AI interpretation is separated from raw data. The audit trail appendix in exports shows the data that underlies each conclusion.

**Not overclaiming**: The "How It Works" panel in the app states explicitly that BioAgent demonstrates GxP-compatible design patterns, not that it is GxP-qualified or validated software. This is the honest position. Validated software requires formal qualification, change control, and user acceptance testing.

### Why this matters for pharma AI roles

Anyone who has run AI at a regulated pharma company knows the difference between a data scientist who thinks about compliance and one who doesn't. Anyone from the antibody design or drug discovery space understands the scientific rigour requirements.

The design choices above signal that the builder understands pharma context: parameterized queries, immutable audit trails, reproducible queries, source attribution, and honest limitation statements. These are table stakes for enterprise pharma AI.

### Key interview talking points

- "We're not claiming GxP qualification — that requires formal validation. But the design patterns are what pharma expects: reproducible queries, phase-separated audit trails, source attribution in every report."
- "Every tool call returns a `reproducible_query`. Not a summary, not a description — the exact SQL or API call. A scientist can re-run it independently."
- "CORS is open because there's no user data. In a production multi-tenant deployment, you'd restrict to the frontend origin and add authentication."
- "Parameterized SQL everywhere. The agent controls the tool inputs. If a malicious or garbled input made it through, asyncpg treats it as a string value, not as SQL."

### Decisions made

| What | Why |
|------|-----|
| Parameterized SQL | Injection safety; agent controls tool inputs |
| No Postgres port in production compose | Reduces attack surface; DB only accessible within Docker network |
| Open CORS | Demo-only, no user data; honest acknowledgement of trade-off |
| `reproducible_query` on every tool call | Scientific reproducibility; GxP traceability pattern |
| Phase-separated audit trail | Investigation auditability; each phase documented separately |
| Honest GxP framing | "Design patterns" not "qualified software"; avoids overclaiming |

---

## 15. What We Chose NOT To Do (YAGNI)

These are the features that were considered, explicitly rejected, and why the rejection was the right call — plus what you'd actually build for production.

### No authentication

**What was skipped**: Login, session management, user accounts, API key per-user.

**Why it was right**: BioAgent is a demo with a small intended audience. There is no data to protect per-user. Authentication adds frontend complexity (login form, session state, token refresh), backend complexity (user table, auth middleware, session storage), and deployment complexity (secure cookie config, HTTPS enforcement). None of that complexity produces value for a demo.

**For production**: Role-based authentication (admin vs user), API key management per organization, rate limits per user, audit trail associated with user identity. OAuth2/SSO integration for enterprise deployment.

### No persistent investigation storage

**What was skipped**: Database table for investigations, investigation history, ability to retrieve past investigations after server restart.

**Why it was right**: The valuable output of an investigation is the exported report, which is generated client-side. The in-memory store supports the `/trace/{id}` endpoint for the duration of a session. Investigations are not valuable enough to persist — a new investigation is a fresh start. Adding persistence requires schema design, migration management, TTL logic (how long to keep old investigations?), and backup/restore considerations. For a demo, none of this earns its complexity.

**For production**: Investigations stored in PostgreSQL (or a document database) with user ownership, TTL of 30-90 days, search by question text, re-run functionality. Integration with a lab notebook system or LIMS for pharma deployments.

### No charts/visualizations

**What was skipped**: Score distribution histograms, binding score scatter plots, CDR H3 length distributions, time-series charts.

**Why it was right**: Without meaningful interactive analysis, charts are cosmetic. A histogram of binding scores is visually appealing but tells you no more than the descriptive statistics the agent already computes and interprets. The agent uses the statistics tool to extract the numerically significant features and writes them into the report in prose. Adding a chart library (Recharts, Vega, Plotly) for purely cosmetic charts would increase bundle size and development time without improving the investigation quality.

The counter-argument is that interactive charts would let users explore the data themselves. That is true — but it is also a different product. BioAgent is an investigative agent, not a data exploration tool.

**For production**: Interactive binding score distribution with selectable targets, CDR H3 length vs binding score scatter with zoom, filtering. These would require the agent to emit structured data alongside prose, or a separate endpoint for raw dataset access.

### No code interpreter

**What was skipped**: A tool that lets the agent write and execute Python code (like ChatGPT's Advanced Data Analysis).

**Why it was right**: A code interpreter requires sandboxed execution (Docker-in-Docker or a subprocess jail), dependency management, and security controls around what the code can access. The implementation complexity is significant, and the risk of sandbox escapes or resource exhaustion is real. The statistics tool covers the analytical needs — descriptive stats, group comparison, correlation, outlier detection, ranking, cross-tabulation — with lower risk and simpler architecture. Every analysis the agent needs can be done with the 7 statistics actions.

**For production**: A sandboxed Python environment (Jupyter-style or E2B sandbox) would enable arbitrary data transformations, custom visualizations, and more complex statistical analyses. Worth the investment for a full research platform, not for an MVP demo.

### No caching layer

**What was skipped**: Redis cache for ChEMBL and SAbDab API responses.

**Why it was right**: An investigation makes ~10-15 unique queries across the external APIs. The same query is rarely repeated within a single investigation, and between investigations the questions and parameters differ. A cache hit rate would be low. Adding Redis requires another Docker service, cache invalidation strategy, and connection management. For a demo with 1-2 concurrent investigations, API latency from ChEMBL (~2-3s) and SAbDab (~1-5s) is acceptable.

**For production**: Redis cache with 24-hour TTL for common queries (target search results, database stats). The ChEMBL bioactivity endpoint is the slowest path — caching target bioactivity results would meaningfully reduce investigation time at scale. Rate limit budget also benefits from caching repeated queries.

### No test suite

**What was skipped**: Unit tests for tools, integration tests for the agent, end-to-end tests for the API.

**Why it was right**: The build window was 14 hours. Writing tests for a system that was still being architected (the agent design changed three times) would have consumed time that went to features the target audience would actually evaluate. Portfolio demos are evaluated on what they do, not on their test coverage. The statistics tool functions are pure Python — trivially testable — but testing them would not improve the demo experience.

This is an explicit violation of the normal development standards. It is acceptable only because: (1) no one else depends on this code, (2) the build was time-boxed, (3) the audience evaluates product, not code quality.

**For production**: pytest suite covering the statistics functions (pure Python, easily testable), integration tests for each tool against live databases (with fixtures for reproducibility), API tests using FastAPI's `TestClient`, and end-to-end investigation tests against a test question with known expected output. Target 80% coverage on the backend.

### No vector database

**What was skipped**: Pinecone, Weaviate, or pgvector for semantic search across antibody sequences or scientific literature.

**Why it was right**: BioAgent is not a RAG system. It does not need to search unstructured text. It queries structured databases (Postgres, REST APIs) using structured queries (SQL, search parameters). The agent's reasoning is what creates cross-database connections, not embedding similarity. Adding a vector database would imply a fundamentally different architecture (ingesting literature, chunking, embedding, retrieval-augmented generation) that is a different product category.

**For production**: Vector search on antibody sequences (to find structurally similar sequences to a query) would be a genuine enhancement. VH/VL amino acid sequences can be embedded using protein language models (ESM-2, ProtBERT) and searched with pgvector or Pinecone. This would add a new dimension to the investigation: "find antibodies with similar sequences to these top binders." Not needed for the demo; high value for a production research platform.

---

## Appendix: Quick Reference

### Data source sizes

| Source | Records | Type | Query latency |
|--------|---------|------|---------------|
| AlphaSeq (Postgres) | 104,972 | Local DB | <100ms |
| SAbDab | 18,744 | REST API | 1-5s |
| ChEMBL | 21.1M bioactivities | REST API | 2-5s |

### Agent phase budgets

| Phase | Tools | Max turns | Purpose |
|-------|-------|-----------|---------|
| Research | Yes | 15 | Explore data landscape |
| Plan | No | 1 | Design investigation strategy |
| Execute | Yes | 20 | Run queries, cross-reference |
| Synthesise | No | 1 | Write structured report |

### LLM retry schedule

| Attempt | Wait before retry |
|---------|------------------|
| 1 | 5 seconds |
| 2 | 10 seconds |
| 3 | 20 seconds |
| 4+ | Raise error |

### Infrastructure summary

```
Browser (HTTPS)
    ↓
Caddy (port 443, Let's Encrypt, flush_interval -1)
    ↓
web container nginx (port 3001, proxy_buffering off)
    ↓ /api/ →
api container (FastAPI, port 8000, uvicorn)
    ↓ asyncpg pool (min=1, max=5)
db container (PostgreSQL 16, 104,972 rows)
```

### Key file locations

- `src/bioagent/agent.py` — All agent logic: RPES prompts, phase runners, orchestrator (924 lines)
- `src/bioagent/models.py` — All Pydantic models (156 lines)
- `src/bioagent/data_map.py` — Data source registry and cross-reference strategy (125 lines)
- `src/bioagent/trace.py` — Audit trail functions (114 lines)
- `src/bioagent/tools/statistics.py` — Pure Python statistics (280 lines)
- `web/src/App.tsx` — React root component (250 lines)
- `web/src/exportReport.ts` — Report export logic (211 lines)
- `deploy/docker-compose.yml` — Production Docker Compose

---

*BioAgent was built in one day (Easter Monday 2026-04-06) as a portfolio piece for a Head of AI role at Katalyze AI. It is live at [bioagent.eu](https://bioagent.eu).*
