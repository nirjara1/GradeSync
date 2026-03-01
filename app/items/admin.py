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
