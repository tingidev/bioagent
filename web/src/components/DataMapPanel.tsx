import type { DataMapResponse, HealthResponse } from "../types";

interface Props {
  dataMap: DataMapResponse | null;
  health: HealthResponse | null;
}

export default function DataMapPanel({ dataMap, health }: Props) {
  if (!dataMap) {
    return (
      <div className="text-bio-muted text-sm">
        Loading data map...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
          Connected Sources
        </h2>
        <div className="space-y-3">
          {dataMap.sources.map((source) => {
            const isConnected = health?.sources[source.name.toLowerCase()] ?? false;
            return (
              <div
                key={source.name}
                className="bg-bio-card border border-bio-border rounded-lg p-3"
              >
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      isConnected ? "bg-bio-accent" : "bg-yellow-500"
                    }`}
                  />
                  <span className="font-medium text-gray-200 text-sm">
                    {source.name}
                  </span>
                  <span className="text-xs text-bio-muted ml-auto">
                    {source.source_type === "local_db" ? "Local DB" : "REST API"}
                  </span>
                </div>
                {source.record_count && (
                  <p className="text-xs text-bio-muted mb-1">
                    {source.record_count.toLocaleString()} records
                  </p>
                )}
                <p className="text-xs text-bio-muted leading-relaxed">
                  {source.description}
                </p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {source.entity_types.map((et) => (
                    <span
                      key={et}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-bio-border text-bio-muted"
                    >
                      {et}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
          Entity Relationships
        </h2>
        <div className="space-y-1.5">
          {dataMap.relationships.map((rel, i) => (
            <div
              key={i}
              className="text-xs text-bio-muted flex items-center gap-1.5"
            >
              <span className="text-gray-300">{rel.source}</span>
              <span className="text-bio-accent">--[{rel.label}]--&gt;</span>
              <span className="text-gray-300">{rel.target}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
