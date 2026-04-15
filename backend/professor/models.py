import re

from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    code = models.CharField(max_length=20)
    section = models.CharField(max_length=10)
    title = models.CharField(max_length=200)
    term = models.CharField(max_length=50)
    year = models.CharField(max_length=4, blank=True, null=True)
    crn = models.CharField(max_length=10, blank=True, null=True)
    grading_default = models.BooleanField(default=True)
    unweighted = models.BooleanField(default=False)
    visibility = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    image_url = models.URLField(blank=True, null=True, help_text="Optional URL to a header image for the course")
    professor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    is_archived = models.BooleanField(default=False)

    def is_generic_code(self):
        return (self.code or '').strip().upper() == 'GENERIC'

    def code_section_label(self):
        """Catalog code + level for UI (e.g. CSCI2002)."""
        code = (self.code or '').strip()
        sec = (self.section or '').strip()
        if code.upper() == 'GENERIC':
            return sec
        if sec:
            return f'{code}{sec}'
        return code

    def code_title_label(self):
        """One line for cards/lists: 'CODE-SEC - Title' or 'SEC - Title' when code is GENERIC."""
        cs = self.code_section_label()
        title = (self.title or '').strip()
        if cs and title:
            return f'{cs} - {title}'
        return title or cs

    def dashboard_year_label(self):
        """Calendar year for dashboard cards."""
        year = (self.year or '').strip()
        if len(year) == 4 and year.isdigit():
            return year
        term = (self.term or '').strip()
        m = re.search(r'\b(19|20)\d{2}\b', term)
        if m:
            return m.group(0)
        sec = (self.section or '').strip()
        if len(sec) == 4 and sec.isdigit():
            return sec
        cs = self.code_section_label()
        if cs and len(cs) == 4 and cs.isdigit():
            return cs
        return ''

    def dashboard_card_title(self):
        """Dashboard cards: 'SUBJECT****-CRN-SEMESTER-YEAR' with robust level parsing."""
        subject = (self.code or '').strip().upper()
        level = (self.section or '').strip()
        if not (len(level) == 4 and level.isdigit()):
            # Backfill for older data where level may be embedded in code/section text.
            match = re.search(r'\b(\d{4})\b', f'{subject} {level}')
            level = match.group(1) if match else ''

        subject_level = f'{subject}{level}' if subject and level else (subject or level)
        crn = (self.crn or '').strip()
        term = (self.term or '').strip()
        year = self.dashboard_year_label()

        label_parts = [p for p in [subject_level, crn, term, year] if p]
        if label_parts:
            return '-'.join(label_parts)
        return (self.title or '').strip() or 'Course'

    def __str__(self):
        cs = self.code_section_label()
        if cs:
            return f'{cs}: {self.title}'
        return self.title or 'Course'

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('FACULTY', 'Faculty'),
        ('STUDENT', 'Student'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    academic_title = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    office_location = models.CharField(max_length=100, blank=True, null=True)
    office_hours = models.CharField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255, blank=True, null=True)
    body = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"From {self.sender.username} to {self.recipient.username}"

class CourseMember(models.Model):
    ROLE_IN_COURSE_CHOICES = [
        ('STUDENT', 'Student'),
        ('GRADING_ASSISTANT', 'Grading Assistant'),
    ]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_memberships')
    role_in_course = models.CharField(max_length=20, choices=ROLE_IN_COURSE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'user')

    def __str__(self):
        label = self.course.code_section_label() or self.course.title or 'course'
        return f"{self.user.username} in {label} as {self.role_in_course}"

class PendingEnrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='pending_enrollments')
    email = models.EmailField()
    role_in_course = models.CharField(max_length=20, default='STUDENT')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'email')

    def __str__(self):
        label = self.course.code_section_label() or self.course.title or 'course'
        return f"Pending: {self.email} in {label}"

class ToDoItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='todo_items')
    text = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['is_completed', '-created_at']

    def __str__(self):
        return f"[{'x' if self.is_completed else ' '}] {self.text}"
