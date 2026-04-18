"""
Portal role assignment for the admin console (UserProfile + Django staff flags).
Effective routing uses middleware: staff/superuser → ADMIN; else UserProfile.role (FACULTY/STUDENT).
"""
from __future__ import annotations

from typing import Literal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import transaction

from professor.models import UserProfile

from admin_dashboard.audit import log_audit

UserModel = get_user_model()

PortalRole = Literal['student', 'instructor', 'admin']

PORTAL_ROLE_CHOICES: tuple[tuple[str, str], ...] = (
    ('student', 'Student'),
    ('instructor', 'Instructor'),
    ('admin', 'Admin'),
)


def effective_portal_role(user: User) -> PortalRole | None:
    """Map Django user to console role (None = no profile and not staff — treat as unassigned)."""
    if user.is_superuser or user.is_staff:
        return 'admin'
    try:
        r = user.profile.role
    except UserProfile.DoesNotExist:
        return None
    if r == 'FACULTY':
        return 'instructor'
    if r == 'STUDENT':
        return 'student'
    return 'student'


def _other_staff_count(exclude_pk: int) -> int:
    return UserModel.objects.filter(is_staff=True).exclude(pk=exclude_pk).count()


def _other_superuser_count(exclude_pk: int) -> int:
    return UserModel.objects.filter(is_superuser=True).exclude(pk=exclude_pk).count()


def apply_portal_role(
    *,
    target: User,
    portal_role: PortalRole,
    actor: User,
) -> tuple[bool, str]:
    """
    Apply role change. Returns (ok, message).
    Does not grant is_superuser (use createsuperuser / Django admin user form).
    """
    if not actor.is_staff:
        return False, 'You do not have permission to change roles.'

    if target.is_superuser and not actor.is_superuser:
        return False, 'Only a superuser can modify superuser accounts.'

    if portal_role not in ('student', 'instructor', 'admin'):
        return False, 'Invalid role.'

    if portal_role in ('student', 'instructor'):
        if target.is_staff and _other_staff_count(target.pk) < 1:
            return False, 'Cannot remove the last staff (admin) account.'
        if target.is_superuser:
            if not actor.is_superuser:
                return False, 'Only a superuser can remove superuser privileges.'
            if _other_superuser_count(target.pk) < 1:
                return False, 'Cannot remove the last superuser.'

    with transaction.atomic():
        if portal_role == 'admin':
            target.is_staff = True
            target.save(update_fields=['is_staff'])
            UserProfile.objects.get_or_create(user=target, defaults={'role': 'FACULTY'})
            return True, f'Updated {target.username}: Admin (staff portal access).'

        target.is_staff = False
        if target.is_superuser:
            target.is_superuser = False
        profile, _ = UserProfile.objects.get_or_create(user=target, defaults={'role': 'STUDENT'})
        if portal_role == 'instructor':
            profile.role = 'FACULTY'
            profile.save(update_fields=['role'])
            target.save(update_fields=['is_staff', 'is_superuser'])
            return True, f'Updated {target.username}: Instructor (faculty dashboard).'
        profile.role = 'STUDENT'
        profile.save(update_fields=['role'])
        target.save(update_fields=['is_staff', 'is_superuser'])
        return True, f'Updated {target.username}: Student (student dashboard).'


def build_role_rows(users_qs, actor: User) -> list[dict]:
    """Prepare template rows with edit permissions."""
    rows = []
    for u in users_qs.order_by('username'):
        eff = effective_portal_role(u)
        profile_role = None
        try:
            profile_role = u.profile.role
        except UserProfile.DoesNotExist:
            pass

        can_edit = True
        if u.is_superuser and not actor.is_superuser:
            can_edit = False

        rows.append(
            {
                'user': u,
                'username': u.username,
                'email': u.email or '—',
                'full_name': (u.get_full_name() or '').strip() or '—',
                'effective': eff,
                'effective_label': _label(eff, u),
                'form_role': eff if eff is not None else 'student',
                'profile_role': profile_role,
                'is_superuser': u.is_superuser,
                'is_staff_only': u.is_staff and not u.is_superuser,
                'can_edit': can_edit,
            }
        )
    return rows


def _label(eff: PortalRole | None, u: User) -> str:
    if u.is_superuser:
        return 'Admin (superuser)'
    if eff == 'admin':
        return 'Admin (staff)'
    if eff == 'instructor':
        return 'Instructor'
    if eff == 'student':
        return 'Student'
    return 'Unassigned'


def handle_role_post(request, actor: User) -> bool:
    """Process POST from roles console. Returns True if handled (redirect recommended)."""
    if request.method != 'POST' or request.POST.get('action') != 'set_portal_role':
        return False

    uid = request.POST.get('user_id')
    portal_role = request.POST.get('portal_role')
    try:
        target = UserModel.objects.get(pk=uid)
    except (UserModel.DoesNotExist, TypeError, ValueError):
        messages.error(request, 'User not found.')
        return True

    if portal_role not in ('student', 'instructor', 'admin'):
        messages.error(request, 'Invalid role selection.')
        return True

    ok, msg = apply_portal_role(target=target, portal_role=portal_role, actor=actor)
    if ok:
        log_audit(
            "portal_role_set",
            actor=actor,
            object_repr=target.username,
            detail=f"portal_role={portal_role}",
        )
        messages.success(request, msg)
    else:
        messages.error(request, msg)
    return True
