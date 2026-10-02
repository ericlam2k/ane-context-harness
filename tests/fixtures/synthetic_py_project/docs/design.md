# Design notes

## Overview

This synthetic project exists to support ANE Context Harness benchmarking.
It contains a small discount-calculation module with an intentional bug,
plus a number of distractor modules used to measure token reduction and
required-evidence recall under a tight token budget.

## Modules

- `src/calculator.py`: basic math helpers (add, subtract, multiply, divide, mean).
- `src/discount.py`: discount logic. Contains `calculate_discount`, which has an
  intentional bug (`price * (price * rate)` instead of `price - price*rate`).
- `src/inventory.py`: inventory management (distractor, unrelated to discount).
- `src/reporting.py`: reporting helpers (distractor).
- `src/analytics.py`: analytics helpers (distractor, large).

## Tests

- `tests/test_calculator.py` – covers `calculator.py`.
- `tests/test_discount.py` – covers `discount.py` and is required by discount tasks.

## Running

`python -m pytest tests/ -q`

## Budget rationale

The distractor modules are intentionally verbose so that a sub-`token_budget`
selection request must drop irrelevant content while retaining the required
discount and test evidence. This lets the benchmark measure reduction percent
and recall independently.
