from django.urls import path
from . import views
from . import api
from grading.views import professor_course_view

urlpatterns = [
    path('dashboard/', views.dashboard, name='professor_dashboard'),
    path('profile/', views.profile, name='professor_profile'),
    path('courses/', views.courses_list, name='professor_courses_list'),
    path('reports/', views.reports, name='professor_reports'),
    path('inbox/', views.inbox, name='professor_inbox'),
    path('help/', views.help_page, name='professor_help'),
    path('create-course/', views.create_course, name='create_course'),
    path('calendar/', views.calendar_view, name='professor_calendar'),
    path('classes/<int:course_id>/', professor_course_view, name='professor_course'),
    path('classes/<int:course_id>/archive/', views.archive_course, name='archive_course'),
    
    # To-Do Widget Endpoints
    path('todo/add/', views.add_todo, name='add_todo'),
    path('todo/toggle/<int:item_id>/', views.toggle_todo, name='toggle_todo'),
    path('todo/delete/<int:item_id>/', views.delete_todo, name='delete_todo'),
    
    # API endpoints
    path('api/courses/<int:course_id>/students/', api.add_students_api, name='api_add_students'),
    path('api/courses/<int:course_id>/graders/', api.add_graders_api, name='api_add_graders'),
    path('api/courses/<int:course_id>/roster/', api.course_roster_api, name='api_course_roster'),
    path('api/courses/<int:course_id>/remove/', api.remove_member_api, name='api_remove_member'),
]
