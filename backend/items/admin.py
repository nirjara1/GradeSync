from django.contrib import admin
from django.contrib.auth.models import User
from .models import Department, Employee


class GradeSyncAdminSite(admin.AdminSite):
    site_header = "GradeSync Administration"
    site_title = "GradeSync Admin"
    index_title = "System Administration Dashboard"

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['user_count'] = User.objects.count()
        return super().index(request, extra_context=extra_context)

    def logout(self, request, extra_context=None):
        from django.contrib.auth import logout as auth_logout
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        auth_logout(request)
        messages.success(request, "You have been successfully logged out.")
        return HttpResponseRedirect(reverse('login'))

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('execution-environment/', self.admin_view(self.execution_environment_view), name='execution_environment'),
            path('archive-class/', self.admin_view(self.archive_class_view), name='archive_class'),
            path('database-maintenance/', self.admin_view(self.database_maintenance_view), name='database_maintenance'),
            path('student-cwid/', self.admin_view(self.student_cwid_view), name='student_cwid'),
        ]
        return custom_urls + urls

    def database_maintenance_view(self, request):
        from .models import DatabaseSettings
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from datetime import datetime

        db_settings = DatabaseSettings.load()

        if request.method == 'POST':
            if 'save_cleanup' in request.POST:
                db_settings.retention_period = request.POST.get('retention_period', db_settings.retention_period)
                db_settings.auto_cleanup_logs = request.POST.get('auto_cleanup_logs') == 'on'
                db_settings.save()
                messages.success(request, 'Cleanup & Retention settings have been updated.')
            elif 'run_backup' in request.POST:
                messages.success(request, 'Database Backup has been initiated successfully!')
            elif 'upload_restore' in request.POST:
                messages.error(request, 'Restore functionality requires an attached backup file. Mock action simulated.')
            
            return redirect('admin:database_maintenance')

        context = dict(
            self.each_context(request),
            title='Database Maintenance',
            db_settings=db_settings,
        )
        return render(request, 'admin/items/database_maintenance.html', context)

    def archive_class_view(self, request):
        from .models import Course
        from django.shortcuts import render, redirect
        from django.contrib import messages

        if request.method == 'POST':
            course_id = request.POST.get('course_id')
            if course_id:
                try:
                    course = Course.objects.get(id=course_id)
                    course.is_archived = True
                    course.save()
                    messages.success(request, f'Class "{course.name}" has been successfully archived.')
                except Course.DoesNotExist:
                    messages.error(request, 'The selected class could not be found.')
            return redirect('admin:archive_class')

        active_courses = Course.objects.filter(is_archived=False)
        
        context = dict(
            self.each_context(request),
            title='Archive Class',
            active_courses=active_courses,
        )
        return render(request, 'admin/items/archive_class.html', context)

    def execution_environment_view(self, request):
        from .models import ExecutionEnvironment
        from django.shortcuts import render, redirect
        from django.contrib import messages

        env = ExecutionEnvironment.load()

        if request.method == 'POST':
            if 'reset' in request.POST:
                env.delete()  # Will recreate defaults on next load
                messages.success(request, 'Execution Environment reset to defaults.')
                return redirect('admin:execution_environment')
            
            # Save logic for limits
            env.cpu_limit = request.POST.get('cpu_limit', env.cpu_limit)
            env.memory_limit = request.POST.get('memory_limit', env.memory_limit)
            env.execution_timeout = request.POST.get('execution_timeout', env.execution_timeout)
            
            # Save logic for sandbox
            env.container_isolation = request.POST.get('container_isolation') == 'on'
            env.network_access = request.POST.get('network_access') == 'on'
            env.file_system_access = request.POST.get('file_system_access', env.file_system_access)

            # Save logic for auto-scaling
            env.enable_auto_scaling = request.POST.get('enable_auto_scaling') == 'on'
            env.max_concurrent_jobs = request.POST.get('max_concurrent_jobs', env.max_concurrent_jobs)

            env.save()
            messages.success(request, 'Execution Environment configuration updated.')
            return redirect('admin:execution_environment')

        context = dict(
            self.each_context(request),
            title='Execution Environment',
            env=env,
        )
        return render(request, 'admin/items/execution_environment.html', context)

    def student_cwid_view(self, request):
        """Staff-facing UI to set or update each student's unique CWID."""
        from grading.models import Student
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from django.db.models import Q
        from django.urls import reverse
        from urllib.parse import quote

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'save_cwid':
                pk = request.POST.get('student_id')
                raw = (request.POST.get('cwid') or '').strip()
                try:
                    st = Student.objects.select_related('user').get(pk=pk)
                except (Student.DoesNotExist, ValueError, TypeError):
                    messages.error(request, 'Student record not found.')
                else:
                    new_cwid = raw if raw else None
                    if new_cwid:
                        conflict = Student.objects.filter(cwid=new_cwid).exclude(pk=st.pk).exists()
                        if conflict:
                            messages.error(request, 'That CWID is already assigned to another student.')
                        else:
                            st.cwid = new_cwid
                            st.save(update_fields=['cwid'])
                            label = (st.user.get_full_name() or '').strip() or st.user.username
                            messages.success(request, f'CWID saved for {label}.')
                    else:
                        st.cwid = None
                        st.save(update_fields=['cwid'])
                        label = (st.user.get_full_name() or '').strip() or st.user.username
                        messages.success(request, f'CWID cleared for {label}.')
            preserve_q = (request.POST.get('preserve_q') or '').strip()
            base = reverse('admin:student_cwid')
            if preserve_q:
                return redirect(f'{base}?q={quote(preserve_q)}')
            return redirect(base)

        qs = Student.objects.select_related('user').order_by(
            'user__last_name', 'user__first_name', 'user__username'
        )
        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
                | Q(cwid__icontains=q)
            )

        context = dict(
            self.each_context(request),
            title='Student CWID',
            students=qs,
            search_q=q,
            student_count=qs.count(),
        )
        return render(request, 'admin/items/student_cwid.html', context)


