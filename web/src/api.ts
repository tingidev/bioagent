import type { DataMapResponse, HealthResponse, TraceEvent } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return fetchJson(`${API_URL}/health`);
}

export function fetchDataMap(): Promise<DataMapResponse> {
  return fetchJson(`${API_URL}/map`);
}

export function subscribeInvestigation(
  question: string,
  onEvent: (event: TraceEvent) => void,
  onError: (error: Error) => void,
  onDone: () => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_URL}/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });

      if (!res.ok) {
        onError(new Error(`Investigation failed: ${res.status}`));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        onError(new Error("No response body"));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as TraceEvent;
              onEvent(event);
            } catch {
              // skip malformed events
            }
          }
        }
      }

      onDone();
    } catch (err) {
      if (!controller.signal.aborted) {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return () => controller.abort();
}
