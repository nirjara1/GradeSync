from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from .models import Course, UserProfile
from django.contrib.auth.models import User
from .forms import CourseForm
from .utils import is_course_instructor

def get_user_from_request(request):
    if request.user.is_authenticated:
        return request.user
    # Mock user for prototype preview
    user, _ = User.objects.get_or_create(username='poudelb2')
    return user

def dashboard(request):
    user = get_user_from_request(request)
    
    # Get courses where user is professor OR a Grading Assistant
    courses = Course.objects.filter(
        Q(professor=user) | 
        Q(members__user=user, members__role_in_course='GRADING_ASSISTANT')
    ).distinct()
    
    # Check if user is primarily a faculty member to show 'Create Class' button
    profile, _ = UserProfile.objects.get_or_create(user=user)
    is_faculty = profile.role == 'FACULTY'

    # The original mock 'poudelb2' is treated as a faculty member by default in our context
    if user.username == 'poudelb2':
        is_faculty = True
    
    context = {
        'courses': courses,
        'display_username': user.username,
        'is_faculty': is_faculty,
    }
    return render(request, 'professor_dashboard.html', context)

def create_course(request):
    user = get_user_from_request(request)
    
    # Enforce RBAC: only faculty can create courses
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.role != 'FACULTY' and user.username != 'poudelb2':
        messages.error(request, "You do not have permission to create courses.")
        return redirect('professor_dashboard')
    
    if request.method == 'POST':
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.professor = user
            course.save()
            messages.success(request, f"Class '{course.title}' created successfully!")
            return redirect('professor_dashboard')
        else:
            messages.error(request, "Error creating class. Please check the form data.")
    else:
        form = CourseForm()
        
    context = {
        'form': form,
        'display_username': user.username
    }
    return render(request, 'create_course.html', context)