# Replace the default admin site
gradesync_admin = GradeSyncAdminSite(name='admin')

# Re-register your models on the custom admin site
gradesync_admin.register(Department)
gradesync_admin.register(Employee)

# Also register Django's built-in auth models so Users/Groups are manageable
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _


class GradeSyncUserAdmin(UserAdmin):
    """
    Platform superuser (is_superuser) must be provisioned only via createsuperuser /
    shell on a secure host — not through the admin UI. Staff may still manage
    faculty/student accounts (is_staff, groups, etc.).
    """

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    def save_model(self, request, obj, form, change):
        if change:
            prior = type(obj).objects.get(pk=obj.pk)
            obj.is_superuser = prior.is_superuser
        else:
            obj.is_superuser = False
        super().save_model(request, obj, form, change)


gradesync_admin.register(User, GradeSyncUserAdmin)
gradesync_admin.register(Group, GroupAdmin)

from django.contrib.admin.models import LogEntry
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag')
    list_filter = ('action_flag', 'content_type')
    search_fields = ('object_repr', 'change_message')
    date_hierarchy = 'action_time'

gradesync_admin.register(LogEntry, LogEntryAdmin)

from .models import ProgrammingLanguage
class ProgrammingLanguageAdmin(admin.ModelAdmin):
    change_list_template = 'admin/items/programminglanguage/change_list.html'
    change_form_template = 'admin/items/programminglanguage/change_form.html'
    list_display = ('name', 'version', 'compile_command', 'run_command', 'status')

gradesync_admin.register(ProgrammingLanguage, ProgrammingLanguageAdmin)

from professor.models import UserProfile


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')
    raw_id_fields = ('user',)


gradesync_admin.register(UserProfile, UserProfileAdmin)

from grading.models import Student


class GradeSyncStudentAdmin(admin.ModelAdmin):
    """Student-only records; CWID is stored here (not on faculty UserProfile)."""
    list_display = ('user', 'cwid', 'enrollment_date')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'cwid')
    autocomplete_fields = ('user',)
    fields = ('user', 'cwid', 'enrollment_date')
    readonly_fields = ('enrollment_date',)


gradesync_admin.register(Student, GradeSyncStudentAdmin)
