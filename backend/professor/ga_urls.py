from django.urls import path
from professor import views as professor_views
from grading import views as grading_views

urlpatterns = [
    path('dashboard/', professor_views.ga_dashboard, name='ga_dashboard'),
    path('classes/<int:course_id>/', grading_views.ga_course_view, name='ga_course'),
]
