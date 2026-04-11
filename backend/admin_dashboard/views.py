"""
Placeholder views for the GradeSync Admin Console (staff-only, mounted under /admin/).
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render

from professor.models import Course

from .metrics import format_turnaround, get_dashboard_metrics
from .courses_service import faculty_assignable_queryset, handle_courses_console_post
from .roles_service import PORTAL_ROLE_CHOICES, build_role_rows, handle_role_post

User = get_user_model()

CONSOLE_TEMPLATE_DIR = 'admin/console'


def _base_context(admin_site, request, *, page_title: str, nav_active: str, extra: dict[str, Any] | None = None):
    ctx = dict(admin_site.each_context(request))
    ctx.update(
        {
            'page_title': page_title,
            'nav_active': nav_active,
        }
    )
    if extra:
        ctx.update(extra)
    return ctx


def console_dashboard(request, admin_site):
    """Reports, analytics, and system alerts."""
    metrics = get_dashboard_metrics()
    extra = {
        'metrics': metrics,
        'turnaround_display': format_turnaround(metrics['grading_turnaround_hours']),
        'system_alerts': [],
    }
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/dashboard.html',
        _base_context(admin_site, request, page_title='Reports & System Alerts', nav_active='dashboard', extra=extra),
    )


def console_users(request, admin_site):
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/users.html',
        _base_context(admin_site, request, page_title='Users', nav_active='users'),
    )


def console_courses(request, admin_site):
    redirect_response = handle_courses_console_post(request)
    if redirect_response is not None:
        return redirect_response

    courses = (
        Course.objects.select_related('professor', 'professor__profile')
        .order_by('is_archived', 'term', 'code', 'section', 'id')
    )
    extra = {
        'courses': courses,
        'faculty_users': faculty_assignable_queryset(),
    }
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/courses.html',
        _base_context(admin_site, request, page_title='Courses', nav_active='courses', extra=extra),
    )


def console_roles(request, admin_site):
    if handle_role_post(request, request.user):
        return redirect('admin:console_roles')

    users = User.objects.select_related('profile').all()
    extra = {
        'role_rows': build_role_rows(users, request.user),
        'portal_role_choices': PORTAL_ROLE_CHOICES,
    }
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/roles_permissions.html',
        _base_context(admin_site, request, page_title='Roles & Permissions', nav_active='roles', extra=extra),
    )


def console_environments(request, admin_site):
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/environments.html',
        _base_context(admin_site, request, page_title='Execution & LMS', nav_active='environments'),
    )


def console_audit(request, admin_site):
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/audit_logs.html',
        _base_context(admin_site, request, page_title='Audit & System Health', nav_active='audit'),
    )


def console_integrity(request, admin_site):
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/integrity.html',
        _base_context(admin_site, request, page_title='Academic Integrity', nav_active='integrity'),
    )


def console_settings(request, admin_site):
    return render(
        request,
        f'{CONSOLE_TEMPLATE_DIR}/settings.html',
        _base_context(admin_site, request, page_title='Settings', nav_active='settings'),
    )
