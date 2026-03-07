from django.urls import path
from . import views

urlpatterns = [
    path('assignments/', views.assignments_dashboard, name='assignments_dashboard'),
    path('assignments/create/', views.create_assignment, name='create_assignment'),
    path('assignments/course/<int:course_id>/create/', views.create_assignment, name='course_create_assignment'),
    path('assignments/<int:pk>/edit/', views.edit_assignment, name='edit_assignment'),
    path('assignments/<int:pk>/delete/', views.delete_assignment, name='delete_assignment'),
    path('assignments/<int:pk>/view/', views.assignment_detail_view, name='assignment_detail'),
    path('submissions/<int:pk>/grade/', views.grade_submission_view, name='grade_submission'),
    path('submissions/<int:pk>/download/', views.download_submission_view, name='download_submission'),
]
