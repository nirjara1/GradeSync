from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages
from django.db.models import Max, Q, Count, Avg
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .models import Assignment, Submission, Grade, Student, Rubric, RubricCriterion, CriterionGrade, TestCase, RuleSet, TestResult, AssignmentGroup, AssignmentGroupMember, CourseGroupSet, CourseGroup, CourseGroupMember
from .forms import AssignmentForm, SubmissionForm, TestCaseUploadForm, TestCaseForm, RuleSetForm
from .services import grade_submission, extract_code_from_file, run_submission_analysis
from .group_services import (
    apply_assignment_groups,
    can_submit_for_group,
    can_view_submission,
    get_effective_submission_for_student,
    resolve_assignment_group_for_student,
)
from .sandbox import execute_code
from .tasks import bulk_grade_assignment
from professor.models import Course, UserProfile, CourseMember
from professor.utils import is_course_instructor, has_course_access, is_enrolled, get_user_course_role

from django.contrib.auth.decorators import login_required
import logging
import json
import csv
import openpyxl
from io import TextIOWrapper
from typing import Optional
from django.utils import timezone
import re
import zipfile
import os
from decimal import Decimal, InvalidOperation

from .rubric_scoring import (
    criterion_weighted_contribution,
    final_score_unweighted_rubric,
    final_score_weighted_rubric,
    sum_unweighted_allocations,
    sum_weights_for_rubric,
    validate_unweighted_rubric_rows,
    validate_weighted_rubric_rows,
)

logger = logging.getLogger(__name__)

def get_user_from_request(request):
    return request.user


