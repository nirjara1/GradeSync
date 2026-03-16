from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Max, Q, Count
from django.http import HttpResponseForbidden, FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .models import Assignment, Submission, Grade, Student, Rubric, RubricCriterion, CriterionGrade, TestCase, RuleSet, TestResult
from .forms import AssignmentForm, SubmissionForm, TestCaseUploadForm, TestCaseForm, RuleSetForm
from .services import grade_submission, extract_code_from_file
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

logger = logging.getLogger(__name__)

def get_user_from_request(request):
    return request.user

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
        assignments = Assignment.objects.filter(course__in=courses).order_by('due_date')
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
        
    assignments = Assignment.objects.filter(course=course).order_by('due_date')
    return render(request, 'assignments_dashboard.html', {
        'assignments': assignments, 'course': course,
        'is_instructor': False, 'is_student': True, 'base_template': 'portal/base_portal.html'
    })

@login_required
def create_assignment(request, course_id=None):
    """Dedicated view for creating an assignment."""
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id) if course_id else None
    
    # Only instructors can create assignments
    if course and not is_course_instructor(user, course, request):
        return HttpResponseForbidden("Only instructors can create assignments.")
        
    if not course:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.role != 'FACULTY' and user.username != 'poudelb2':
            return HttpResponseForbidden("You do not have permission to create assignments.")

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
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
            
            # Process test cases from CSV (if provided)
            test_cases_json = request.POST.get('test_cases_json', '')
            if test_cases_json:
                try:
                    import json
                    test_cases_data = json.loads(test_cases_json)
                    for idx, tc_data in enumerate(test_cases_data, 1):
                        TestCase.objects.create(
                            assignment=assignment,
                            name=f"Test Case {idx}",
                            input_data=tc_data.get('input_data', ''),
                            expected_output=tc_data.get('expected_output', ''),
                            is_private=tc_data.get('is_private', False),
                            points_awarded=tc_data.get('points', 5),
                            order=idx
                        )
                    logger.info(f"Created {len(test_cases_data)} test cases for assignment {assignment.id}")
                except Exception as e:
                    logger.error(f"Error processing test cases for assignment {assignment.id}: {e}")
            
            messages.success(request, f"Assignment '{assignment.name}' successfully {assignment.status}!")
            
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

    course_role = get_user_course_role(user, course, request) if course else ('INSTRUCTOR' if getattr(request, 'user_role', None) == 'FACULTY' else 'GRADING_ASSISTANT')
    
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'

    context = {
        'form': form,
        'course': course,
        'base_template': base_template
    }
    return render(request, 'create_assignment.html', context)


@login_required
def rubric_view(request):
    """Shown when opening rubric from create assignment (no assignment yet)."""
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
                max_order = RubricCriterion.objects.filter(rubric=rubric).aggregate(
                    m=Max('order'))['m'] or 0
                points = request.POST.get('criterion_points')
                weight = request.POST.get('criterion_weight')
                c = RubricCriterion.objects.create(
                    rubric=rubric,
                    name=name,
                    order=max_order + 1,
                    points=float(points or 0) if not rubric.is_weighted else 0,
                    weight=float(weight or 0) if rubric.is_weighted else None,
                )
                messages.success(request, f"Criterion '{name}' added.")
        elif action == 'delete_criterion':
            cid = request.POST.get('criterion_id')
            if cid:
                RubricCriterion.objects.filter(rubric=rubric, id=cid).delete()
                messages.success(request, "Criterion removed.")
        return redirect('assignment_rubric', assignment_id=assignment.id)

    criteria = list(rubric.criteria.all())
    # For weighted criteria, compute points from weight using proper rounding (widthratio truncates and can show 99 for 100)
    total_pts = int(assignment.points) if assignment.points is not None else 0
    criteria_with_display = []
    for c in criteria:
        if rubric.is_weighted and c.weight is not None:
            display_pts = round(float(total_pts) * float(c.weight) / 100)
        else:
            display_pts = int(c.points) if c.points is not None else 0
        criteria_with_display.append({'criterion': c, 'display_points': display_pts})
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
    }
    return render(request, 'rubric.html', context)


