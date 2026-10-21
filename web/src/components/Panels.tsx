import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import type { FunctionMetric, IterationSource, Issue, Mutant, Report, RequirementTrace, Severity, StageId } from "../types";
import type { StageState } from "./Pipeline";

export interface IterationView { iteration: number; source: IterationSource; code: string; report?: Report; stages?: Record<StageId, StageState> }

const SOURCE_LABEL: Record<IterationSource, string> = {
  input: "Pasted code",
  generated: "AI first draft",
  "llm-repair": "Claude repair",
  "replay-repair": "AI repair (replay)",
};

export function Timeline({ items, selected, onSelect }: { items: IterationView[]; selected: number; onSelect: (n: number) => void }) {
  if (!items.length) return <div className="empty">Iterations appear here: draft → gate → feedback → repair.</div>;
  return (
    <div className="timeline">
      {items.map((it, i) => {
        const prev = items[i - 1]?.report?.gate.overall;
        const score = it.report?.gate.overall;
        const delta = score !== undefined && prev !== undefined ? score - prev : null;
        const state = !it.report ? "running" : it.report.gate.passed ? "pass" : it.report.gate.repairable ? "fail" : "escalate";
        return (
          <motion.button
            key={it.iteration}
            className={`tl-item tl-${state} ${selected === it.iteration ? "active" : ""}`}
            onClick={() => onSelect(it.iteration)}
            initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            layout
          >
            <span className="tl-v">v{it.iteration}</span>
            <span className="tl-source">{SOURCE_LABEL[it.source]}</span>
            <span className="tl-score">{score ?? "…"}</span>
            {delta !== null && <span className={`tl-delta ${delta >= 0 ? "up" : "down"}`}>{delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}</span>}
            {i < items.length - 1 && <span className="tl-arrow">feedback →</span>}
          </motion.button>
        );
      })}
    </div>
  );
}

const STATUS_TEXT = { met: "PROVEN", partial: "PARTIAL", missing: "FAILED", untested: "NO TEST" } as const;

export function Requirements({ items }: { items: RequirementTrace[] }) {
  if (!items.length) return <div className="empty">Numbered requirements (R1, R2 …) from the spec are traced to tests here.</div>;
  return (
    <div className="reqs">
      {items.map((r, i) => (
        <motion.div key={r.id} className={`req req-${r.status}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}>
          <span className="req-id">{r.id}</span>
          <div className="req-body">
            <div className="req-text">{r.text}</div>
            <div className="req-evidence">{r.evidence}{r.tests.length > 0 && <> · <code>{r.tests.length} test{r.tests.length > 1 ? "s" : ""}</code></>}</div>
          </div>
          <span className="req-status">{STATUS_TEXT[r.status]}</span>
        </motion.div>
      ))}
    </div>
  );
}

export function MutationMap({ mutants, coverage }: { mutants: Mutant[]; coverage: Report["coverage"] }) {
  const killed = mutants.filter((m) => m.killed).length;
  const survivors = mutants.filter((m) => !m.killed);
  return (
    <div className="mutation">
      <div className="mut-stats">
        <div><b>{coverage ? `${coverage.line_percent}%` : "—"}</b><span>line coverage</span></div>
        <div><b>{coverage?.branch_percent != null ? `${coverage.branch_percent}%` : "—"}</b><span>branch coverage</span></div>
        <div><b>{mutants.length ? `${Math.round((100 * killed) / mutants.length)}%` : "—"}</b><span>mutants killed</span></div>
      </div>
      {mutants.length === 0 ? (
        <div className="empty">Mutation testing runs once every test passes. It plants small bugs (<code>&lt;</code>→<code>&lt;=</code>, <code>+</code>→<code>-</code>…) and checks that the tests catch them.</div>
      ) : (
        <>
          <div className="mut-grid">
            {mutants.map((m, i) => (
              <motion.span
                key={m.id}
                className={`mut ${m.killed ? "killed" : "survived"}`}
                title={`${m.description} — ${m.killed ? "caught by tests" : "SURVIVED: no test noticed"}`}
                initial={{ scale: 0, rotate: 45 }} animate={{ scale: 1, rotate: 0 }}
                transition={{ delay: i * 0.03, type: "spring", stiffness: 400, damping: 15 }}
              />
            ))}
          </div>
          {survivors.length > 0 && (
            <ul className="survivors">
              {survivors.map((m) => <li key={m.id}><span>survived</span> {m.description}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function Findings({ issues, onJump }: { issues: Issue[]; onJump?: (line: number) => void }) {
  const [filter, setFilter] = useState<string>("all");
  const stages = useMemo(() => [...new Set(issues.map((i) => i.stage))], [issues]);
  const shown = issues
    .filter((i) => filter === "all" || i.stage === filter)
    .sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));

  if (!issues.length) return <div className="empty">No findings. Static analysis results stream in here.</div>;
  return (
    <div className="findings">
      <div className="chips">
        {["all", ...stages].map((s) => (
          <button key={s} className={`chip ${filter === s ? "on" : ""}`} onClick={() => setFilter(s)}>
            {s} <i>{s === "all" ? issues.length : issues.filter((i) => i.stage === s).length}</i>
          </button>
        ))}
      </div>
      <ul className="finding-list">
        <AnimatePresence initial>
          {shown.map((i, n) => (
            <motion.li
              key={`${i.stage}-${i.rule}-${i.line}-${n}`}
              className={`finding sev-${i.severity}`}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ delay: Math.min(n * 0.025, 0.6) }}
              onClick={() => i.line && onJump?.(i.line)}
            >
              <span className="sev">{i.severity}</span>
              <span className="rule">{i.stage}/{i.rule}</span>
              <span className="msg">{i.message}</span>
              {i.line && <span className="line">L{i.line}</span>}
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}

export function Functions({ items, mi }: { items: FunctionMetric[]; mi: number | null }) {
  if (!items.length) return <div className="empty">Per-function complexity appears here.</div>;
  const max = Math.max(15, ...items.map((f) => f.complexity));
  return (
    <div className="functions">
      <div className="mi">Maintainability index <b>{mi ?? "—"}</b><span>/100 (radon)</span></div>
      {items.map((f, i) => (
        <div key={`${f.name}-${f.line}`} className="fn">
          <span className="fn-name" title={`line ${f.line}`}>{f.name}</span>
          <div className="fn-bar">
            <motion.div
              className={`fn-fill ${f.complexity > 8 ? "bad" : f.complexity > 5 ? "mid" : ""}`}
              initial={{ width: 0 }} animate={{ width: `${(f.complexity / max) * 100}%` }}
              transition={{ delay: i * 0.05, duration: 0.8, ease: "easeOut" }}
            />
            <span className="fn-limit" style={{ left: `${(8 / max) * 100}%` }} />
          </div>
          <span className="fn-meta">CC {f.complexity} · {f.length}L · depth {f.max_depth}</span>
        </div>
      ))}
    </div>
  );
}