def _coerce_bool(val, default=False):
    """Normalize JSON/form booleans; avoids Python truthiness bugs on strings like 'false'."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val) and val != 0
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return default


def _save_rubric_from_create_post(request, assignment):
    """Optional rubric + criteria from the create-assignment form (same POST as assignment)."""
    raw = (request.POST.get("rubric_criteria_json") or "").strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, list):
        return
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        rows.append(item)
    if not rows:
        return
    is_weighted = request.POST.get("rubric_is_weighted") == "on"
    ap = int(assignment.points) if assignment.points is not None else 0
    if is_weighted:
        err = validate_weighted_rubric_rows(rows)
        if err:
            raise ValueError(err)
    else:
        err = validate_unweighted_rubric_rows(rows, ap)
        if err:
            raise ValueError(err)

    rubric = Rubric.objects.create(assignment=assignment, is_weighted=is_weighted)
    for order, item in enumerate(rows, start=1):
        name = (item.get("name") or "").strip()
        mp = float(item.get("max_points") or 0)
        if is_weighted:
            w = float(item.get("weight") or 0)
            RubricCriterion.objects.create(
                rubric=rubric,
                name=name,
                order=order,
                max_points=mp,
                weight=w,
            )
        else:
            RubricCriterion.objects.create(
                rubric=rubric,
                name=name,
                order=order,
                max_points=mp,
                weight=None,
            )


@login_required
def assignments_dashboard(request):
    """Shows all assignments for all courses the user is enrolled or teaching in."""
    user = get_user_from_request(request)
    role = request.session.get('active_role') or getattr(request, 'user_role', None)
    
    if role in ['FACULTY', 'INSTRUCTOR']:
        base_template = 'base_professor.html'
        assignments = Assignment.objects.filter(course__professor=user).order_by('due_date')
        return render(request, 'assignments_dashboard.html', {
            'assignments': assignments, 'is_instructor': True, 'is_student': False, 'base_template': base_template
        })
    elif role == 'STUDENT':
        base_template = 'portal/base_portal.html'
        courses = Course.objects.filter(members__user=user, members__role_in_course='STUDENT')

        # Student assignments tab should only show assignments that are still due
        # AND have not been submitted yet by this student.
        student_profile, _ = Student.objects.get_or_create(user=user)
        
        # Determine submitted assignments (considering both individual and group submissions)
        submitted_individual = Submission.objects.filter(student=student_profile).values_list('assignment_id', flat=True)
        submitted_group = Submission.objects.filter(group__members__student=student_profile).values_list('assignment_id', flat=True)
        submitted_assignment_ids = set(list(submitted_individual) + list(submitted_group))

        now = timezone.now()
        assignments = (
            Assignment.objects.filter(course__in=courses)
            .filter(Q(is_group_assignment=False) | Q(assignment_groups__members__student=student_profile))
            .exclude(id__in=submitted_assignment_ids)
            .filter(Q(no_due_date=True) | Q(due_date__isnull=True) | Q(due_date__gte=now))
            .distinct()
            .order_by('due_date', 'id')
        )
        return render(request, 'assignments_dashboard.html', {
            'assignments': assignments, 'is_instructor': False, 'is_student': True, 'base_template': base_template
        })
    elif role == 'GRADING_ASSISTANT':
        base_template = 'base_grading_assistant.html'
        courses = Course.objects.filter(members__user=user, members__role_in_course='GRADING_ASSISTANT')
        assignments = Assignment.objects.filter(course__in=courses).order_by('due_date')
        return render(request, 'assignments_dashboard.html', {
            'assignments': assignments, 'is_instructor': False, 'is_student': False, 'base_template': base_template
        })
    else:
        return HttpResponseForbidden("No role found.")

@login_required
def professor_course_view(request, course_id):
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    course_role = get_user_course_role(user, course, request)
    
    logger.info(f"[Course View Navigation] Route: PROFESSOR_COURSE | Relational Role: {course_role} | Target Class: {course_id}")
    if course_role != 'INSTRUCTOR':
        return HttpResponseForbidden("Access Denied")
        
    assignments = Assignment.objects.filter(course=course).order_by('due_date')
    # Use the first assignment as the default gradebook target for the sidebar
    default_gradebook_assignment = assignments.first()
    return render(request, 'assignments_dashboard.html', {
        'assignments': assignments, 'course': course,
        'is_instructor': True, 'is_student': False, 'base_template': 'base_professor.html',
        'gradebook_assignment': default_gradebook_assignment, 'active_tab': 'assignments'
    })

@login_required
def course_students_view(request, course_id):
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    course_role = get_user_course_role(user, course, request)
    
    if course_role not in ['INSTRUCTOR', 'GRADING_ASSISTANT']:
        return HttpResponseForbidden("Access Denied")
        
    assignments = Assignment.objects.filter(course=course).order_by('due_date')
    default_gradebook_assignment = assignments.first()
    
    # We pass the same base_template logic as in course_view
    base_template = 'base_professor.html' if course_role == 'INSTRUCTOR' else 'base_grading_assistant.html'
    
    return render(request, 'course_students.html', {
        'course': course,
        'is_instructor': course_role == 'INSTRUCTOR',
        'is_student': False,
        'base_template': base_template,
        'gradebook_assignment': default_gradebook_assignment,
        'active_tab': 'students'
    })

@login_required
def ga_course_view(request, course_id):
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    course_role = get_user_course_role(user, course, request)
    
    logger.info(f"[Course View Navigation] Route: GA_COURSE | Relational Role: {course_role} | Target Class: {course_id}")
    if course_role != 'GRADING_ASSISTANT':
        return HttpResponseForbidden("Access Denied")
        
    assignments = Assignment.objects.filter(course=course).order_by('due_date')
    return render(request, 'assignments_dashboard.html', {
        'assignments': assignments, 'course': course,
        'is_instructor': False, 'is_student': False, 'base_template': 'base_grading_assistant.html'
    })

@login_required
def student_course_view(request, course_id):
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    course_role = get_user_course_role(user, course, request)
    
    logger.info(f"[Course View Navigation] Route: STUDENT_COURSE | Relational Role: {course_role} | Target Class: {course_id}")
    if course_role != 'STUDENT':
        return HttpResponseForbidden("Access Denied")
        
    # Only show assignments that are either individual or where the student is a member of a group
    student_profile, _ = Student.objects.get_or_create(user=user)
    assignments = list(
        Assignment.objects.filter(course=course)
        .filter(Q(is_group_assignment=False) | Q(assignment_groups__members__student=student_profile))
        .distinct()
        .order_by('due_date', 'id')
    )
    
    submission_dict = {}
    for a in assignments:
        submission_dict[a.id] = get_effective_submission_for_student(a, student_profile)
    now = timezone.now()

    for assignment in assignments:
        assignment.student_feedback = ''
        submission = submission_dict.get(assignment.id)
        if submission:
            g = getattr(submission, 'grade', None)
            if g:
                assignment.student_status = 'GRADED'
                assignment.student_grade = g.score
                assignment.student_feedback = (g.feedback or '').strip()
            else:
                assignment.student_status = 'SUBMITTED'
                assignment.student_grade = None
        else:
            assignment.student_grade = None
            if not assignment.no_due_date and assignment.due_date and assignment.due_date < now:
                assignment.student_status = 'MISSING'
            else:
                assignment.student_status = 'UPCOMING'

    return render(request, 'assignments_dashboard.html', {
        'assignments': assignments, 'course': course,
        'is_instructor': False, 'is_student': True, 'base_template': 'portal/base_portal.html'
    })

@login_required
def create_assignment(request, course_id=None):
    """Dedicated view for creating an assignment."""
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id) if course_id else None
    
    # Define role and template early for use in all code paths
    course_role = get_user_course_role(user, course, request) if course else ('INSTRUCTOR' if getattr(user, 'role', None) == 'FACULTY' else 'GRADING_ASSISTANT')
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    
    # Only instructors can create assignments
    if course and not is_course_instructor(user, course, request):
        return HttpResponseForbidden("Only instructors can create assignments.")
        
    if not course:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.role != 'FACULTY' and user.username != 'poudelb2':
            return HttpResponseForbidden("You do not have permission to create assignments.")

    course_students = []
    course_group_sets = []
    if course:
        course_students = CourseMember.objects.filter(course=course, role_in_course='STUDENT').select_related('user')
        for member in course_students:
            student_profile, _ = Student.objects.get_or_create(user=member.user)
            member.student_id = student_profile.id
        course_group_sets = CourseGroupSet.objects.filter(course=course).order_by('-created_at')

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save(commit=False)
                    if course:
                        assignment.course = course
                        
                    # Determine status based on which button was clicked
                    action = request.POST.get('action')
                    if action == 'draft':
                        assignment.status = 'draft'
                    else:
                        assignment.status = 'published'
                        
                    assignment.save()
                    
                    assignment_type = request.POST.get('assignment_type')
                    assignment.is_group_assignment = assignment_type == 'group'
                    assignment.save(update_fields=['is_group_assignment'])
                    if assignment.is_group_assignment:
                        group_source_mode = request.POST.get('group_source_mode')
                        selected_group_set_id = request.POST.get('course_group_set_id')
                        if group_source_mode == 'course_set' and selected_group_set_id:
                            apply_assignment_groups(
                                assignment=assignment,
                                groups_data_raw=None,
                                max_group_size=assignment.max_group_size,
                                course_group_set_id=int(selected_group_set_id),
                            )
                        else:
                            apply_assignment_groups(
                                assignment=assignment,
                                groups_data_raw=request.POST.get('groups_data'),
                                max_group_size=assignment.max_group_size,
                                course_group_set_id=None,
                            )
                        save_set_name = (request.POST.get('save_as_course_group_set_name') or '').strip()
                        if save_set_name:
                            course_set = CourseGroupSet.objects.create(
                                course=assignment.course,
                                name=save_set_name,
                                created_by=user,
                            )
                            for grp in assignment.assignment_groups.prefetch_related('members').all():
                                cg = CourseGroup.objects.create(group_set=course_set, name=grp.name)
                                CourseGroupMember.objects.bulk_create([
                                    CourseGroupMember(group=cg, student_id=gm.student_id) for gm in grp.members.all()
                                ])
                    
                    
                    # Process test cases from CSV (if provided)
                    test_cases_json = request.POST.get('test_cases_json', '')
                    if test_cases_json:
                        import json
                        test_cases_data = json.loads(test_cases_json)
                        seen_tcs = set()
                        order_idx = 1
                        for tc_data in test_cases_data:
                            key = (
                                tc_data.get('input_data', '').strip(),
                                tc_data.get('expected_output', '').strip(),
                                _coerce_bool(tc_data.get('is_private'), False)
                            )
                            if key in seen_tcs:
                                continue
                            seen_tcs.add(key)
                            
                            TestCase.objects.create(
                                assignment=assignment,
                                name=f"Test Case {order_idx}",
                                input_data=tc_data.get('input_data', ''),
                                expected_output=tc_data.get('expected_output', ''),
                                is_private=key[2],
                                points_awarded=tc_data.get('points', 5),
                                order=order_idx
                            )
                            order_idx += 1
                        logger.info(f"Created {order_idx - 1} test cases for assignment {assignment.id}")

                    _save_rubric_from_create_post(request, assignment)

                    # Success message removed as per user request
            except Exception as e:
                logger.error(f"Error creating assignment: {e}")
                messages.error(request, f"An error occurred while creating the assignment: {str(e)}")
                return render(request, 'create_assignment.html', {
                    'form': form,
                    'course': course,
                    'base_template': base_template,
                    'course_students': course_students,
                    'course_group_sets': course_group_sets,
                })
                
            if course:
                course_role = get_user_course_role(user, course, request)
                route_name = 'professor_course' if course_role == 'INSTRUCTOR' else ('student_course' if course_role == 'STUDENT' else 'ga_course')
                return redirect(route_name, course_id=course.id)
            return redirect('assignments_dashboard')
        else:
            messages.error(request, "Error creating assignment. Please check the form data.")
    else:
        initial_data = {}
        if course:
            initial_data['course'] = course
        form = AssignmentForm(initial=initial_data)

    context = {
        'form': form,
        'course': course,
        'base_template': base_template,
        'course_students': course_students,
        'course_group_sets': course_group_sets,
    }
    return render(request, 'create_assignment.html', context)


@login_required
def rubric_view(request):
    """Legacy/info page when visiting rubric URL without an assignment context."""
    user = get_user_from_request(request)
    role = request.session.get('active_role') or getattr(request, 'user_role', None)
    if role == 'INSTRUCTOR' or (role in ['FACULTY', 'PROFESSOR']):
        base_template = 'base_professor.html'
    elif role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    context = {'base_template': base_template}
    return render(request, 'rubric_no_assignment.html', context)


@login_required
def assignment_rubric_view(request, assignment_id):
    """Add/edit rubric and criteria for an assignment (weighted or unweighted)."""
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    if not is_course_instructor(user, assignment.course, request):
        return HttpResponseForbidden("Only instructors can edit this rubric.")

    rubric, _ = Rubric.objects.get_or_create(assignment=assignment, defaults={'is_weighted': False})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle_weighted':
            rubric.is_weighted = request.POST.get('is_weighted') == 'on'
            rubric.save()
            messages.success(request, "Rubric type updated.")
        elif action == 'add_criterion':
            name = request.POST.get('criterion_name', '').strip()
            if name:
                try:
                    mp = float(request.POST.get('criterion_max_points') or 0)
                except ValueError:
                    mp = 0
                if mp <= 0:
                    messages.error(request, "Max points must be greater than 0.")
                    return redirect('assignment_rubric', assignment_id=assignment.id)
                max_order = RubricCriterion.objects.filter(rubric=rubric).aggregate(
                    m=Max('order'))['m'] or 0
                if rubric.is_weighted:
                    try:
                        w = float(request.POST.get('criterion_weight') or 0)
                    except ValueError:
                        w = 0
                    current_w = float(sum_weights_for_rubric(rubric))
                    if current_w + w - 100 > 0.02:
                        messages.error(request, "Total weight cannot exceed 100%.")
                        return redirect('assignment_rubric', assignment_id=assignment.id)
                    RubricCriterion.objects.create(
                        rubric=rubric,
                        name=name,
                        order=max_order + 1,
                        max_points=mp,
                        weight=w,
                    )
                else:
                    ap = Decimal(str(assignment.points or 0))
                    current_sum = sum_unweighted_allocations(rubric.criteria.all())
                    new_mp = Decimal(str(mp))
                    if ap > 0 and current_sum + new_mp - ap > Decimal("0.01"):
                        messages.error(
                            request,
                            "That would exceed the assignment total (%s points)." % ap,
                        )
                        return redirect("assignment_rubric", assignment_id=assignment.id)
                    RubricCriterion.objects.create(
                        rubric=rubric,
                        name=name,
                        order=max_order + 1,
                        max_points=mp,
                        weight=None,
                    )
                messages.success(request, f"Criterion '{name}' added.")
        elif action == 'delete_criterion':
            cid = request.POST.get('criterion_id')
            if cid:
                RubricCriterion.objects.filter(rubric=rubric, id=cid).delete()
                messages.success(request, "Criterion removed.")
        return redirect('assignment_rubric', assignment_id=assignment.id)

    criteria = list(rubric.criteria.all())
    total_pts = int(assignment.points) if assignment.points is not None else 0
    criteria_with_display = []
    weight_total = float(sum_weights_for_rubric(rubric)) if rubric.is_weighted else None
    for c in criteria:
        if rubric.is_weighted and c.weight is not None:
            alloc = round(float(total_pts) * float(c.weight) / 100)
        else:
            alloc = int(c.max_points) if c.max_points is not None else 0
        criteria_with_display.append({
            'criterion': c,
            'display_points': alloc,
            'assignment_points_allocation': alloc if rubric.is_weighted else None,
        })
    role = request.session.get('active_role') or getattr(request, 'user_role', None)
    if role == 'INSTRUCTOR' or (role in ['FACULTY', 'PROFESSOR']):
        base_template = 'base_professor.html'
    elif role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    context = {
        'base_template': base_template,
        'assignment': assignment,
        'rubric': rubric,
        'criteria': criteria,
        'criteria_with_display': criteria_with_display,
        'rubric_weight_total': weight_total,
        'unweighted_points_sum': (
            sum_unweighted_allocations(criteria) if not rubric.is_weighted else None
        ),
    }
    return render(request, 'rubric.html', context)


@login_required
def edit_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    # Define role and template early for use in all code paths
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    
    if not is_course_instructor(user, assignment.course, request):
        return HttpResponseForbidden("Only instructors can edit assignments.")
        
    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save()
                    assignment_type = request.POST.get('assignment_type')
                    if assignment_type == 'group':
                        assignment.is_group_assignment = True
                        assignment.save(update_fields=['is_group_assignment'])
                        group_source_mode = request.POST.get('group_source_mode')
                        selected_group_set_id = request.POST.get('course_group_set_id')
                        if group_source_mode == 'course_set' and selected_group_set_id:
                            apply_assignment_groups(
                                assignment=assignment,
                                groups_data_raw=None,
                                max_group_size=assignment.max_group_size,
                                course_group_set_id=int(selected_group_set_id),
                            )
                        else:
                            apply_assignment_groups(
                                assignment=assignment,
                                groups_data_raw=request.POST.get('groups_data'),
                                max_group_size=assignment.max_group_size,
                            )

                        save_set_name = (request.POST.get('save_as_course_group_set_name') or '').strip()
                        if save_set_name:
                            course_set = CourseGroupSet.objects.create(
                                course=assignment.course,
                                name=save_set_name,
                                created_by=user,
                            )
                            for grp in assignment.assignment_groups.prefetch_related('members').all():
                                cg = CourseGroup.objects.create(group_set=course_set, name=grp.name)
                                CourseGroupMember.objects.bulk_create([
                                    CourseGroupMember(group=cg, student_id=gm.student_id) for gm in grp.members.all()
                                ])
                    else:
                        # Switched to Individual
                        if assignment.is_group_assignment:
                            assignment.is_group_assignment = False
                            assignment.save()
                            # Delete groups when switching to individual
                            assignment.assignment_groups.all().delete()
                    
                    # Process test cases JSON
                    test_cases_json = request.POST.get('test_cases_json', '')
                    if test_cases_json:
                        import json
                        test_cases_data = json.loads(test_cases_json)
                        TestCase.objects.filter(assignment=assignment).delete()
                        seen_tcs = set()
                        order_idx = 1
                        for tc_data in test_cases_data:
                            key = (
                                tc_data.get('input_data', '').strip(),
                                tc_data.get('expected_output', '').strip(),
                                _coerce_bool(tc_data.get('is_private'), False)
                            )
                            if key in seen_tcs:
                                continue
                            seen_tcs.add(key)
                            
                            TestCase.objects.create(
                                assignment=assignment,
                                name=f"Test Case {order_idx}",
                                input_data=tc_data.get('input_data', ''),
                                expected_output=tc_data.get('expected_output', ''),
                                is_private=key[2],
                                points_awarded=tc_data.get('points', 5),
                                order=order_idx
                            )
                            order_idx += 1
            except Exception as e:
                logger.error(f"Error updating assignment: {e}")
                messages.error(request, f"An error occurred while updating the assignment: {str(e)}")
                return render(request, 'edit_assignment.html', {
                    'form': form,
                    'assignment': assignment,
                    'base_template': base_template,
                    'course_students': CourseMember.objects.filter(course=assignment.course, role_in_course='STUDENT').select_related('user'),
                    'course_group_sets': CourseGroupSet.objects.filter(course=assignment.course).order_by('-created_at'),
                })

            # If a new public_test_data CSV file was uploaded, replace all DB test cases for this assignment
            # with rows from the file (honors is_private per row — students only run is_private=False).
            public_test_file = form.cleaned_data.get('public_test_data')
            if public_test_file:
                try:
                    import csv

                    public_test_file.open('r')
                    content = public_test_file.read()
                    public_test_file.close()
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    content = content.lstrip('\ufeff')

                    reader = csv.DictReader(content.splitlines())
                    TestCase.objects.filter(assignment=assignment).delete()

                    count = 0
                    seen_tcs = set()
                    order_idx = 1
                    for raw in reader:
                        row = {
                            (k or '').strip().lstrip('\ufeff').lower(): (v if v is not None else '').strip()
                            for k, v in raw.items()
                        }
                        input_data = row.get('input_data', '')
                        expected_output = row.get('expected_output', '')
                        is_private_str = str(row.get('is_private', 'false')).strip().lower()
                        is_private = is_private_str in ('true', '1', 'yes')
                        
                        key = (input_data.strip(), expected_output.strip(), is_private)
                        if key in seen_tcs:
                            continue
                        seen_tcs.add(key)

                        points_val = row.get('points', '') or '5'
                        try:
                            points = int(float(points_val))
                        except ValueError:
                            points = 5

                        TestCase.objects.create(
                            assignment=assignment,
                            name=f"Test Case {order_idx}",
                            input_data=input_data,
                            expected_output=expected_output,
                            is_private=is_private,
                            is_hidden=False,
                            points_awarded=points,
                            order=order_idx,
                        )
                        order_idx += 1
                        count += 1

                    logger.info(f"Re-imported {count} test cases for assignment {assignment.id} from CSV")
                except Exception as e:
                    logger.error(f"Error parsing public_test_data CSV for assignment {assignment.id}: {e}")

            # Success message removed as per user request
            course_role = get_user_course_role(user, assignment.course, request)
            route_name = 'professor_course' if course_role == 'INSTRUCTOR' else ('student_course' if course_role == 'STUDENT' else 'ga_course')
            return redirect(route_name, course_id=assignment.course.id)
    else:
        form = AssignmentForm(instance=assignment)
        
    # Get students for group selection
    course_students = []
    group_member_ids = []
    if assignment.course:
        course_students = CourseMember.objects.filter(course=assignment.course, role_in_course='STUDENT').select_related('user')
        for member in course_students:
            student_profile, _ = Student.objects.get_or_create(user=member.user)
            member.student_id = student_profile.id
            
        if assignment.is_group_assignment:
            # Get existing group members
            group = assignment.assignment_groups.first()
            if group:
                group_member_ids = list(AssignmentGroupMember.objects.filter(group=group).values_list('student_id', flat=True))
    
    return render(request, 'edit_assignment.html', {
        'form': form, 
        'assignment': assignment, 
        'base_template': base_template,
        'course_students': course_students,
        'course_group_sets': CourseGroupSet.objects.filter(course=assignment.course).order_by('-created_at'),
    })

@login_required
def delete_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    course = assignment.course
    course_id = course.id if course else None
    
    if course and not is_course_instructor(user, course, request):
        return HttpResponseForbidden("Only instructors can delete assignments.")
        
    if request.method == 'POST':
        assignment.delete()
        # Success message removed as per user request
        if course_id:
            course_role = get_user_course_role(user, course, request)
            route_name = 'professor_course' if course_role == 'INSTRUCTOR' else ('student_course' if course_role == 'STUDENT' else 'ga_course')
            return redirect(route_name, course_id=course_id)
        return redirect('assignments_dashboard')
        
    course_role = get_user_course_role(user, course, request) if course else 'INSTRUCTOR'
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    # Technically we should use a confirmation template for GET, but let's provide basic routing
    return render(request, 'delete_assignment.html', {'assignment': assignment, 'base_template': base_template})

@login_required
def assignment_detail_view(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    if not is_enrolled(user, assignment.course, request):
        return HttpResponseForbidden("You are not enrolled in this course.")
        
    course_role = get_user_course_role(user, assignment.course, request)
    is_instructor = course_role == 'INSTRUCTOR'
    is_student = course_role == 'STUDENT'
    
    # Handle Submissions for Students
    form = None
    group_members = []
    if is_student:
        student_profile, _ = Student.objects.get_or_create(user=user)
        group = resolve_assignment_group_for_student(assignment, student_profile) if assignment.is_group_assignment else None
        
        if request.method == 'POST':
            # Check for existing submission (re-submission)
            submission = get_effective_submission_for_student(assignment, student_profile)
                
            files = request.FILES.getlist('file_path')
            monaco_files_json = request.POST.get('monaco_files', '').strip()
            
            import json
            monaco_files = []
            if monaco_files_json:
                try:
                    monaco_files = json.loads(monaco_files_json)
                except json.JSONDecodeError:
                    pass
            
            if files or monaco_files:
                if assignment.is_group_assignment and submission:
                    messages.error(request, "Your group already has a submission. Ask faculty to reopen submissions.")
                    return redirect('assignment_detail', pk=pk)
                if not submission:
                    if assignment.is_group_assignment:
                        if not group:
                            return HttpResponseForbidden("You are not part of a group for this assignment.")
                        submission = Submission(group=group, assignment=assignment)
                    else:
                        submission = Submission(student=student_profile, assignment=assignment)
                
                # Link the actual submitter for record keeping even in groups
                submission.student = student_profile
                
                file_contents = {}
                for f in files:
                    file_contents[f.name] = f.read()
                for mf in monaco_files:
                    name = mf.get('name')
                    # If extension is missing or we just need a default name:
                    if not name:
                        extension = ".java" if assignment.allowed_language == "java" else ".py"
                        name = f"submission_{len(file_contents)}{extension}"
                    file_contents[name] = mf.get('content', '').encode('utf-8')
                
                if len(file_contents) > 1:
                    import zipfile
                    import io
                    from django.core.files.base import ContentFile
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w') as zf:
                        for name, content in file_contents.items():
                            zf.writestr(name, content)
                    zip_buffer.seek(0)
                    submission.file_path.save(f"submission_{user.username}_{assignment.id}.zip", ContentFile(zip_buffer.read()))
                elif file_contents:
                    name, content = list(file_contents.items())[0]
                    from django.core.files.base import ContentFile
                    import os
                    base, ext = os.path.splitext(name)
                    if not ext:
                        ext = ".java" if assignment.allowed_language == "java" else ".py"
                    filename = f"submission_{user.username}_{assignment.id}{ext}"
                    submission.file_path.save(filename, ContentFile(content))
                    
                # Ensure the submission is fully saved to the database before analysis
                submission.save()

                # --- AUTO-GRADER TRIGGER ---
                # This is where we would trigger the backend autograder service.
                # Example: run_autograder(submission.id)
                # The mockup requirements specify this happens automatically on submission.

                # --- AI AND PLAGIARISM DETECTION ---
                try:
                    from grading.services import run_submission_analysis
                    # Run the analysis service synchronously so it gets saved on page reload
                    run_submission_analysis(submission.id)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error triggering Code Analysis service: {e}")
                
                messages.success(request, "Submission successful.")
                return redirect('assignment_detail', pk=pk)
            else:
                messages.error(request, "Please upload a file or enter code before submitting.")
        else:
            form = SubmissionForm()

    submissions = Submission.objects.filter(assignment=assignment).select_related('student__user', 'grade')
    
    import json
    submission_files = []
    latest_submission = None
    
    if is_student:
        if assignment.is_group_assignment:
            if group:
                submissions = submissions.filter(group=group)
                group_members = AssignmentGroupMember.objects.filter(group=group).select_related('student__user')
            else:
                submissions = submissions.none()
                latest_submission = None
        else:
            submissions = submissions.filter(student__user=user)

        if not (assignment.is_group_assignment and not group):
            latest_submission = submissions.order_by('-submission_time', '-id').first()
        
        # Monaco Editor Support
        if latest_submission and latest_submission.file_path:
            file_name = latest_submission.file_path.name.lower()
            if hasattr(latest_submission.file_path, 'read'):
                try:
                    latest_submission.file_path.open('rb')
                    file_content = latest_submission.file_path.read()
                    latest_submission.file_path.close()
                    
                    if file_name.endswith('.zip'):
                        import zipfile
                        import io
                        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zf:
                            for zip_info in zf.infolist():
                                if not zip_info.is_dir() and not zip_info.filename.startswith('__MACOSX'):
                                    name = zip_info.filename
                                    if name.endswith('.py') or name.endswith('.java'):
                                        content = zf.read(name).decode('utf-8', errors='ignore')
                                        lang = 'python' if name.endswith('.py') else 'java'
                                        import os
                                        submission_files.append({"name": os.path.basename(name), "content": content, "language": lang})
                    elif file_name.endswith('.py') or file_name.endswith('.java'):
                        content = file_content.decode('utf-8', errors='ignore')
                        lang = 'python' if file_name.endswith('.py') else 'java'
                        import os
                        basename = os.path.basename(latest_submission.file_path.name)
                        submission_files.append({"name": basename, "content": content, "language": lang})
                except Exception as e:
                    logger.error(f"Error reading file for preview: {e}")
                    
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    
    submission_files_json = json.dumps(submission_files)
    
    can_preview_code = False
    if len(submission_files) > 0:
        can_preview_code = True

    rubric = getattr(assignment, 'rubric', None)
    criteria = list(rubric.criteria.all()) if rubric else []
    total_pts = int(assignment.points) if assignment.points is not None else 0
    criteria_with_display = []
    for c in criteria:
        if rubric.is_weighted and c.weight is not None:
            display_pts = round(float(total_pts) * float(c.weight) / 100)
        else:
            display_pts = int(c.max_points) if c.max_points is not None else 0
        criteria_with_display.append({
            'criterion': c,
            'display_points': display_pts,
            'assignment_points_allocation': display_pts if rubric.is_weighted else None,
        })
    has_rubric = rubric is not None
    group_submission_locked = (
        is_student and assignment.is_group_assignment and latest_submission is not None
    )
    can_reopen_group_submissions = (
        course_role in ('INSTRUCTOR', 'GRADING_ASSISTANT') and assignment.is_group_assignment
    )
    context = {
        'assignment': assignment,
        'submissions': submissions,
        'latest_submission': latest_submission,
        'group_submission_locked': group_submission_locked,
        'can_reopen_group_submissions': can_reopen_group_submissions,
        'submission_files_json': submission_files_json,
        'can_preview_code': can_preview_code,
        'is_instructor': is_instructor,
        'is_student': is_student,
        'base_template': base_template,
        'form': form,
        'group_members': group_members,
        'has_rubric': has_rubric,
        'rubric': rubric,
        'criteria_with_display': criteria_with_display,
        'unweighted_points_sum': (
            sum_unweighted_allocations(criteria)
            if rubric and not rubric.is_weighted
            else None
        ),
    }
    return render(request, 'assignment_detail.html', context)


@login_required
def gradebook_view(request, pk):
    """
    Gradebook for an assignment.

    For instructors, this view also builds a course-level grid (students x assignments)
    so the template can render a Canvas-style gradebook table.
    """
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    if not has_course_access(user, assignment.course, request):
        return HttpResponseForbidden("You do not have permission to view this gradebook.")
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    submissions = Submission.objects.filter(assignment=assignment).select_related('student__user', 'grade').order_by('id')

    context = {
        'assignment': assignment,
        'submissions': submissions,
        'base_template': base_template,
        # For instructor sidebar navigation
        'course': assignment.course,
        'gradebook_assignment': assignment,
        'active_tab': 'grades',
    }

    # For instructors, also build the course-level grid view (students x assignments)
    if course_role == 'INSTRUCTOR':
        course = assignment.course
        # Columns: all assignments in this course
        grid_assignments = Assignment.objects.filter(course=course).order_by('due_date', 'id')
        # Rows: all enrolled students
        member_qs = CourseMember.objects.filter(
            course=course,
            role_in_course='STUDENT',
        ).select_related('user').order_by('user__last_name', 'user__first_name', 'user__username')

        student_users = [m.user for m in member_qs]
        grid_students = Student.objects.filter(user__in=student_users).select_related('user')
        student_by_user_id = {s.user_id: s for s in grid_students}

        # All submissions/grades for these assignments
        grid_submissions = Submission.objects.filter(
            assignment__in=grid_assignments
        ).select_related('assignment', 'student', 'group', 'grade').prefetch_related('group__members')

        cell_lookup = {}
        for sub in grid_submissions:
            if sub.group:
                # Map to all members of the group
                for member in sub.group.members.all():
                    cell_lookup[(member.student_id, sub.assignment_id)] = sub
            elif sub.student_id:
                cell_lookup[(sub.student_id, sub.assignment_id)] = sub

        rows = []
        for member in member_qs:
            stu = student_by_user_id.get(member.user_id)
            if not stu:
                continue

            cells = []
            for a in grid_assignments:
                sub = cell_lookup.get((stu.id, a.id))
                if not sub:
                    # If due date has passed, mark as missing; otherwise it's simply not submitted yet
                    due = getattr(a, 'due_date', None)
                    if due and due < timezone.now():
                        status = 'missing'
                    else:
                        status = 'not_submitted'
                    score = None
                else:
                    g = getattr(sub, 'grade', None)
                    if g:
                        status = 'graded'
                        score = float(g.score)
                    else:
                        status = 'ungraded'
                        score = None
                submission_id = sub.id if sub else None
                cells.append({
                    "assignment": a,
                    "status": status,
                    "score": score,
                    "submission_id": submission_id,
                })

            rows.append({
                "student": stu,
                "cells": cells,
            })

        context['assignments'] = grid_assignments
        context['rows'] = rows

    return render(request, 'gradebook.html', context)


@login_required
def grade_submission_view(request, pk):
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment

    if not has_course_access(user, assignment.course, request):
        return HttpResponseForbidden("You do not have permission to grade this assignment.")

    # Previous/next submission within same assignment (stable order: id)
    submission_ids = list(
        Submission.objects.filter(assignment=assignment).order_by('id').values_list('pk', flat=True)
    )
    try:
        current_index = submission_ids.index(submission.pk)
    except ValueError:
        current_index = -1
    previous_submission = None
    next_submission = None
    if current_index > 0:
        previous_submission = Submission.objects.filter(pk=submission_ids[current_index - 1]).first()
    if current_index >= 0 and current_index + 1 < len(submission_ids):
        next_submission = Submission.objects.filter(pk=submission_ids[current_index + 1]).first()

    grade = getattr(submission, 'grade', None)
    rubric = getattr(assignment, 'rubric', None)
    criteria = list(rubric.criteria.all()) if rubric else []
    criterion_grades = {}  # criterion_id -> points_earned (Decimal)
    if submission and criteria:
        for cg in CriterionGrade.objects.filter(submission=submission, criterion__in=criteria):
            criterion_grades[cg.criterion_id] = cg.points_earned

    def _build_criteria_rows():
        rows = []
        for c in criteria:
            pe = criterion_grades.get(c.id)
            if pe is None:
                pe = Decimal('0')
            else:
                pe = Decimal(str(pe))
            mx = Decimal(str(c.max_points or 0))
            w = Decimal(str(c.weight)) if c.weight is not None else None
            row = {
                'criterion': c,
                'points_earned': pe,
                'max_points': c.max_points,
                'weight': c.weight,
                'contribution_pct': None,
            }
            if rubric and rubric.is_weighted and w is not None and mx > 0:
                row['contribution_pct'] = criterion_weighted_contribution(pe, mx, w)
            rows.append(row)
        return rows

    criteria_with_scores = _build_criteria_rows()

    if request.method == 'POST':
        feedback = request.POST.get('feedback', '')
        rubric_grade_submit = bool(rubric and criteria and request.POST.get('submit_grade_rubric'))
        if rubric_grade_submit:
            earned_by_id = {}
            for c in criteria:
                raw = request.POST.get('score_criterion_' + str(c.id), '')
                try:
                    pts = Decimal(str(raw)) if raw not in (None, '') else Decimal('0')
                except (InvalidOperation, ValueError):
                    pts = Decimal('0')
                if rubric.is_weighted:
                    mx = Decimal(str(c.max_points or 0))
                    if mx > 0:
                        pts = max(Decimal('0'), min(pts, mx))
                    else:
                        pts = Decimal('0')
                else:
                    pts = max(Decimal('0'), pts)
                earned_by_id[c.id] = pts

            skip_rubric_save = False
            if not rubric.is_weighted and assignment.points:
                ap_lim = Decimal(str(assignment.points))
                raw_total = sum(earned_by_id[c.id] for c in criteria)
                if raw_total - ap_lim > Decimal('0.01'):
                    skip_rubric_save = True
                    messages.error(
                        request,
                        "Sum of criterion scores (%s) cannot exceed the assignment total (%s)."
                        % (raw_total, ap_lim),
                    )
                    for c in criteria:
                        criterion_grades[c.id] = earned_by_id[c.id]
                    criteria_with_scores = _build_criteria_rows()

            if not skip_rubric_save:
                for c in criteria:
                    CriterionGrade.objects.update_or_create(
                        submission=submission,
                        criterion=c,
                        defaults={'points_earned': earned_by_id[c.id]},
                    )

                if rubric.is_weighted:
                    total = final_score_weighted_rubric(criteria, earned_by_id, assignment.points)
                else:
                    total = final_score_unweighted_rubric(criteria, earned_by_id, assignment.points)

            pct_note = ''
            if rubric.is_weighted and assignment.points:
                try:
                    p_pct = (float(total) / float(assignment.points)) * 100.0
                    pct_note = ' (%.1f%% of assignment)' % p_pct
                except (ValueError, ZeroDivisionError):
                    pass
            messages.success(
                request,
                "Grade saved. Score: %s / %s%s"
                % (total, assignment.points, pct_note),
            )
            if next_submission:
                return redirect('grade_submission', pk=next_submission.pk)
            return redirect('gradebook', pk=assignment.pk)
        # Single score (no rubric)
        score = request.POST.get('score', '').strip()
        if score == '':
            # Empty score = UNGRADE: delete the Grade record and reset submission status
            if grade:
                grade.delete()
                CriterionGrade.objects.filter(submission=submission).delete()
                messages.success(request, "Grade removed. Submission is now ungraded.")
            else:
                messages.info(request, "No grade to remove.")

            # Always ensure the status gets reset
            submission.status = 'submitted'
            submission.save(update_fields=['status'])
            return redirect('gradebook', pk=assignment.pk)
        else:
            # Non-empty score = save/update the grade
            try:
                score_val = float(score)
                if grade:
                    grade.score = score_val
                    grade.feedback = feedback
                    grade.save()
                    messages.success(request, "Grade updated successfully.")
                else:
                    Grade.objects.create(submission=submission, score=score_val, feedback=feedback)
                    messages.success(request, "Grade submitted successfully.")
                submission.status = 'graded'
                submission.save(update_fields=['status'])
                return redirect('gradebook', pk=assignment.pk)
            except ValueError:
                messages.error(request, "Invalid score submitted.")
            
    course_role = get_user_course_role(user, assignment.course, request)
    is_instructor = (course_role == 'INSTRUCTOR')
    
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
            
    import json
    submission_files = []
    
    if submission and submission.file_path:
        file_name = submission.file_path.name.lower()
        if hasattr(submission.file_path, 'read'):
            try:
                submission.file_path.open('rb')
                file_content = submission.file_path.read()
                submission.file_path.close()
                
                if file_name.endswith('.zip'):
                    import zipfile
                    import io
                    with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zf:
                        for zip_info in zf.infolist():
                            if not zip_info.is_dir() and not zip_info.filename.startswith('__MACOSX'):
                                name = zip_info.filename
                                # Support common code and data extensions
                                ext = name.split('.')[-1].lower() if '.' in name else ''
                                supported_exts = ['py', 'java', 'js', 'ts', 'html', 'css', 'json', 'txt', 'csv', 'md', 'sql', 'cpp', 'c', 'h']
                                
                                if ext in supported_exts or not ext:
                                    try:
                                        # Skip binary files if they somehow get in
                                        content_bytes = zf.read(name)
                                        content = content_bytes.decode('utf-8', errors='ignore')
                                        
                                        # Improved language mapping for Monaco
                                        lang_map = {
                                            'py': 'python',
                                            'java': 'java',
                                            'js': 'javascript',
                                            'ts': 'typescript',
                                            'html': 'html',
                                            'css': 'css',
                                            'json': 'json',
                                            'md': 'markdown',
                                            'sql': 'sql',
                                            'cpp': 'cpp',
                                            'c': 'c',
                                            'h': 'cpp'
                                        }
                                        lang = lang_map.get(ext, 'plaintext')
                                        
                                        import os
                                        submission_files.append({
                                            "name": os.path.basename(name), 
                                            "content": content, 
                                            "language": lang,
                                            "full_path": name
                                        })
                                    except:
                                        continue
                elif file_name.endswith('.py') or file_name.endswith('.java') or file_name.endswith('.txt') or file_name.endswith('.csv'):
                    content = file_content.decode('utf-8', errors='ignore')
                    ext = file_name.split('.')[-1]
                    lang = 'python' if ext == 'py' else ('java' if ext == 'java' else 'plaintext')
                    import os
                    basename = os.path.basename(submission.file_path.name)
                    submission_files.append({"name": basename, "content": content, "language": lang})
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error reading file for preview: {e}")
                
    submission_files_json = json.dumps(submission_files)
    
    can_preview_code = False
    if len(submission_files) > 0:
        can_preview_code = True
        
    group_members = []
    if submission.group:
        group_members = AssignmentGroupMember.objects.filter(group=submission.group).select_related('student__user')

    context = {
        'submission': submission,
        'assignment': assignment,
        'grade': grade,
        'base_template': base_template,
        'can_preview_code': can_preview_code,
        'submission_files_json': submission_files_json,
        'is_instructor': is_instructor,
        'previous_submission': previous_submission,
        'next_submission': next_submission,
        'rubric': rubric,
        'criteria': criteria,
        'criteria_with_scores': criteria_with_scores,
        'criterion_grades': criterion_grades,
        'group_members': group_members,
    }
    return render(request, 'grade_submission.html', context)

@login_required
def download_submission_view(request, pk):
    """
    Forces the browser to prompt the user with a 'Save As' dialog box
    by setting the Content-Disposition header to attachment.
    """
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=pk)
    
    # Check permissions
    if not can_view_submission(user, submission) and not has_course_access(user, submission.assignment.course, request):
        return HttpResponseForbidden("You do not have permission to download this submission.")
        
    try:
        response = FileResponse(submission.file_path.open('rb'))
        # Using attachment; filename= forces most browsers to ask the user where to save it
        response['Content-Disposition'] = f'attachment; filename="{submission.file_path.name.split("/")[-1]}"'
        return response
    except FileNotFoundError:
        raise Http404("File not found.")

@login_required
def delete_submission_view(request, pk):
    """
    Allows a student to delete their own submission.
    """
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=pk)
    
    if not can_view_submission(user, submission):
        return HttpResponseForbidden("You do not have permission to delete this submission.")
        
    if request.method == 'POST':
        assignment_id = submission.assignment.id
        
        # Delete the actual file from storage
        if submission.file_path:
            submission.file_path.delete(save=False)
            
        # Delete the database record
        submission.delete()
        
        messages.success(request, "Submission successfully deleted.")
        return redirect('assignment_detail', pk=assignment_id)
        
    return HttpResponseForbidden("Invalid request method.")


@login_required
@require_POST
def reopen_group_submission_view(request, assignment_id, group_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, is_group_assignment=True)
    user = get_user_from_request(request)
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role not in ['INSTRUCTOR', 'GRADING_ASSISTANT']:
        return HttpResponseForbidden("You do not have permission to reopen this group submission.")
    group = get_object_or_404(AssignmentGroup, id=group_id, assignment=assignment)
    Submission.objects.filter(assignment=assignment, group=group).delete()
    messages.success(request, f"Reopened submission slot for {group.name or 'group'}.")
    return redirect('assignment_detail', pk=assignment.id)


@login_required
def upload_test_cases(request, assignment_id):
    """
    Professor uploads test cases via JSON, CSV, or Excel file.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    if request.method == 'POST':
        form = TestCaseUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                test_file = request.FILES['test_file']
                file_format = form.cleaned_data['file_format']
                clear_existing = form.cleaned_data['clear_existing']
                
                # Clear existing test cases if requested
                if clear_existing:
                    TestCase.objects.filter(assignment=assignment).delete()
                
                # Parse and import test cases
                test_cases = parse_test_cases(test_file, file_format)
                
                # Get the maximum order to append new tests
                max_order = TestCase.objects.filter(assignment=assignment).aggregate(Max('order'))['order__max'] or 0
                
                # Create TestCase objects (avoid duplicates for same assignment + core fields)
                created_count = 0
                for idx, tc in enumerate(test_cases):
                    name = tc.get('name', f'Test {max_order + idx + 1}')
                    description = tc.get('description', '')
                    input_data = tc.get('input_data', '')
                    expected_output = tc.get('expected_output', '')
                    points_awarded = float(tc.get('points_awarded', 1))
                    is_hidden = tc.get('is_hidden', False)
                    is_private = tc.get('is_private', False)

                    obj, created = TestCase.objects.update_or_create(
                        assignment=assignment,
                        input_data=input_data.strip(),
                        expected_output=expected_output.strip(),
                        is_private=is_private,
                        is_hidden=is_hidden,
                        defaults={
                            'name': name,
                            'description': description,
                            'points_awarded': points_awarded,
                            'order': max_order + idx + 1,
                        },
                    )
                    if created:
                        created_count += 1
                
                messages.success(request, f'Successfully imported {created_count} test cases.')
                return redirect('assignment_detail', pk=assignment_id)
                
            except Exception as e:
                messages.error(request, f'Error importing test cases: {str(e)}')
                logger.exception(f"Error importing test cases for assignment {assignment_id}")
    else:
        form = TestCaseUploadForm()
    
    return render(request, 'grading/upload_test_cases.html', {
        'form': form,
        'assignment': assignment,
        'base_template': 'base_professor.html'
    })


