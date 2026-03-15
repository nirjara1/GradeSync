from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from professor.models import CourseMember, UserProfile

@login_required
def student_dashboard_view(request):
    try:
        profile = UserProfile.objects.get(user=request.user)
        if profile.role != 'STUDENT':
            # Not a student, send them to the professor dashboard as fallback
            return redirect('professor_dashboard')
    except UserProfile.DoesNotExist:
        # Default behavior for users without a profile
        if request.user.is_superuser or request.user.is_staff:
             return redirect('professor_dashboard')
        return redirect('login')

    # Get the courses this user is enrolled in as a STUDENT
    enrollments = CourseMember.objects.filter(
        user=request.user,
        role_in_course='STUDENT'
    ).select_related('course', 'course__professor')

    # Extract the actual courses
    courses = [enrollment.course for enrollment in enrollments]

    context = {
        'courses': courses,
    }
    
    return render(request, 'portal/dashboard.html', context)


@login_required
def user_profile_view(request):
    """Placeholder user profile page (to be implemented)."""
    return render(request, 'portal/user_profile.html')
