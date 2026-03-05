from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Course, CourseMember, UserProfile
import json

def get_user_from_request(request):
    if request.user.is_authenticated:
        return request.user
    # Mock user for prototype preview
    user, _ = User.objects.get_or_create(username='poudelb2')
    return user

@require_POST
def add_students_api(request, course_id):
    return _add_members(request, course_id, expected_role='STUDENT')

@require_POST
def add_graders_api(request, course_id):
    return _add_members(request, course_id, expected_role='GRADING_ASSISTANT')

def _add_members(request, course_id, expected_role):
    # Verify faculty owns the course
    current_user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id, professor=current_user)
    
    try:
        data = json.loads(request.body)
        emails = data.get('emails', [])
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not emails:
        return JsonResponse({'error': 'No emails provided'}, status=400)
    
    results = []
    
    for raw_email in emails:
        email = str(raw_email).strip().lower()
        if not email:
            continue
            
        try:
            # Look up user by email
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            results.append({"email": email, "status": "not_found"})
            continue
            
        # Verify role (assuming missing UserProfile defaults to STUDENT for backwards compatibility, or creating one)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.role != expected_role:
            results.append({"email": email, "status": "wrong_role"})
            continue
            
        # Prevent duplicates
        if CourseMember.objects.filter(course=course, user=user).exists():
            results.append({"email": email, "status": "already_added"})
            continue
            
        # Add to course
        CourseMember.objects.create(
            course=course,
            user=user,
            role_in_course=expected_role
        )
        results.append({"email": email, "status": "added"})
        
    return JsonResponse({"results": results})

@require_GET
def course_roster_api(request, course_id):
    # Retrieve course members for UI
    course = get_object_or_404(Course, id=course_id)
    members = CourseMember.objects.filter(course=course).select_related('user')
    
    students = []
    graders = []
    for member in members:
        user_info = {
            "id": member.user.id,
            "username": member.user.username,
            "email": member.user.email,
            "first_name": member.user.first_name,
            "last_name": member.user.last_name,
            "added_at": member.added_at.strftime('%b %d, %Y')
        }
        if member.role_in_course == 'STUDENT':
            students.append(user_info)
        elif member.role_in_course == 'GRADING_ASSISTANT':
            graders.append(user_info)
            
    return JsonResponse({
        "students": students,
        "graders": graders
    })