@login_required
def configure_rules(request, assignment_id):
    """
    Professor configures static analysis rules for an assignment.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    # Get or create RuleSet for this assignment
    rule_set, created = RuleSet.objects.get_or_create(assignment=assignment)
    
    if request.method == 'POST':
        form = RuleSetForm(request.POST, instance=rule_set)
        if form.is_valid():
            form.save()
            messages.success(request, 'Static analysis rules updated successfully.')
            return redirect('assignment_detail', pk=assignment_id)
    else:
        form = RuleSetForm(instance=rule_set)
    
    return render(request, 'grading/configure_rules.html', {
        'form': form,
        'assignment': assignment,
        'base_template': 'base_professor.html'
    })


@login_required
def manage_test_cases(request, assignment_id):
    """
    Professor view to manage test cases - view, create, edit, delete.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    test_cases = TestCase.objects.filter(assignment=assignment).order_by('order')
    
    return render(request, 'grading/manage_test_cases.html', {
        'assignment': assignment,
        'test_cases': test_cases,
        'base_template': 'base_professor.html'
    })


@login_required
def create_test_case(request, assignment_id):
    """
    Professor creates a new test case.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    if request.method == 'POST':
        form = TestCaseForm(request.POST)
        if form.is_valid():
            test_case = form.save(commit=False)
            test_case.assignment = assignment
            
            # Auto-assign order if not provided
            if not test_case.order:
                max_order = TestCase.objects.filter(assignment=assignment).aggregate(Max('order'))['order__max'] or 0
                test_case.order = max_order + 1
            
            test_case.save()
            messages.success(request, 'Test case created successfully.')
            return redirect('manage_test_cases', assignment_id=assignment_id)
    else:
        form = TestCaseForm()
    
    return render(request, 'grading/create_test_case.html', {
        'form': form,
        'assignment': assignment,
        'base_template': 'base_professor.html'
    })


@login_required
def edit_test_case(request, test_case_id):
    """
    Professor edits an existing test case.
    """
    test_case = get_object_or_404(TestCase, id=test_case_id)
    assignment = test_case.assignment
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    if request.method == 'POST':
        form = TestCaseForm(request.POST, instance=test_case)
        if form.is_valid():
            form.save()
            messages.success(request, 'Test case updated successfully.')
            return redirect('manage_test_cases', assignment_id=assignment.id)
    else:
        form = TestCaseForm(instance=test_case)
    
    return render(request, 'grading/edit_test_case.html', {
        'form': form,
        'test_case': test_case,
        'assignment': assignment,
        'base_template': 'base_professor.html'
    })


@login_required
def delete_test_case(request, test_case_id):
    """
    Professor deletes a test case.
    """
    test_case = get_object_or_404(TestCase, id=test_case_id)
    assignment = test_case.assignment
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to manage this assignment.")
    
    if request.method == 'POST':
        test_case.delete()
        messages.success(request, 'Test case deleted successfully.')
        return redirect('manage_test_cases', assignment_id=assignment.id)
    
    return render(request, 'grading/delete_test_case_confirm.html', {
        'test_case': test_case,
        'assignment': assignment,
        'base_template': 'base_professor.html'
    })


@login_required
def toggle_test_case_visibility(request, test_case_id):
    """
    AJAX endpoint to toggle test case visibility (visible/hidden).
    """
    test_case = get_object_or_404(TestCase, id=test_case_id)
    assignment = test_case.assignment
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    test_case.is_hidden = not test_case.is_hidden
    test_case.save()
    
    return JsonResponse({
        'success': True,
        'is_hidden': test_case.is_hidden,
        'status': 'Hidden' if test_case.is_hidden else 'Visible'
    })


def parse_test_cases(test_file, file_format):
    """
    Parse test cases from uploaded file.
    Supports JSON, CSV, and Excel formats.
    
    JSON format expected:
    [
        {
            "name": "Test 1",
            "description": "...",
            "input_data": "...",
            "expected_output": "...",
            "points_awarded": 1,
            "is_hidden": false,
            "is_private": false
        }
    ]
    
    CSV format expected columns:
    name, description, input_data, expected_output, points_awarded, is_hidden, is_private
    
    Excel format expected same as CSV.
    """
    test_cases = []
    
    if file_format == 'json':
        content = test_file.read().decode('utf-8')
        test_cases = json.loads(content)
        if not isinstance(test_cases, list):
            raise ValueError('JSON must be an array of test case objects')
    
    elif file_format == 'csv':
        text_file = TextIOWrapper(test_file.file, encoding='utf-8')
        reader = csv.DictReader(text_file)
        
        required_fields = {'input_data', 'expected_output'}
        for row in reader:
            if not all(row.get(field) for field in required_fields):
                raise ValueError('CSV must contain "input_data" and "expected_output" columns')
            
            # Convert is_hidden to boolean
            is_hidden_str = str(row.get('is_hidden', 'false')).lower()
            is_hidden = is_hidden_str in ('true', '1', 'yes')

            # Convert is_private to boolean
            is_private_str = str(row.get('is_private', 'false')).lower()
            is_private = is_private_str in ('true', '1', 'yes')
            
            test_cases.append({
                'name': row.get('name', ''),
                'description': row.get('description', ''),
                'input_data': row.get('input_data', ''),
                'expected_output': row.get('expected_output', ''),
                'points_awarded': float(row.get('points_awarded', 1)),
                'is_hidden': is_hidden,
                'is_private': is_private,
            })
    
    elif file_format == 'excel':
        workbook = openpyxl.load_workbook(test_file)
        worksheet = workbook.active
        
        # Get headers from first row
        headers = [cell.value for cell in worksheet[1]]
        required_fields = {'input_data', 'expected_output'}
        
        if not all(field in headers for field in required_fields):
            raise ValueError('Excel must contain "input_data" and "expected_output" columns')
        
        for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            row_dict = dict(zip(headers, row))
            
            is_hidden_val = row_dict.get('is_hidden', False)
            is_hidden = str(is_hidden_val).lower() in ('true', '1', 'yes') if is_hidden_val else False

            is_private_val = row_dict.get('is_private', False)
            is_private = str(is_private_val).lower() in ('true', '1', 'yes') if is_private_val else False
            
            test_cases.append({
                'name': row_dict.get('name', ''),
                'description': row_dict.get('description', ''),
                'input_data': row_dict.get('input_data', ''),
                'expected_output': row_dict.get('expected_output', ''),
                'points_awarded': float(row_dict.get('points_awarded', 1)),
                'is_hidden': is_hidden,
                'is_private': is_private,
            })
    
    else:
        raise ValueError(f'Unsupported file format: {file_format}')
    
    return test_cases


@login_required
@require_POST
def grade_submission_api(request, submission_id):
    """
    API endpoint to trigger grading of a submission.
    
    Returns JSON with test results and rule violations.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    assignment = submission.assignment
    user = get_user_from_request(request)
    
    # Check permission - must be student submitting their own work or course instructor
    is_student_owner = can_view_submission(user, submission)
    is_instructor = is_course_instructor(user, assignment.course)
    
    if not (is_student_owner or is_instructor):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        result = grade_submission(submission_id)
        return JsonResponse(result)
    except Exception as e:
        logger.exception(f"Error grading submission {submission_id}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def autograde_submission_api(request, submission_id):
    """
    Runs the full autograder pipeline on a submission:
      1. Execute all test cases (grade_submission)
      2. AI likelihood + plagiarism analysis (run_submission_analysis)
      3. Return combined results as JSON for the Autograding tab.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    assignment = submission.assignment
    user = get_user_from_request(request)

    # Only course instructors / GAs may trigger autograding
    if not is_course_instructor(user, assignment.course, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        # ── 1. Run test cases ──────────────────────────────────────────
        grade_result = grade_submission(submission_id)

        if grade_result.get('status') == 'error':
            return JsonResponse({
                'status': 'error',
                'error': grade_result.get('error', 'Grading failed'),
            }, status=500)

        test_results = grade_result.get('test_results', [])
        total_score  = grade_result.get('total_score', 0)
        max_score    = grade_result.get('max_score', 0)

        # ── Scale test case points to assignment total points ──────────
        assignment_points = getattr(assignment, 'points', 0)
        if assignment_points > 0:
            if max_score > 0:
                # Proportional scaling (e.g., got 10/20 on tests = 50/100 for assignment)
                total_score = round((total_score / max_score) * assignment_points)
            else:
                # No tests available or tests total to 0, autograder yields 0 points
                total_score = 0
            max_score = assignment_points

        # ── 2. AI + Plagiarism analysis ────────────────────────────────
        analysis = run_submission_analysis(submission_id)

        # ── 3. Build feedback text from test results ───────────────────
        passed_count  = sum(1 for t in test_results if t.get('passed'))
        failed_count  = len(test_results) - passed_count

        feedback_lines = []
        if not test_results:
            feedback_lines.append("⚠️ No test cases found for this assignment. Add test cases to enable autograding.")
        else:
            feedback_lines.append(f"✅ {passed_count} / {len(test_results)} test cases passed.")
            for t in test_results:
                icon = "✅" if t.get('passed') else "❌"
                pts  = t.get('points_earned', 0)
                feedback_lines.append(f"  {icon} {t.get('name', 'Test')}  (+{pts} pts)")

        rule_violations = grade_result.get('rule_violations', [])
        if rule_violations:
            feedback_lines.append(f"\n⛔ {len(rule_violations)} static-analysis violation(s):")
            for v in rule_violations[:5]:
                feedback_lines.append(f"  • {v.get('message', '')}")

        if analysis.get('status') == 'ok':
            ai_pct = analysis.get('ai_likelihood_score')
            if ai_pct is not None:
                flag = " ⚠️" if ai_pct > 70 else ""
                feedback_lines.append(f"\n🤖 AI-generated likelihood: {ai_pct:.1f}%{flag}")
            plag_score = analysis.get('plagiarism_score')
            if plag_score is not None:
                flag = " ⚠️" if plag_score > 60 else ""
                feedback_lines.append(f"🔍 Plagiarism similarity: {plag_score:.1f}%{flag}")
                match_info = analysis.get('plagiarism_match_info', '')
                if match_info:
                    feedback_lines.append(f"   {match_info}")

        feedback_text = "\n".join(feedback_lines)

        # ── 4. Breakdown dict for the UI score card ────────────────────
        breakdown = {}
        for i, t in enumerate(test_results):
            name = t.get('name', f'Test {i+1}')
            earned = t.get('points_earned', 0)
            # Reconstruct max per test: if passed, earned==max; if failed, check test_case DB
            try:
                tc = TestCase.objects.get(id=t.get('test_case_id'))
                max_pts = tc.points_awarded
            except Exception:
                max_pts = earned if t.get('passed') else 0
            icon = '✅' if t.get('passed') else '❌'
            breakdown[name] = f'{icon} {earned} / {max_pts} pts'

        return JsonResponse({
            'status':               'ok',
            'score':                total_score,
            'max_score':            max_score,
            'breakdown':            breakdown,
            'feedback':             feedback_text,
            'ai_likelihood':        analysis.get('ai_likelihood_score'),
            'ai_confidence':        analysis.get('ai_confidence_score'),
            'ai_explanation':       analysis.get('ai_explanation', ''),
            'plagiarism_score':     analysis.get('plagiarism_score'),
            'plagiarism_match_info': analysis.get('plagiarism_match_info', ''),
            'plagiarism_match_id':  analysis.get('plagiarism_match_id'),
            'rule_violations':      rule_violations,
            'test_results':         test_results,
        })

    except Exception as e:
        logger.exception(f"Autograder failed for submission {submission_id}")
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@require_POST
def execute_submission_api(request, submission_id):
    """
    API endpoint to execute a submission once and return raw stdout/stderr.
    Used by the instructor Console tab on the grading page.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    assignment = submission.assignment
    user = get_user_from_request(request)

    # Only course instructors (or GAs with instructor-level access) can run code from this console
    if not is_course_instructor(user, assignment.course, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        payload = {}

    stdin = payload.get('stdin', '') or ''

    # Extract code for this submission
    code_str, _ = extract_code_from_file(submission.file_path)
    if not code_str.strip():
        return JsonResponse({'error': 'No valid source code found'}, status=400)

    language = assignment.allowed_language.lower()
    try:
        result = execute_code(language, code_str, stdin, submission_id)
    except Exception as e:
        logger.exception(f"Error executing submission {submission_id} from console")
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'stdout': result.get('stdout', ''),
        'stderr': result.get('stderr', ''),
        'exit_code': result.get('exit_code', 0),
        'timed_out': not result.get('success', True),
    })


