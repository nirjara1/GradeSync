"""
Aggregate metrics for the admin console dashboard (reports view).
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
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
        | (Q(plagiarism_match_info__isnull=False) & ~Q(plagiarism_match_info=""))
    ).count()

    failed_submissions_recent = Submission.objects.filter(
        status="failed",
        submission_time__gte=recent_start,
    ).count()

    trend_days = 14
    trend_start = now - timedelta(days=trend_days)
    trend_qs = (
        Submission.objects.filter(submission_time__gte=trend_start)
        .annotate(day=TruncDate("submission_time"))
        .values("day")
        .annotate(c=Count("id"))
        .order_by("day")
    )
    submission_trend = [{"day": row["day"], "count": row["c"]} for row in trend_qs if row["day"]]

    storage_bytes = _approximate_submission_storage_bytes()

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
        "failed_submissions_recent": failed_submissions_recent,
        "submission_trend": submission_trend,
        "submission_trend_days": trend_days,
        "approx_storage_bytes": storage_bytes,
    }


def _approximate_submission_storage_bytes() -> int:
    """Sum known uploaded submission files and archived resubmit snapshots (best effort)."""
    from admin_dashboard.models import SubmissionFileVersion

    from grading.models import Submission

    total = 0
    qs = Submission.objects.exclude(file_path="").only("file_path")
    for sub in qs.iterator(chunk_size=400):
        try:
            total += sub.file_path.size
        except OSError:
            pass
        except Exception:
            pass
    for ver in SubmissionFileVersion.objects.only("snapshot_file").iterator(chunk_size=200):
        try:
            total += ver.snapshot_file.size
        except OSError:
            pass
        except Exception:
            pass
    return total


def format_turnaround(hours: float | None) -> str:
    if hours is None:
        return '—'
    if hours < 1:
        return f'{int(round(hours * 60))} min avg'
    return f'{hours} h avg'
