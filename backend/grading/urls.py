from django.urls import path
from . import views
from .execute_view import execute_code_view

urlpatterns = [
    path('assignments/', views.assignments_dashboard, name='assignments_dashboard'),
    path('assignments/create/', views.create_assignment, name='create_assignment'),
    path('assignments/create/rubric/', views.rubric_view, name='rubric'),
    path('assignments/course/<int:course_id>/create/', views.create_assignment, name='course_create_assignment'),
    path('assignments/<int:assignment_id>/rubric/', views.assignment_rubric_view, name='assignment_rubric'),
    path('assignments/<int:pk>/edit/', views.edit_assignment, name='edit_assignment'),
    path('assignments/<int:pk>/delete/', views.delete_assignment, name='delete_assignment'),
    path('assignments/<int:pk>/view/', views.assignment_detail_view, name='assignment_detail'),
    path('assignments/<int:pk>/gradebook/', views.gradebook_view, name='gradebook'),
    path('submissions/<int:pk>/grade/', views.grade_submission_view, name='grade_submission'),
    path('submissions/<int:pk>/download/', views.download_submission_view, name='download_submission'),
    path('submissions/<int:pk>/delete/', views.delete_submission_view, name='delete_submission'),
    # Remote code execution sandbox endpoint
    path('api/execute/', execute_code_view, name='execute_code'),
]
