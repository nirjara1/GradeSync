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
    name = models.CharField(max_length=200, help_text="Name of the course")
    is_archived = models.BooleanField(default=False, help_text="Locks the course from further edits")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"
