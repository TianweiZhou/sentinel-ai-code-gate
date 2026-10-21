import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror, { EditorView, type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getHealth, getSamples, runGate } from "./api";
import { Background } from "./components/Background";
import { Diff } from "./components/Diff";
import { Findings, Functions, MutationMap, Requirements, Timeline, type IterationView } from "./components/Panels";
import { Pipeline, type StageState } from "./components/Pipeline";
import { Radar } from "./components/Radar";
import { Verdict } from "./components/Verdict";
import { STAGES, type Health, type PipelineEvent, type Sample, type StageId } from "./types";

type Tab = "spec" | "code" | "tests" | "diff";
type Log = { level: "info" | "warn" | "error"; message: string; at: number };

const idleStages = () => Object.fromEntries(STAGES.map((s) => [s.id, { status: "idle" }])) as Record<StageId, StageState>;
const editorTheme = EditorView.theme({ "&": { backgroundColor: "transparent" }, ".cm-gutters": { backgroundColor: "transparent" } });

function Card({ title, kicker, children, className = "", delay = 0 }: { title: string; kicker?: string; children: React.ReactNode; className?: string; delay?: number }) {
  return (
    <motion.section
      className={`card ${className}`}
      initial={{ opacity: 0, y: 24, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ delay, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      <header className="card-head">
        <h2>{title}</h2>
        {kicker && <span>{kicker}</span>}
      </header>
      {children}
    </motion.section>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [sampleId, setSampleId] = useState<string>("signup");
  const [spec, setSpec] = useState("");
  const [code, setCode] = useState("");
  const [tests, setTests] = useState("");
  const [tab, setTab] = useState<Tab>("spec");
  const [autoRepair, setAutoRepair] = useState(true);

  const [running, setRunning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [stages, setStages] = useState(idleStages);
  const [iterations, setIterations] = useState<IterationView[]>([]);
  const [selected, setSelected] = useState(0);
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState<string | null>(null);
  const editorRef = useRef<ReactCodeMirrorRef>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stagesRef = useRef(idleStages());

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setError("API offline — start it with: uv run uvicorn sentinel.api:app"));
    getSamples().then((s) => {
      setSamples(s);
      if (s[0]) loadSample(s[0]);
    }).catch(() => undefined);
  }, []);

  const loadSample = (s: Sample) => {
    setSampleId(s.id); setSpec(s.spec); setTests(s.tests); setCode(s.generated);
    setIterations([]); setStages(idleStages()); setLogs([]); setSelected(0); setTab("spec");
  };

  const onEvent = useCallback((e: PipelineEvent) => {
    switch (e.type) {
      case "mode":
        setHealth((h) => (h ? { ...h, mode: e.mode, model: e.model } : h));
        break;
      case "iteration":
        stagesRef.current = { ...idleStages(), generate: stagesRef.current.generate };
        setStages(stagesRef.current);
        setIterations((its) => [...its, { iteration: e.iteration, source: e.source, code: e.code }]);
        setSelected(e.iteration);
        setCode(e.code);
        break;
      case "stage":
        stagesRef.current = { ...stagesRef.current, [e.stage]: { status: e.status, summary: e.summary, duration_ms: e.duration_ms } };
        setStages(stagesRef.current);
        break;
      case "report": {
        // Snapshot the stage strip so older versions can be replayed in the pipeline view.
        // Read the ref now: React may run the updater later, after the next iteration has reset it.
        const snapshot = stagesRef.current;
        setIterations((its) => its.map((it) => (it.iteration === e.report.iteration ? { ...it, report: e.report, stages: snapshot } : it)));
        break;
      }
      case "log":
        setLogs((l) => [...l.slice(-30), { level: e.level, message: e.message, at: Date.now() }]);
        break;
      case "done":
        setLogs((l) => [...l, { level: e.passed ? "info" : "warn", message: e.passed ? `Gate passed after ${e.iterations} iteration(s).` : "Run finished — gate still blocking.", at: Date.now() }]);
        break;
    }
  }, []);

  const start = async (generate: boolean) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true); setGenerating(generate); setError(null);
    stagesRef.current = idleStages();
    setIterations([]); setLogs([]); setStages(stagesRef.current);
    setTab("code");
    try {
      await runGate({ spec, code, tests, sample_id: sampleId, generate, auto_repair: autoRepair, max_iterations: 3 }, onEvent, ctrl.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !running) start(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const current = iterations.find((i) => i.iteration === selected);
  const report = current?.report ?? null;
  const previous = iterations.find((i) => i.iteration === selected - 1)?.report ?? null;
  const canDiff = selected > 1 && !!iterations.find((i) => i.iteration === selected - 1);
  const intensity = running ? 1 : 0;

  const selectIteration = (n: number) => {
    const it = iterations.find((i) => i.iteration === n);
    if (!it) return;
    setSelected(n);
    setCode(it.code);
  };

  const jumpTo = (line: number) => {
    setTab("code");
    requestAnimationFrame(() => {
      const view = editorRef.current?.view;
      if (!view) return;
      const pos = view.state.doc.line(Math.min(line, view.state.doc.lines)).from;
      view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
      view.focus();
    });
  };

  const sample = samples.find((s) => s.id === sampleId);
  const editorValue = tab === "spec" ? spec : tab === "tests" ? tests : code;
  const setEditor = tab === "spec" ? setSpec : tab === "tests" ? setTests : setCode;
  const extensions = useMemo(() => [python(), editorTheme, EditorView.lineWrapping], []);

  return (
    <div className="app">
      <Background intensity={intensity} />

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
            <p>Quality gate for AI-generated Python</p>
          </div>
        </div>
        <div className="status-pills">
          <span className={`pill ${health?.mode === "live" ? "live" : ""}`}>
            <i />{health ? (health.mode === "live" ? `LIVE · ${health.model}` : "REPLAY · offline demo") : "connecting…"}
          </span>
          <span className="pill">gate ≥ {health?.threshold ?? 85}</span>
          <span className="pill">mutation ≥ {health?.min_mutation_score ?? 70}%</span>
        </div>
      </header>

      <AnimatePresence>
        {error && (
          <motion.div className="error-bar" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      <Card title="Verification pipeline" kicker={running ? "streaming live from the engine" : "spec → code → evidence → decision"} className="pipeline-card">
        <Pipeline stages={current?.stages ?? stages} showGenerate={generating} />
      </Card>

      <main className="grid">
        <div className="col-left">
          <Card title="Scenario" kicker="AI drafts with real-world flaws" delay={0.05}>
            <div className="samples">
              {samples.map((s) => (
                <button key={s.id} className={`sample ${s.id === sampleId ? "on" : ""}`} onClick={() => loadSample(s)} disabled={running}>
                  <b>{s.title}</b>
                  <span>{s.tagline}</span>
                </button>
              ))}
            </div>
          </Card>

          <Card title="Workspace" kicker={sample ? `${sample.id}/solution.py` : ""} className="editor-card" delay={0.1}>
            <div className="tabs">
              {(["spec", "code", "tests", "diff"] as Tab[]).map((t) => (
                <button key={t} className={`tab ${tab === t ? "on" : ""}`} onClick={() => setTab(t)} disabled={t === "diff" && !canDiff}>
                  {t === "spec" ? "Spec" : t === "code" ? (current ? `Code v${current.iteration}` : "Code") : t === "tests" ? "Tests (human-owned)" : "Repair diff"}
                  {tab === t && <motion.span layoutId="tab-underline" className="tab-underline" />}
                </button>
              ))}
            </div>
            <div className="editor">
              {tab === "diff" && canDiff ? (
                <Diff before={iterations.find((i) => i.iteration === selected - 1)!.code} after={current!.code} />
              ) : (
                <CodeMirror
                  ref={editorRef}
                  value={editorValue}
                  onChange={setEditor}
                  theme={oneDark}
                  extensions={tab === "spec" ? [editorTheme, EditorView.lineWrapping] : extensions}
                  readOnly={running}
                  height="100%"
                  basicSetup={{ foldGutter: false, highlightActiveLine: true }}
                />
              )}
            </div>
            <div className="actions">
              <label className="toggle">
                <input type="checkbox" checked={autoRepair} onChange={(e) => setAutoRepair(e.target.checked)} />
                <span className="track"><span className="thumb" /></span>
                Auto-repair loop
              </label>
              <div className="buttons">
                <button className="btn ghost" disabled={running} onClick={() => start(false)} title="⌘/Ctrl + Enter">Gate this code</button>
                <button className="btn primary" disabled={running} onClick={() => start(true)}>
                  {running ? <span className="btn-spinner" /> : <span className="btn-glyph">✦</span>}
                  {running ? "Running…" : "Generate with AI & gate"}
                </button>
              </div>
            </div>
            <div className="log">
              <AnimatePresence initial={false}>
                {logs.slice(-3).map((l) => (
                  <motion.div key={l.at + l.message} className={`log-line ${l.level}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    › {l.message}
                  </motion.div>
                ))}
              </AnimatePresence>
              {!logs.length && <div className="log-line muted">› Pick a scenario, then “Generate with AI &amp; gate”.</div>}
            </div>
          </Card>
        </div>

        <div className="col-right">
          <div className="row-2">
            <Card title="Verdict" kicker={report ? `v${report.iteration} · ${report.lines_of_code} LOC` : ""} delay={0.15}>
              <Verdict gate={report?.gate ?? null} running={running} />
            </Card>
            <Card title="Quality dimensions" kicker={previous ? "dashed = previous version" : "weighted score"} delay={0.2}>
              <Radar scores={report?.scores ?? null} previous={previous?.scores ?? null} weights={health?.weights} />
            </Card>
          </div>

          <Card title="Generate → verify → repair" kicker="the AI never sees the tests, only the failures" delay={0.25}>
            <Timeline items={iterations} selected={selected} onSelect={selectIteration} />
          </Card>

          <div className="row-2">
            <Card title="Requirement traceability" kicker="@pytest.mark.req" delay={0.3}>
              <Requirements items={report?.requirements ?? []} />
            </Card>
            <Card title="Who tests the tests?" kicker="coverage + mutation testing" delay={0.35}>
              <MutationMap mutants={report?.mutants ?? []} coverage={report?.coverage ?? null} />
            </Card>
          </div>

          <div className="row-2">
            <Card title="Findings" kicker="click to jump to line" delay={0.4}>
              <Findings issues={report?.issues ?? []} onJump={jumpTo} />
            </Card>
            <Card title="Complexity" kicker="cyclomatic per function · limit 8" delay={0.45}>
              <Functions items={report?.functions ?? []} mi={report?.maintainability_index ?? null} />
            </Card>
          </div>
        </div>
      </main>

      <footer className="foot">
        ruff · mypy --strict · bandit · radon · pytest · coverage · mutation testing · requirement tracing · Claude repair loop
      </footer>
    </div>
  );
}
