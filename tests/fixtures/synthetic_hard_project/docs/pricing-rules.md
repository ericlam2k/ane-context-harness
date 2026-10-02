# Pricing rules (authoritative)

This document is the single source of truth for how price concessions are
computed at checkout. Code elsewhere implements these rules.

## Concessions

A **price concession** (also called a *markdown* in older notes) reduces the
line total before tax. Three kinds exist:

1. **Loyalty concession** — determined by tier, capped at 25%.
2. **Promo concession** — a per-code rate applied across all lines.
3. **Clearance markdown** — warehouse stock aging, applied to stock cost only
   (never to customer-facing line totals).

## Rounding

Concessions are computed in cents and rounded **half to even** at the line
level. Never round down to whole currency units — that loses cents on every
line and compounds across a cart.

## Tax and shipping order

Apply concessions first, then tax, then shipping surcharge. The shipping
surcharge uses the zone table (EU 5%, US 4%, APAC 7%, default 3%).

## Duplicate definitions

The legacy checkout service under `legacy/` still defines its own
`computeDiscount`. It must converge to this policy before the old service is
retired.
