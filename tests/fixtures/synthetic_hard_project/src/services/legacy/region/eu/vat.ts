// EU VAT handling, deeply nested on purpose (hard case: deep nesting).

import type { TaxProfile } from "../../../types";

export const EU_COUNTRIES = ["DE", "FR", "ES", "IT", "NL", "BE", "AT", "IE"];

export function profileFor(country: string): TaxProfile {
  const standard: Record<string, number> = { DE: 0.19, FR: 0.20, ES: 0.21, IT: 0.22, NL: 0.21 };
  return {
    country,
    rate: standard[country] ?? 0.20,
    includesVat: EU_COUNTRIES.includes(country),
  };
}

export function applyVat(amount: number, profile: TaxProfile): number {
  if (!profile.includesVat) return amount;
  // BUG (fixture): applies VAT as if it were already included.
  return amount + amount * profile.rate;
}
