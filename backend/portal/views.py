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

    # Get the courses this user is enrolled in as a STUDENT or GRADING_ASSISTANT
    enrollments = CourseMember.objects.filter(
        user=request.user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT']
    ).select_related('course', 'course__professor')

    context = {
        'enrollments': enrollments,
    }
    
    return render(request, 'portal/dashboard.html', context)
