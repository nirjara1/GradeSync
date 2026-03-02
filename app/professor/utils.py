from .models import CourseMember, Course

def get_user_course_role(user, course, request=None):
    """
    Returns the role of the user for a specific course.
    If 'request' is provided, it respects the user's active session dashboard role.
    """
    # 1. Obey the active dashboard role if they actually have that role in the course
    if request:
        active_role = request.session.get('active_role')
        if active_role in ['GRADING_ASSISTANT', 'STUDENT']:
            try:
                member = CourseMember.objects.get(course=course, user=user)
                if member.role_in_course == active_role:
                    return active_role
            except CourseMember.DoesNotExist:
                pass
                
    # 2. Standard fallback evaluation
    if course.professor == user:
        return 'INSTRUCTOR'
        
    try:
        member = CourseMember.objects.get(course=course, user=user)
        return member.role_in_course
    except CourseMember.DoesNotExist:
        return None

def has_course_access(user, course, request=None):
    role = get_user_course_role(user, course, request)
    return role in ['INSTRUCTOR', 'GRADING_ASSISTANT']

def is_enrolled(user, course, request=None):
    role = get_user_course_role(user, course, request)
    return role in ['INSTRUCTOR', 'GRADING_ASSISTANT', 'STUDENT']

def is_course_instructor(user, course, request=None):
    return get_user_course_role(user, course, request) == 'INSTRUCTOR'
