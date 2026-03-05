from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from .models import Course, UserProfile
from django.contrib.auth.models import User
from .forms import CourseForm, UserRegistrationForm
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from .utils import is_course_instructor

def get_user_from_request(request):
    return request.user

@login_required
def dashboard(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    
    # Get courses where user is professor
    courses = Course.objects.filter(professor=user).distinct()
    
    # Check if user is primarily a faculty member to show 'Create Class' button
    profile, _ = UserProfile.objects.get_or_create(user=user)
    is_faculty = profile.role == 'FACULTY'

    # The original mock 'poudelb2' is treated as a faculty member by default in our context
    if user.username == 'poudelb2':
        is_faculty = True
    
    context = {
        'courses': courses,
        'is_faculty': is_faculty,
    }
    return render(request, 'professor_dashboard.html', context)

@login_required
def ga_dashboard(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'GRADING_ASSISTANT'
    
    # Get courses where user is a Grading Assistant
    courses = Course.objects.filter(
        members__user=user, 
        members__role_in_course='GRADING_ASSISTANT'
    ).distinct()
    
    context = {
        'courses': courses,
    }
    return render(request, 'ga_dashboard.html', context)

@login_required
def create_course(request):
    user = get_user_from_request(request)
    
    # Enforce RBAC: only faculty can create courses
    profile, _ = UserProfile.objects.get_or_create(user=user)
    allowed_roles = ['FACULTY', 'INSTRUCTOR', 'PROFESSOR']
    if str(profile.role).upper() not in allowed_roles and user.username != 'poudelb2':
        messages.error(request, f"You ({profile.role}) do not have permission to create courses.")
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
    }
    return render(request, 'create_course.html', context)

def register_view(request):
    if request.user.is_authenticated:
        return redirect('professor_dashboard')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            role = form.cleaned_data['role']

            # Create the Django User
            user = User.objects.create_user(username=email, email=email, password=password)
            
            # Create the UserProfile
            UserProfile.objects.create(user=user, role=role)

            # Log the user in
            login(request, user)
            
            messages.success(request, f"Welcome to GradeSync! Your {role.lower().replace('_', ' ')} account has been created.")
            
            if role == 'STUDENT':
                return redirect('student_dashboard')
            elif role == 'GRADING_ASSISTANT':
                return redirect('ga_dashboard')
            else:
                return redirect('professor_dashboard')
    else:
        form = UserRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})

class CustomLoginView(LoginView):
    def get_success_url(self):
        # Default destination fallback
        url = super().get_success_url()
        
        # Try to get the user's profile role
        try:
            profile = UserProfile.objects.get(user=self.request.user)
            if profile.role == 'FACULTY':
                url = '/professor/dashboard/'
            elif profile.role == 'STUDENT':
                url = '/student/dashboard/'  # Make sure this matches your student UI route
            elif profile.role == 'GRADING_ASSISTANT':
                url = '/ga/dashboard/'  # Modify if GA has a distinct dashboard
        except UserProfile.DoesNotExist:
            # If no profile, perhaps they are a superuser, default to professor dashboard
            pass
            
        return url
