import json
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from professor.models import CourseMember

from .models import (
    Assignment,
    AssignmentGroup,
    AssignmentGroupMember,
    CourseGroupSet,
    Student,
    Submission,
)


@dataclass
class AssignmentGroupResolution:
    student_group: AssignmentGroup | None
    submission: Submission | None


def resolve_assignment_group_for_student(assignment: Assignment, student: Student) -> AssignmentGroup | None:
    return (
        AssignmentGroup.objects.filter(assignment=assignment, members__student=student)
        .distinct()
        .first()
    )


def get_effective_submission_for_student(assignment: Assignment, student: Student) -> Submission | None:
    if assignment.is_group_assignment:
        group = resolve_assignment_group_for_student(assignment, student)
        if not group:
            return None
        return Submission.objects.filter(assignment=assignment, group=group).order_by('-submission_time', '-id').first()
    # In individual mode, only consider individual submissions (group is null).
    return (
        Submission.objects.filter(assignment=assignment, student=student, group__isnull=True)
        .order_by('-submission_time', '-id')
        .first()
    )


def can_view_submission(user, submission: Submission) -> bool:
    if submission.assignment.course.members.filter(user=user, role_in_course__in=['INSTRUCTOR', 'GRADING_ASSISTANT']).exists():
        return True
    if submission.student_id and submission.student.user_id == user.id:
        return True
    if submission.group_id and submission.group.members.filter(student__user=user).exists():
        return True
    return False


def can_submit_for_group(user, assignment: Assignment, group: AssignmentGroup | None) -> bool:
    if not assignment.is_group_assignment or not group:
        return False
    return group.members.filter(student__user=user).exists()


def parse_groups_payload(raw_groups_data: str):
    if not raw_groups_data:
        return []
    groups_list = json.loads(raw_groups_data)
    if not isinstance(groups_list, list):
        raise ValidationError("Invalid groups payload.")
    return groups_list


def _validate_students_in_course(course, member_student_ids):
    roster_user_ids = set(
        CourseMember.objects.filter(course=course, role_in_course='STUDENT')
        .values_list('user_id', flat=True)
    )
    valid_student_ids = set(
        Student.objects.filter(id__in=member_student_ids, user_id__in=roster_user_ids).values_list('id', flat=True)
    )
    if valid_student_ids != set(member_student_ids):
        raise ValidationError("One or more selected students are not in this course roster.")


def _groups_from_course_set(course_group_set: CourseGroupSet):
    groups = []
    for group in course_group_set.groups.prefetch_related('members').all():
        groups.append({
            "name": group.name or "Group",
            "members": [member.student_id for member in group.members.all()],
        })
    return groups


@transaction.atomic
def apply_assignment_groups(
    assignment: Assignment,
    groups_data_raw: str | None,
    max_group_size: int,
    course_group_set_id: int | None = None,
):
    source_groups = []
    if course_group_set_id:
        cgs = CourseGroupSet.objects.select_related('course').prefetch_related('groups__members').get(
            id=course_group_set_id,
            course=assignment.course,
        )
        source_groups = _groups_from_course_set(cgs)
    elif groups_data_raw:
        source_groups = parse_groups_payload(groups_data_raw)

    assignment.assignment_groups.all().delete()
    if not source_groups:
        return

    assigned_students = set()
    for g_data in source_groups:
        member_ids = [int(sid) for sid in (g_data.get('members') or [])]
        if not member_ids:
            continue
        if len(member_ids) > max_group_size:
            raise ValidationError(f"Group '{g_data.get('name', 'Unnamed Group')}' exceeds max group size.")
        overlap = assigned_students.intersection(member_ids)
        if overlap:
            raise ValidationError("Each student can only belong to one group per assignment.")
        _validate_students_in_course(assignment.course, member_ids)

        group = AssignmentGroup.objects.create(
            assignment=assignment,
            name=(g_data.get('name') or 'Unnamed Group').strip() or 'Unnamed Group',
        )
        members = [AssignmentGroupMember(group=group, student_id=sid) for sid in member_ids]
        AssignmentGroupMember.objects.bulk_create(members)
        assigned_students.update(member_ids)