@login_required
def submission_test_results(request, submission_id):
    """
    View test results for a submission (student or instructor only).
    """
    submission = get_object_or_404(Submission, id=submission_id)
    assignment = submission.assignment
    user = get_user_from_request(request)
    
    # Check permission
    is_student_owner = can_view_submission(user, submission)
    is_instructor = is_course_instructor(user, assignment.course)
    
    if not (is_student_owner or is_instructor):
        return HttpResponseForbidden("You do not have permission to view these results.")
    
    test_results = TestResult.objects.filter(submission=submission).select_related('test_case').order_by('test_case__order')
    
    # Count results
    total_tests = test_results.count()
    passed_tests = test_results.filter(passed=True).count()
    
    # Get rule violations
    rule_violations = submission.get_rule_violations_list()
    
    # Determine which tests are visible to student
    if not is_instructor:
        # Students only see visible tests
        visible_results = []
        for result in test_results:
            if not result.test_case.is_hidden:
                visible_results.append(result)
        test_results = visible_results
    
    context = {
        'submission': submission,
        'assignment': assignment,
        'test_results': test_results,
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'rule_violations': rule_violations,
        'is_instructor': is_instructor,
        'is_student': is_student_owner,
    }
    
    return render(request, 'grading/submission_test_results.html', context)


