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
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    is_faculty = profile_obj.role == 'FACULTY'

    # The original mock 'poudelb2' is treated as a faculty member by default in our context
    if user.username == 'poudelb2':
        is_faculty = True
    
    context = {
        'courses': courses,
        'is_faculty': is_faculty,
    }
    return render(request, 'professor_dashboard.html', context)

@login_required
def profile(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        # Update User model fields
        full_name = request.POST.get('full_name', '').strip()
        if full_name:
            # Simple split for first and last name
            parts = full_name.split(' ', 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]
            else:
                user.last_name = ''
            user.save()
            
        # Update UserProfile fields
        profile_obj.academic_title = request.POST.get('academic_title', '')
        profile_obj.department = request.POST.get('department', '')
        profile_obj.office_location = request.POST.get('office_location', '')
        profile_obj.office_hours = request.POST.get('office_hours', '')
        profile_obj.bio = request.POST.get('bio', '')
        
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            profile_obj.profile_picture = request.FILES['profile_picture']
            
        profile_obj.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('professor_profile')
    
    context = {
        'profile': profile_obj,
    }
    return render(request, 'professor_profile.html', context)

@login_required
def courses_list(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    courses = Course.objects.filter(professor=user).distinct()
    return render(request, 'professor_courses.html', {'courses': courses})

@login_required
def reports(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    courses = Course.objects.filter(professor=user).distinct()
    return render(request, 'professor_reports.html', {'courses': courses})

from .models import Course, UserProfile, Message

@login_required
def inbox(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    
    # Handle sending a message
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient_id')
        body = request.POST.get('body')
        if recipient_id and body:
            try:
                recipient = User.objects.get(id=recipient_id)
                Message.objects.create(sender=user, recipient=recipient, body=body.strip())
                messages.success(request, f"Message sent to {recipient.first_name or recipient.username}!")
            except User.DoesNotExist:
                messages.error(request, "Recipient not found.")
        return redirect(f"{request.path}?user_id={recipient_id}" if recipient_id else request.path)
        
    # Get all users (for a real app, you'd filter this to just faculty/students in their courses)
    # Exclude current user and superusers
    contacts = User.objects.exclude(id=user.id).exclude(is_superuser=True)
    
    active_user_id = request.GET.get('user_id')
    active_user = None
    chat_messages = []
    
    if active_user_id:
        try:
            active_user = User.objects.get(id=active_user_id)
            # Fetch messages between current user and active user
            chat_messages = Message.objects.filter(
                Q(sender=user, recipient=active_user) | 
                Q(sender=active_user, recipient=user)
            ).order_by('timestamp')
            
            # Mark received messages from this user as read
            Message.objects.filter(sender=active_user, recipient=user, is_read=False).update(is_read=True)
            
        except User.DoesNotExist:
            pass

    context = {
        'contacts': contacts,
        'active_user': active_user,
        'chat_messages': chat_messages,
    }
    return render(request, 'professor_inbox.html', context)

@login_required
def help_page(request):
    user = get_user_from_request(request)
    request.session['active_role'] = 'INSTRUCTOR'
    return render(request, 'professor_help.html')

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
        # Superusers go straight to admin, not professor dashboard
        if request.user.is_superuser or request.user.is_staff:
            return redirect('/admin/')
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
            else:
                return redirect('professor_dashboard')
    else:
        form = UserRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})

class CustomLoginView(LoginView):
    """
    Priority order for post-login redirect:
      1. Superuser / staff  →  Django admin panel  (/admin/)
      2. FACULTY            →  Professor dashboard (/professor/dashboard/)
      3. STUDENT            →  Student dashboard   (/student/dashboard/)
      4. No profile found   →  Falls back to LOGIN_REDIRECT_URL
    """
    def get_success_url(self):
        user = self.request.user

        # ── Priority 1: Django superuser / staff → Admin panel ──────────────
        if user.is_superuser or user.is_staff:
            return '/admin/'

        # ── Priority 2-4: Role from UserProfile ─────────────────────────────
        try:
            profile = UserProfile.objects.get(user=user)
            if profile.role == 'FACULTY':
                return '/professor/dashboard/'
            elif profile.role == 'STUDENT':
                return '/student/dashboard/'
        except UserProfile.DoesNotExist:
            pass

        # ── Fallback: LOGIN_REDIRECT_URL defined in settings.py ─────────────
        return super().get_success_url()