@login_required
def edit_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    if not is_course_instructor(user, assignment.course, request):
        return HttpResponseForbidden("Only instructors can edit assignments.")
        
    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, "Assignment updated successfully!")
            course_role = get_user_course_role(user, assignment.course, request)
            route_name = 'professor_course' if course_role == 'INSTRUCTOR' else ('student_course' if course_role == 'STUDENT' else 'ga_course')
            return redirect(route_name, course_id=assignment.course.id)
    else:
        form = AssignmentForm(instance=assignment)
        
    course_role = get_user_course_role(user, assignment.course, request)
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    
    return render(request, 'edit_assignment.html', {'form': form, 'assignment': assignment, 'base_template': base_template})

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
        messages.success(request, "Assignment deleted successfully!")
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
    if is_student:
        student_profile, _ = Student.objects.get_or_create(user=user)
        if request.method == 'POST':
            # Check for existing submission (re-submission)
            submission = Submission.objects.filter(student=student_profile, assignment=assignment).first()
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
                if not submission:
                    submission = Submission(student=student_profile, assignment=assignment)
                
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
        submissions = submissions.filter(student__user=user)
        latest_submission = submissions.first()
        
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
            display_pts = int(c.points) if c.points is not None else 0
        criteria_with_display.append({'criterion': c, 'display_points': display_pts})
    has_rubric = rubric is not None
    context = {
        'assignment': assignment,
        'submissions': submissions,
        'latest_submission': latest_submission,
        'submission_files_json': submission_files_json,
        'can_preview_code': can_preview_code,
        'is_instructor': is_instructor,
        'is_student': is_student,
        'base_template': base_template,
        'form': form,
        'has_rubric': has_rubric,
        'rubric': rubric,
        'criteria_with_display': criteria_with_display,
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

        # All submissions/grades for these assignments/students
        grid_submissions = Submission.objects.filter(
            assignment__in=grid_assignments,
            student__in=grid_students,
        ).select_related('assignment', 'student__user', 'grade')

        cell_lookup = {}
        for sub in grid_submissions:
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
                    status = 'missing'
                    score = None
                else:
                    g = getattr(sub, 'grade', None)
                    if g:
                        status = 'graded'
                        score = float(g.score)
                    else:
                        status = 'ungraded'
                        score = None
                cells.append({
                    "assignment": a,
                    "status": status,
                    "score": score,
                    "submission_id": sub.id if sub else None,
                })

            rows.append({
                "student": stu,
                "cells": cells,
                "active_submission_id": cell_lookup.get((stu.id, assignment.id)).id if cell_lookup.get((stu.id, assignment.id)) else None,
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
    criterion_grades = {}  # criterion_id -> points_earned
    if submission and criteria:
        for cg in CriterionGrade.objects.filter(submission=submission, criterion__in=criteria):
            criterion_grades[cg.criterion_id] = cg.points_earned
    criteria_with_scores = [{'criterion': c, 'points_earned': criterion_grades.get(c.id, 0)} for c in criteria]

    if request.method == 'POST':
        feedback = request.POST.get('feedback', '')
        if rubric and criteria and request.POST.get('submit_grade_rubric'):
            # Save per-criterion scores and total from rubric
            total = 0
            for c in criteria:
                raw = request.POST.get('score_criterion_' + str(c.id), '')
                try:
                    pts = float(raw) if raw else 0
                except ValueError:
                    pts = 0
                total += pts
                CriterionGrade.objects.update_or_create(
                    submission=submission, criterion=c,
                    defaults={'points_earned': pts}
                )
            if grade:
                grade.score = total
                grade.feedback = feedback
                grade.save()
            else:
                Grade.objects.create(submission=submission, score=total, feedback=feedback)
            messages.success(request, "Grade saved. Total: %s / %s" % (total, assignment.points))
            if next_submission:
                return redirect('grade_submission', pk=next_submission.pk)
            return redirect('gradebook', pk=assignment.pk)
        # Single score (no rubric)
        score = request.POST.get('score')
        if score:
            try:
                score_val = float(score)
                if grade:
                    grade.score = score_val
                    grade.feedback = feedback
                    grade.save()
                    messages.success(request, "Grade updated successfully.")
                else:
                    Grade.objects.create(
                        submission=submission,
                        score=score_val,
                        feedback=feedback
                    )
                messages.success(request, "Grade submitted successfully.")
                return redirect('assignment_detail', pk=assignment.pk)
            except ValueError:
                messages.error(request, "Invalid score submitted.")
        else:
            messages.error(request, "Score is required.")
            
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
    if getattr(request, 'user_role', None) == 'STUDENT' and submission.student.user != user:
        return HttpResponseForbidden("You can only download your own submissions.")
        
    if not has_course_access(user, submission.assignment.course, request) and submission.student.user != user:
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
    
    # Check permissions - only the submitting student can delete it
    if submission.student.user != user:
        return HttpResponseForbidden("You can only delete your own submissions.")
        
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
                
                # Create TestCase objects
                created_count = 0
                for idx, tc in enumerate(test_cases):
                    TestCase.objects.create(
                        assignment=assignment,
                        name=tc.get('name', f'Test {max_order + idx + 1}'),
                        description=tc.get('description', ''),
                        input_data=tc.get('input_data', ''),
                        expected_output=tc.get('expected_output', ''),
                        points_awarded=float(tc.get('points_awarded', 1)),
                        is_hidden=tc.get('is_hidden', False),
                        is_private=tc.get('is_private', False),
                        order=max_order + idx + 1,
                    )
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
    is_student_owner = submission.student.user == user
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
    is_student_owner = submission.student.user == user
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
    
    # Get existing submission if any
    submission = Submission.objects.filter(
        student=student_profile,
        assignment=assignment
    ).first()
    
    # Handle file upload
    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            if not submission:
                submission = Submission(student=student_profile, assignment=assignment)
            
            submission.file_path = form.cleaned_data['file_path']
            submission.save()
            
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
    
    # Get all submissions for this assignment
    submissions = Submission.objects.filter(
        assignment=assignment
    ).select_related('student__user')
    
    submission_dict = {sub.student_id: sub for sub in submissions}
    
    # Get all test results for these submissions in one query
    all_results = TestResult.objects.filter(
        submission__assignment=assignment
    ).select_related('submission', 'test_case')
    
    # Organize results: submission_id -> test_case_id -> result_object
    results_map = {}
    for res in all_results:
        if res.submission_id not in results_map:
            results_map[res.submission_id] = {}
        results_map[res.submission_id][res.test_case_id] = res
    
    def get_status_label(result):
        if not result:
            return 'UNGRADED'
        if result.passed:
            return 'PASS'
        err = (result.error_message or '').lower()
        if 'timeout' in err:
            return 'TIMEOUT'
        if result.error_message:
            return 'ERROR'
        return 'FAIL'

    # Build grade report data
    grade_data = []
    
    for student in students:
        submission = submission_dict.get(student.id)
        
        student_results = []
        passed_count = 0
        
        if submission:
            sub_results = results_map.get(submission.id, {})
            for tc in test_cases:
                res = sub_results.get(tc.id)
                status = get_status_label(res)
                if status == 'PASS':
                    passed_count += 1
                
                student_results.append({
                    'test_case_id': tc.id,
                    'status': status,
                    'actual': res.actual_output if res else '',
                    'expected': tc.expected_output,
                    'error': res.error_message if res else '',
                    'time': res.execution_time if res else 0
                })
            
            total_tests = len(test_cases)
            pass_rate = round((passed_count / total_tests * 100) if total_tests > 0 else 0, 1)
            
            # Safe access to grade (from incoming branch)
            g = getattr(submission, 'grade', None)
            
            grade_data.append({
                'id': student.id,
                'name': student.user.get_full_name() or student.user.username,
                'email': student.user.email,
                'submission_id': submission.id,
                'status': submission.status.upper(),
                'submitted_at': submission.submission_time,
                'score': submission.total_score,
                'max_score': submission.max_score,
                'passed_tests': passed_count,
                'total_tests': total_tests,
                'pass_rate': pass_rate,
                'test_results': student_results,
                'has_submission': True,
                'grade': g,
            })
        else:
            # No submission
            for tc in test_cases:
                student_results.append({
                    'test_case_id': tc.id,
                    'status': 'NOT SUBMITTED'
                })
                
            grade_data.append({
                'id': student.id,
                'name': student.user.get_full_name() or student.user.username,
                'email': student.user.email,
                'status': 'NOT SUBMITTED',
                'passed_tests': 0,
                'total_tests': len(test_cases),
                'pass_rate': 0,
                'score': 0,
                'max_score': assignment.points,
                'test_results': student_results,
                'has_submission': False
            })
    
    # Sort by name
    grade_data.sort(key=lambda x: x['name'])
    
    # Calculate statistics
    total_students = len(grade_data)
    submitted_count = sum(1 for g in grade_data if g['has_submission'])
    missing_count = total_students - submitted_count
    
    graded_subs = [g for g in grade_data if g['has_submission']]
    avg_score = sum(g['score'] for g in graded_subs) / submitted_count if submitted_count > 0 else 0
    avg_pass_rate = sum(g['pass_rate'] for g in graded_subs) / submitted_count if submitted_count > 0 else 0
    
    context = {
        'assignment': assignment,
        'test_cases': test_cases,
        'grade_data': grade_data,
        'total_students': total_students,
        'submitted': submitted_count,
        'missing': missing_count,
        'avg_score': round(avg_score, 2),
        'max_score': assignment.points or 100,
        'avg_pass_rate': round(avg_pass_rate, 1),
        'base_template': 'base_professor.html' if course_role == 'INSTRUCTOR' else 'base_grading_assistant.html'
    }
    
    return render(request, 'grading/grade_report.html', context)


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
    
    # Get only public test cases (is_private=False)
    public_test_cases = TestCase.objects.filter(
        assignment=assignment,
        is_private=False
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
                input_data=test_case.input_data
            )
            
            actual_output = exec_result.get('stdout', '')
            expected_output = test_case.expected_output
            
            # Simple string comparison (can be extended with normalization)
            passed = actual_output.strip() == expected_output.strip()
            
            results.append({
                'test_case_id': test_case.id,
                'passed': passed,
                'expected_output': expected_output,
                'actual_output': actual_output
            })
            
        except Exception as e:
            logger.error(f"Error executing test case {test_case.id}: {e}")
            results.append({
                'passed': False,
                'expected_output': test_case.expected_output,
                'actual_output': f"Error: {str(e)}",
                'test_name': test_case.name
            })
    
    return JsonResponse({'results': results})
