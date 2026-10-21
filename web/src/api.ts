import type { Health, Report, ReportSummary, StreamEvent } from "./types";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const getHealth = () => fetch("/api/health").then((r) => json<Health>(r));
export const getReports = () => fetch("/api/reports").then((r) => json<ReportSummary[]>(r));
export const getReport = (id: string) => fetch(`/api/reports/${encodeURIComponent(id)}`).then((r) => json<Report>(r));
export const syncRepo = (repo: string) =>
  fetch("/api/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo }) })
    .then((r) => json<{ open_prs: number; imported: number }>(r));

/** POSTs and calls `onEvent` for every NDJSON line as it streams in. */
export async function stream(url: string, body: unknown, onEvent: (e: StreamEvent) => void, signal?: AbortSignal) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}), signal });
  if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`);
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
