from django.contrib import admin
from .models import (
    Student, Assignment, TestCase, RuleSet, Submission, 
    TestResult, Grade, Rubric, RubricCriterion, CriterionGrade
)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'cwid', 'enrollment_date')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'cwid')
    ordering = ('-enrollment_date',)

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'allowed_language', 'points', 'due_date', 'status', 'course')
    list_filter = ('allowed_language', 'status', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)

@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'assignment', 'is_hidden', 'order')
    list_filter = ('is_hidden', 'assignment', 'created_at')
    search_fields = ('name', 'description', 'assignment__name')
    ordering = ('assignment', 'order')

@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'requires_docstring', 'max_function_length')
    list_filter = ('requires_docstring', 'created_at')
    search_fields = ('assignment__name',)
    fieldsets = (
        ('Assignment', {'fields': ('assignment',)}),
        ('Required Elements', {'fields': ('required_functions',), 'classes': ('wide',)}),
        ('Forbidden Elements', {'fields': ('forbidden_keywords',), 'classes': ('wide',)}),
        ('Code Quality Rules', {'fields': ('requires_docstring', 'max_function_length')}),
    )

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'assignment', 'submission_time', 'status', 'total_score', 'max_score')
    list_filter = ('status', 'assignment', 'submission_time')
    search_fields = ('student__user__username', 'student__user__first_name', 'assignment__name')
    readonly_fields = ('submission_time', 'total_score', 'rule_violations')
    ordering = ('-submission_time',)

@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ('submission', 'test_case', 'passed', 'points_earned', 'execution_time')
    list_filter = ('passed', 'test_case__assignment', 'created_at')
    search_fields = ('submission__student__user__username', 'test_case__name')
    readonly_fields = ('submission', 'test_case', 'passed', 'actual_output', 'error_message', 'execution_time')
    ordering = ('-created_at',)

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('submission', 'score', 'graded_at')
    list_filter = ('graded_at',)
    search_fields = ('submission__student__user__username', 'submission__assignment__name')
    ordering = ('-graded_at',)

@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'is_weighted')
    list_filter = ('is_weighted',)
    search_fields = ('assignment__name',)

@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ('name', 'rubric', 'order', 'max_points', 'weight')
    list_filter = ('rubric__assignment', 'order')
    search_fields = ('name', 'rubric__assignment__name')
    ordering = ('rubric', 'order')

@admin.register(CriterionGrade)
class CriterionGradeAdmin(admin.ModelAdmin):
    list_display = ('submission', 'criterion', 'points_earned')
    list_filter = ('criterion__rubric__assignment',)
    search_fields = ('submission__student__user__username', 'criterion__name')
    readonly_fields = ('submission', 'criterion')

