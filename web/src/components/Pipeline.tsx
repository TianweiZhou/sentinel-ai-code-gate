import { motion } from "framer-motion";
import { STAGES, type StageId, type StageStatus } from "../types";

export interface StageState { status: StageStatus; summary?: string; duration_ms?: number }

const ICONS: Record<StageId, string> = {
  generate: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  parse: "M8 6 3 12l5 6M16 6l5 6-5 6",
  imports: "M12 3 4 7.5v9L12 21l8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9",
  lint: "M4 6h16M4 12h10M4 18h7M17 15l2 2 3-4",
  types: "M5 5h14M12 5v14M8 19h8",
  complexity: "M3 17 9 11l4 4 8-8M15 7h6v6",
  security: "M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  tests: "M9 3v6L4 19a1.5 1.5 0 0 0 1.3 2h13.4a1.5 1.5 0 0 0 1.3-2L15 9V3M8 3h8",
  coverage: "M12 3a9 9 0 1 0 9 9h-9z",
  mutation: "M8 3c0 6 8 6 8 12s-8 6-8 6M16 3c0 6-8 6-8 12M7 8h10M7 16h10",
  requirements: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01",
  gate: "M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16M3 21h18M9 9h6M9 13h6",
};

export function Pipeline({ stages, showGenerate }: { stages: Record<StageId, StageState>; showGenerate: boolean }) {
  const list = STAGES.filter((s) => showGenerate || s.id !== "generate");
  const doneCount = list.filter((s) => !["idle", "running"].includes(stages[s.id].status)).length;
  const progress = doneCount / list.length;

  return (
    <div className="pipeline">
      <div className="pipeline-track">
        <motion.div className="pipeline-fill" animate={{ scaleX: progress }} transition={{ type: "spring", stiffness: 60, damping: 18 }} />
        <div className="pipeline-pulse" style={{ opacity: progress > 0 && progress < 1 ? 1 : 0 }} />
      </div>
      <div className="pipeline-nodes" style={{ gridTemplateColumns: `repeat(${list.length}, minmax(0, 1fr))` }}>
        {list.map((s, i) => {
          const st = stages[s.id];
          return (
            <motion.div
              key={s.id}
              className={`node node-${st.status}`}
              title={s.hint}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <div className="node-orb">
                {st.status === "running" && <span className="node-spinner" />}
                <motion.svg
                  viewBox="0 0 24 24" className="node-icon"
                  key={st.status}
                  initial={{ scale: 0.6, rotate: -20 }} animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 14 }}
                >
                  <path d={ICONS[s.id]} />
                </motion.svg>
                {(st.status === "pass" || st.status === "fail" || st.status === "warn") && (
                  <motion.span className="node-burst" initial={{ scale: 0.6, opacity: 0.9 }} animate={{ scale: 2.4, opacity: 0 }} transition={{ duration: 0.8 }} />
                )}
              </div>
              <div className="node-label">{s.label}</div>
              <div className="node-summary">{st.status === "running" ? "analysing…" : st.summary ?? " "}</div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
