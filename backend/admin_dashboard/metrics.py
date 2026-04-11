"""
Aggregate metrics for the admin console dashboard (reports view).
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, ExpressionWrapper, F, Q
from django.db.models.fields import DurationField
from django.utils import timezone

User = get_user_model()


def get_dashboard_metrics(*, recent_days: int = 30) -> dict:
    """
    Return counts and formatted strings for dashboard cards.
    Uses professor.Course and grading.Submission / Grade (canonical app data).
    """
    # Local imports avoid import cycles if models touch each other at load time.
    from grading.models import Grade, Submission
    from professor.models import Course

    now = timezone.now()
    recent_start = now - timedelta(days=recent_days)

    total_users = User.objects.count()
    active_courses = Course.objects.filter(is_archived=False).count()
    submission_total = Submission.objects.count()
    submissions_recent = Submission.objects.filter(submission_time__gte=recent_start).count()

    plagiarism_flags = Submission.objects.filter(
        Q(plagiarism_score__isnull=False, plagiarism_score__gt=0)
        | (Q(plagiarism_match_info__isnull=False) & ~Q(plagiarism_match_info=''))
    ).count()

    # Avg time from submission to first Grade record (autograded / recorded grade).
    avg_turnaround = (
        Grade.objects.filter(
            graded_at__gte=recent_start,
            submission__submission_time__isnull=False,
        )
        .annotate(
            turnaround=ExpressionWrapper(
                F('graded_at') - F('submission__submission_time'),
                output_field=DurationField(),
            )
        )
        .aggregate(avg=Avg('turnaround'))['avg']
    )
    turnaround_hours = None
    if avg_turnaround is not None:
        turnaround_hours = round(avg_turnaround.total_seconds() / 3600, 1)

    return {
        'total_users': total_users,
        'active_courses': active_courses,
        'submission_total': submission_total,
        'submissions_recent': submissions_recent,
        'recent_period_days': recent_days,
        'plagiarism_flags': plagiarism_flags,
        'grading_turnaround_hours': turnaround_hours,
    }


def format_turnaround(hours: float | None) -> str:
    if hours is None:
        return '—'
    if hours < 1:
        return f'{int(round(hours * 60))} min avg'
    return f'{hours} h avg'
