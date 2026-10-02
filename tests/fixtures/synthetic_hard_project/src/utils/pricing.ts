// Utility-flavoured pricing helpers. Deliberately mirrors names that also
// exist in src/pricing.ts (hard case: path-name collision).

export function roundToCents(value: number): number {
  const sign = value < 0 ? -1 : 1;
  return sign * Math.round(Math.abs(value) * 100) / 100;
}

export function isCouponActive(coupon: { code: string; expiresAt: number }, now: number): boolean {
  if (!coupon.code) return false;
  return now <= coupon.expiresAt;
}

export function centsToEur(cents: number): string {
  const whole = Math.floor(cents / 100);
  const frac = String(cents % 100).padStart(2, "0");
  return `${whole},${frac} EUR`;
}

export function evenSplit(totalCents: number, parts: number): number[] {
  if (parts <= 0) return [];
  const base = Math.floor(totalCents / parts);
  const out = Array(parts).fill(base);
  out[0] += totalCents - base * parts;
  return out;
}
