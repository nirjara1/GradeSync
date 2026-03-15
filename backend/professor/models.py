from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    code = models.CharField(max_length=20)
    section = models.CharField(max_length=10)
    title = models.CharField(max_length=200)
    term = models.CharField(max_length=50)
    crn = models.CharField(max_length=10, blank=True, null=True)
    grading_default = models.BooleanField(default=True)
    unweighted = models.BooleanField(default=False)
    visibility = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    image_url = models.URLField(blank=True, null=True, help_text="Optional URL to a header image for the course")
    professor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code}-{self.section}: {self.title}"

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
        return f"{self.user.username} in {self.course.code} as {self.role_in_course}"
