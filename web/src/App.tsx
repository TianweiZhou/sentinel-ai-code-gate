import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, getReport, getReports, stream, syncRepo } from "./api";
import { idleStages, Pipeline, type StageMap } from "./components/Pipeline";
import { Checklist, Criteria, Files, Queue, Reasons, TestStrength } from "./components/Review";
import { VerdictHero } from "./components/Verdict";
import type { Health, Report, ReportSummary, StageId, StreamEvent } from "./types";

function Card({ title, kicker, children, className = "", delay = 0 }: {
  title: string; kicker?: string; children: React.ReactNode; className?: string; delay?: number;
}) {
  return (
    <motion.section className={`card ${className}`} initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4, ease: "easeOut" }}>
      <header className="card-head"><h2>{title}</h2>{kicker && <span>{kicker}</span>}</header>
      {children}
    </motion.section>
  );
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const stagesOf = (r: Report): StageMap => {
  const m = idleStages();
  Object.entries(r.stages).forEach(([k, v]) => { m[k as StageId] = v; });
  return m;
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [queue, setQueue] = useState<ReportSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [live, setLive] = useState<string | null>(null);
  const [liveStages, setLiveStages] = useState<StageMap>(idleStages);
  const [repo, setRepo] = useState("TianweiZhou/sentinel-demo-service");
  const [notice, setNotice] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const stagesRef = useRef(idleStages());

  const refresh = useCallback(async (selectFirst = false) => {
    const items = await getReports();
    setQueue(items);
    if (selectFirst && items[0]) setSelected((s) => s ?? items[0].id);
  }, []);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setNotice({ kind: "error", text: "API offline — start it with: uv run uvicorn sentinel.api:app" }));
    refresh(true).catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    getReport(selected).then(setReport).catch(() => setReport(null));
  }, [selected]);

  const onEvent = useCallback((e: StreamEvent) => {
    if (e.type === "pr") {
      stagesRef.current = idleStages();
      setLiveStages(stagesRef.current);
      setLive(`${e.title} (${e.index}/${e.total})`);
      setReport(null);
      setSelected(null);
    } else if (e.type === "stage") {
      stagesRef.current = { ...stagesRef.current, [e.stage]: { status: e.status, summary: e.summary } };
      setLiveStages(stagesRef.current);
    } else if (e.type === "report") {
      setQueue((q) => [e.summary, ...q.filter((x) => x.id !== e.summary.id && !(x.repo === e.summary.repo && x.number === e.summary.number))]);
      setSelected(e.report.id);
      setReport(e.report);
    } else if (e.type === "error") {
      setNotice({ kind: "error", text: e.message });
    }
  }, []);

  const runDemo = async () => {
    setRunning(true); setNotice(null);
    try {
      await stream("/api/demo", {}, onEvent);
      setNotice({ kind: "info", text: "Reviewed the three agent PRs of the demo service." });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    } finally {
      setRunning(false); setLive(null);
    }
  };

  const sync = async () => {
    setRunning(true); setNotice(null);
    try {
      const r = await syncRepo(repo);
      await refresh(true);
      setNotice({ kind: "info", text: `${repo}: ${r.open_prs} open PRs, imported ${r.imported} Sentinel report(s).` });
    } catch (err) {
      setNotice({ kind: "error", text: `Sync failed: ${(err as Error).message}` });
    } finally {
      setRunning(false);
    }
  };

  const pipeline = live ? liveStages : report ? stagesOf(report) : idleStages();
  const v = report?.verdict;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Sentinel</h1>
          <p>Merge-readiness review for agent-written pull requests</p>
        </div>
        <div className="toolbar">
          <span className="pill"><i className={health?.ai_reviewer ? "on" : ""} />{health ? (health.ai_reviewer ? `AI reviewer on · ${health.model}` : "AI reviewer off") : "Connecting…"}</span>
          <div className="sync">
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/repo" spellCheck={false} />
            <button className="btn ghost" disabled={running} onClick={sync}>Sync GitHub</button>
          </div>
          <button className="btn primary" disabled={running} onClick={runDemo}>
            {running && <span className="btn-spinner" />}
            {running ? "Reviewing" : "Review demo PRs"}
          </button>
        </div>
      </header>

      <AnimatePresence>
        {notice && (
          <motion.div className={`notice ${notice.kind}`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            onClick={() => setNotice(null)}>
            {notice.text}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="layout">
        <aside>
          <Card title="Review queue" kicker="Worst first" className="queue-card">
            <Queue items={[...queue].sort((a, b) => ["do_not_merge", "after_checks", "ready"].indexOf(a.verdict) - ["do_not_merge", "after_checks", "ready"].indexOf(b.verdict))}
              selected={selected} onSelect={(id) => { if (!running) setSelected(id); }} live={live} />
          </Card>
        </aside>

        <div className="main">
          <Card title="Pull request" kicker={report ? new Date(report.created_at).toLocaleString() : ""} delay={0.05}>
            <VerdictHero report={report} running={running} liveTitle={live ?? undefined} />
          </Card>

          <Card title="Evidence pipeline" kicker={live ? "Running" : "Tools and tests decide. AI can only escalate."} delay={0.1}>
            <Pipeline stages={pipeline} />
          </Card>

          {report && v && (
            <>
              <div className="row-2">
                <Card title={v.kind === "ready" ? "Why it's ready" : "Why"} kicker={`${plural(v.blockers.length, "blocker")}, ${plural(v.checks.length, "check")}`} delay={0.12}>
                  <Reasons report={report} />
                </Card>
                <Card title="Your review checklist" kicker="What tools can't decide for you" delay={0.16}>
                  <Checklist report={report} />
                </Card>
              </div>

              <Card title="Acceptance criteria" kicker="Each must be proven by a passing test" delay={0.2}>
                <Criteria items={report.criteria} />
              </Card>

              <Card title="Can we trust the tests?" kicker="Changed-line coverage and mutation testing" delay={0.24}>
                <TestStrength report={report} />
                {report.ai_summary && <p className="ai-summary"><b>AI reviewer:</b> {report.ai_summary}</p>}
              </Card>

              <Card title="Changed lines" kicker="Findings shown where they occur" delay={0.32}>
                <Files report={report} />
              </Card>
            </>
          )}
        </div>
      </main>

      <footer className="foot">AI advises, rules enforce, humans decide. Sentinel never merges.</footer>
    </div>
  );
}
