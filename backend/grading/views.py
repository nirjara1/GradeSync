from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseForbidden, FileResponse, Http404
from .models import Assignment, Submission, Grade, Student
from .forms import AssignmentForm, SubmissionForm
from professor.models import Course, UserProfile
from professor.utils import is_course_instructor, has_course_access, is_enrolled, get_user_course_role

from django.contrib.auth.decorators import login_required
import logging

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
    return render(request, 'assignments_dashboard.html', {
        'assignments': assignments, 'course': course,
        'is_instructor': True, 'is_student': False, 'base_template': 'base_professor.html'
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
def edit_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    if not is_course_instructor(user, assignment.course, request):
        return HttpResponseForbidden("Only instructors can edit assignments.")
        
    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment)
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
            monaco_code = request.POST.get('monaco_code', '').strip()
            
            if files or monaco_code:
                if not submission:
                    submission = Submission(student=student_profile, assignment=assignment)
                
                if files:
                    if len(files) > 1:
                        import zipfile
                        import io
                        from django.core.files.base import ContentFile
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w') as zf:
                            for f in files:
                                zf.writestr(f.name, f.read())
                        zip_buffer.seek(0)
                        submission.file_path.save(f"submission_{user.username}_{assignment.id}.zip", ContentFile(zip_buffer.read()))
                    else:
                        submission.file_path = files[0]
                        submission.save()
                elif monaco_code:
                    from django.core.files.base import ContentFile
                    extension = ".java" if assignment.allowed_language == "java" else ".py"
                    filename = f"submission_{user.username}_{assignment.id}{extension}"
                    submission.file_path.save(filename, ContentFile(monaco_code.encode('utf-8')))
                    
                # --- AUTO-GRADER TRIGGER ---
                # This is where we would trigger the backend autograder service.
                # Example: run_autograder(submission.id)
                # The mockup requirements specify this happens automatically on submission.
                
                messages.success(request, "Submission successful.")
                return redirect('assignment_detail', pk=pk)
            else:
                messages.error(request, "Please upload a file or enter code before submitting.")
        else:
            form = SubmissionForm()

    submissions = Submission.objects.filter(assignment=assignment).select_related('student__user', 'grade')
    
    latest_submission = None
    submitted_code = ""
    submitted_language = "plaintext"
    can_preview_code = False
    
    if is_student:
        submissions = submissions.filter(student__user=user)
        latest_submission = submissions.first()
        
        # Monaco Editor Support
        if latest_submission and latest_submission.file_path:
            file_name = latest_submission.file_path.name.lower()
            if hasattr(latest_submission.file_path, 'read'):
                if file_name.endswith('.py'):
                    try:
                        latest_submission.file_path.open('r')
                        submitted_code = latest_submission.file_path.read().decode('utf-8', errors='ignore')
                        submitted_language = 'python'
                        can_preview_code = True
                        latest_submission.file_path.close()
                    except Exception as e:
                        logger.error(f"Error reading python file for preview: {e}")
                elif file_name.endswith('.java'):
                    try:
                        latest_submission.file_path.open('r')
                        submitted_code = latest_submission.file_path.read().decode('utf-8', errors='ignore')
                        submitted_language = 'java'
                        can_preview_code = True
                        latest_submission.file_path.close()
                    except Exception as e:
                        logger.error(f"Error reading java file for preview: {e}")
    
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
    
    context = {
        'assignment': assignment,
        'submissions': submissions,
        'latest_submission': latest_submission,
        'submitted_code': submitted_code,
        'submitted_language': submitted_language,
        'can_preview_code': can_preview_code,
        'is_instructor': is_instructor,
        'is_student': is_student,
        'base_template': base_template,
        'form': form
    }
    return render(request, 'assignment_detail.html', context)

@login_required
def grade_submission_view(request, pk):
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment
    
    if not has_course_access(user, assignment.course, request):
        return HttpResponseForbidden("You do not have permission to grade this assignment.")
        
    grade = getattr(submission, 'grade', None)
    
    if request.method == 'POST':
        score = request.POST.get('score')
        feedback = request.POST.get('feedback', '')
        
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
    if course_role == 'INSTRUCTOR':
        base_template = 'base_professor.html'
    elif course_role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        base_template = 'base_grading_assistant.html'
            
    submitted_code = ""
    submitted_language = "plaintext"
    can_preview_code = False
    
    if submission and submission.file_path:
        file_name = submission.file_path.name.lower()
        if hasattr(submission.file_path, 'read'):
            if file_name.endswith('.py'):
                try:
                    submission.file_path.seek(0)
                    submitted_code = submission.file_path.read().decode('utf-8')
                    submitted_language = 'python'
                    can_preview_code = True
                except Exception as e:
                    logger.error(f"Error reading python file for preview: {e}")
            elif file_name.endswith('.java'):
                try:
                    submission.file_path.seek(0)
                    submitted_code = submission.file_path.read().decode('utf-8')
                    submitted_language = 'java'
                    can_preview_code = True
                except Exception as e:
                    logger.error(f"Error reading java file for preview: {e}")
                    
    context = {
        'submission': submission,
        'grade': grade,
        'base_template': base_template,
        'submitted_code': submitted_code,
        'submitted_language': submitted_language,
        'can_preview_code': can_preview_code
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
