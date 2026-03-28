"""Shared helpers for student-facing grade totals (kept small to match grading report logic)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from grading.models import Assignment, Submission


def course_grade_totals(assignments: list, submission_by_assignment: dict[int, Any]) -> tuple[Optional[float], float, float]:
    """
    Returns (overall_percentage_or_none, points_earned, points_possible).
    Mirrors weighted handling in grading.views.student_course_report.
    """
    if not assignments:
        return None, 0.0, 0.0

    use_weighted = any(getattr(a, "is_weighted", False) for a in assignments)
    total_points_possible = 0.0
    total_points_earned = 0.0
    total_weight_possible = 0.0
    total_weight_earned = 0.0

    for a in assignments:
        total_points_possible += float(a.points or 0)
        sub = submission_by_assignment.get(a.id)
        score = None
        if sub:
            g = getattr(sub, "grade", None)
            if g:
                score = float(g.score)
                total_points_earned += score
        if use_weighted and getattr(a, "is_weighted", False) and a.weight and float(a.points or 0) > 0:
            w = float(a.weight)
            total_weight_possible += w
            if score is not None:
                pts = float(a.points or 0)
                pct = max(0.0, min(1.0, float(score) / pts)) if pts > 0 else 0.0
                total_weight_earned += pct * w

    if use_weighted and total_weight_possible > 0:
        overall = (total_weight_earned / total_weight_possible) * 100.0
    elif total_points_possible > 0:
        overall = (total_points_earned / total_points_possible) * 100.0
    else:
        overall = None

    return overall, total_points_earned, total_points_possible
