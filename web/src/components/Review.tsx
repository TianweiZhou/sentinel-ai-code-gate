import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { VERDICT_META, type ACTrace, type ChangedFile, type Finding, type Report, type ReportSummary, type Severity } from "../types";

// ---------- queue ----------

type Filter = "all" | "do_not_merge" | "after_checks" | "ready";

export function Queue({ items, selected, onSelect, live }: {
  items: ReportSummary[]; selected: string | null; onSelect: (id: string) => void; live: string | null;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const counts = { do_not_merge: 0, after_checks: 0, ready: 0 };
  items.forEach((i) => counts[i.verdict]++);
  const shown = items.filter((i) => filter === "all" || i.verdict === filter);
  return (
    <div className="queue">
      <div className="queue-filters">
        {(["all", "do_not_merge", "after_checks", "ready"] as Filter[]).map((f) => (
          <button key={f} className={`qf ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
            {f === "all" ? `All ${items.length}` : `${VERDICT_META[f].icon} ${counts[f]}`}
          </button>
        ))}
      </div>
      {live && (
        <motion.div className="q-item live" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
          <span className="q-dot" /><div><b>Reviewing</b><span>{live}</span></div>
        </motion.div>
      )}
      <AnimatePresence initial={false}>
        {shown.map((i) => {
          const m = VERDICT_META[i.verdict];
          return (
            <motion.button key={i.id} layout className={`q-item ${m.cls} ${selected === i.id ? "active" : ""}`} onClick={() => onSelect(i.id)}
              initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
              <span className="q-icon">{m.icon}</span>
              <div className="q-main">
                <span className="q-repo">{i.repo}{i.number ? ` #${i.number}` : ""}</span>
                <b>{i.title}</b>
                <span className="q-meta">{m.label}{i.blockers ? ` · ${i.blockers} blocker${i.blockers > 1 ? "s" : ""}` : ""}
                  {i.checks ? ` · ${i.checks} to check` : ""}</span>
              </div>
              <span className="q-score">{i.overall}</span>
            </motion.button>
          );
        })}
      </AnimatePresence>
      {!items.length && !live && <div className="empty">No reviews yet. Run the demo PRs or sync a GitHub repository.</div>}
    </div>
  );
}

// ---------- why / checklist ----------

export function Reasons({ report }: { report: Report }) {
  const v = report.verdict;
  if (!v.blockers.length && !v.checks.length)
    return <div className="reasons ok">Every acceptance criterion is proven by a passing test, the tests are intact and strong, and nothing on the changed lines was flagged.</div>;
  return (
    <ul className="reasons">
      {v.blockers.map((b, i) => (
        <motion.li key={`b${i}`} className="block" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}>
          <span className="tag">BLOCKER</span><Md text={b} />
        </motion.li>
      ))}
      {v.checks.map((c, i) => (
        <motion.li key={`c${i}`} className="check" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: (v.blockers.length + i) * 0.06 }}>
          <span className="tag">CHECK</span><Md text={c} />
        </motion.li>
      ))}
    </ul>
  );
}

