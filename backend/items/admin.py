from django import forms
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
            path('dashboard/', self.admin_view(self.console_dashboard_view), name='console_dashboard'),
            path('users/', self.admin_view(self.console_users_view), name='console_users'),
            path('courses/', self.admin_view(self.console_courses_view), name='console_courses'),
            path('roles/', self.admin_view(self.console_roles_view), name='console_roles'),
            path('environments/', self.admin_view(self.console_environments_view), name='console_environments'),
            path('audit/', self.admin_view(self.console_audit_view), name='console_audit'),
            path('system-errors/', self.admin_view(self.console_system_errors_view), name='console_system_errors'),
            path('integrity/', self.admin_view(self.console_integrity_view), name='console_integrity'),
            path('settings/', self.admin_view(self.console_settings_view), name='console_settings'),
            path('execution-environment/', self.admin_view(self.execution_environment_view), name='execution_environment'),
            path('archive-class/', self.admin_view(self.archive_class_view), name='archive_class'),
            path('database-maintenance/', self.admin_view(self.database_maintenance_view), name='database_maintenance'),
            path('student-cwid/', self.admin_view(self.student_cwid_view), name='student_cwid'),
            path('create-student/', self.admin_view(self.create_student_view), name='create_student'),
        ]
        return custom_urls + urls

    def console_dashboard_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_dashboard(request, self)

    def console_users_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_users(request, self)

    def console_courses_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_courses(request, self)

    def console_roles_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_roles(request, self)

    def console_environments_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_environments(request, self)

    def console_audit_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_audit(request, self)

    def console_system_errors_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_system_errors(request, self)

    def console_integrity_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_integrity(request, self)

    def console_settings_view(self, request):
        from admin_dashboard import views as console_views
        return console_views.console_settings(request, self)

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

    def create_student_view(self, request):
        """Staff-only: provision a student with CWID and send welcome / password-setup email."""
        from django.conf import settings as dj_settings
        from django.db.utils import ProgrammingError
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from grading.models import Student, StudentOnboarding
        from grading.student_invite import create_student_account, resend_welcome_email

        if request.method == 'POST':
            try:
                StudentOnboarding.objects.exists()
            except ProgrammingError:
                messages.error(
                    request,
                    'Database is missing required tables (e.g. grading_studentonboarding). '
                    'Run migrations: docker compose exec web python manage.py migrate',
                )
                return redirect('admin:create_student')

            action = request.POST.get('action')
            if action == 'resend':
                sid = request.POST.get('student_id')
                try:
                    sid_int = int(sid)
                except (TypeError, ValueError):
                    messages.error(request, 'Invalid student.')
                else:
                    result = resend_welcome_email(student_id=sid_int)
                    if result.get('ok'):
                        if result.get('email_sent'):
                            messages.success(
                                request,
                                'Welcome email sent. Docker dev: open http://localhost:8025 (Mailpit) to read it.',
                            )
                        else:
                            err = (result.get('email_error') or 'unknown error')[:800]
                            messages.warning(
                                request,
                                f'Email was not delivered. Fix SMTP settings and resend again. Detail: {err}',
                            )
                    else:
                        messages.error(request, result.get('error') or 'Could not resend email.')
                return redirect('admin:create_student')

            full_name = (request.POST.get('full_name') or '').strip()
            email = (request.POST.get('email') or '').strip()
            auto_cwid = request.POST.get('auto_cwid') == 'on'
            manual_cwid = (request.POST.get('cwid') or '').strip() if not auto_cwid else None

            result = create_student_account(full_name=full_name, email=email, manual_cwid=manual_cwid)
            if not result.get('ok'):
                messages.error(request, result.get('error') or 'Could not create student.')
            else:
                cwid = result.get('cwid')
                if result.get('email_sent'):
                    messages.success(
                        request,
                        f"Student created. CWID: {cwid}. Welcome email sent to {email}. "
                        f'(Docker dev: read it at http://localhost:8025 if using Mailpit.)',
                    )
                else:
                    err = (result.get('email_error') or 'unknown error')[:800]
                    messages.warning(
                        request,
                        f"Student created. CWID: {cwid}. Welcome email failed: {err}. "
                        f'Fix email settings and use Resend below.',
                    )
            return redirect('admin:create_student')

        recent_rows = []
        migration_needed = False
        try:
            StudentOnboarding.objects.exists()
        except ProgrammingError:
            migration_needed = True
        recent = list(
            Student.objects.select_related('user').order_by('-enrollment_date', '-id')[:30]
        )
        if migration_needed:
            recent_rows = [{'student': s, 'onboarding': None} for s in recent]
        else:
            for s in recent:
                ob = StudentOnboarding.objects.filter(student=s).first()
                recent_rows.append({'student': s, 'onboarding': ob})

        context = dict(
            self.each_context(request),
            title='Create student account',
            recent_rows=recent_rows,
            migration_needed=migration_needed,
            site_url=getattr(dj_settings, 'SITE_URL', ''),
        )
        return render(request, 'admin/items/create_student.html', context)


# Replace the default admin site
gradesync_admin = GradeSyncAdminSite(name='admin')

# Re-register your models on the custom admin site
gradesync_admin.register(Department)
gradesync_admin.register(Employee)

# Also register Django's built-in auth models so Users/Groups are manageable
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from hijack.contrib.admin import HijackUserAdminMixin


class GradeSyncUserChangeForm(forms.ModelForm):
    """Edit form: identity fields only; password is changed via the separate reset screen."""

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")


class GradeSyncUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "last_name", "email")


class GradeSyncUserAdmin(HijackUserAdminMixin, UserAdmin):
    """
    Superuser flag cannot be granted or cleared here (see save_model).
    Staff/active/permissions are managed elsewhere (e.g. Roles console), not on this form.
    """

    form = GradeSyncUserChangeForm
    add_form = GradeSyncUserCreationForm
    readonly_fields = ()

    fieldsets = (
        (None, {"fields": ("username",)}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "email",
                    "password1",
                    "password2",
                ),
            },
        ),
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

from grading.models import Student, StudentOnboarding


class StudentOnboardingAdmin(admin.ModelAdmin):
    list_display = ('student', 'welcome_email_sent_at', 'last_error_short', 'created_at')
    search_fields = ('student__user__email', 'student__user__username', 'student__cwid')

    @admin.display(description='Last email error')
    def last_error_short(self, obj):
        err = (obj.welcome_email_last_error or '').strip()
        if not err:
            return '—'
        return (err[:100] + '…') if len(err) > 100 else err

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


gradesync_admin.register(StudentOnboarding, StudentOnboardingAdmin)


class GradeSyncStudentAdmin(admin.ModelAdmin):
    """Student-only records; CWID is stored here (not on faculty UserProfile)."""
    list_display = ('user', 'cwid', 'enrollment_date')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'cwid')
    autocomplete_fields = ('user',)
    fields = ('user', 'cwid', 'enrollment_date')
    readonly_fields = ('enrollment_date',)


gradesync_admin.register(Student, GradeSyncStudentAdmin)
