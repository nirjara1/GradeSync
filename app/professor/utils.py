from .models import CourseMember, Course

def get_user_course_role(user, course):
    """
    Returns the role of the user for a specific course:
    - 'INSTRUCTOR' if the user is the professor who created the course.
    - 'GRADING_ASSISTANT' if the user is a CourseMember with that role.
    - 'STUDENT' if the user is a CourseMember with that role.
    - None if the user has no access.
    """
    if course.professor == user:
        return 'INSTRUCTOR'
        
    try:
        member = CourseMember.objects.get(course=course, user=user)
        return member.role_in_course
    except CourseMember.DoesNotExist:
        return None

def has_course_access(user, course):
    """
    Returns True if the user is an INSTRUCTOR or GRADING_ASSISTANT.
    """
    role = get_user_course_role(user, course)
    return role in ['INSTRUCTOR', 'GRADING_ASSISTANT']

def is_course_instructor(user, course):
    """
    Returns True only if the user is the INSTRUCTOR (professor) of the course.
    """
    return get_user_course_role(user, course) == 'INSTRUCTOR'
