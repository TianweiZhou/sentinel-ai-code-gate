import { motion } from "framer-motion";
import type { Scores } from "../types";

const AXES: { key: keyof Scores; label: string }[] = [
  { key: "requirements", label: "Requirements" },
  { key: "correctness", label: "Correctness" },
  { key: "security", label: "Security" },
  { key: "test_strength", label: "Test strength" },
  { key: "maintainability", label: "Maintainability" },
  { key: "integrity", label: "Integrity" },
];

const C = 150, R = 100;
const point = (i: number, v: number) => {
  const a = (Math.PI * 2 * i) / AXES.length - Math.PI / 2;
  return [C + Math.cos(a) * R * (v / 100), C + Math.sin(a) * R * (v / 100)] as const;
};
const poly = (vals: number[]) => vals.map((v, i) => point(i, v).join(",")).join(" ");

export function Radar({ scores }: { scores: Scores | null }) {
  const vals = AXES.map((a) => scores?.[a.key] ?? 0);
  return (
    <svg viewBox="0 0 300 300" className="radar">
      {[25, 50, 75, 100].map((l) => <polygon key={l} points={poly(AXES.map(() => l))} className="radar-ring" />)}
      {AXES.map((_, i) => {
        const [x, y] = point(i, 100);
        return <line key={i} x1={C} y1={C} x2={x} y2={y} className="radar-axis" />;
      })}
      <motion.polygon className="radar-shape" initial={false} animate={{ points: poly(vals) }}
        transition={{ type: "spring", stiffness: 70, damping: 14 }} />
      {AXES.map((a, i) => {
        const [x, y] = point(i, vals[i]);
        return <motion.circle key={a.key} r="3.5" className="radar-dot" initial={false} animate={{ cx: x, cy: y }}
          transition={{ type: "spring", stiffness: 70, damping: 14 }} />;
      })}
      {AXES.map((a, i) => {
        const [x, y] = point(i, 126);
        return (
          <text key={a.key} x={x} y={y} className="radar-label" textAnchor={Math.abs(x - C) < 5 ? "middle" : x > C ? "start" : "end"}>
            <tspan x={x} dy="0">{a.label}</tspan>
            <tspan x={x} dy="13" className="radar-value">{scores ? vals[i] : "—"}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
