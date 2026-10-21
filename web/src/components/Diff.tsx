import { useMemo } from "react";

type Row = { kind: "same" | "add" | "del"; text: string; a?: number; b?: number };

/** Line diff via longest-common-subsequence — plenty for files of a few hundred lines. */
function diffLines(before: string, after: string): Row[] {
  const a = before.split("\n"), b = after.split("\n");
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const rows: Row[] = [];
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { rows.push({ kind: "same", text: a[i], a: i + 1, b: j + 1 }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push({ kind: "del", text: a[i], a: i + 1 }); i++; }
    else { rows.push({ kind: "add", text: b[j], b: j + 1 }); j++; }
  }
  while (i < a.length) { rows.push({ kind: "del", text: a[i], a: i + 1 }); i++; }
  while (j < b.length) { rows.push({ kind: "add", text: b[j], b: j + 1 }); j++; }
  return rows;
}

export function Diff({ before, after }: { before: string; after: string }) {
  const rows = useMemo(() => diffLines(before, after), [before, after]);
  const added = rows.filter((r) => r.kind === "add").length;
  const removed = rows.filter((r) => r.kind === "del").length;
  return (
    <div className="diff">
      <div className="diff-head"><span className="add">+{added}</span> <span className="del">−{removed}</span> lines changed by the repair</div>
      <pre>
        {rows.map((r, i) => (
          <div key={i} className={`diff-row ${r.kind}`} style={{ animationDelay: `${Math.min(i * 8, 900)}ms` }}>
            <span className="ln">{r.a ?? ""}</span>
            <span className="ln">{r.b ?? ""}</span>
            <span className="mark">{r.kind === "add" ? "+" : r.kind === "del" ? "−" : " "}</span>
            <span className="txt">{r.text || " "}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}
