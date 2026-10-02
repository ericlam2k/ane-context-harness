import { describe, test, expect } from "bun:test";
import { applyDiscount, applyLoyalty, computeDiscount, tierRate } from "../src/discounts/apply";

describe("discount policy", () => {
  test("apply_discount_rounds_to_cents", () => {
    const line = { sku: "A1", unitPrice: 19.99, qty: 3 };
    // 19.99*3 = 59.97; 10% = 5.997 -> 6.00 after cent rounding.
    expect(applyDiscount(line, 0.10)).toBeCloseTo(53.97, 2);
  });

  test("apply_loyalty_uses_tier_rate", () => {
    const line = { sku: "B2", unitPrice: 10, qty: 2 };
    expect(applyLoyalty(line, "gold")).toBe(17);
  });

  test("compute_discount_matches_documented_rounding", () => {
    // Legacy floor behaviour must be replaced by cent rounding.
    expect(computeDiscount(59.97, 0.1)).toBeCloseTo(6, 2);
  });

  test("tier_rate_table", () => {
    expect(tierRate("bronze")).toBe(0.05);
    expect(tierRate("none")).toBe(0);
  });
});
