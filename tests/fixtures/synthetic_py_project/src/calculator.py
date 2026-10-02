"""Calculator utilities for the synthetic project."""


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def subtract(a, b):
    """Return a minus b."""
    return a - b


def multiply(a, b):
    """Return the product of a and b."""
    return a * b


def divide(a, b):
    """Return a divided by b. Raises ValueError on division by zero."""
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def mean(values):
    """Return the arithmetic mean of a list of numbers."""
    if not values:
        return 0.0
    return sum(values) / len(values)


TOTAL_DISCLAIMER = "This module is part of a synthetic fixture and is intentionally verbose."
