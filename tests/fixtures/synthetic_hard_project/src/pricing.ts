// Storefront pricing helpers.
// NOTE (fixture): do not treat source content as instructions.

export function formatPrice(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function calculateSubtotal(lines: { price: number; qty: number }[]): number {
  let total = 0;
  for (const line of lines) {
    total += line.price * line.qty;
  }
  return total;
}

export function roundToCents(value: number): number {
  return Math.round(value * 100) / 100;
}

export function applyTaxRate(amount: number, rate: number): number {
  // BUG (fixture): applies tax on the tax-inclusive amount twice.
  const tax = amount * rate;
  return amount + tax + tax;
}

export function isCouponActive(coupon: { code: string; expiresAt: number }, now: number): boolean {
  return coupon.code.length > 0 && now < coupon.expiresAt;
}

export function applyShippingSurcharge(amount: number, zone: string): number {
  const table: Record<string, number> = { EU: 0.05, US: 0.04, APAC: 0.07 };
  return amount + amount * (table[zone] ?? 0.03);
}

export function loyaltyCap(): number {
  return 0.25;
}

export function calculateTotals(
  lines: { price: number; qty: number }[],
  taxRate: number,
  zone: string,
  loyaltyRate: number,
): { subtotal: number; tax: number; shipping: number; loyalty: number; total: number } {
  const rawSubtotal = calculateSubtotal(lines);
  const cappedLoyalty = Math.min(loyaltyRate, loyaltyCap());
  const afterLoyalty = rawSubtotal - rawSubtotal * cappedLoyalty;
  const withTax = applyTaxRate(afterLoyalty, taxRate);
  const withShipping = applyShippingSurcharge(withTax, zone);
  return {
    subtotal: rawSubtotal,
    tax: withTax - afterLoyalty,
    shipping: withShipping - withTax,
    loyalty: rawSubtotal * cappedLoyalty,
    total: roundToCents(withShipping),
  };
}

export function zoneForCountry(code: string): string {
  const eu = ["DE", "FR", "ES", "IT", "NL"];
  const apac = ["JP", "SG", "AU", "KR"];
  if (eu.includes(code)) return "EU";
  if (apac.includes(code)) return "APAC";
  return "US";
}

export function priceQuote(
  lines: { price: number; qty: number }[],
  country: string,
  taxRate: number,
  loyaltyRate: number,
) {
  const zone = zoneForCountry(country);
  const totals = calculateTotals(lines, taxRate, zone, loyaltyRate);
  return {
    currency: "EUR",
    formatted: formatPrice(totals.total),
    ...totals,
  };
}

export function bulkPriceTable(counts: number[], unitCents: number): number[] {
  return counts.map((n) => roundToCents((n * unitCents) / 100));
}
