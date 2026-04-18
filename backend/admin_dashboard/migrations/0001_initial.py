import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_system_settings_and_rules(apps, schema_editor):
    SystemSettings = apps.get_model("admin_dashboard", "SystemSettings")
    SystemSettings.objects.get_or_create(pk=1)

    PermissionRule = apps.get_model("admin_dashboard", "PermissionRule")
    rows = [
        (
            "staff-console",
            "Staff / superuser",
            "Full Django admin and GradeSync console URLs; can impersonate (if enabled), manage courses, notices, and audit views.",
        ),
        (
            "faculty-instructor",
            "Faculty (course instructor)",
            "Create courses and assignments, grade, run bulk autograde, and configure rubrics within owned or assigned courses.",
        ),
        (
            "grading-assistant",
            "Grading assistant",
            "Limited grading access for courses where the instructor has granted GA membership.",
        ),
        (
            "student-portal",
            "Student",
            "Submit work, view released grades and feedback, and use the student dashboard for enrolled courses only.",
        ),
        (
            "auth-backend",
            "Authentication stack",
            "Django auth plus optional Axes lockout for repeated failed logins; session cookies and HTTPS flags from deployment settings.",
        ),
    ]
    for slug, title, desc in rows:
        PermissionRule.objects.get_or_create(slug=slug, defaults={"title": title, "description": desc})


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("grading", "0016_remove_testcase_points_awarded"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "plagiarism_detection_enabled",
                    models.BooleanField(default=True),
                ),
                ("ai_code_detection_enabled", models.BooleanField(default=True)),
                ("max_submission_file_mb", models.PositiveIntegerField(default=25)),
                (
                    "allowed_upload_extensions",
                    models.CharField(
                        default=".py,.java,.zip",
                        help_text="Comma-separated extensions (lowercase), e.g. .py,.java,.zip",
                        max_length=500,
                    ),
                ),
                (
                    "global_late_grace_hours",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Hours after the assignment due time before a submission is marked late.",
                    ),
                ),
                (
                    "default_grades_released_to_students",
                    models.BooleanField(
                        default=True,
                        help_text="Default for new assignments: students can see scores in the portal.",
                    ),
                ),
            ],
            options={
                "verbose_name": "System settings",
                "verbose_name_plural": "System settings",
            },
        ),
        migrations.CreateModel(
            name="SystemNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True)),
                (
                    "severity",
                    models.CharField(
                        choices=[("info", "Info"), ("warning", "Warning"), ("danger", "Danger")],
                        default="info",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("detail", models.TextField(blank=True)),
                ("object_repr", models.CharField(blank=True, max_length=255)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PermissionRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("title", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["slug"],
            },
        ),
        migrations.CreateModel(
            name="SubmissionFileVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_file", models.FileField(upload_to="submission_versions/")),
                ("replaced_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.CharField(blank=True, max_length=200)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="file_versions",
                        to="grading.submission",
                    ),
                ),
            ],
            options={
                "ordering": ["-replaced_at"],
            },
        ),
        migrations.RunPython(seed_system_settings_and_rules, migrations.RunPython.noop),
    ]
