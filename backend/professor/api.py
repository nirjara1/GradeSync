from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Course, CourseMember, UserProfile
import json
import csv
import io

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
    
    emails = []
    
    # 1. Parse manual emails from FormData
    manual_emails_raw = request.POST.get('manual_emails', '[]')
    try:
        manual_emails = json.loads(manual_emails_raw)
        if isinstance(manual_emails, list):
            emails.extend(manual_emails)
    except json.JSONDecodeError:
        pass
        
    # 2. Parse CSV file if provided
    csv_file = request.FILES.get('csv_file')
    if csv_file:
        try:
            # Decode file safely (handling optional BOM)
            file_data = csv_file.read().decode('utf-8-sig', errors='replace')
            reader = csv.DictReader(io.StringIO(file_data))
            
            # Find the header matching "sis login id" (case-insensitive, tolerant of underscores/spaces)
            if reader.fieldnames:
                sis_col = None
                for header in reader.fieldnames:
                    normalized = header.lower().replace('_', ' ').strip()
                    if normalized == 'sis login id' or normalized == 'sis loginid':
                        sis_col = header
                        break
                
                if sis_col:
                    for row in reader:
                        raw_id = row.get(sis_col, "").strip()
                        if raw_id:
                            csv_email = f"{raw_id}@warhawks.ulm.edu"
                            emails.append(csv_email)
        except Exception as e:
            return JsonResponse({'error': f'Error parsing CSV: {str(e)}'}, status=400)
    
    if not emails:
        return JsonResponse({'error': 'No emails or valid CSV provided'}, status=400)
    
    # 3. Deduplicate
    unique_emails = []
    seen = set()
    for e in emails:
        clean_e = str(e).strip().lower()
        if clean_e and clean_e not in seen:
            seen.add(clean_e)
            unique_emails.append(clean_e)
            
    results = []
    
    for email in unique_emails:
            
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