@login_required
def student_submit_and_test(request, assignment_id):
    """
    Student-facing view to submit code and run tests.
    Displays file upload, Run Tests button, and test feedback.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check if student is enrolled
    if not is_enrolled(user, assignment.course, request):
        return HttpResponseForbidden("You are not enrolled in this course.")
    
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role != 'STUDENT':
        return HttpResponseForbidden("Only students can access this view.")
    
    student_profile, _ = Student.objects.get_or_create(user=user)
    
    student_group = resolve_assignment_group_for_student(assignment, student_profile)
    submission = get_effective_submission_for_student(assignment, student_profile)
    
    # Handle file upload
    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            if assignment.is_group_assignment:
                if not can_submit_for_group(user, assignment, student_group):
                    return HttpResponseForbidden("You are not assigned to a group for this assignment.")
                if submission:
                    messages.error(request, "Your group already has a submission. Ask faculty to reopen submissions.")
                    return redirect('student_submit_and_test', assignment_id=assignment_id)
                submission = Submission(student=student_profile, group=student_group, assignment=assignment)
            elif not submission:
                submission = Submission(student=student_profile, assignment=assignment)

            submission.file_path = form.cleaned_data['file_path']
            submission.save()
            
            # --- Trigger Background Integrity Analysis ---
            try:
                from grading.tasks import run_submission_analysis_async
                run_submission_analysis_async.delay(submission.id)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to queue background integrity analysis for submission {submission.id}: {e}")
            
            messages.success(request, 'Code submitted successfully!')
            return redirect('student_submit_and_test', assignment_id=assignment_id)
    else:
        form = SubmissionForm()
    
    # Get visible test cases
    test_cases = TestCase.objects.filter(
        assignment=assignment,
        is_hidden=False
    ).order_by('order')
    
    # Get test results for current submission
    test_results = None
    if submission:
        test_results = TestResult.objects.filter(submission=submission).select_related('test_case').order_by('test_case__order')
        passed_count = test_results.filter(passed=True).count()
        total_count = test_results.count()
    else:
        passed_count = 0
        total_count = 0
    
    context = {
        'assignment': assignment,
        'submission': submission,
        'student_group': student_group,
        'form': form,
        'test_cases': test_cases,
        'test_results': test_results,
        'passed_count': passed_count,
        'total_count': total_count,
        'base_template': 'portal/base_portal.html',
    }
    
    return render(request, 'grading/student_submit_and_test.html', context)


@login_required
@require_POST
def trigger_bulk_grade(request, assignment_id):
    """
    Trigger bulk grading for all submissions in an assignment.
    Only accessible to course instructors.
    
    POST endpoint that queues a Celery task and returns task_id for progress tracking.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor
    if not is_course_instructor(user, assignment.course):
        return JsonResponse({
            'status': 'error',
            'message': 'You do not have permission to grade this assignment.'
        }, status=403)
    
    try:
        # Queue the bulk grading task
        task = bulk_grade_assignment.delay(assignment_id)
        
        return JsonResponse({
            'status': 'success',
            'task_id': task.id,
            'message': f'Bulk grading started for "{assignment.name}"'
        })
    except Exception as e:
        logger.error(f"Error queueing bulk grade task: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to start bulk grading. Please try again.'
        }, status=500)


