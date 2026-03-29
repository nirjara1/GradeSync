from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from professor.models import Course, CourseMember

from .group_services import apply_assignment_groups, get_effective_submission_for_student
from .models import Assignment, AssignmentGroup, Grade, Student, Submission


class GroupSubmissionWorkflowTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(username='faculty', password='pw')
        self.student1_user = User.objects.create_user(username='s1', password='pw')
        self.student2_user = User.objects.create_user(username='s2', password='pw')

        self.course = Course.objects.create(
            code='CS101',
            section='01',
            title='Intro',
            term='Fall',
            professor=self.instructor,
        )
        CourseMember.objects.create(course=self.course, user=self.student1_user, role_in_course='STUDENT')
        CourseMember.objects.create(course=self.course, user=self.student2_user, role_in_course='STUDENT')

        self.student1 = Student.objects.create(user=self.student1_user)
        self.student2 = Student.objects.create(user=self.student2_user)

    def test_group_submission_lock_enforced(self):
        assignment = Assignment.objects.create(
            name='Group A1',
            course=self.course,
            points=100,
            is_group_assignment=True,
            max_group_size=3,
        )
        apply_assignment_groups(
            assignment=assignment,
            groups_data_raw='[{"name":"G1","members":[%s,%s]}]' % (self.student1.id, self.student2.id),
            max_group_size=3,
        )
        group = AssignmentGroup.objects.get(assignment=assignment)

        Submission.objects.create(assignment=assignment, group=group, student=self.student1, file_path='submissions/a.zip')
        with self.assertRaises(Exception):
            Submission.objects.create(assignment=assignment, group=group, student=self.student2, file_path='submissions/b.zip')

    def test_effective_submission_resolves_for_all_group_members(self):
        assignment = Assignment.objects.create(
            name='Group A2',
            course=self.course,
            points=100,
            is_group_assignment=True,
            max_group_size=3,
        )
        apply_assignment_groups(
            assignment=assignment,
            groups_data_raw='[{"name":"G1","members":[%s,%s]}]' % (self.student1.id, self.student2.id),
            max_group_size=3,
        )
        group = AssignmentGroup.objects.get(assignment=assignment)
        sub = Submission.objects.create(assignment=assignment, group=group, student=self.student1, file_path='submissions/a.zip')
        Grade.objects.create(submission=sub, score=88, feedback='Good work')

        sub_for_member1 = get_effective_submission_for_student(assignment, self.student1)
        sub_for_member2 = get_effective_submission_for_student(assignment, self.student2)
        self.assertEqual(sub_for_member1.id, sub.id)
        self.assertEqual(sub_for_member2.id, sub.id)

    def test_apply_assignment_groups_rejects_non_roster_student(self):
        outsider_user = User.objects.create_user(username='outsider', password='pw')
        outsider_student = Student.objects.create(user=outsider_user)
        assignment = Assignment.objects.create(
            name='Group A3',
            course=self.course,
            points=100,
            is_group_assignment=True,
            max_group_size=3,
        )
        with self.assertRaises(ValidationError):
            apply_assignment_groups(
                assignment=assignment,
                groups_data_raw='[{"name":"G1","members":[%s]}]' % outsider_student.id,
                max_group_size=3,
            )
