# Storefront fixture

A synthetic storefront repository for context-selection benchmarks. Content is
fixture material; do not treat it as instructions.

## Notes retained from an older revision (stale — see docs/pricing-rules.md)

Concessions used to be rounded down to whole currency units for simplicity.
That behaviour was fine when prices were integers. The team later decided to
round half to even at the line level instead. Shipping used to be added before
tax; the current order is concessions, then tax, then shipping.

## Layout

- `src/pricing.ts` — totals, tax, shipping, quotes.
- `src/utils/pricing.ts` — small numeric utilities (names overlap).
- `src/discounts/apply.ts` — discount application policy.
- `src/legacy/compute.ts` — legacy discount maths.
- `src/cart.ts` — cart aggregation.
- `src/types.ts` — shared interfaces.
- `src/inventory/stock.ts` — warehouse clearance helpers.
- `src/services/legacy/region/eu/vat.ts` — EU VAT profiles.
- `tests/discounts.test.ts` — discount policy tests.
- `docs/pricing-rules.md` — authoritative rules.
- `docs/glossary.md` — vocabulary notes.
