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

    # Code Analysis Fields
    ai_likelihood_score = models.FloatField(null=True, blank=True)
    ai_confidence_score = models.FloatField(null=True, blank=True)
    ai_explanation = models.TextField(blank=True)
    
    plagiarism_score = models.FloatField(null=True, blank=True)
    plagiarism_confidence_score = models.FloatField(null=True, blank=True)
    plagiarism_match_info = models.TextField(blank=True)

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


class Rubric(models.Model):
    """One rubric per assignment; criteria can be weighted or unweighted."""
    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name='rubric')
    is_weighted = models.BooleanField(default=False, help_text="True = criteria use weight %; False = criteria use points")

    def __str__(self):
        return f"Rubric for {self.assignment.name}"


class RubricCriterion(models.Model):
    """Single criterion in a rubric. For unweighted: points = max points. For weighted: weight = percentage (0-100)."""
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name='criteria')
    name = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)
    # Unweighted: max points for this criterion
    points = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # Weighted: percentage (0-100) of total assignment points
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.name} ({self.rubric.assignment.name})"


class CriterionGrade(models.Model):
    """Points earned for one criterion on one submission."""
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='criterion_grades')
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='grades')
    points_earned = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        unique_together = ('submission', 'criterion')

    def __str__(self):
        return f"{self.points_earned} for {self.criterion.name} ({self.submission})"
