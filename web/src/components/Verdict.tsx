import { AnimatePresence, animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";
import { VERDICT_META, type Report } from "../types";

function useCountUp(value: number) {
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v));
  useEffect(() => {
    const c = animate(mv, value, { duration: 0.8, ease: "easeOut" });
    return () => c.stop();
  }, [value, mv]);
  return rounded;
}

export function Score({ score }: { score: number | null }) {
  const shown = useCountUp(score ?? 0);
  return (
    <div className="score">
      <motion.span className="score-value">{score === null ? "–" : shown}</motion.span>
      <span className="score-caption">score out of 100</span>
    </div>
  );
}

export function VerdictHero({ report, running, liveTitle }: { report: Report | null; running: boolean; liveTitle?: string }) {
  const meta = report ? VERDICT_META[report.verdict.kind] : null;
  const pr = report?.pr;
  return (
    <div className="hero">
      <Score score={report ? report.overall : null} />
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
              initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <span className="dot" />{meta.label}
            </motion.div>
          ) : (
            <motion.div key="idle" className="verdict-badge idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {running ? "Collecting evidence…" : "No pull request selected"}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="hero-note">Sentinel advises. You own the merge.</div>
      </div>
    </div>
  );
}