/** Renders `code` spans in reason text. */
function Md({ text }: { text: string }) {
  return <span>{text.split(/(`[^`]+`)/).map((p, i) => (p.startsWith("`") ? <code key={i}>{p.slice(1, -1)}</code> : p))}</span>;
}

export function Checklist({ report }: { report: Report }) {
  const key = `sentinel-checklist-${report.id}`;
  const [done, setDone] = useState<number[]>(() => {
    try { return JSON.parse(localStorage.getItem(key) ?? "[]"); } catch { return []; }
  });
  useEffect(() => {
    try { setDone(JSON.parse(localStorage.getItem(key) ?? "[]")); } catch { setDone([]); }
  }, [key]);
  const toggle = (i: number) => {
    const next = done.includes(i) ? done.filter((d) => d !== i) : [...done, i];
    setDone(next);
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* private mode */ }
  };
  const items = report.verdict.human_review;
  return (
    <div className="checklist">
      <div className="cl-progress"><motion.div className="cl-fill" animate={{ width: `${(100 * done.length) / items.length}%` }} /></div>
      {items.map((h, i) => (
        <label key={i} className={`cl-item ${done.includes(i) ? "done" : ""}`}>
          <input type="checkbox" checked={done.includes(i)} onChange={() => toggle(i)} />
          <span className="cl-box" /><Md text={h} />
        </label>
      ))}
    </div>
  );
}

// ---------- acceptance criteria ----------

const AC_TEXT: Record<ACTrace["status"], string> = {
  proven: "PROVEN", failing: "FAILING", not_run: "NOT RUN", untested: "NO TEST", disputed: "DISPUTED",
};

export function Criteria({ items }: { items: ACTrace[] }) {
  if (!items.length) return <div className="empty">No acceptance criteria found. Link an issue (<code>Closes #12</code>) that lists <code>AC1: …</code> items.</div>;
  return (
    <div className="reqs">
      {items.map((c, i) => (
        <motion.div key={c.id} className={`req req-${c.status}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.07 }}>
          <span className="req-id">{c.id}</span>
          <div className="req-body">
            <div className="req-text"><Md text={c.text} /></div>
            <div className="req-evidence">{c.evidence}{c.tests.length > 0 && <> · <code>{c.tests.map((t) => t.split("::").pop()).join(", ")}</code></>}</div>
          </div>
          <span className="req-status">{AC_TEXT[c.status]}</span>
        </motion.div>
      ))}
      <div className="req-source">source: {items[0].source}</div>
    </div>
  );
}

// ---------- test strength ----------

export function TestStrength({ report }: { report: Report }) {
  const { mutants, coverage, tests } = report;
  const killed = mutants.filter((m) => m.killed).length;
  const ran = tests.filter((t) => t.message !== "skipped");
  const skipped = tests.length - ran.length;
  return (
    <div className="mutation">
      <div className="mut-stats">
        <div><b>{ran.filter((t) => t.passed).length}/{ran.length}</b><span>tests passing{skipped ? ` · ${skipped} skipped` : ""}</span></div>
        <div><b>{coverage?.percent != null ? `${Math.round(coverage.percent)}%` : "—"}</b><span>changed lines covered</span></div>
        <div><b>{mutants.length ? `${Math.round((100 * killed) / mutants.length)}%` : "—"}</b><span>planted bugs caught</span></div>
      </div>
      {mutants.length > 0 ? (
        <div className="mut-grid">
          {mutants.map((m, i) => (
            <motion.span key={m.id} className={`mut ${m.killed ? "killed" : "survived"}`}
              title={`${m.path}:${m.line} ${m.description} — ${m.killed ? "caught" : "NOT caught by any test"}`}
              initial={{ scale: 0, rotate: 45 }} animate={{ scale: 1, rotate: 0 }} transition={{ delay: i * 0.03, type: "spring", stiffness: 400, damping: 15 }} />
          ))}
        </div>
      ) : <div className="empty">Mutation testing plants small bugs on the changed lines once all tests pass, and checks the tests catch them.</div>}
      {mutants.some((m) => !m.killed) && (
        <ul className="survivors">
          {mutants.filter((m) => !m.killed).map((m) => <li key={m.id}><span>not caught</span> {m.path}:{m.line} <Md text={m.description} /></li>)}
        </ul>
      )}
      {report.test_error && <pre className="test-error">{report.test_error}</pre>}
    </div>
  );
}

// ---------- changed files with inline findings ----------

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function Files({ report }: { report: Report }) {
  const files = report.changed_files;
  const [active, setActive] = useState(0);
  useEffect(() => setActive(0), [report.id]);
  const file: ChangedFile | undefined = files[active];
  const byLine = useMemo(() => {
    const m = new Map<number, Finding[]>();
    report.findings.filter((f) => f.path === file?.path && f.line).forEach((f) => m.set(f.line!, [...(m.get(f.line!) ?? []), f]));
    return m;
  }, [report, file]);
  const uncovered = new Set(report.coverage?.uncovered[file?.path ?? ""] ?? []);
  const survived = new Set(report.mutants.filter((m) => !m.killed && m.path === file?.path).map((m) => m.line));

  const rows = useMemo(() => {
    const out: { kind: string; text: string; n?: number }[] = [];
    let n = 0;
    for (const raw of (file?.patch ?? "").split("\n")) {
      const h = /^@@ -\d+(?:,\d+)? \+(\d+)/.exec(raw);
      if (h) { n = Number(h[1]); out.push({ kind: "hunk", text: raw }); continue; }
      if (!n || raw.startsWith("+++") || raw.startsWith("---")) continue;
      if (raw.startsWith("+")) out.push({ kind: "add", text: raw.slice(1), n: n++ });
      else if (raw.startsWith("-")) out.push({ kind: "del", text: raw.slice(1) });
      else if (raw.startsWith(" ")) out.push({ kind: "ctx", text: raw.slice(1), n: n++ });
    }
    return out;
  }, [file]);

  if (!files.length) return <div className="empty">No changed files.</div>;
  return (
    <div className="files">
      <div className="file-tabs">
        {files.map((f, i) => {
          const count = report.findings.filter((x) => x.path === f.path && SEV_ORDER.indexOf(x.severity) <= 2).length;
          return (
            <button key={f.path} className={`ftab ${i === active ? "on" : ""}`} onClick={() => setActive(i)}>
              {f.is_test ? "🧪 " : ""}{f.path}<i>+{f.added_lines.length}</i>{count > 0 && <em>{count}</em>}
            </button>
          );
        })}
      </div>
      <div className="patch">
        {rows.map((r, i) => (
          <div key={i}>
            <div className={`prow ${r.kind}`} style={{ animationDelay: `${Math.min(i * 6, 600)}ms` }}>
              <span className="ln">{r.n ?? ""}</span>
              <span className="mk">
                {r.n && uncovered.has(r.n) ? <i className="mk-unc" title="not covered by any test" /> : null}
                {r.n && survived.has(r.n) ? <i className="mk-mut" title="a planted bug here was not caught" /> : null}
              </span>
              <span className="txt">{r.text || " "}</span>
            </div>
            {r.kind === "add" && r.n && byLine.get(r.n)?.map((f, j) => (
              <motion.div key={j} className={`inline-note sev-${f.severity}`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
                <b>{f.source === "ai" ? "AI reviewer" : `${f.stage} · ${f.rule}`}</b> {f.message}
              </motion.div>
            ))}
          </div>
        ))}
      </div>
      <div className="legend"><i className="mk-unc" /> not covered by tests <i className="mk-mut" /> planted bug not caught</div>
    </div>
  );
}
