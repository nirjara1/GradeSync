"""
Admin console: list and update professor.Course shells (term, faculty, archive).
"""
from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

from professor.models import Course

User = get_user_model()


def faculty_assignable_queryset():
    """
    Users who may own a course shell: faculty profile, staff, or current course owners
    (so existing owners stay selectable even if their profile is not FACULTY).
    """
    owner_ids = Course.objects.values_list('professor_id', flat=True).distinct()
    return (
        User.objects.filter(Q(pk__in=owner_ids) | Q(profile__role='FACULTY') | Q(is_staff=True))
        .select_related('profile')
        .distinct()
        .order_by('username')
    )


def handle_courses_console_post(request) -> Optional[HttpResponseRedirect]:
    """
    Process POST from courses console. Returns HttpResponseRedirect if handled, else None.
    """
    if request.method != 'POST' or request.POST.get('action') != 'update_course':
        return None

    if not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('admin:console_courses')

    course_id = request.POST.get('course_id')
    term = (request.POST.get('term') or '').strip()
    professor_id = request.POST.get('professor_id')
    archive_raw = request.POST.get('archive_state', 'active')

    try:
        course = Course.objects.select_related('professor').get(pk=course_id)
    except (Course.DoesNotExist, TypeError, ValueError):
        messages.error(request, 'Course not found.')
        return redirect('admin:console_courses')

    if not term:
        messages.error(request, 'Term cannot be empty.')
        return redirect('admin:console_courses')

    if len(term) > 50:
        term = term[:50]

    try:
        pid = int(professor_id)
    except (TypeError, ValueError):
        messages.error(request, 'Invalid faculty selection.')
        return redirect('admin:console_courses')

    new_professor = faculty_assignable_queryset().filter(pk=pid).first()
    if not new_professor:
        messages.error(request, 'Selected user cannot be assigned as course owner.')
        return redirect('admin:console_courses')

    is_archived = archive_raw == 'archived'

    with transaction.atomic():
        course.term = term
        course.professor = new_professor
        course.is_archived = is_archived
        course.save(update_fields=['term', 'professor', 'is_archived'])

    state = 'archived' if is_archived else 'active'
    messages.success(
        request,
        f'Updated "{course.code_title_label()}": term, faculty, and {state} state saved.',
    )
    return redirect('admin:console_courses')
