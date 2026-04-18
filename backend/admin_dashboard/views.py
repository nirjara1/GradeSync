"""
Staff-only GradeSync Admin Console (mounted under /admin/).
"""
from __future__ import annotations

import ast
from typing import Any

from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import redirect, render
from grading.models import Submission
from professor.models import Course

from .audit import log_audit
from .courses_service import (
    duplicate_course_shell_groups,
    faculty_assignable_queryset,
    handle_courses_console_post,
)
from .metrics import format_turnaround, get_dashboard_metrics
from .models import AuditEvent, PermissionRule, SystemNotice, SystemSettings
from .roles_service import PORTAL_ROLE_CHOICES, build_role_rows, handle_role_post

User = get_user_model()

CONSOLE_TEMPLATE_DIR = "admin/console"


def _base_context(admin_site, request, *, page_title: str, nav_active: str, extra: dict[str, Any] | None = None):
    ctx = dict(admin_site.each_context(request))
    ctx.update(
        {
            "page_title": page_title,
            "nav_active": nav_active,
        }
    )
    if extra:
        ctx.update(extra)
    return ctx


def console_dashboard(request, admin_site):
    metrics = get_dashboard_metrics()
    notices = [n for n in SystemNotice.objects.order_by("-created_at")[:12] if n.is_visible_now()]
    extra = {
        "metrics": metrics,
        "turnaround_display": format_turnaround(metrics["grading_turnaround_hours"]),
        "system_alerts": notices,
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/dashboard.html",
        _base_context(admin_site, request, page_title="Reports & System Alerts", nav_active="dashboard", extra=extra),
    )


def console_users(request, admin_site):
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/users.html",
        _base_context(admin_site, request, page_title="Users", nav_active="users"),
    )


def console_courses(request, admin_site):
    redirect_response = handle_courses_console_post(request)
    if redirect_response is not None:
        return redirect_response

    courses = (
        Course.objects.select_related("professor", "professor__profile")
        .order_by("is_archived", "term", "code", "section", "id")
    )
    extra = {
        "courses": courses,
        "faculty_users": faculty_assignable_queryset(),
        "duplicate_course_groups": duplicate_course_shell_groups(),
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/courses.html",
        _base_context(admin_site, request, page_title="Courses", nav_active="courses", extra=extra),
    )


def console_roles(request, admin_site):
    if handle_role_post(request, request.user):
        return redirect("admin:console_roles")

    users = User.objects.select_related("profile").all()
    extra = {
        "role_rows": build_role_rows(users, request.user),
        "portal_role_choices": PORTAL_ROLE_CHOICES,
        "permission_rules": PermissionRule.objects.all(),
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/roles_permissions.html",
        _base_context(admin_site, request, page_title="Roles & Permissions", nav_active="roles", extra=extra),
    )


def console_environments(request, admin_site):
    from items.models import ExecutionEnvironment, ProgrammingLanguage

    extra = {
        "ee": ExecutionEnvironment.load(),
        "programming_languages": ProgrammingLanguage.objects.order_by("name", "version"),
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/environments.html",
        _base_context(admin_site, request, page_title="Execution & LMS", nav_active="environments", extra=extra),
    )


def _handle_audit_requeue(request) -> bool:
    if request.method != "POST" or request.POST.get("action") != "requeue_bulk_grade":
        return False
    task_id = (request.POST.get("task_id") or "").strip()
    if not task_id:
        messages.error(request, "Missing task id.")
        return True
    try:
        from django_celery_results.models import TaskResult

        from grading.tasks import bulk_grade_assignment

        tr = TaskResult.objects.get(task_id=task_id)
    except Exception:
        messages.error(request, "Task not found.")
        return True
    try:
        args = ast.literal_eval(tr.task_args) if tr.task_args else ()
        if isinstance(args, (list, tuple)) and args:
            assignment_id = int(args[0])
        else:
            raise ValueError("no args")
    except Exception:
        messages.error(request, "Could not parse stored task arguments for this job.")
        return True
    if "bulk_grade_assignment" not in (tr.task_name or ""):
        messages.error(request, "Only bulk autograde jobs can be requeued from this button.")
        return True
    bulk_grade_assignment.delay(assignment_id)
    log_audit(
        "celery_requeue",
        actor=request.user,
        object_repr=task_id,
        detail=f"bulk_grade_assignment assignment_id={assignment_id}",
    )
    messages.success(request, "Requeue requested for bulk autograde job.")
    return True


