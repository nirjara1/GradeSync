from django.urls import path
from . import views
from grading.views import student_course_view

urlpatterns = [
    path("dashboard/", views.student_dashboard_view, name="student_dashboard"),
    path('profile/', views.student_profile, name='student_profile'),
    path('courses/', views.student_courses_list, name='student_courses_list'),
    path('assignments/', views.student_assignments, name='student_assignments'),
    path('calendar/', views.student_calendar_view, name='student_calendar'),
    path('inbox/', views.student_inbox, name='student_inbox'),
    path('help/', views.student_help, name='student_help'),
    path("classes/<int:course_id>/", student_course_view, name="student_course"),
    
    # To-Do Widget Endpoints
    path('todo/add/', views.add_todo, name='add_todo'),
    path('todo/toggle/<int:item_id>/', views.toggle_todo, name='toggle_todo'),
    path('todo/delete/<int:item_id>/', views.delete_todo, name='delete_todo'),
]
