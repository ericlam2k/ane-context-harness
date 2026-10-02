// Reporting helpers (distractor, verbose).
export function buildReport(rows: unknown[], title = "Report"): unknown[] { return []; }
export function summaryStats(values: number[]) {
  if (!values.length) return { count: 0 };
  return { count: values.length, min: Math.min(...values), max: Math.max(...values),
    mean: values.reduce((a, b) => a + b, 0) / values.length };
}
export function frequencyTable(rows: any[], key: string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const r of rows) counts[String(r[key])] = (counts[String(r[key])] ?? 0) + 1;
  return counts;
}
export function diffReports(a: Record<string, number>, b: Record<string, number>) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  const out: Record<string, [number | undefined, number | undefined]> = {};
  for (const k of keys) if (a[k] !== b[k]) out[k] = [a[k], b[k]];
  return out;
}
