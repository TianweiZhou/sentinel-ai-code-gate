import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, getReport, getReports, stream, syncRepo } from "./api";
import { Background } from "./components/Background";
import { idleStages, Pipeline, type StageMap } from "./components/Pipeline";
import { Radar } from "./components/Radar";
import { Checklist, Criteria, Files, Queue, Reasons, TestStrength } from "./components/Review";
import { VerdictHero } from "./components/Verdict";
import type { Health, Report, ReportSummary, StageId, StreamEvent } from "./types";

function Card({ title, kicker, children, className = "", delay = 0 }: {
  title: string; kicker?: string; children: React.ReactNode; className?: string; delay?: number;
}) {
  return (
    <motion.section className={`card ${className}`} initial={{ opacity: 0, y: 20, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ delay, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}>
      <header className="card-head"><h2>{title}</h2>{kicker && <span>{kicker}</span>}</header>
      {children}
    </motion.section>
  );
}

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
      <Background intensity={running ? 1 : 0} />

      <header className="topbar">
        <div className="brand">
          <div className="logo">
            <svg viewBox="0 0 48 48">
              <circle cx="24" cy="24" r="21" className="logo-orbit" />
              <path d="M24 8 36 13v9c0 8-5.2 13.4-12 16-6.8-2.6-12-8-12-16v-9z" className="logo-shield" />
              <path d="m18.5 24 4 4 7.5-8" className="logo-check" />
            </svg>
          </div>
          <div>
            <h1>SENTINEL</h1>
            <p>Merge-readiness review for agent-written PRs</p>
          </div>
        </div>
        <div className="toolbar">
          <span className={`pill ${health?.ai_reviewer ? "live" : ""}`}><i />{health ? (health.ai_reviewer ? `AI reviewer · ${health.model}` : "AI reviewer off · tools only") : "connecting…"}</span>
          <div className="sync">
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/repo" spellCheck={false} />
            <button className="btn ghost" disabled={running} onClick={sync}>Sync GitHub</button>
          </div>
          <button className="btn primary" disabled={running} onClick={runDemo}>
            {running ? <span className="btn-spinner" /> : <span className="btn-glyph">▶</span>}
            {running ? "Reviewing…" : "Review demo PRs"}
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
          <Card title="Review queue" kicker="every open PR, worst first" className="queue-card">
            <Queue items={[...queue].sort((a, b) => ["do_not_merge", "after_checks", "ready"].indexOf(a.verdict) - ["do_not_merge", "after_checks", "ready"].indexOf(b.verdict))}
              selected={selected} onSelect={(id) => { if (!running) setSelected(id); }} live={live} />
          </Card>
        </aside>

        <div className="main">
          <Card title="Pull request" kicker={report ? new Date(report.created_at).toLocaleString() : ""} delay={0.05}>
            <VerdictHero report={report} running={running} liveTitle={live ?? undefined} />
          </Card>

          <Card title="Evidence pipeline" kicker={live ? "streaming from the engine" : "tools & tests decide · AI can only escalate"} delay={0.1}>
            <Pipeline stages={pipeline} />
          </Card>

          {report && v && (
            <>
              <div className="row-2">
                <Card title={v.kind === "ready" ? "Why it's ready" : "Why"} kicker={`${v.blockers.length} blockers · ${v.checks.length} checks`} delay={0.12}>
                  <Reasons report={report} />
                </Card>
                <Card title="Your review checklist" kicker="what tools can't decide for you" delay={0.16}>
                  <Checklist report={report} />
                </Card>
              </div>

              <Card title="Acceptance criteria" kicker="each must be proven by a passing test" delay={0.2}>
                <Criteria items={report.criteria} />
              </Card>

              <div className="row-2">
                <Card title="Can we trust the tests?" kicker="changed-line coverage · mutation testing" delay={0.24}>
                  <TestStrength report={report} />
                </Card>
                <Card title="Quality dimensions" kicker={`overall ${report.overall}/100`} delay={0.28}>
                  <Radar scores={report.scores} />
                  {report.ai_summary && <p className="ai-summary"><b>AI reviewer:</b> {report.ai_summary}</p>}
                </Card>
              </div>

              <Card title="Changed lines" kicker="findings shown where they occur" delay={0.32}>
                <Files report={report} />
              </Card>
            </>
          )}
        </div>
      </main>

      <footer className="foot">AI advises · rules enforce · humans decide — Sentinel never merges</footer>
    </div>
  );
}