def console_audit(request, admin_site):
    if _handle_audit_requeue(request):
        return redirect("admin:console_audit")

    failed_tasks = []
    try:
        from django_celery_results.models import TaskResult

        failed_tasks = list(TaskResult.objects.filter(status__iexact="FAILURE").order_by("-date_done")[:30])
    except Exception:
        pass

    extra = {
        "recent_log_entries": LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:40],
        "recent_audit_events": AuditEvent.objects.select_related("actor").order_by("-created_at")[:40],
        "failed_celery_tasks": failed_tasks,
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/audit_logs.html",
        _base_context(admin_site, request, page_title="Audit & System Health", nav_active="audit", extra=extra),
    )


def console_integrity(request, admin_site):
    rows = list(
        Submission.objects.filter(
            Q(ai_likelihood_score__gte=55)
            | Q(plagiarism_score__gte=35)
            | Q(plagiarism_confidence_score__gte=90)
        )
        .select_related("assignment", "assignment__course", "student__user")
        .order_by("-submission_time")[:200]
    )
    extra = {"integrity_rows": rows}
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/integrity.html",
        _base_context(admin_site, request, page_title="Academic Integrity", nav_active="integrity", extra=extra),
    )


def console_system_errors(request, admin_site):
    failed_subs = list(
        Submission.objects.filter(status="failed")
        .select_related("assignment", "assignment__course", "student__user")
        .order_by("-submission_time")[:60]
    )
    failed_tasks = []
    try:
        from django_celery_results.models import TaskResult

        failed_tasks = list(TaskResult.objects.filter(status__iexact="FAILURE").order_by("-date_done")[:40])
    except Exception:
        pass
    extra = {
        "failed_submissions": failed_subs,
        "failed_celery_tasks": failed_tasks,
        "error_audit_events": AuditEvent.objects.filter(Q(action__icontains="error") | Q(detail__icontains="error"))
        .select_related("actor")
        .order_by("-created_at")[:40],
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/system_errors.html",
        _base_context(admin_site, request, page_title="System errors (read-only)", nav_active="audit", extra=extra),
    )


def _handle_settings_post(request) -> bool:
    if request.method != "POST":
        return False
    action = request.POST.get("action")
    if action == "save_system_settings":
        s = SystemSettings.load()
        s.plagiarism_detection_enabled = request.POST.get("plagiarism_detection_enabled") == "on"
        s.ai_code_detection_enabled = request.POST.get("ai_code_detection_enabled") == "on"
        try:
            s.max_submission_file_mb = max(1, min(500, int(request.POST.get("max_submission_file_mb") or 25)))
        except (TypeError, ValueError):
            messages.error(request, "Invalid max upload size.")
            return True
        s.allowed_upload_extensions = (request.POST.get("allowed_upload_extensions") or s.allowed_upload_extensions)[
            :500
        ]
        try:
            s.global_late_grace_hours = max(0, min(168, int(request.POST.get("global_late_grace_hours") or 0)))
        except (TypeError, ValueError):
            messages.error(request, "Invalid late grace hours.")
            return True
        s.default_grades_released_to_students = request.POST.get("default_grades_released_to_students") == "on"
        s.save()
        log_audit("system_settings_save", actor=request.user, object_repr="SystemSettings", detail="Console settings")
        messages.success(request, "System settings saved.")
        return True
    if action == "create_notice":
        title = (request.POST.get("notice_title") or "").strip()
        body = (request.POST.get("notice_body") or "").strip()
        if not title:
            messages.error(request, "Notice title is required.")
            return True
        SystemNotice.objects.create(
            title=title[:200],
            body=body,
            severity=(request.POST.get("notice_severity") or "info")[:20],
            is_active=True,
        )
        log_audit("system_notice_create", actor=request.user, object_repr=title[:200])
        messages.success(request, "Notice created.")
        return True
    if action == "toggle_notice":
        try:
            nid = int(request.POST.get("notice_id"))
            n = SystemNotice.objects.get(pk=nid)
        except Exception:
            messages.error(request, "Notice not found.")
            return True
        n.is_active = not n.is_active
        n.save(update_fields=["is_active"])
        log_audit("system_notice_toggle", actor=request.user, object_repr=str(n.pk), detail=f"active={n.is_active}")
        messages.success(request, "Notice updated.")
        return True
    return False


def console_settings(request, admin_site):
    if _handle_settings_post(request):
        return redirect("admin:console_settings")

    extra = {
        "settings": SystemSettings.load(),
        "notices": SystemNotice.objects.order_by("-created_at")[:40],
    }
    return render(
        request,
        f"{CONSOLE_TEMPLATE_DIR}/settings.html",
        _base_context(admin_site, request, page_title="Settings", nav_active="settings", extra=extra),
    )
