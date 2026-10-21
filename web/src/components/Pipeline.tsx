import { motion } from "framer-motion";
import { STAGES, type StageId, type StageStatus } from "../types";

export interface StageState { status: StageStatus; summary?: string; duration_ms?: number }
export type StageMap = Record<StageId, StageState>;

export const idleStages = (): StageMap =>
  Object.fromEntries(STAGES.map((s) => [s.id, { status: "idle" }])) as StageMap;

const ICONS: Record<StageId, string> = {
  diff: "M6 3v12M18 9v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 9c0 6 12 0 12 6",
  requirements: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  imports: "M12 3 4 7.5v9L12 21l8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9",
  lint: "M4 6h16M4 12h10M4 18h7M17 15l2 2 3-4",
  types: "M5 5h14M12 5v14M8 19h8",
  complexity: "M3 17 9 11l4 4 8-8M15 7h6v6",
  security: "M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  integrity: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5zM12 15v2",
  tests: "M9 3v6L4 19a1.5 1.5 0 0 0 1.3 2h13.4a1.5 1.5 0 0 0 1.3-2L15 9V3M8 3h8",
  coverage: "M12 3a9 9 0 1 0 9 9h-9z",
  mutation: "M8 3c0 6 8 6 8 12s-8 6-8 6M16 3c0 6-8 6-8 12M7 8h10M7 16h10",
  ai_review: "M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15.5l-1.8-4.7L5.5 9l4.7-1.3zM18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z",
  verdict: "M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16M3 21h18M9 9h6M9 13h6",
};

export function Pipeline({ stages }: { stages: StageMap }) {
  const done = STAGES.filter((s) => !["idle", "running"].includes(stages[s.id].status)).length;
  const progress = done / STAGES.length;

  return (
    <div className="pipeline">
      <div className="pipeline-track">
        <motion.div className="pipeline-fill" animate={{ scaleX: progress }} transition={{ duration: 0.4, ease: "easeOut" }} />
      </div>
      <div className="pipeline-nodes" style={{ gridTemplateColumns: `repeat(${STAGES.length}, minmax(0, 1fr))` }}>
        {STAGES.map((s, i) => {
          const st = stages[s.id];
          return (
            <motion.div
              key={s.id}
              className={`node node-${st.status}`}
              title={s.hint}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.02 }}
            >
              <div className="node-orb">
                <svg viewBox="0 0 24 24" className="node-icon"><path d={ICONS[s.id]} /></svg>
              </div>
              <div className="node-label">{s.label}</div>
              <div className="node-summary" title={st.summary}>{st.status === "running" ? "checking…" : st.summary ?? " "}</div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
