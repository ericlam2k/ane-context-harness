// Legacy discount maths kept for the old checkout service.
// Same symbol name as src/discounts/apply.ts (hard case: symbol collision).

export function computeDiscount(base: number, rate: number): number {
  // Legacy behaviour: half-up rounding to whole units.
  return Math.round(base * rate);
}

export function legacyAdjustment(total: number, rate: number): number {
  return total - computeDiscount(total, rate);
}

export function migrateLine(base: number, rate: number): { old: number; new: number } {
  return {
    old: computeDiscount(base, rate),
    new: Math.floor(base * rate),
  };
}
