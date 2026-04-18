from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from professor.models import CourseMember, UserProfile
from django.utils import timezone
from django.db.models import Q
from django.http import HttpResponseForbidden

from grading.models import Assignment, Submission, Student
from grading.group_services import get_effective_submission_for_student
from professor.utils import get_user_course_role

from .gradebook_utils import course_grade_totals, build_student_course_gradebook_section

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

    # Get course IDs to filter assignments
    course_ids = enrollments.values_list('course_id', flat=True)

    # To-Do Items
    from professor.models import ToDoItem
    todo_items = ToDoItem.objects.filter(user=request.user)

    # Upcoming Assignments
    student_profile = getattr(request.user, 'student_profile', None)
    
    if student_profile:
        # Assignments not submitted, due in future
        submitted_assignment_ids = set(
            Submission.objects.filter(student=student_profile).values_list('assignment_id', flat=True)
        )
        submitted_assignment_ids.update(
            Submission.objects.filter(group__members__student=student_profile).values_list('assignment_id', flat=True)
        )
        now = timezone.now()
        upcoming_assignments = (
            Assignment.objects.filter(course__in=course_ids)
            .exclude(id__in=submitted_assignment_ids)
            .filter(Q(no_due_date=True) | Q(due_date__isnull=True) | Q(due_date__gte=now))
            .order_by('due_date', 'id')[:5]
        )
        
        # Recent Submissions by this student
        recent_submissions = Submission.objects.filter(
            student=student_profile
        ).order_by('-submission_time')[:5]
    else:
        upcoming_assignments = []
        recent_submissions = []

    # Per-course overall percentage for dashboard cards (same totals logic as gradebook/report)
    enrolled_courses = [e.course for e in enrollments]
    if student_profile and enrolled_courses:
        all_assignments = list(
            Assignment.objects.filter(course__in=enrolled_courses, status='published')
            .order_by('course_id', 'due_date', 'id')
        )
        sub_by_assignment = {a.id: get_effective_submission_for_student(a, student_profile) for a in all_assignments}
        assignments_by_course = {}
        for a in all_assignments:
            assignments_by_course.setdefault(a.course_id, []).append(a)

        for enrollment in enrollments:
            course_assignments = assignments_by_course.get(enrollment.course_id, [])
            pct, _, _ = course_grade_totals(course_assignments, sub_by_assignment, respect_grade_release=True)
            enrollment.course_percentage = pct
    else:
        for enrollment in enrollments:
            enrollment.course_percentage = None

    context = {
        'enrollments': enrollments,
        'todo_items': todo_items,
        'upcoming_assignments': upcoming_assignments,
        'recent_submissions': recent_submissions,
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
    student_obj, _ = Student.objects.get_or_create(user=user)

    if request.method == 'POST':
        # Identity fields (full name, email, CWID, role) are not editable here—only registration/admin.
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
        'student': student_obj,
    }
    return render(request, 'portal/student_profile.html', context)

@login_required
def student_courses_list(request):
    request.session['active_role'] = 'STUDENT'
    enrollments = list(CourseMember.objects.filter(
        user=request.user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT']
    ).select_related('course', 'course__professor'))
    
    active_enrollments = [e for e in enrollments if not e.course.is_archived]
    archived_enrollments = [e for e in enrollments if e.course.is_archived]

    return render(request, 'portal/student_courses.html', {
        'enrollments': enrollments,
        'active_enrollments': active_enrollments,
        'archived_enrollments': archived_enrollments
    })

@login_required
def student_assignments(request):
    request.session['active_role'] = 'STUDENT'
    
    # Fetch all courses the student is enrolled in
    enrollments = CourseMember.objects.filter(
        user=request.user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT']
    ).select_related('course')
    courses = [e.course for e in enrollments]

    student_profile, _ = Student.objects.get_or_create(user=request.user)
    
    # Fetch all published assignments for these courses
    assignments = (
        Assignment.objects.filter(course__in=courses, status='published')
        .order_by('due_date', 'id')
    )
    
    # Fetch submissions for this student for these assignments to determine status
    submission_dict = {a.id: get_effective_submission_for_student(a, student_profile) for a in assignments}
    now = timezone.now()

    for assignment in assignments:
        assignment.student_feedback = ''
        submission = submission_dict.get(assignment.id)
        if submission:
            if hasattr(submission, 'grade') and submission.grade:
                assignment.student_status = 'GRADED'
                assignment.student_grade = submission.grade.score
                assignment.student_feedback = (submission.grade.feedback or '').strip()
            else:
                assignment.student_status = 'SUBMITTED'
                assignment.student_grade = None
        else:
            assignment.student_grade = None
            if not assignment.no_due_date and assignment.due_date and assignment.due_date < now:
                assignment.student_status = 'MISSING'
            else:
                assignment.student_status = 'UPCOMING'

    return render(request, 'portal/student_assignments.html', {
        'assignments': assignments,
        'enrollments': enrollments,
    })


