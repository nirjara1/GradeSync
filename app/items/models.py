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
