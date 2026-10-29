"""Category normalization and warehouse zone/separation compatibility rules."""

from __future__ import annotations

from typing import Any

import pandas as pd

CATEGORY_ALIASES = {
    "normal": "normal",
    "standard": "normal",
    "general": "normal",
    "fragile": "fragile",
    "medical": "medical",
    "medicine": "medical",
    "pharma": "medical",
    "pharmaceutical": "medical",
    "fire": "fire",
    "flammable": "fire",
    "fire_risk": "fire",
    "fire-risk": "fire",
    "hazard": "hazardous",
    "hazmat": "hazardous",
    "hazardous": "hazardous",
}

DEFAULT_CATEGORY_ZONES = {
    "normal": "STANDARD",
    "fragile": "STANDARD",
    "medical": "MEDICAL",
    "fire": "FIRE",
    "hazardous": "HAZMAT",
}


def normalize_category(value: object) -> str:
    """Normalize common category labels and reject unknown category names."""
    label = "normal" if value is None or pd.isna(value) else str(value).strip().lower()
    if not label:
        label = "normal"
    try:
        return CATEGORY_ALIASES[label]
    except KeyError as error:
        raise ValueError(
            f"Unsupported product category {value!r}; use normal, fragile, medical, fire, or hazardous"
        ) from error


def effective_category(sku: Any) -> str:
    """Treat any non-empty hazard class as hazardous, regardless of product label."""
    hazard = str(sku.get("hazard_class", "none")).strip().lower()
    if hazard not in {"", "none", "no", "na", "n/a", "nan"}:
        return "hazardous"
    return normalize_category(sku.get("category", "normal"))


def required_zone(sku: Any, rules: dict[str, Any]) -> str:
    """Return the only compatible storage zone for this SKU under the configured matrix."""
    category = effective_category(sku)
    configured = dict(DEFAULT_CATEGORY_ZONES)
    configured.update(rules.get("category_zones", {}))
    if "hazardous" not in rules.get("category_zones", {}):
        configured["hazardous"] = str(rules.get("hazardous_zone", "HAZMAT"))
    if category not in configured:
        raise ValueError(f"No storage zone is configured for product category {category!r}")
    return str(configured[category])


def separation_rules(rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized, symmetric category-pair clearance requirements."""
    configured = rules.get("category_separation_rules")
    if configured is None:
        configured = [
            {
                "categories": ["hazardous", category],
                "min_clearance_m": float(rules.get("hazard_min_clearance_m", 0.0)),
            }
            for category in ("normal", "fragile", "medical", "fire")
        ]
    result = []
    for item in configured:
        pair = tuple(sorted(normalize_category(category) for category in item["categories"]))
        if len(pair) != 2:
            raise ValueError("Each category separation rule must name exactly two categories")
        clearance = float(item["min_clearance_m"])
        if clearance < 0:
            raise ValueError("Category separation distances cannot be negative")
        result.append({"categories": pair, "min_clearance_m": clearance})
    return result


def required_pair_clearance(left: str, right: str, rules: dict[str, Any]) -> float:
    """Look up symmetric physical clearance for an assigned category pair."""
    pair = tuple(sorted((normalize_category(left), normalize_category(right))))
    return max(
        (
            float(item["min_clearance_m"])
            for item in separation_rules(rules)
            if tuple(item["categories"]) == pair
        ),
        default=0.0,
    )
