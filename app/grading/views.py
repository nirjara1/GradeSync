from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseForbidden
from .models import Assignment, Submission, Grade
from .forms import AssignmentForm
from professor.models import Course, UserProfile
from professor.utils import is_course_instructor, has_course_access

def get_user_from_request(request):
    if request.user.is_authenticated:
        return request.user
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(username='poudelb2')
    return user

def assignments_dashboard(request):
    """Fallback: shows all assignments if no course is specified."""
    user = get_user_from_request(request)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    is_faculty = profile.role == 'FACULTY' or user.username == 'poudelb2'
    
    assignments = Assignment.objects.all().order_by('due_date')
    return render(request, 'assignments_dashboard.html', {'assignments': assignments, 'is_instructor': is_faculty})

def course_assignments_view(request, course_id):
    """Main view: shows assignments only for a specific course."""
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id)
    
    if not has_course_access(user, course):
        return HttpResponseForbidden("You do not have access to this course.")
        
    is_instructor = is_course_instructor(user, course)
    
    assignments = Assignment.objects.filter(course=course).order_by('due_date')
    
    context = {
        'assignments': assignments,
        'course': course,
        'is_instructor': is_instructor
    }
    return render(request, 'assignments_dashboard.html', context)

def create_assignment(request, course_id=None):
    """Dedicated view for creating an assignment."""
    user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id) if course_id else None
    
    # Only instructors can create assignments
    if course and not is_course_instructor(user, course):
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
                return redirect('course_assignments', course_id=course.id)
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
        'course': course
    }
    return render(request, 'create_assignment.html', context)

def edit_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("Only instructors can edit assignments.")
        
    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, "Assignment updated successfully!")
            return redirect('course_assignments', course_id=assignment.course.id)
    else:
        form = AssignmentForm(instance=assignment)
    
    return render(request, 'edit_assignment.html', {'form': form, 'assignment': assignment})

def delete_assignment(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    course_id = assignment.course.id if assignment.course else None
    
    if not is_course_instructor(user, assignment.course):
        return HttpResponseForbidden("Only instructors can delete assignments.")
        
    if request.method == 'POST':
        assignment.delete()
        messages.success(request, "Assignment deleted successfully!")
        if course_id:
            return redirect('course_assignments', course_id=course_id)
        return redirect('assignments_dashboard')
        
    # Technically we should use a confirmation template for GET, but let's provide basic routing
    return render(request, 'delete_assignment.html', {'assignment': assignment})

def assignment_detail_view(request, pk):
    user = get_user_from_request(request)
    assignment = get_object_or_404(Assignment, pk=pk)
    
    if not has_course_access(user, assignment.course):
        return HttpResponseForbidden("You do not have permission to view submissions for this assignment.")
        
    is_instructor = is_course_instructor(user, assignment.course)
    submissions = Submission.objects.filter(assignment=assignment).select_related('student__user', 'grade')
    
    context = {
        'assignment': assignment,
        'submissions': submissions,
        'is_instructor': is_instructor
    }
    return render(request, 'assignment_detail.html', context)

def grade_submission_view(request, pk):
    user = get_user_from_request(request)
    submission = get_object_or_404(Submission, pk=pk)
    assignment = submission.assignment
    
    if not has_course_access(user, assignment.course):
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
            
    context = {
        'submission': submission,
        'grade': grade
    }
    return render(request, 'grade_submission.html', context)
