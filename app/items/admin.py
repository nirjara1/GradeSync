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
        return HttpResponseRedirect(reverse('home'))

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('execution-environment/', self.admin_view(self.execution_environment_view), name='execution_environment'),
            path('archive-class/', self.admin_view(self.archive_class_view), name='archive_class'),
            path('database-maintenance/', self.admin_view(self.database_maintenance_view), name='database_maintenance'),
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

# Replace the default admin site
gradesync_admin = GradeSyncAdminSite(name='admin')

# Re-register your models on the custom admin site
gradesync_admin.register(Department)
gradesync_admin.register(Employee)

# Also register Django's built-in auth models so Users/Groups are manageable
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
gradesync_admin.register(User, UserAdmin)
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
