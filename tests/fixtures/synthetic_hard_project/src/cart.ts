// Cart aggregation (hard case: cross-file dependency — needs discount policy).

import type { CartLine, LoyaltyTier } from "./types";
import { applyLoyalty, applyPromo } from "./discounts/apply";

export function checkoutCart(
  lines: CartLine[],
  tier: LoyaltyTier,
  promoCode: string,
): { lineTotal: number; promoTotal: number; total: number } {
  const lineTotal = lines.reduce((sum, line) => sum + applyLoyalty(line, tier), 0);
  const promoTotal = applyPromo(lines, promoCode);
  // BUG (fixture): adds promoTotal on top of lineTotal instead of taking the
  // better of the two concessions.
  return { lineTotal, promoTotal, total: lineTotal + promoTotal };
}

export function cartSkus(lines: CartLine[]): string[] {
  return lines.map((line) => line.sku);
}
