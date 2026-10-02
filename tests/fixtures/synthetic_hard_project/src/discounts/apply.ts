// Discount application policy for the storefront.
// The authoritative rounding/cap rules live in docs/pricing-rules.md.

import type { CartLine, LoyaltyTier } from "../types";

export function computeDiscount(base: number, rate: number): number {
  // BUG (fixture): rounds down to whole units, losing cents.
  return Math.floor(base * rate);
}

export function tierRate(tier: LoyaltyTier): number {
  switch (tier) {
    case "bronze":
      return 0.05;
    case "silver":
      return 0.10;
    case "gold":
      return 0.15;
    default:
      return 0;
  }
}

export function applyDiscount(line: CartLine, rate: number): number {
  const discount = computeDiscount(line.unitPrice * line.qty, rate);
  return line.unitPrice * line.qty - discount;
}

export function applyPromo(lines: CartLine[], promoCode: string): number {
  const promos: Record<string, number> = { SPRING10: 0.10, WINTER20: 0.20 };
  const rate = promos[promoCode] ?? 0;
  return lines.reduce((sum, line) => sum + applyDiscount(line, rate), 0);
}

export function applyLoyalty(line: CartLine, tier: LoyaltyTier): number {
  return applyDiscount(line, tierRate(tier));
}

export function describePolicy(): string {
  return "Concessions are computed per line, capped by tier, rounded per docs.";
}
