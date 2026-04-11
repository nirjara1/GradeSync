"""
Admin provisioning: create student accounts with CWID and send welcome / password-setup email.
"""
from __future__ import annotations

import logging
import random

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from professor.models import UserProfile

from .models import Student, StudentOnboarding

logger = logging.getLogger(__name__)


def generate_unique_cwid() -> str:
    for _ in range(100):
        candidate = f'{random.randint(0, 99_999_999):08d}'
        if not Student.objects.filter(cwid=candidate).exists():
            return candidate
    raise RuntimeError('Could not allocate a unique CWID after many attempts.')


def normalize_cwid(manual: str | None) -> str:
    if not manual or not str(manual).strip():
        return generate_unique_cwid()
    s = str(manual).strip()
    if not s.isdigit() or len(s) != 8:
        raise ValueError('CWID must be exactly 8 digits.')
    if Student.objects.filter(cwid=s).exists():
        raise ValueError('That CWID is already in use.')
    return s


def build_password_set_url(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    return f'{base}/accounts/reset/{uid}/{token}/'


def send_student_welcome_email(*, to_email: str, full_name: str, cwid: str, setup_url: str) -> None:
    subject = 'Welcome to GradeSync — your CWID and password setup'
    body = (
        f'Hello {full_name},\n\n'
        f'Welcome to GradeSync. Your Campus-Wide ID (CWID) is: {cwid}\n\n'
        f'Your login username is this email address: {to_email}\n\n'
        f'Set your password using this one-time link (if it expires, ask your administrator to resend '
        f'the welcome email):\n{setup_url}\n\n'
        f'If you did not expect this message, contact your school administrator.\n'
    )
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        fail_silently=False,
    )


def run_welcome_email(*, user_id: int, onboarding_id: int, full_name: str, cwid: str, email: str) -> tuple[bool, str | None]:
    try:
        user = User.objects.get(pk=user_id)
        onboarding = StudentOnboarding.objects.get(pk=onboarding_id)
        url = build_password_set_url(user)
        send_student_welcome_email(
            to_email=email,
            full_name=full_name,
            cwid=cwid,
            setup_url=url,
        )
        onboarding.welcome_email_sent_at = timezone.now()
        onboarding.welcome_email_last_error = ''
        onboarding.save(update_fields=['welcome_email_sent_at', 'welcome_email_last_error'])
        return True, None
    except Exception as exc:
        logger.exception('Welcome email failed for user_id=%s', user_id)
        try:
            onboarding = StudentOnboarding.objects.get(pk=onboarding_id)
            onboarding.welcome_email_last_error = str(exc)[:2000]
            onboarding.save(update_fields=['welcome_email_last_error'])
        except StudentOnboarding.DoesNotExist:
            pass
        return False, str(exc)


def create_student_account(*, full_name: str, email: str, manual_cwid: str | None) -> dict:
    """
    Create User (student) + profile + Student + StudentOnboarding, then send welcome email.
    Returns dict: ok, error, user_id, student_id, cwid, email_sent, email_error
    """
    email_n = (email or '').strip().lower()
    full_name = (full_name or '').strip()
    if not email_n or not full_name:
        return {'ok': False, 'error': 'Full name and email are required.'}
    if User.objects.filter(username=email_n).exists():
        return {'ok': False, 'error': 'A user with this email already exists.'}

    try:
        cwid = normalize_cwid(manual_cwid)
    except ValueError as e:
        return {'ok': False, 'error': str(e)}

    parts = full_name.split(None, 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ''

    try:
        with transaction.atomic():
            user = User.objects.create(username=email_n, email=email_n, first_name=first, last_name=last)
            user.set_unusable_password()
            user.save()
            UserProfile.objects.create(user=user, role='STUDENT')
            student = Student.objects.create(user=user, cwid=cwid)
            onboarding = StudentOnboarding.objects.create(student=student)
    except IntegrityError:
        return {'ok': False, 'error': 'Could not create account (database conflict).'}

    email_sent, email_err = run_welcome_email(
        user_id=user.pk,
        onboarding_id=onboarding.pk,
        full_name=full_name,
        cwid=cwid,
        email=email_n,
    )

    return {
        'ok': True,
        'error': None,
        'user_id': user.pk,
        'student_id': student.pk,
        'cwid': cwid,
        'email_sent': email_sent,
        'email_error': email_err,
    }


def resend_welcome_email(*, student_id: int) -> dict:
    try:
        student = Student.objects.select_related('user').get(pk=student_id)
    except Student.DoesNotExist:
        return {'ok': False, 'error': 'Student not found.'}
    if not student.cwid:
        return {'ok': False, 'error': 'Assign a CWID before sending a welcome email.'}
    user = student.user
    full_name = (user.get_full_name() or '').strip() or user.username
    email_n = (user.email or user.username or '').strip().lower()
    if not email_n:
        return {'ok': False, 'error': 'Student has no email address.'}

    onboarding, _ = StudentOnboarding.objects.get_or_create(student=student)
    email_sent, email_err = run_welcome_email(
        user_id=user.pk,
        onboarding_id=onboarding.pk,
        full_name=full_name,
        cwid=student.cwid,
        email=email_n,
    )
    return {'ok': True, 'error': None, 'email_sent': email_sent, 'email_error': email_err}
