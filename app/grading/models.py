from django.db import models
from django.contrib.auth.models import User

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    enrollment_date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return self.user.get_full_name() or self.user.username

class Assignment(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]
    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('java', 'Java'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    course = models.ForeignKey('professor.Course', on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    points = models.IntegerField(default=0)
    due_date = models.DateTimeField(null=True, blank=True)
    no_due_date = models.BooleanField(default=False)
    allowed_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='python')
    public_test_data = models.FileField(upload_to='test_data/', null=True, blank=True)
    expected_outputs = models.FileField(upload_to='expected_outputs/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Submission(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='submissions')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    file_path = models.FileField(upload_to='submissions/')
    submission_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'assignment')

    def __str__(self):
        return f"{self.student} -> {self.assignment}"

class Grade(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name='grade')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.score} for {self.submission}"
