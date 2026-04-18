from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SystemSettings(models.Model):
    """
    Singleton (pk=1) for institution-wide grading and integrity defaults.
    """

    plagiarism_detection_enabled = models.BooleanField(default=True)
    ai_code_detection_enabled = models.BooleanField(default=True)
    max_submission_file_mb = models.PositiveIntegerField(default=25)
    allowed_upload_extensions = models.CharField(
        max_length=500,
        default=".py,.java,.zip",
        help_text="Comma-separated extensions (lowercase), e.g. .py,.java,.zip",
    )
    global_late_grace_hours = models.PositiveIntegerField(
        default=0,
        help_text="Hours after the assignment due time before a submission is marked late.",
    )
    default_grades_released_to_students = models.BooleanField(
        default=True,
        help_text="Default for new assignments: students can see scores in the portal.",
    )

    class Meta:
        verbose_name = "System settings"
        verbose_name_plural = "System settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "GradeSync system settings"


class SystemNotice(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    severity = models.CharField(
        max_length=20,
        default="info",
        choices=[("info", "Info"), ("warning", "Warning"), ("danger", "Danger")],
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_visible_now(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class AuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64, db_index=True)
    detail = models.TextField(blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at}"


class SubmissionFileVersion(models.Model):
    """Immutable snapshot of a prior upload when a student replaces their submission file."""

    submission = models.ForeignKey(
        "grading.Submission",
        on_delete=models.CASCADE,
        related_name="file_versions",
    )
    snapshot_file = models.FileField(upload_to="submission_versions/")
    replaced_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-replaced_at"]


class PermissionRule(models.Model):
    """
    Documents the coarse role model shipped with GradeSync.
    Rows are seeded for transparency; enforcement remains in views/middleware.
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.title