@login_required
def get_bulk_grade_status(request, task_id):
    """
    Get the status of a bulk grading task.
    """
    from celery.result import AsyncResult
    
    try:
        task_result = AsyncResult(task_id)
        
        response = {
            'task_id': task_id,
            'status': task_result.status,
        }
        
        if task_result.state == 'PROGRESS':
            response['progress'] = task_result.info
        elif task_result.state == 'SUCCESS':
            response['result'] = task_result.result
        elif task_result.state == 'FAILURE':
            response['error'] = str(task_result.info)
        
        return JsonResponse(response)
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to get task status.'
        }, status=500)


@login_required
def grade_report(request, assignment_id):
    """
    Display a grade report for an assignment showing:
    - All students in the course
    - Their submission status
    - Detailed results for each test case (bulk execution grid)
    - Scores and pass rates
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)
    
    # Check permission - must be course instructor or GA
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role not in ['INSTRUCTOR', 'GRADING_ASSISTANT']:
        return HttpResponseForbidden("You do not have permission to view this report.")
    
    # Get all students in the course
    students = Student.objects.filter(
        user__course_memberships__course=assignment.course,
        user__course_memberships__role_in_course='STUDENT'
    ).select_related('user')
    
    # Get all test cases for this assignment
    test_cases = TestCase.objects.filter(assignment=assignment).order_by('order')
    
    # Build grade report data (initially EMPTY cells; results are filled after "Run Bulk Testing")
    grade_data = []
    
    for student in students:
        submission = get_effective_submission_for_student(assignment, student)
        
        student_results = []
        
        for tc in test_cases:
            student_results.append({
                'test_case_id': tc.id,
                'status': 'EMPTY',
            })

        grade_data.append({
            'id': student.id,
            'name': student.user.get_full_name() or student.user.username,
            'email': student.user.email,
            'submission_id': submission.id if submission else None,
            'has_submission': bool(submission),
            'test_results': student_results,
        })
    
    # Sort by name
    grade_data.sort(key=lambda x: x['name'])
    
    # Calculate statistics (keep only the essentials for this page)
    total_students = len(grade_data)
    submitted_count = sum(1 for g in grade_data if g['has_submission'])
    missing_count = total_students - submitted_count
    
    context = {
        'assignment': assignment,
        'test_cases': test_cases,
        'grade_data': grade_data,
        'total_students': total_students,
        'submitted': submitted_count,
        'missing': missing_count,
        'base_template': 'base_professor.html' if course_role == 'INSTRUCTOR' else 'base_grading_assistant.html'
    }
    
    return render(request, 'grading/grade_report.html', context)


@login_required
@require_http_methods(["GET"])
def grade_report_data_api(request, assignment_id):
    """
    Return the grade report grid data as JSON (used after bulk testing runs).
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = get_user_from_request(request)

    course_role = get_user_course_role(user, assignment.course, request)
    if course_role not in ['INSTRUCTOR', 'GRADING_ASSISTANT']:
        return JsonResponse({"error": "Permission denied"}, status=403)

    students = Student.objects.filter(
        user__course_memberships__course=assignment.course,
        user__course_memberships__role_in_course='STUDENT'
    ).select_related('user')

    test_cases = list(TestCase.objects.filter(assignment=assignment).order_by('order'))

    all_results = TestResult.objects.filter(
        submission__assignment=assignment
    ).select_related('submission', 'test_case')

    results_map = {}
    for res in all_results:
        results_map.setdefault(res.submission_id, {})[res.test_case_id] = res

    def status_for(res: Optional[TestResult]) -> str:
        # When bulk testing has run, missing results should be treated as FAIL
        # (e.g., compilation/runtime error prevented a per-test result row).
        if not res:
            return "FAIL"
        if res.passed:
            return "PASS"
        # Never surface "ERROR" as a grid label; treat as FAIL and show details in modal
        return "FAIL"

    rows = []
    for student in students:
        submission = get_effective_submission_for_student(assignment, student)
        sub_results = results_map.get(submission.id, {}) if submission else {}

        test_results = []
        for tc in test_cases:
            res = sub_results.get(tc.id)
            test_results.append({
                "test_case_id": tc.id,
                "status": status_for(res) if submission else "EMPTY",
            })

        rows.append({
            "id": student.id,
            "name": student.user.get_full_name() or student.user.username,
            "email": student.user.email,
            "submission_id": submission.id if submission else None,
            "has_submission": bool(submission),
            "test_results": test_results,
        })

    rows.sort(key=lambda x: x["name"])

    logger.info("[grade_report_data_api] assignment=%s rows=%s", assignment_id, len(rows))
    return JsonResponse({"students": rows})


