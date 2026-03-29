"""Weighted and unweighted rubric final score calculations."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Optional

WEIGHT_SUM_TOLERANCE = Decimal("0.02")


def clamp_earned(earned: Decimal, max_points: Decimal) -> Decimal:
    if max_points <= 0:
        return Decimal("0")
    e = max(Decimal("0"), earned)
    return min(e, max_points)


def weighted_percentage_from_criteria(
    criteria: Iterable,
    earned_by_criterion_id: Mapping[int, Decimal],
) -> Decimal:
    """
    Sum over criteria: (earned / max_points) * weight.
    Result is 0–100 when weights sum to 100.
    """
    total = Decimal("0")
    for c in criteria:
        wid = getattr(c, "id", None)
        mx = Decimal(str(c.max_points or 0))
        w = Decimal(str(c.weight or 0))
        if mx <= 0:
            continue
        earned = Decimal(str(earned_by_criterion_id.get(wid, 0) or 0))
        earned = clamp_earned(earned, mx)
        total += (earned / mx) * w
    return total


def percentage_to_assignment_score(percentage_0_100: Decimal, assignment_points) -> Decimal:
    ap = Decimal(str(assignment_points or 0))
    return (percentage_0_100 / Decimal("100")) * ap


def final_score_weighted_rubric(
    criteria: Iterable,
    earned_by_criterion_id: Mapping[int, Decimal],
    assignment_points,
) -> Decimal:
    pct = weighted_percentage_from_criteria(criteria, earned_by_criterion_id)
    return percentage_to_assignment_score(pct, assignment_points).quantize(Decimal("0.01"))


def final_score_unweighted_rubric(
    criteria: Iterable,
    earned_by_criterion_id: Mapping[int, Decimal],
) -> Decimal:
    total = Decimal("0")
    for c in criteria:
        wid = getattr(c, "id", None)
        mx = Decimal(str(c.max_points or 0))
        earned = Decimal(str(earned_by_criterion_id.get(wid, 0) or 0))
        total += clamp_earned(earned, mx)
    return total.quantize(Decimal("0.01"))


def criterion_weighted_contribution(
    earned: Decimal,
    max_points: Decimal,
    weight: Decimal,
) -> Decimal:
    """Single criterion contribution toward the 0–100 percentage total."""
    if max_points <= 0:
        return Decimal("0")
    e = clamp_earned(earned, max_points)
    return ((e / max_points) * weight).quantize(Decimal("0.01"))


def validate_weighted_rubric_rows(rows: list) -> Optional[str]:
    """rows: list of dicts with 'weight' and 'max_points'. Returns error message or None."""
    if not rows:
        return None
    total_w = sum(float(r.get("weight") or 0) for r in rows)
    if abs(total_w - 100.0) > float(WEIGHT_SUM_TOLERANCE):
        return "Weighted rubric: weights must total 100%% (currently %.2f%%)." % total_w
    for r in rows:
        mp = float(r.get("max_points") or 0)
        if mp <= 0:
            return "Each criterion must have max points greater than 0."
    return None


def validate_unweighted_rubric_rows(rows: list, assignment_points: int) -> Optional[str]:
    """Ensure positive max points; sum of max points should match assignment total when set."""
    if not rows:
        return None
    for r in rows:
        mp = float(r.get("max_points") or 0)
        if mp <= 0:
            return "Each criterion must have max points greater than 0."
    s = sum(float(r.get("max_points") or 0) for r in rows)
    ap = float(assignment_points or 0)
    if ap > 0 and abs(s - ap) > 0.02:
        return (
            "Unweighted rubric: the sum of max points (%.2f) should match the assignment total (%s)."
            % (s, assignment_points)
        )
    return None


def sum_weights_for_rubric(rubric) -> Decimal:
    from django.db.models import Sum

    agg = rubric.criteria.aggregate(s=Sum("weight"))
    v = agg.get("s")
    return Decimal(str(v or 0))
