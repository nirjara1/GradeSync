from django.db import models
from django.contrib.auth.models import User
import json

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
    is_weighted = models.BooleanField(default=False)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    no_due_date = models.BooleanField(default=False)
    allowed_language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='python')
    starter_code = models.FileField(upload_to='starter_code/', null=True, blank=True, help_text="Optional starter code file for students")
    test_cases_file = models.FileField(upload_to='test_cases/', null=True, blank=True, help_text="JSON file containing test cases with public/private split")
    public_test_data = models.FileField(upload_to='test_data/', null=True, blank=True)
    expected_outputs = models.FileField(upload_to='expected_outputs/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    def get_starter_code(self, language=None):
        """Get starter code content for the given language"""
        if not self.starter_code:
            return None
        
        try:
            self.starter_code.open('r')
            content = self.starter_code.read()
            self.starter_code.close()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            return content
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error reading starter code for {self.name}: {e}")
            return None
    
    def get_test_cases(self, include_private=False):
        """Parse and return test cases from JSON file. Filter private tests if include_private=False"""
        if not self.test_cases_file:
            return []
        
        try:
            self.test_cases_file.open('r')
            content = self.test_cases_file.read()
            self.test_cases_file.close()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            test_cases = json.loads(content)
            
            # If include_private is False, filter out private tests (marked as isPrivate or isHidden)
            if not include_private and isinstance(test_cases, list):
                test_cases = [tc for tc in test_cases if not tc.get('isPrivate') and not tc.get('isHidden')]
            
            return test_cases
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error parsing test cases for {self.name}: {e}")
            return []

class TestCase(models.Model):
    """Individual test case for an assignment with input, expected output, and configuration"""
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='test_cases_db')
    name = models.CharField(max_length=255, default='Test Case')
    description = models.TextField(blank=True, help_text="Description of what this test case checks")
    input_data = models.TextField(blank=True, help_text="Input to pass to the program (stdin)")
    expected_output = models.TextField(help_text="Expected output from the program (stdout)")
    points_awarded = models.IntegerField(default=1, help_text="Points awarded for passing this test case")
    is_hidden = models.BooleanField(default=False, help_text="If True, students cannot see input/output during practice")
    is_private = models.BooleanField(default=False, help_text="If True, test is private (grading only). If False, test is public (students can run)")
    order = models.IntegerField(default=0, help_text="Order in which to display test cases")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.assignment.name} - {self.name}"

class RuleSet(models.Model):
    """Static analysis rules for code quality checks"""
    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name='ruleset', null=True, blank=True)
    
    # Required elements
    required_functions = models.TextField(
        blank=True, 
        help_text="Comma-separated list of required function names (e.g., 'main, validate, check_palindrome')"
    )
    
    # Forbidden elements
    forbidden_keywords = models.TextField(
        blank=True,
        help_text="Comma-separated list of forbidden keywords (e.g., 'global, break, continue')"
    )
    
    # Additional rules
    requires_docstring = models.BooleanField(default=False, help_text="If True, all functions must have docstrings")
    max_function_length = models.IntegerField(null=True, blank=True, help_text="Maximum lines per function")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def get_required_functions(self):
        """Return list of required function names"""
        if not self.required_functions:
            return []
        return [f.strip() for f in self.required_functions.split(',') if f.strip()]
    
    def get_forbidden_keywords(self):
        """Return list of forbidden keywords"""
        if not self.forbidden_keywords:
            return []
        return [k.strip() for k in self.forbidden_keywords.split(',') if k.strip()]
    
    def __str__(self):
        return f"RuleSet for {self.assignment.name if self.assignment else 'Unlinked'}"

class Submission(models.Model):
    """Student code submission for an assignment"""
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('grading', 'Grading'),
        ('graded', 'Graded'),
        ('failed', 'Failed'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='submissions')
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    file_path = models.FileField(upload_to='submissions/')
    submission_time = models.DateTimeField(auto_now_add=True)
    
    # Grading results
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    total_score = models.IntegerField(default=0, help_text="Total points earned from test cases")
    max_score = models.IntegerField(default=0, help_text="Maximum points possible")
    
    # Code Analysis Fields
    ai_likelihood_score = models.FloatField(null=True, blank=True)
    ai_confidence_score = models.FloatField(null=True, blank=True)
    ai_explanation = models.TextField(blank=True)
    
    plagiarism_score = models.FloatField(null=True, blank=True)
    plagiarism_confidence_score = models.FloatField(null=True, blank=True)
    plagiarism_match_info = models.TextField(blank=True)
    
    # Static analysis violations
    rule_violations = models.TextField(blank=True, help_text="JSON list of rule violations found")

    class Meta:
        unique_together = ('student', 'assignment')

    def __str__(self):
        return f"{self.student} -> {self.assignment}"
    
    def get_rule_violations_list(self):
        """Return list of rule violations from JSON"""
        if not self.rule_violations:
            return []
        try:
            return json.loads(self.rule_violations)
        except:
            return []
    
    def set_rule_violations(self, violations_list):
        """Set rule violations from a list"""
        self.rule_violations = json.dumps(violations_list)

class TestResult(models.Model):
    """Result of a single test case execution for a submission"""
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='test_results')
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='results')
    
    passed = models.BooleanField(default=False, help_text="True if actual output matches expected output")
    actual_output = models.TextField(blank=True, help_text="Actual output from code execution")
    error_message = models.TextField(blank=True, help_text="Any error/stderr from execution")
    execution_time = models.FloatField(default=0.0, help_text="Execution time in seconds")
    points_earned = models.IntegerField(default=0, help_text="Points awarded for this test (0 or test_case.points_awarded)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['test_case__order', 'created_at']
        unique_together = ('submission', 'test_case')

    def __str__(self):
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        return f"{self.submission} - {self.test_case.name}: {status}"

class Grade(models.Model):
    """Overall grade for a submission (manual or auto-grading)"""
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
