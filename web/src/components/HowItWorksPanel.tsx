export default function HowItWorksPanel() {
  return (
    <div className="flex-1 overflow-y-auto p-8 max-w-5xl mx-auto space-y-10">
      {/* Hero */}
      <section className="text-center space-y-3">
        <h2 className="text-2xl font-bold text-gray-100">
          An Agent That Investigates Across Databases
        </h2>
        <p className="text-bio-muted text-sm max-w-2xl mx-auto leading-relaxed">
          BioAgent connects to real scientific data sources, builds a navigable
          map of what's available, and reasons across them to answer research
          questions — with every step traced and every finding reproducible.
        </p>
      </section>

      {/* Data Sources */}
      <section className="space-y-4">
        <SectionHeader
          title="Connected Data Sources"
          subtitle="Real databases, real data. No synthetic shortcuts."
        />
        <div className="grid grid-cols-3 gap-4">
          <SourceCard
            name="MIT AlphaSeq"
            type="Local Database"
            color="text-blue-400"
            borderColor="border-blue-400/30"
            records="104,972"
            description="Antibody-antigen binding measurements from MIT Lincoln Lab. Heavy/light chain sequences with quantitative binding scores against SARS-CoV-2 spike protein variants."
            entities={["Antibody", "Target"]}
            queryExample="SELECT * FROM alphaseq_bindings WHERE binding_score > 6.0 ORDER BY binding_score DESC"
          />
          <SourceCard
            name="SAbDab"
            type="REST API"
            color="text-purple-400"
            borderColor="border-purple-400/30"
            records="18,744"
            description="Structural Antibody Database from Oxford. Curated crystal structures from the PDB with CDR annotations, species, resolution, and antigen binding data."
            entities={["Antibody", "Structure"]}
            queryExample="GET /sabdab/search/?antigen_name=spike&output=json"
          />
          <SourceCard
            name="ChEMBL 35"
            type="REST API"
            color="text-amber-400"
            borderColor="border-amber-400/30"
            records="21.1M"
            description="EMBL-EBI bioactivity database. Compounds, targets, and activity measurements (IC50, Ki, EC50) from medicinal chemistry literature."
            entities={["Compound", "Target", "Bioactivity", "Assay"]}
            queryExample="GET /chembl/api/data/activity.json?target_chembl_id=CHEMBL4662936"
          />
        </div>
      </section>

      {/* Data Map */}
      <section className="space-y-4">
        <SectionHeader
          title="Data Map"
          subtitle="Before investigating, the agent maps what's connected."
        />
        <div className="bg-bio-card border border-bio-border rounded-xl p-6">
          <div className="flex items-center justify-center gap-2 text-sm">
            <EntityNode label="Target" color="text-rose-400" />
            <Arrow label="binds" />
            <EntityNode label="Antibody" color="text-blue-400" />
            <Arrow label="has structure" />
            <EntityNode label="Structure" color="text-purple-400" />
          </div>
          <div className="flex items-center justify-center gap-2 text-sm mt-4">
            <EntityNode label="Target" color="text-rose-400" />
            <Arrow label="tested against" />
            <EntityNode label="Bioactivity" color="text-emerald-400" />
            <Arrow label="from assay" />
            <EntityNode label="Assay" color="text-sky-400" />
          </div>
          <div className="flex items-center justify-center gap-2 text-sm mt-4">
            <EntityNode label="Compound" color="text-amber-400" />
            <Arrow label="measured in" />
            <EntityNode label="Bioactivity" color="text-emerald-400" />
          </div>
          <p className="text-xs text-bio-muted text-center mt-5">
            The agent uses this map to navigate between sources. A question about
            an antibody target can lead to binding data (AlphaSeq), crystal
            structures (SAbDab), and known compounds (ChEMBL).
          </p>
        </div>
      </section>

      {/* Investigation Phases */}
      <section className="space-y-4">
        <SectionHeader
          title="Investigation Workflow"
          subtitle="The agent works in visible phases, each with a clear purpose."
        />
        <div className="grid grid-cols-4 gap-3">
          <PhaseCard
            number={1}
            name="Research"
            description="Profile the data landscape. Understand what's available before diving in. Get record counts, check connectivity, identify relevant entities."
            example="Get AlphaSeq statistics, list available targets, check which databases are reachable."
          />
          <PhaseCard
            number={2}
            name="Plan"
            description="Describe the investigation strategy. Which databases to query, in what order, and what to expect. Make the reasoning visible."
            example="'Top binders are against MIT_Target — I'll search ChEMBL for SARS-CoV-2 spike protein targets.'"
          />
          <PhaseCard
            number={3}
            name="Execute"
            description="Run queries across databases. Cross-reference findings. Follow leads from one source to another. Each call is logged."
            example="Query AlphaSeq top binders, search ChEMBL for matching targets, fetch bioactivity measurements."
          />
          <PhaseCard
            number={4}
            name="Synthesize"
            description="Produce a structured report with findings, citations to actual data, and reproducible queries. State what was and wasn't found."
            example="Report with cross-database connections, potency comparisons, and limitations."
          />
        </div>
      </section>

      {/* Traceability */}
      <section className="space-y-4">
        <SectionHeader
          title="Full Traceability"
          subtitle="Every step is auditable. Every finding is reproducible."
        />
        <div className="bg-bio-card border border-bio-border rounded-xl p-6 space-y-3">
          <TraceExample
            step={1}
            phase="research"
            action="query_alphaseq_bindings"
            detail="get_statistics"
            duration="22ms"
            query="SELECT COUNT(*), AVG(binding_score), STDDEV(binding_score) FROM alphaseq_bindings"
          />
          <TraceExample
            step={2}
            phase="execute"
            action="query_chembl"
            detail="search_target: SARS-CoV-2 spike"
            duration="2,270ms"
            query="GET https://www.ebi.ac.uk/chembl/api/data/target/search.json?q=SARS-CoV-2+spike&limit=10"
          />
          <TraceExample
            step={3}
            phase="execute"
            action="query_chembl"
            detail="get_bioactivities: CHEMBL4662936"
            duration="263ms"
            query="GET https://www.ebi.ac.uk/chembl/api/data/activity.json?target_chembl_id=CHEMBL4662936&limit=20"
          />
          <p className="text-xs text-bio-muted pt-2">
            Each trace entry includes the tool name, input parameters, output
            summary, execution time, and the exact query needed to reproduce the
            result independently. The full audit trail is available via the API
            after each investigation.
          </p>
        </div>
      </section>

      {/* Architecture */}
      <section className="space-y-4">
        <SectionHeader
          title="Architecture"
          subtitle="Python/FastAPI backend, React frontend, real-time streaming."
        />
        <div className="space-y-4">
          {/* Top row: Frontend ↔ API */}
          <div className="flex items-stretch gap-0">
            <ArchBox label="Frontend" accent>
              <p>React + TypeScript</p>
              <p>Live trace stream</p>
              <p>Data map panel</p>
              <p>Audit trail</p>
            </ArchBox>
            <ArchArrow label="SSE Stream" biDirectional />
            <ArchBox label="FastAPI Server" accent>
              <p>/investigate (SSE)</p>
              <p>/map</p>
              <p>/health</p>
              <p>/trace/&#123;id&#125;</p>
            </ArchBox>
          </div>

          {/* Down arrow */}
          <div className="flex justify-center">
            <ArchArrowDown />
          </div>

          {/* Agent box */}
          <div className="flex justify-center">
            <div className="rounded-lg border border-bio-accent/30 bg-bio-bg px-6 py-3 text-center">
              <span className="text-xs font-medium uppercase tracking-wider text-bio-accent">
                Agent Loop
              </span>
              <div className="mt-1 space-y-0.5 text-xs text-bio-muted">
                <p>Claude (LLM) via Bedrock</p>
                <p>Phase management</p>
                <p>Trace capture</p>
              </div>
            </div>
          </div>

          {/* Down arrow */}
          <div className="flex justify-center">
            <ArchArrowDown />
          </div>

          {/* Bottom row: 3 data sources */}
          <div className="flex items-stretch gap-0">
            <ArchBox label="AlphaSeq" color="text-blue-400" borderColor="border-blue-400/30">
              <p>PostgreSQL</p>
              <p>104,972 antibodies</p>
            </ArchBox>
            <ArchSpacer />
            <ArchBox label="SAbDab" color="text-purple-400" borderColor="border-purple-400/30">
              <p>REST API</p>
              <p>18,744 structures</p>
            </ArchBox>
            <ArchSpacer />
            <ArchBox label="ChEMBL" color="text-amber-400" borderColor="border-amber-400/30">
              <p>REST API</p>
              <p>21.1M activities</p>
            </ArchBox>
          </div>
        </div>
      </section>

      {/* Tech */}
      <section className="space-y-4 pb-8">
        <SectionHeader
          title="Built With"
          subtitle=""
        />
        <div className="flex flex-wrap gap-2 justify-center">
          {[
            "Python 3.12",
            "FastAPI",
            "asyncpg",
            "httpx",
            "Claude (Bedrock)",
            "PostgreSQL 16",
            "React 19",
            "TypeScript",
            "Vite",
            "Tailwind CSS",
            "SSE Streaming",
            "Docker Compose",
          ].map((tech) => (
            <span
              key={tech}
              className="text-xs px-3 py-1.5 rounded-full bg-bio-border text-gray-300"
            >
              {tech}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
        {title}
      </h3>
      {subtitle && (
        <p className="text-xs text-bio-muted mt-1">{subtitle}</p>
      )}
    </div>
  );
}

function SourceCard({
  name,
  type,
  color,
  borderColor,
  records,
  description,
  entities,
  queryExample,
}: {
  name: string;
  type: string;
  color: string;
  borderColor: string;
  records: string;
  description: string;
  entities: string[];
  queryExample: string;
}) {
  return (
    <div className={`bg-bio-card border ${borderColor} rounded-xl p-4 space-y-3`}>
      <div className="flex items-center justify-between">
        <span className={`font-semibold text-sm ${color}`}>{name}</span>
        <span className="text-[10px] text-bio-muted px-2 py-0.5 rounded-full bg-bio-border">
          {type}
        </span>
      </div>
      <p className="text-2xl font-bold text-gray-100">{records}</p>
      <p className="text-xs text-bio-muted leading-relaxed">{description}</p>
      <div className="flex flex-wrap gap-1.5">
        {entities.map((e) => (
          <span
            key={e}
            className="text-[10px] px-2 py-0.5 rounded border border-bio-border text-gray-300"
          >
            {e}
          </span>
        ))}
      </div>
      <div className="bg-bio-bg rounded p-2.5">
        <code className="text-[10px] break-all">
          <QueryHighlight query={queryExample} />
        </code>
      </div>
    </div>
  );
}

function QueryHighlight({ query }: { query: string }) {
  // SQL
  if (query.startsWith("SELECT")) {
    return highlightSql(query);
  }
  // REST
  if (query.startsWith("GET")) {
    return highlightRest(query);
  }
  return <span className="text-bio-muted">{query}</span>;
}

function highlightSql(query: string) {
  const kw = new Set(["SELECT", "FROM", "WHERE", "ORDER", "BY", "GROUP", "LIMIT", "AND", "OR", "AS", "COUNT", "AVG", "STDDEV", "MIN", "MAX", "DESC", "ASC"]);
  const tokens = query.split(/(\s+|\b)/);
  return (
    <>
      {tokens.map((tok, i) =>
        kw.has(tok) ? (
          <span key={i} className="text-gray-300 font-medium">{tok}</span>
        ) : (
          <span key={i} className="text-bio-muted">{tok}</span>
        ),
      )}
    </>
  );
}

function highlightRest(query: string) {
  const match = query.match(/^(GET)\s+(.+?)(\?.+)?$/);
  if (!match) return <span className="text-bio-muted">{query}</span>;
  const [, method, path, params] = match;
  return (
    <>
      <span className="text-gray-300 font-medium">{method}</span>
      <span className="text-bio-muted"> {path}</span>
      {params && <span className="text-gray-500">{params}</span>}
    </>
  );
}

function EntityNode({ label, color }: { label: string; color: string }) {
  return (
    <span className={`px-3 py-1.5 rounded-lg bg-bio-bg border border-bio-border ${color} font-medium`}>
      {label}
    </span>
  );
}

function Arrow({ label }: { label: string }) {
  return (
    <span className="text-bio-muted flex items-center gap-1">
      <span className="text-gray-600">---[</span>
      <span className="text-gray-500 text-[10px]">{label}</span>
      <span className="text-gray-600">]---&gt;</span>
    </span>
  );
}

function PhaseCard({
  number,
  name,
  description,
  example,
}: {
  number: number;
  name: string;
  description: string;
  example: string;
}) {
  return (
    <div className="bg-bio-card border border-bio-border rounded-xl p-4 space-y-2 relative">
      <div className="flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-bio-accent/20 text-bio-accent text-xs font-bold flex items-center justify-center">
          {number}
        </span>
        <span className="font-semibold text-sm text-gray-200 uppercase tracking-wider">
          {name}
        </span>
      </div>
      <p className="text-xs text-bio-muted leading-relaxed">{description}</p>
      <div className="bg-bio-bg rounded p-2">
        <p className="text-[10px] text-gray-400 italic">{example}</p>
      </div>
    </div>
  );
}

function ArchBox({
  label,
  children,
  accent,
  color,
  borderColor,
}: {
  label: string;
  children: React.ReactNode;
  accent?: boolean;
  color?: string;
  borderColor?: string;
}) {
  return (
    <div
      className={`flex-1 rounded-lg border ${borderColor ?? "border-bio-border"} bg-bio-bg px-4 py-3`}
    >
      <span
        className={`text-xs font-medium uppercase tracking-wider ${
          accent ? "text-bio-accent" : color ?? "text-gray-300"
        }`}
      >
        {label}
      </span>
      <div className="mt-1 space-y-0.5 text-xs text-bio-muted">{children}</div>
    </div>
  );
}

function ArchArrow({ label, biDirectional }: { label: string; biDirectional?: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center px-3 gap-0.5">
      <svg width="80" height="16" viewBox="0 0 80 16" fill="none" className="text-bio-border">
        {biDirectional && (
          <path d="M13 8H3m0 0l3-3m-3 3l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        )}
        <path d="M67 8h10m0 0l-3-3m3 3l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <line x1={biDirectional ? "13" : "3"} y1="8" x2="67" y2="8" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <span className="text-[10px] text-bio-muted">{label}</span>
    </div>
  );
}

function ArchArrowDown() {
  return (
    <svg width="16" height="28" viewBox="0 0 16 28" fill="none" className="text-bio-border">
      <path d="M8 3v22m0 0l-3-3m3 3l3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArchSpacer() {
  return <div className="w-3" />;
}

function TraceExample({
  step,
  phase,
  action,
  detail,
  duration,
  query,
}: {
  step: number;
  phase: string;
  action: string;
  detail: string;
  duration: string;
  query: string;
}) {
  return (
    <div className="flex items-start gap-3 text-xs font-mono">
      <span className="text-bio-accent w-4 text-right shrink-0">{step}.</span>
      <span className="text-bio-muted w-20 shrink-0">[{phase}]</span>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-gray-300">{action}</span>
          <span className="text-bio-muted">{detail}</span>
          <span className="ml-auto text-bio-muted">{duration}</span>
        </div>
        <div className="text-bio-accent/70 mt-0.5 break-all">{query}</div>
      </div>
    </div>
  );
}
