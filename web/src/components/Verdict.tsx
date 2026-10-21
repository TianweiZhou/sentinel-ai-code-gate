import { AnimatePresence, animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";
import type { Gate } from "../types";

function useCountUp(value: number) {
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v));
  useEffect(() => {
    const controls = animate(mv, value, { duration: 1.4, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [value, mv]);
  return rounded;
}

export function ScoreRing({ score, threshold, passed }: { score: number; threshold: number; passed: boolean | null }) {
  const r = 70, c = 2 * Math.PI * r;
  const shown = useCountUp(score);
  const color = passed === null ? "var(--cyan)" : passed ? "var(--green)" : score >= threshold ? "var(--amber)" : "var(--red)";
  const thresholdAngle = (threshold / 100) * 360 - 90;

  return (
    <div className="ring">
      <svg viewBox="0 0 180 180">
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={color} />
            <stop offset="100%" stopColor="var(--violet)" />
          </linearGradient>
        </defs>
        <circle cx="90" cy="90" r={r} className="ring-bg" />
        {Array.from({ length: 60 }, (_, i) => (
          <line key={i} x1="90" y1="8" x2="90" y2={i % 5 === 0 ? 14 : 11} className="ring-tick" transform={`rotate(${i * 6} 90 90)`} />
        ))}
        <motion.circle
          cx="90" cy="90" r={r} className="ring-fg" stroke="url(#ringGrad)"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - score / 100) }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
          style={{ filter: `drop-shadow(0 0 10px ${color})` }}
        />
        <g transform={`rotate(${thresholdAngle} 90 90)`}>
          <line x1={90 + r - 10} y1="90" x2={90 + r + 10} y2="90" className="ring-threshold" />
        </g>
      </svg>
      <div className="ring-center">
        <motion.span className="ring-score" style={{ color }}>{shown}</motion.span>
        <span className="ring-caption">quality score</span>
      </div>
    </div>
  );
}

export function Verdict({ gate, running }: { gate: Gate | null; running: boolean }) {
  return (
    <div className="verdict">
      <ScoreRing score={gate?.overall ?? 0} threshold={gate?.threshold ?? 85} passed={gate ? gate.passed : null} />
      <div className="verdict-body">
        <AnimatePresence mode="wait">
          {!gate ? (
            <motion.div key="idle" className="verdict-state idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {running ? <span className="scanning">SCANNING<span className="dots" /></span> : "AWAITING CODE"}
            </motion.div>
          ) : (
            <motion.div
              key={`${gate.passed}-${gate.overall}`}
              className={`verdict-state ${gate.passed ? "pass" : gate.repairable ? "fail" : "escalate"}`}
              initial={{ opacity: 0, scale: 0.85, filter: "blur(8px)" }}
              animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
              transition={{ type: "spring", stiffness: 200, damping: 16 }}
            >
              {gate.passed ? "PASS · SHIP IT" : gate.repairable ? "BLOCKED" : "NEEDS HUMAN"}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="verdict-threshold">threshold {gate?.threshold ?? 85} · hard rules always win</div>
        <ul className="blockers">
          <AnimatePresence>
            {gate?.blockers.map((b, i) => (
              <motion.li
                key={b}
                className={gate.escalations.includes(b) ? "esc" : ""}
                initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
                transition={{ delay: 0.3 + i * 0.08 }}
              >
                <span className="blocker-tag">{gate.escalations.includes(b) ? "HUMAN" : "AI-FIX"}</span>
                {b}
              </motion.li>
            ))}
          </AnimatePresence>
          {gate?.passed && <li className="ok">All hard rules satisfied — every requirement is proven by a passing test.</li>}
        </ul>
      </div>
    </div>
  );
}
