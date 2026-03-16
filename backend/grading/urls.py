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
    
    # Test case management
    path('assignments/<int:assignment_id>/test-cases/upload/', views.upload_test_cases, name='upload_test_cases'),
    path('assignments/<int:assignment_id>/test-cases/manage/', views.manage_test_cases, name='manage_test_cases'),
    path('assignments/<int:assignment_id>/test-cases/create/', views.create_test_case, name='create_test_case'),
    path('test-cases/<int:test_case_id>/edit/', views.edit_test_case, name='edit_test_case'),
    path('test-cases/<int:test_case_id>/delete/', views.delete_test_case, name='delete_test_case'),
    path('test-cases/<int:test_case_id>/toggle-visibility/', views.toggle_test_case_visibility, name='toggle_test_case_visibility'),
    
    # Rule configuration
    path('assignments/<int:assignment_id>/rules/', views.configure_rules, name='configure_rules'),
    
    # Student submission and testing
    path('assignments/<int:assignment_id>/submit-and-test/', views.student_submit_and_test, name='student_submit_and_test'),
    
    # Grading API endpoints
    path('api/submissions/<int:submission_id>/grade/', views.grade_submission_api, name='grade_submission_api'),
    path('api/submissions/<int:submission_id>/execute/', views.execute_submission_api, name='execute_submission_api'),
    path('submissions/<int:submission_id>/test-results/', views.submission_test_results, name='submission_test_results'),
    
    # Bulk grading and reporting
    path('api/assignments/<int:assignment_id>/bulk-grade/', views.trigger_bulk_grade, name='trigger_bulk_grade'),
    path('api/bulk-grade/<str:task_id>/status/', views.get_bulk_grade_status, name='get_bulk_grade_status'),
    path('assignments/<int:assignment_id>/grade-report/', views.grade_report, name='grade_report'),
    path('courses/<int:course_id>/students/<int:student_id>/grades/', views.student_course_grades_view, name='student_course_grades'),
    
    # Remote code execution sandbox endpoint
    path('api/execute/', execute_code_view, name='execute_code'),
    
    # Run public tests endpoint
    path('api/run-public-tests/', views.run_public_tests_api, name='run_public_tests_api'),
]
