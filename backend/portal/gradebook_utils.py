"""Shared helpers for student-facing grade totals (kept small to match grading report logic)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Tuple

from django.db.models import Q
from django.utils import timezone

from grading.models import Assignment, CriterionGrade, Submission

if TYPE_CHECKING:
    from grading.models import Student
    from professor.models import Course


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


def _instructor_name(u) -> str:
    full = (u.get_full_name() or "").strip()
    return full or u.get_username()


def _feedback_time_label(dt) -> str:
    if not dt:
        return ""
    dt = timezone.localtime(dt)
    h = dt.hour % 12 or 12
    m = dt.minute
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{dt.strftime('%b')} {dt.day} at {h}:{m:02d}{ampm}"


def build_student_course_gradebook_section(
    course: "Course",
    student_profile: "Student",
    now,
) -> Tuple[dict, dict[str, dict]]:
    """
    One course block for the student gradebook UI: published assignments visible to this
    student (individual or group member), submissions via direct or group membership.

    Returns (section_dict, feedback_payload_updates) where feedback keys are str(assignment_id).
    """
    assignments = list(
        Assignment.objects.filter(course=course, status="published")
        .filter(Q(is_group_assignment=False) | Q(assignment_groups__members__student=student_profile))
        .distinct()
        .order_by("due_date", "id")
    )

    feedback_payload: dict[str, dict] = {}

    if not assignments:
        return (
            {
                "course": course,
                "rows": [],
                "total_percentage": None,
                "total_earned": 0.0,
                "total_possible": 0.0,
            },
            feedback_payload,
        )

    subs = (
        Submission.objects.filter(
            Q(student=student_profile) | Q(group__members__student=student_profile),
            assignment__in=assignments,
        )
        .select_related("grade")
        .distinct()
    )
    sub_by_aid: dict[int, Any] = {}
    for s in subs:
        sub_by_aid[s.assignment_id] = s

    rubric_rows_by_submission_id: dict[int, list[dict[str, Any]]] = {}
    if subs:
        criterion_grades = (
            CriterionGrade.objects.filter(submission__in=subs)
            .select_related("criterion")
            .order_by("criterion__order", "criterion_id")
        )
        for cg in criterion_grades:
            c = cg.criterion
            rubric_rows_by_submission_id.setdefault(cg.submission_id, []).append(
                {
                    "name": c.name,
                    "earned": float(cg.points_earned or 0),
                    "max": float(c.max_points or 0),
                    "weight": float(c.weight) if c.weight is not None else None,
                }
            )

    pct, earned, possible = course_grade_totals(assignments, sub_by_aid)

    rows = []
    for a in assignments:
        sub = sub_by_aid.get(a.id)
        grade = getattr(sub, "grade", None) if sub else None
        points = float(a.points or 0)

        is_late = False
        if sub:
            st = sub.submission_time
            if a.due_date and not a.no_due_date and st > a.due_date:
                is_late = True

        status_badges = []
        if grade:
            status_key = "graded"
        elif sub:
            status_key = "submitted"
            status_badges.append("pending")
        elif not a.no_due_date and a.due_date and a.due_date < now:
            status_key = "missing"
            status_badges.append("missing")
        else:
            status_key = "upcoming"

        if is_late:
            status_badges.append("late")

        feedback_text = (grade.feedback or "").strip() if grade else ""
        rubric_scores = (
            rubric_rows_by_submission_id.get(sub.id, [])
            if sub
            else []
        )
        has_feedback = bool(feedback_text or rubric_scores)

        score_num = float(grade.score) if grade else None
        if has_feedback and grade:
            feedback_payload[str(a.id)] = {
                "assignmentName": a.name,
                "body": feedback_text,
                "instructor": _instructor_name(course.professor),
                "gradedAt": _feedback_time_label(grade.graded_at),
                "rubricScores": rubric_scores,
            }

        rows.append(
            {
                "assignment": a,
                "course": course,
                "due_dt": a.due_date,
                "no_due_date": a.no_due_date,
                "submitted_time": sub.submission_time if sub else None,
                "status_key": status_key,
                "status_badges": status_badges,
                "score_num": score_num,
                "points": points,
                "has_feedback": has_feedback,
                "is_late": is_late,
            }
        )

    section = {
        "course": course,
        "rows": rows,
        "total_percentage": pct,
        "total_earned": earned,
        "total_possible": possible,
    }
    return section, feedback_payload
