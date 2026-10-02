# Synthetic Project

A synthetic fixture repository for the ANE Context Harness benchmark.

This repository is purpose-built for measuring Phase 0/1 deterministic context
selection. It is intentionally labelled so recall of required evidence can be
measured against a compact, predictable token budget.

## Layout

- `src/calculator.py` – basic arithmetic helpers.
- `src/discount.py` – discount logic (contains a fixture bug for benchmark tasks).
- `src/inventory.py` – inventory management utilities (distractor).
- `src/reporting.py` – reporting helpers (distractor).
- `src/analytics.py` – analytics helpers (distractor, large).
- `tests/test_calculator.py` – tests for calculator.
- `tests/test_discount.py` – tests for discount logic (required by discount tasks).
- `docs/design.md` – design notes (supporting documentation).

## Notes

This file is supporting documentation and is frequently a distractor for
tasks focused on the discount calculation. Keeping it large exercises the
token budget packing and diversity selection logic of the harness.
