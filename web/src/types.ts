export interface DataSource {
  name: string;
  source_type: string;
  description: string;
  entity_types: string[];
  record_count: number | null;
  url: string | null;
}

export interface Relationship {
  source: string;
  target: string;
  label: string;
}

export interface DataMapResponse {
  sources: DataSource[];
  relationships: Relationship[];
  built_at: string;
}

export interface ToolCallTrace {
  tool_name: string;
  input_params: Record<string, unknown>;
  output_summary: string;
  duration_ms: number;
  reproducible_query: string;
}

export interface TraceStep {
  step_number: number;
  phase: string;
  description: string;
  reasoning: string;
  timestamp: string;
  tool_call: ToolCallTrace | null;
}

export interface TraceEvent {
  event_type: string;
  data: {
    phase?: string;
    step_number?: number;
    description?: string;
    reasoning?: string;
    tool_call?: ToolCallTrace;
    report?: string;
    message?: string;
  };
}

export interface HealthResponse {
  status: string;
  sources: Record<string, boolean>;
  alphaseq_count: number | null;
}
