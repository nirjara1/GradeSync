from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .models import Course, CourseMember, UserProfile, PendingEnrollment
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
            # Pre-enroll as whatever role was requested
            PendingEnrollment.objects.get_or_create(
                course=course,
                email=email,
                role_in_course=expected_role
            )
            results.append({"email": email, "status": "pending"})
            continue
            
        # Verify role: Allow STUDENT profile role to be used as either STUDENT or GRADING_ASSISTANT in course
        profile, _ = UserProfile.objects.get_or_create(user=user)
        # Any user can be added as a student, but only students can be added as grading assistants (or as specifically requested)
        # However, the user specifically requested that ANY student can be a GA. 
        # If the expected role is GRADING_ASSISTANT, we allow it if the user is a STUDENT.
        if profile.role == 'FACULTY' and expected_role != 'FACULTY':
             # Faculty shouldn't be added as students/graders usually, but let's stick to the rule: 
             # currently only FACULTY and STUDENT exist.
             results.append({"email": email, "status": "wrong_role"})
             continue
        
        # If the user is a STUDENT, they can be a STUDENT or a GRADING_ASSISTANT in a course.
        # So we don't strictly enforce profile.role == expected_role if profile.role is STUDENT.
        if profile.role != 'STUDENT' and profile.role != expected_role:
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

    # Include pending students and graders
    pending_members = PendingEnrollment.objects.filter(course=course)
    for pm in pending_members:
        member_info = {
            "id": None,
            "username": pm.email,
            "email": pm.email,
            "first_name": "",
            "last_name": "(pending)",
            "added_at": pm.created_at.strftime('%b %d, %Y'),
            "is_pending": True
        }
        if pm.role_in_course == 'STUDENT':
            students.append(member_info)
        elif pm.role_in_course == 'GRADING_ASSISTANT':
            graders.append(member_info)
            
    return JsonResponse({
        "students": students,
        "graders": graders
    })

@require_POST
def remove_member_api(request, course_id):
    current_user = get_user_from_request(request)
    course = get_object_or_404(Course, id=course_id, professor=current_user)
    
    data = json.loads(request.body)
    user_id = data.get('user_id')
    email = data.get('email')
    is_pending = data.get('is_pending', False)
    
    if is_pending and email:
        # Remove from pending enrollments
        deleted_count, _ = PendingEnrollment.objects.filter(course=course, email__iexact=email).delete()
        if deleted_count > 0:
            return JsonResponse({"status": "removed", "email": email})
        return JsonResponse({"error": "Pending enrollment not found"}, status=404)
    
    elif user_id:
        # Remove from CourseMember
        deleted_count, _ = CourseMember.objects.filter(course=course, user_id=user_id).delete()
        if deleted_count > 0:
            return JsonResponse({"status": "removed", "user_id": user_id})
        return JsonResponse({"error": "Course member not found"}, status=404)
        
    return JsonResponse({"error": "Invalid request parameters"}, status=400)
