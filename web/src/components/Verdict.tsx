import { AnimatePresence, animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";
import { VERDICT_META, type Report } from "../types";

function useCountUp(value: number) {
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v));
  useEffect(() => {
    const c = animate(mv, value, { duration: 1.3, ease: [0.16, 1, 0.3, 1] });
    return () => c.stop();
  }, [value, mv]);
  return rounded;
}

const RING_COLOR = { ready: "var(--green)", after_checks: "var(--amber)", do_not_merge: "var(--red)" } as const;

export function ScoreRing({ score, kind }: { score: number; kind: Report["verdict"]["kind"] | null }) {
  const r = 52, c = 2 * Math.PI * r;
  const shown = useCountUp(score);
  const color = kind ? RING_COLOR[kind] : "var(--cyan)";
  return (
    <div className="ring">
      <svg viewBox="0 0 130 130">
        <circle cx="65" cy="65" r={r} className="ring-bg" />
        {Array.from({ length: 48 }, (_, i) => (
          <line key={i} x1="65" y1="5" x2="65" y2={i % 4 === 0 ? 10 : 8} className="ring-tick" transform={`rotate(${i * 7.5} 65 65)`} />
        ))}
        <motion.circle cx="65" cy="65" r={r} className="ring-fg" stroke={color} strokeDasharray={c}
          initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - score / 100) }}
          transition={{ duration: 1.3, ease: [0.16, 1, 0.3, 1] }} style={{ filter: `drop-shadow(0 0 8px ${color})` }} />
      </svg>
      <div className="ring-center">
        <motion.span className="ring-score" style={{ color }}>{shown}</motion.span>
        <span className="ring-caption">score</span>
      </div>
    </div>
  );
}

export function VerdictHero({ report, running, liveTitle }: { report: Report | null; running: boolean; liveTitle?: string }) {
  const meta = report ? VERDICT_META[report.verdict.kind] : null;
  const pr = report?.pr;
  return (
    <div className="hero">
      <ScoreRing score={report?.overall ?? 0} kind={report?.verdict.kind ?? null} />
      <div className="hero-body">
        <div className="hero-pr">
          {pr ? <>{pr.repo}{pr.number ? <b> #{pr.number}</b> : null}{pr.author ? <> · by <b>{pr.author}</b></> : null}
            {pr.linked_issue ? <> · closes issue #{pr.linked_issue}</> : null}</> : running ? "Reviewing…" : "No PR selected"}
        </div>
        <h2 className="hero-title">
          {pr?.url ? <a href={pr.url} target="_blank" rel="noreferrer">{pr.title} ↗</a> : pr?.title ?? liveTitle ?? "Pick a pull request from the queue"}
        </h2>
        <AnimatePresence mode="wait">
          {meta ? (
            <motion.div key={report!.id} className={`verdict-badge ${meta.cls}`}
              initial={{ opacity: 0, scale: 0.85, filter: "blur(8px)" }} animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
              transition={{ type: "spring", stiffness: 200, damping: 16 }}>
              <span>{meta.icon}</span>{meta.label}
            </motion.div>
          ) : (
            <motion.div key="idle" className="verdict-badge idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {running ? <span className="scanning">COLLECTING EVIDENCE<span className="dots" /></span> : "AWAITING A PR"}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="hero-note">Sentinel advises — you own the merge.</div>
      </div>
    </div>
  );
}
