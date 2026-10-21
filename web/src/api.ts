import type { Health, PipelineEvent, Sample } from "./types";

export async function getHealth(): Promise<Health> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function getSamples(): Promise<Sample[]> {
  const r = await fetch("/api/samples");
  if (!r.ok) throw new Error(`samples ${r.status}`);
  return r.json();
}

export interface RunBody {
  spec: string; code: string; tests: string; sample_id?: string;
  generate: boolean; auto_repair: boolean; max_iterations: number;
}

/** POSTs a run and calls `onEvent` for every NDJSON line as it streams in. */
export async function runGate(body: RunBody, onEvent: (e: PipelineEvent) => void, signal?: AbortSignal) {
  const r = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`run failed: ${r.status} ${await r.text()}`);

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}
