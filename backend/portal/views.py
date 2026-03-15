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

from django.contrib import messages
from django.db.models import Q
from professor.models import Message, Course
from django.contrib.auth.models import User

@login_required
def student_profile(request):
    user = request.user
    request.session['active_role'] = 'STUDENT'
    
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        # Update User model fields
        full_name = request.POST.get('full_name', '').strip()
        if full_name:
            parts = full_name.split(' ', 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]
            else:
                user.last_name = ''
            user.save()
            
        # Update UserProfile fields
        profile_obj.department = request.POST.get('department', '')  # Used as major
        profile_obj.bio = request.POST.get('bio', '')
        
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            profile_obj.profile_picture = request.FILES['profile_picture']
            
        profile_obj.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('student_profile')
    
    context = {
        'profile': profile_obj,
    }
    return render(request, 'portal/student_profile.html', context)

@login_required
def student_courses_list(request):
    request.session['active_role'] = 'STUDENT'
    enrollments = CourseMember.objects.filter(
        user=request.user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT']
    ).select_related('course', 'course__professor')
    return render(request, 'portal/student_courses.html', {'enrollments': enrollments})

@login_required
def student_assignments(request):
    request.session['active_role'] = 'STUDENT'
    # For now, just a placeholder view like the professor's reports
    # In a real app, this would fetch assignments from enrolled courses
    return render(request, 'portal/student_assignments.html')

@login_required
def student_inbox(request):
    user = request.user
    request.session['active_role'] = 'STUDENT'
    
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
        
    contacts = User.objects.exclude(id=user.id).exclude(is_superuser=True)
    
    active_user_id = request.GET.get('user_id')
    active_user = None
    chat_messages = []
    
    if active_user_id:
        try:
            active_user = User.objects.get(id=active_user_id)
            chat_messages = Message.objects.filter(
                Q(sender=user, recipient=active_user) | 
                Q(sender=active_user, recipient=user)
            ).order_by('timestamp')
            
            Message.objects.filter(sender=active_user, recipient=user, is_read=False).update(is_read=True)
            
        except User.DoesNotExist:
            pass

    context = {
        'contacts': contacts,
        'active_user': active_user,
        'chat_messages': chat_messages,
    }
    return render(request, 'portal/student_inbox.html', context)

@login_required
def student_help(request):
    request.session['active_role'] = 'STUDENT'
    return render(request, 'portal/student_help.html')

import json
from django.core.serializers.json import DjangoJSONEncoder
from grading.models import Assignment

@login_required
def student_calendar_view(request):
    request.session['active_role'] = 'STUDENT'
    
    # Fetch assignments for courses the student is enrolled in
    assignments = Assignment.objects.filter(
        course__members__user=request.user, 
        course__members__role_in_course__in=['STUDENT', 'GRADING_ASSISTANT'],
        due_date__isnull=False
    ).distinct()
    
    # Serialize for FullCalendar
    events = []
    for assignment in assignments:
        # Determine URL based on GA vs Student
        is_ga = assignment.course.members.filter(user=request.user, role_in_course='GRADING_ASSISTANT').exists()
        url = f"/ga/classes/{assignment.course.id}/" if is_ga else f"/student/classes/{assignment.course.id}/"
        
        events.append({
            'title': f"{assignment.course.code}: {assignment.name}",
            'start': assignment.due_date.isoformat(),
            'url': url,
            'backgroundColor': '#fdb913' if is_ga else 'var(--maroon)',
            'borderColor': '#fdb913' if is_ga else 'var(--maroon)'
        })
        
    context = {
        'events_json': json.dumps(events, cls=DjangoJSONEncoder)
    }
    
    return render(request, 'portal/student_calendar.html', context)
