// Analytics helpers (distractor).
export class Metrics {
  points: number[] = [];
  record(v: number) { this.points.push(v); }
  average() { return this.points.reduce((a, b) => a + b, 0) / (this.points.length || 1); }
}
export function movingAverage(values: number[], window: number): number[] {
  if (window < 1 || !values.length) return [];
  const out: number[] = [];
  let acc = 0;
  for (let i = 0; i < values.length; i++) {
    acc += values[i];
    if (i >= window) acc -= values[i - window];
    out.push(acc / Math.min(i + 1, window));
  }
  return out;
}
export function smooth(values: number[], alpha = 0.3): number[] {
  if (!values.length) return [];
  const out: number[] = [values[0]];
  for (let i = 1; i < values.length; i++) out.push(alpha * values[i] + (1 - alpha) * out[i - 1]);
  return out;
}
