from django.urls import path
from . import views
from grading.views import student_course_view

urlpatterns = [
    path("dashboard/", views.student_dashboard_view, name="student_dashboard"),
    path("classes/<int:course_id>/", student_course_view, name="student_course"),
]