@login_required
def student_gradebook(request):
    """
    Canvas-style table: assignments, due dates, submission time, status (late/missing),
    score, feedback indicator, and per-course totals.
    """
    request.session['active_role'] = 'STUDENT'
    student_profile, _ = Student.objects.get_or_create(user=request.user)
    enrollments = CourseMember.objects.filter(
        user=request.user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT'],
    ).select_related('course', 'course__professor')

    course_ids = [e.course_id for e in enrollments]
    course_filter = request.GET.get('course')
    if course_filter:
        try:
            cf = int(course_filter)
            if cf in course_ids:
                course_ids = [cf]
        except ValueError:
            pass

    courses = [e.course for e in enrollments if e.course_id in course_ids]
    # Preserve order from enrollments
    seen = set()
    courses_ordered = []
    for e in enrollments:
        if e.course_id in course_ids and e.course_id not in seen:
            seen.add(e.course_id)
            courses_ordered.append(e.course)
    courses = courses_ordered

    now = timezone.now()
    sections = []
    course_pcts = []
    feedback_payload = {}

    for course in courses:
        section, fb_part = build_student_course_gradebook_section(course, student_profile, now)
        sections.append(section)
        feedback_payload.update(fb_part)
        if section["total_percentage"] is not None:
            course_pcts.append(section["total_percentage"])

    overall_pct = None
    if course_pcts:
        overall_pct = sum(course_pcts) / len(course_pcts)

    fid = None
    if course_filter and str(course_filter).isdigit():
        try:
            fid = int(course_filter)
            if fid not in [e.course_id for e in enrollments]:
                fid = None
        except ValueError:
            fid = None

    return render(request, 'portal/student_gradebook.html', {
        'sections': sections,
        'overall_percentage': overall_pct,
        'filter_course_id': fid,
        'enrollments': enrollments,
        'feedback_payload': feedback_payload,
        'gradebook_course_layout': False,
    })


@login_required
def student_course_gradebook(request, course_id):
    """Per-course grades for the logged-in student (matches course assignment visibility)."""
    request.session['active_role'] = 'STUDENT'
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    if get_user_course_role(user, course, request) != 'STUDENT':
        return HttpResponseForbidden('Access denied.')

    student_profile, _ = Student.objects.get_or_create(user=user)
    now = timezone.now()
    section, feedback_payload = build_student_course_gradebook_section(course, student_profile, now)

    enrollments = CourseMember.objects.filter(
        user=user,
        role_in_course__in=['STUDENT', 'GRADING_ASSISTANT'],
    ).select_related('course', 'course__professor')

    return render(request, 'portal/student_gradebook.html', {
        'sections': [section],
        'overall_percentage': section['total_percentage'],
        'filter_course_id': course.id,
        'enrollments': enrollments,
        'feedback_payload': feedback_payload,
        'gradebook_course_layout': True,
        'course': course,
        'active_tab': 'grades',
    })


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
                messages.success(request, f"Message sent to {(recipient.get_full_name() or '').strip() or recipient.username}!")
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
            'title': f"{assignment.course.code_section_label() or assignment.course.title}: {assignment.name}",
            'start': assignment.due_date.isoformat(),
            'url': url,
            'backgroundColor': '#fdb913' if is_ga else 'var(--maroon)',
            'borderColor': '#fdb913' if is_ga else 'var(--maroon)'
        })
        
    context = {
        'events_json': json.dumps(events, cls=DjangoJSONEncoder)
    }
    
    return render(request, 'portal/student_calendar.html', context)

@login_required
def execution_sandbox(request):
    user = request.user
    
    # Determine which base template to use based on the user's role
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)
    
    if profile_obj.role in ['FACULTY', 'INSTRUCTOR']:
        base_template = 'base_professor.html'
    elif profile_obj.role == 'STUDENT':
        base_template = 'portal/base_portal.html'
    else:
        # Default fallback or for GRADING_ASSISTANT etc.
        base_template = 'base_grading_assistant.html'
        
        base_template = 'base_grading_assistant.html'
        
    context = {
        'base_template': base_template,
    }
    return render(request, 'shared/sandbox.html', context)

def get_dashboard_url(user):
    from professor.models import UserProfile
    try:
        profile = UserProfile.objects.get(user=user)
        if profile.role == 'STUDENT':
            return 'student_dashboard'
    except UserProfile.DoesNotExist:
        pass
    return 'professor_dashboard'

@login_required
def add_todo(request):
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            from professor.models import ToDoItem
            ToDoItem.objects.create(user=request.user, text=text)
    return redirect(get_dashboard_url(request.user))

@login_required
def toggle_todo(request, item_id):
    if request.method == 'POST':
        from professor.models import ToDoItem
        try:
            item = ToDoItem.objects.get(id=item_id, user=request.user)
            item.delete()  # Checking it off now completely removes the task
        except ToDoItem.DoesNotExist:
            pass
    return redirect(get_dashboard_url(request.user))

@login_required
def delete_todo(request, item_id):
    if request.method == 'POST':
        from professor.models import ToDoItem
        try:
            item = ToDoItem.objects.get(id=item_id, user=request.user)
            item.delete()
        except ToDoItem.DoesNotExist:
            pass
    return redirect(get_dashboard_url(request.user))
