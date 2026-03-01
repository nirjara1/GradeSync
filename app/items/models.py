import uuid
from django.db import models

class Department(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.name}"


class Employee(models.Model):
    department = models.ForeignKey("Department", on_delete=models.PROTECT)

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    email = models.EmailField(unique=True, blank=True)  # <-- allow blank so form doesn’t require it

    job_title = models.CharField(max_length=100)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    hire_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def generate_email(self):
        base = f"{self.last_name.lower()}{self.first_name[0].lower()}"
        domain = "gradesync.com"

        # First try: last + first initial
        candidate = f"{base}@{domain}"

        # If taken, try last+initial2, last+initial3, etc.
        n = 2
        while Employee.objects.filter(email=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}{n}@{domain}"
            n += 1

        return candidate

    def save(self, *args, **kwargs):
        if not self.email and self.first_name and self.last_name:
            self.email = self.generate_email()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class ProgrammingLanguage(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50)
    compile_command = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. javac Main.java (Leave blank for interpreted languages)")
    run_command = models.CharField(max_length=255, help_text="e.g. python main.py or java Main")
    status = models.BooleanField(default=True, verbose_name="Enabled")
    container_image = models.CharField(max_length=255, help_text="e.g. python:3.10-slim")
    memory_limit_mb = models.IntegerField(default=256, help_text="Memory limit in MB")
    time_limit_ms = models.IntegerField(default=5000, help_text="Time limit in milliseconds")

    def __str__(self):
        return f"{self.name} {self.version}"

    class Meta:
        verbose_name = "Programming Language"
        verbose_name_plural = "Programming Languages"


class ExecutionEnvironment(models.Model):
    # Singleton pattern - always override PK 1
    
    # Resource Limits
    cpu_limit = models.CharField(max_length=50, choices=[
        ('1 core', '1 core'), ('2 cores', '2 cores'), ('4 cores', '4 cores')
    ], default='1 core')
    memory_limit = models.CharField(max_length=50, choices=[
        ('512 MB', '512 MB'), ('1 GB', '1 GB'), ('2 GB', '2 GB'), ('4 GB', '4 GB')
    ], default='1 GB')
    execution_timeout = models.IntegerField(default=10, help_text="Timeout in seconds")

    # Sandbox Configuration
    container_isolation = models.BooleanField(default=True)
    network_access = models.BooleanField(default=False)
    file_system_access = models.CharField(max_length=50, choices=[
        ('Read only', 'Read only'), ('Restricted Write', 'Restricted Write'), ('Full Access (Admin only)', 'Full Access (Admin only)')
    ], default='Restricted Write')

    # Auto Scaling
    enable_auto_scaling = models.BooleanField(default=False)
    max_concurrent_jobs = models.IntegerField(default=10)

    class Meta:
        verbose_name = "Execution Environment"
        verbose_name_plural = "Execution Environments"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "System Execution Environment Settings"

class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, default="CSCI-xxxx", help_text="Course code")
    title = models.CharField(max_length=200, default="Untitled Course", help_text="Name of the course")
    term = models.CharField(max_length=50, default="Spring 2026")
    professor_id = models.UUIDField(null=True, blank=True, help_text="Matches User UUID")
    
    is_archived = models.BooleanField(default=False, help_text="Locks the course from further edits")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        # Fallback for older admin views that used 'name'
        return self.title

    def __str__(self):
        return f"{self.code} - {self.title}"

    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"

class DatabaseSettings(models.Model):
    # Singleton pattern
    
    retention_period = models.CharField(max_length=50, choices=[
        ('30 Days', '30 Days'), ('60 Days', '60 Days'), ('90 Days', '90 Days'), ('1 Year', '1 Year')
    ], default='30 Days')
    
    auto_cleanup_logs = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Database Settings"
        verbose_name_plural = "Database Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Global Database Maintenance Settings"


class Enrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    student_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=[('ACTIVE', 'ACTIVE'), ('DROPPED', 'DROPPED')], default='ACTIVE')

    def __str__(self):
        return f"Enrollment: {self.student_id} in {self.course.code}"


class Assignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=50, choices=[('python', 'python'), ('java', 'java')], default='python')
    due_at = models.DateTimeField()
    points = models.IntegerField(default=100)
    published = models.BooleanField(default=False)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class TestBundle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    version = models.IntegerField(default=1)
    uploaded_by = models.UUIDField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Tests v{self.version} for {self.assignment.title}"


class Submission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    student_id = models.UUIDField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=[
        ('UPLOADED', 'UPLOADED'), ('GRADING', 'GRADING'), ('GRADED', 'GRADED'), ('ERROR', 'ERROR')
    ], default='UPLOADED')
    language = models.CharField(max_length=50, choices=[('python', 'python'), ('java', 'java')], default='python')
    artifact_url = models.CharField(max_length=255, help_text="Download link or storage path")

    def __str__(self):
        return f"Submission {self.id} for {self.assignment.title}"


class GradeReport(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, primary_key=True)
    success = models.BooleanField(default=False)
    total_score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=100)
    breakdown = models.JSONField(default=list, help_text="[{name, passed, score, max_score, output, error}]")
    feedback = models.JSONField(default=list, help_text="[{category, message, severity}]")
    ai_likelihood = models.FloatField(default=0.0)
    ai_explanation = models.TextField(blank=True)
    plagiarism_matches = models.JSONField(default=list, help_text="[{file, score}]")
    error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Report for Submission {self.submission.id}"
