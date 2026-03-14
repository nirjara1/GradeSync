"""
GradeSync permission utilities
================================
Centralised RBAC helpers that encode the four-role permission matrix:

  Role               | System-level role |  Course-level role (CourseMember)
  -------------------|-------------------|----------------------------------
  Admin              | is_superuser      |  —  (can do everything)
  Professor/Faculty  | FACULTY           |  INSTRUCTOR (course.professor == user)
  Grading Assistant  | GRADING_ASSISTANT |  GRADING_ASSISTANT in CourseMember
  Student            | STUDENT           |  STUDENT in CourseMember

Permission matrix
-----------------
  Action                           | Admin | Professor | GA (assigned) | Student
  ---------------------------------|-------|-----------|---------------|--------
  Create course                    |  ✓    |    ✓      |      ✗        |   ✗
  Create / edit / delete assignment|  ✓    |    ✓      |      ✗        |   ✗
  Invite students / assign GAs     |  ✓    |    ✓      |      ✗        |   ✗
  Grade assignments                |  ✓    |    ✓      |      ✓        |   ✗
  Run code against test data       |  ✓    |    ✓      |      ✓        |   ✓ (own submission + public tests)
  Submit assignments               |  ✗    |    ✗      |      ✓*       |   ✓
  View all class grades            |  ✓    |    ✓      |      ✓        |   ✗
  View own grades                  |  ✓    |    —      |      ✓*       |   ✓

  * GAs are Students by default; their GRADING_ASSISTANT role is per-course.
"""

from .models import CourseMember, Course, UserProfile


# ---------------------------------------------------------------------------
# Low-level course-role resolver (unchanged — existing callers depend on this)
# ---------------------------------------------------------------------------

def get_user_course_role(user, course, request=None):
    """
    Returns the COURSE-LEVEL role of *user* for *course*.
    Returns one of: 'INSTRUCTOR', 'GRADING_ASSISTANT', 'STUDENT', or None.

    If *request* is provided, the active session dashboard role is respected
    (lets a GA act as a plain student in their own student view).
    """
    if request:
        active_role = request.session.get('active_role')
        if active_role in ('GRADING_ASSISTANT', 'STUDENT'):
            try:
                member = CourseMember.objects.get(course=course, user=user)
                if member.role_in_course == active_role:
                    return active_role
            except CourseMember.DoesNotExist:
                pass

    if course.professor == user:
        return 'INSTRUCTOR'

    try:
        member = CourseMember.objects.get(course=course, user=user)
        return member.role_in_course
    except CourseMember.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Convenience wrappers used widely across views (unchanged signatures)
# ---------------------------------------------------------------------------

def has_course_access(user, course, request=None):
    """True if the user can manage/view the course at an elevated level (not student)."""
    role = get_user_course_role(user, course, request)
    return role in ('INSTRUCTOR', 'GRADING_ASSISTANT')


def is_enrolled(user, course, request=None):
    """True if the user has ANY relationship with the course."""
    role = get_user_course_role(user, course, request)
    return role in ('INSTRUCTOR', 'GRADING_ASSISTANT', 'STUDENT')


def is_course_instructor(user, course, request=None):
    """True only for the course professor."""
    return get_user_course_role(user, course, request) == 'INSTRUCTOR'


# ---------------------------------------------------------------------------
# New permission helpers — spec-aligned
# ---------------------------------------------------------------------------

def _system_role(user):
    """Returns the system-wide UserProfile role, or 'ADMIN' for superusers."""
    if user.is_superuser or user.is_staff:
        return 'ADMIN'
    try:
        return user.profile.role      # uses the OneToOneField related_name='profile'
    except UserProfile.DoesNotExist:
        return None


def can_create_course(user):
    """
    Only professors (FACULTY) and admins may create courses.
    """
    role = _system_role(user)
    return role in ('ADMIN', 'FACULTY')


def can_create_assignment(user, course, request=None):
    """
    Only the course instructor (professor) or admin may create/edit/delete
    assignments. GAs cannot create assignments.
    """
    if user.is_superuser:
        return True
    return get_user_course_role(user, course, request) == 'INSTRUCTOR'


def can_invite_members(user, course, request=None):
    """
    Only the course instructor (professor) or admin may invite students /
    assign grading assistants.
    """
    if user.is_superuser:
        return True
    return get_user_course_role(user, course, request) == 'INSTRUCTOR'


def can_grade(user, course, request=None):
    """
    Professors and GAs *assigned to this specific course* may grade.
    Students cannot grade.

    This is the key per-course check for GAs: a user with the system-level
    GRADING_ASSISTANT role only gains grading access for courses where they
    appear as GRADING_ASSISTANT in CourseMember — not all courses.
    """
    if user.is_superuser:
        return True
    role = get_user_course_role(user, course, request)
    return role in ('INSTRUCTOR', 'GRADING_ASSISTANT')


def can_view_all_grades(user, course, request=None):
    """
    Professors and GAs assigned to the course may see the full grade book.
    Students may only see their own grade (handled in the view layer).
    """
    return can_grade(user, course, request)


def can_run_code(user, course, request=None):
    """
    Everyone enrolled in the course can run code.
      - Professor / GA: can run student submissions against private test data.
      - Student: can run their own code against public test data only.
        (The view layer enforces *which* test data; this just gates entry.)
    """
    if user.is_superuser:
        return True
    return get_user_course_role(user, course, request) is not None


def can_submit_assignment(user, course, request=None):
    """
    Students and GAs (who are also students in their non-GA courses) can
    submit assignments.  Professors do not submit.
    """
    if user.is_superuser:
        return False   # Admins don't submit student work
    role = get_user_course_role(user, course, request)
    return role in ('STUDENT', 'GRADING_ASSISTANT')

