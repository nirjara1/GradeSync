"""
Shared submission status for gradebook and course reports.

Statuses distinguish on-time vs late using assignment due_date and submission_time.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

from django.utils import timezone

if TYPE_CHECKING:
    from grading.models import Assignment, Submission

ReportStatus = Literal[
    "missing",
    "not_submitted",
    "graded",
    "ungraded",
    "late_graded",
    "late_ungraded",
]


def effective_due(assignment: "Assignment"):
    if getattr(assignment, "no_due_date", False):
        return None
    return getattr(assignment, "due_date", None)


def submission_is_late(assignment: "Assignment", submission: "Submission") -> bool:
    due = effective_due(assignment)
    if due is None:
        return False
    return submission.submission_time > due


def assignment_submission_report_status(
    assignment: "Assignment",
    submission: Optional["Submission"],
) -> ReportStatus:
    """
    - missing: no submission and due date has passed
    - not_submitted: no submission and (no due or due not yet passed)
    - graded / ungraded: submitted on or before due (or no due)
    - late_graded / late_ungraded: submitted after due
    """
    now = timezone.now()
    due = effective_due(assignment)

    if submission is None:
        if due is not None and due < now:
            return "missing"
        return "not_submitted"

    has_grade = getattr(submission, "grade", None) is not None
    if due is not None and submission_is_late(assignment, submission):
        return "late_graded" if has_grade else "late_ungraded"
    if has_grade:
        return "graded"
    return "ungraded"


def report_status_csv_label(status: ReportStatus) -> str:
    return {
        "missing": "Missing",
        "not_submitted": "Not submitted",
        "graded": "Graded",
        "ungraded": "Ungraded",
        "late_graded": "Late (graded)",
        "late_ungraded": "Late (ungraded)",
    }.get(status, status)


def report_status_short_label(status: ReportStatus) -> str:
    """UI labels for instructor reports."""
    return report_status_csv_label(status)