@login_required
@require_http_methods(["GET"])
def test_result_detail_api(request, submission_id, test_case_id):
    """
    Return expected/actual/error details for one submission x test case.
    Used by the grade report modal on click.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    assignment = submission.assignment
    user = get_user_from_request(request)

    course_role = get_user_course_role(user, assignment.course, request)
    if course_role not in ['INSTRUCTOR', 'GRADING_ASSISTANT']:
        return JsonResponse({"error": "Permission denied"}, status=403)

    tc = get_object_or_404(TestCase, id=test_case_id, assignment=assignment)
    res = TestResult.objects.filter(submission=submission, test_case=tc).first()

    return JsonResponse({
        "test_case": {"id": tc.id, "name": tc.name, "order": tc.order},
        "passed": bool(res.passed) if res else False,
        "expected_output": tc.expected_output or "",
        "actual_output": (res.actual_output or "") if res else "",
        "error_message": (res.error_message or "") if res else "",
        "execution_time": float(res.execution_time) if res else 0.0,
        "has_result": bool(res),
    })


@login_required
@login_required
def student_course_report(request, course_id, student_id):
    """
    Detailed report for an instructor to see a specific student's 
    performance across all assignments in a particular course.
    Includes assignment details, student scores, and class averages.
    """
    from django.db.models import Avg
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    student = get_object_or_404(Student, id=student_id)
    
    # Permission check: Only instructor or GA of this course, or the student themselves
    course_role = get_user_course_role(user, course, request)
    is_instructor = course_role in ['INSTRUCTOR', 'GRADING_ASSISTANT']
    is_self_student = (course_role == 'STUDENT' and student.user == user)
    
    if not (is_instructor or is_self_student or user.is_staff):
        return HttpResponseForbidden("You do not have permission to view this report.")
        
    assignments = Assignment.objects.filter(course=course).order_by('due_date', 'id')
    submissions = Submission.objects.filter(
        student=student, 
        assignment__in=assignments
    ).select_related('grade', 'assignment')
    
    # Map submissions by assignment ID for easy lookup
    submission_lookup = {sub.assignment_id: sub for sub in submissions}
    
    # Class averages per assignment
    class_avgs = (
        Submission.objects.filter(assignment__in=assignments, grade__isnull=False)
        .values('assignment_id')
        .annotate(avg_score=Avg('grade__score'))
    )
    avg_by_assignment = {row['assignment_id']: float(row['avg_score']) for row in class_avgs}
    
    report_data = []
    total_points_possible = 0
    total_points_earned = 0
    total_weight_possible = 0.0
    total_weight_earned = 0.0
    use_weighted = assignments.filter(is_weighted=True).exists()
    
    for a in assignments:
        sub = submission_lookup.get(a.id)
        total_points_possible += float(a.points or 0)
        
        score = None
        status = 'missing'
        if sub:
            g = getattr(sub, 'grade', None)
            if g:
                status = 'graded'
                score = float(g.score)
                total_points_earned += score
            else:
                status = 'ungraded'
        
        # Weighted grading: compute weighted earned/possible using weight (%)
        if use_weighted and a.is_weighted and a.weight and float(a.points or 0) > 0:
            w = float(a.weight)
            total_weight_possible += w
            if score is not None:
                pct = max(0.0, min(1.0, float(score) / float(a.points)))
                total_weight_earned += pct * w

        report_data.append({
            'assignment': a,
            'submission': sub,
            'status': status,
            'score': score,
            'class_avg': avg_by_assignment.get(a.id),
        })
        
    if use_weighted and total_weight_possible > 0:
        overall_percentage = (total_weight_earned / total_weight_possible * 100.0)
    else:
        overall_percentage = (total_points_earned / total_points_possible * 100) if total_points_possible > 0 else 0
    
    # Determine base template
    if is_instructor:
        base_template = 'base_professor.html' if course_role == 'INSTRUCTOR' else 'base_grading_assistant.html'
    else:
        base_template = 'portal/base_portal.html'
    
    context = {
        'course': course,
        'student': student,
        'report_data': report_data,
        'total_points_possible': total_points_possible,
        'total_points_earned': total_points_earned,
        'overall_percentage': overall_percentage,
        'base_template': base_template,
        'active_tab': 'grades',
    }
    
    return render(request, 'grading/student_course_report.html', context)


@login_required
@require_http_methods(["GET"])
def download_student_course_report(request, course_id, student_id):
    """
    Downloadable CSV version of the student course report.
    Mirrors the on-page report but excludes class average and action columns.
    """
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    student = get_object_or_404(Student, id=student_id)

    course_role = get_user_course_role(user, course, request)
    is_instructor = course_role in ["INSTRUCTOR", "GRADING_ASSISTANT"]
    is_self_student = (course_role == "STUDENT" and student.user == user)
    if not (is_instructor or is_self_student or user.is_staff):
        return HttpResponseForbidden("You do not have permission to download this report.")

    assignments = Assignment.objects.filter(course=course).order_by("due_date", "id")
    submissions = (
        Submission.objects.filter(student=student, assignment__in=assignments)
        .select_related("grade", "assignment")
    )
    submission_lookup = {sub.assignment_id: sub for sub in submissions}

    total_points_possible = 0.0
    total_points_earned = 0.0
    total_weight_possible = 0.0
    total_weight_earned = 0.0
    use_weighted = assignments.filter(is_weighted=True).exists()
    rows = []

    for a in assignments:
        sub = submission_lookup.get(a.id)
        points_possible = float(a.points or 0)
        total_points_possible += points_possible

        score = None
        status = "missing"
        if sub:
            g = getattr(sub, "grade", None)
            if g:
                status = "graded"
                score = float(g.score)
                total_points_earned += score
            else:
                status = "ungraded"

        if use_weighted and a.is_weighted and a.weight and points_possible > 0:
            w = float(a.weight)
            total_weight_possible += w
            if score is not None:
                pct = max(0.0, min(1.0, float(score) / points_possible))
                total_weight_earned += pct * w

        rows.append({
            "assignment": a,
            "status": status,
            "score": score,
            "points_possible": points_possible,
        })

    if use_weighted and total_weight_possible > 0:
        overall_percentage = (total_weight_earned / total_weight_possible * 100.0)
    else:
        overall_percentage = (
            (total_points_earned / total_points_possible * 100.0)
            if total_points_possible > 0
            else 0.0
        )

    student_name = student.user.get_full_name() or student.user.username or "student"
    course_code = getattr(course, "code", "") or "course"
    safe_base = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{course_code}_{student_name}").strip("_")
    filename = f"student_report_{safe_base}.csv"

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Student Performance Report"])
    writer.writerow(["Student Name", student_name])
    writer.writerow(["Student Email", student.user.email or ""])
    writer.writerow(["Course", f"{course.code}: {course.title}"])
    writer.writerow(["Overall Course Grade (%)", f"{overall_percentage:.1f}"])
    writer.writerow(["Points Earned", f"{total_points_earned:.1f}"])
    writer.writerow(["Points Possible", f"{total_points_possible:.1f}"])
    writer.writerow([])
    writer.writerow(["Assignment", "Due Date", "Status", "Score", "Points Possible"])

    for r in rows:
        a = r["assignment"]
        due = a.due_date.strftime("%Y-%m-%d") if getattr(a, "due_date", None) else ""
        score_str = "" if r["score"] is None else f"{r['score']:.1f}"
        writer.writerow([
            a.name,
            due,
            r["status"],
            score_str,
            f"{r['points_possible']:.1f}",
        ])

    return response


@login_required
@require_http_methods(["POST"])
def run_public_tests_api(request):
    """
    API endpoint to run only public test cases (is_private=False) against student code.
    
    Expects JSON payload:
    {
        "code": "student code here",
        "language": "python" or "java",
        "filename": "main.py",
        "assignment_id": 123
    }
    
    Returns JSON with test results:
    {
        "results": [
            {
                "passed": true/false,
                "expected_output": "...",
                "actual_output": "..."
            },
            ...
        ]
    }
    """
    import json
    from django.http import JsonResponse
    from .execute_view import _run_in_docker_with_input
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    code = data.get('code', '')
    language = data.get('language', 'python')
    filename = data.get('filename', 'main.py')
    assignment_id = data.get('assignment_id')
    
    if not code or not assignment_id:
        return JsonResponse({'error': 'Missing required fields: code, assignment_id'}, status=400)
    
    # Fetch assignment and get public test cases
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)

    user = get_user_from_request(request)
    if assignment.course and not user.is_staff:
        if not is_enrolled(user, assignment.course, request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
    
    # Students may only execute tests marked non-private (faculty "Test" button uses same rule).
    public_test_cases = TestCase.objects.filter(
        assignment=assignment,
        is_private=False,
    ).order_by('order')
    
    if not public_test_cases.exists():
        return JsonResponse({
            'results': []
        })
    
    results = []
    
    for test_case in public_test_cases:
        try:
            # Execute student code with test input
            exec_result = _run_in_docker_with_input(
                code=code,
                language=language,
                filename=filename,
                input_data=test_case.input_data,
                files=data.get('files') if isinstance(data.get('files'), list) else None,
            )

            # Combine stdout and stderr so students can see compile/runtime errors
            stdout = exec_result.get('stdout', '') or ''
            stderr = exec_result.get('stderr', '') or ''
            actual_output = stdout
            if stderr:
                if actual_output:
                    actual_output += "\n"
                actual_output += stderr

            expected_output = test_case.expected_output

            # Simple string comparison (can be extended with normalization)
            passed = actual_output.strip() == expected_output.strip()
            
            results.append({
                'test_case_id': test_case.id,
                'test_name': test_case.name,
                'passed': passed,
                'expected_output': expected_output,
                'actual_output': actual_output,
            })
            
        except Exception as e:
            logger.error(f"Error executing test case {test_case.id}: {e}")
            results.append({
                'test_case_id': test_case.id,
                'test_name': test_case.name,
                'passed': False,
                'expected_output': test_case.expected_output,
                'actual_output': f"Error: {str(e)}",
            })
    
    return JsonResponse({'results': results})

@login_required
def submission_files_api(request, submission_id):
    """API for fetching student submission files for preview."""
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=submission_id)
    
    # Check if user is instructor or student themselves (though this is for prof preview, it should be secure)
    if not is_course_instructor(user, submission.assignment.course, request) and not can_view_submission(user, submission):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    file_path = submission.file_path.path
    files = []
    
    if file_path.endswith('.zip'):
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('/') or name.startswith('__MACOSX'): continue
                    with zf.open(name) as f:
                        try:
                            content = f.read().decode('utf-8')
                            language = 'java' if name.lower().endswith('.java') else 'python'
                            files.append({'name': name, 'content': content, 'language': language})
                        except (UnicodeDecodeError, Exception):
                            continue
        except Exception as e:
            return JsonResponse({'error': f'Failed to open zip: {str(e)}'}, status=500)
    else:
        # Single file
        name = os.path.basename(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                language = 'java' if name.lower().endswith('.java') else 'python'
                files.append({'name': name, 'content': content, 'language': language})
        except Exception as e:
            return JsonResponse({'error': f'Failed to read file: {str(e)}'}, status=500)
            
    return JsonResponse({'files': files})

import zipfile
import io
import os
from django.http import HttpResponseForbidden, Http404

@login_required
def compare_submissions_view(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    course = submission.assignment.course
    
    user = get_user_from_request(request)
    if not is_course_instructor(user, course, request):
        return HttpResponseForbidden("Not authorized to view plagiarism comparisons.")
        
    matched_sub = submission.plagiarism_match
    if not matched_sub:
        raise Http404("No plagiarism match found for this submission.")
        
    def get_source_files(sub):
        files = []
        if not sub.file_path or not hasattr(sub.file_path, 'name'):
            return files
            
        file_name = sub.file_path.name.lower()
        sub.file_path.open('rb')
        content = sub.file_path.read()
        sub.file_path.close()
        
        if file_name.endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
                    for zip_info in zf.infolist():
                        if zip_info.is_dir() or zip_info.filename.startswith('__MACOSX'):
                            continue
                        name = zip_info.filename
                        lower_name = name.lower()
                        if lower_name.endswith('.py') or lower_name.endswith('.java'):
                            try:
                                text = zf.read(name).decode('utf-8', errors='ignore')
                                files.append({'name': name, 'content': text})
                            except Exception:
                                pass
            except Exception:
                pass
        elif file_name.endswith('.py') or file_name.endswith('.java'):
            text = content.decode('utf-8', errors='ignore')
            # Extract just the filename for single uploads
            base_name = os.path.basename(sub.file_path.name)
            files.append({'name': base_name, 'content': text})
        return files

    sub_files = get_source_files(submission)
    match_files = get_source_files(matched_sub)
    
    context = {
        'submission': submission,
        'matched_sub': matched_sub,
        'sub_files': sub_files,
        'match_files': match_files,
        'assignment': submission.assignment,
        'course': course
    }
    
    return render(request, 'compare_submissions.html', context)
