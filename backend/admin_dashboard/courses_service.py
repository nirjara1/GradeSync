"""
Admin console: list and update professor.Course shells (term, faculty, archive),
create empty shells, remove duplicates, and delete invalid rows.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

from professor.models import Course

from .audit import log_audit

User = get_user_model()


def faculty_assignable_queryset():
    """
    Users who may own a course shell: faculty profile, staff, or current course owners
    (so existing owners stay selectable even if their profile is not FACULTY).
    """
    owner_ids = Course.objects.values_list("professor_id", flat=True).distinct()
    return (
        User.objects.filter(Q(pk__in=owner_ids) | Q(profile__role="FACULTY") | Q(is_staff=True))
        .select_related("profile")
        .distinct()
        .order_by("username")
    )


def duplicate_course_shell_groups() -> list[list[Course]]:
    """Courses grouped by (code, section, term) when more than one row exists."""
    buckets: dict[tuple[str, str, str], list[Course]] = defaultdict(list)
    for c in Course.objects.all().order_by("id"):
        key = ((c.code or "").strip().upper(), (c.section or "").strip(), (c.term or "").strip())
        buckets[key].append(c)
    return [rows for rows in buckets.values() if len(rows) > 1]


def handle_courses_console_post(request) -> Optional[HttpResponseRedirect]:
    """
    Process POST from courses console. Returns HttpResponseRedirect if handled, else None.
    """
    if request.method != "POST":
        return None

    action = request.POST.get("action")
    if not action:
        return None

    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("admin:console_courses")

    if action == "create_course_shell":
        code = (request.POST.get("new_code") or "").strip() or "NEW"
        section = (request.POST.get("new_section") or "").strip() or "001"
        title = (request.POST.get("new_title") or "").strip() or "Untitled shell"
        term = (request.POST.get("new_term") or "").strip() or "Unspecified"
        if len(term) > 50:
            term = term[:50]
        try:
            pid = int(request.POST.get("new_professor_id"))
        except (TypeError, ValueError):
            messages.error(request, "Select a valid faculty owner.")
            return redirect("admin:console_courses")
        prof = faculty_assignable_queryset().filter(pk=pid).first()
        if not prof:
            messages.error(request, "Selected user cannot own a course shell.")
            return redirect("admin:console_courses")
        c = Course.objects.create(
            code=code[:20],
            section=section[:10],
            title=title[:200],
            term=term,
            professor=prof,
        )
        log_audit(
            "course_shell_create",
            actor=request.user,
            object_repr=str(c.pk),
            detail=f"Created shell {c.code_title_label()}",
        )
        messages.success(request, f'Created empty shell "{c.code_title_label()}".')
        return redirect("admin:console_courses")

    if action == "delete_course":
        course_id = request.POST.get("course_id")
        try:
            course = Course.objects.get(pk=course_id)
        except (Course.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Course not found.")
            return redirect("admin:console_courses")
        label = course.code_title_label()
        course.delete()
        log_audit("course_delete", actor=request.user, object_repr=str(course_id), detail=f"Deleted {label}")
        messages.success(request, f"Deleted course shell: {label}.")
        return redirect("admin:console_courses")

    if action == "update_course":
        course_id = request.POST.get("course_id")
        term = (request.POST.get("term") or "").strip()
        professor_id = request.POST.get("professor_id")
        archive_raw = request.POST.get("archive_state", "active")

        try:
            course = Course.objects.select_related("professor").get(pk=course_id)
        except (Course.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Course not found.")
            return redirect("admin:console_courses")

        if not term:
            messages.error(request, "Term cannot be empty.")
            return redirect("admin:console_courses")

        if len(term) > 50:
            term = term[:50]

        try:
            pid = int(professor_id)
        except (TypeError, ValueError):
            messages.error(request, "Invalid faculty selection.")
            return redirect("admin:console_courses")

        new_professor = faculty_assignable_queryset().filter(pk=pid).first()
        if not new_professor:
            messages.error(request, "Selected user cannot be assigned as course owner.")
            return redirect("admin:console_courses")

        is_archived = archive_raw == "archived"

        with transaction.atomic():
            course.term = term
            course.professor = new_professor
            course.is_archived = is_archived
            course.save(update_fields=["term", "professor", "is_archived"])

        state = "archived" if is_archived else "active"
        log_audit(
            "course_shell_update",
            actor=request.user,
            object_repr=str(course.pk),
            detail=f"Updated {course.code_title_label()} term/faculty/{state}",
        )
        messages.success(
            request,
            f'Updated "{course.code_title_label()}": term, faculty, and {state} state saved.',
        )
        return redirect("admin:console_courses")

    return None
