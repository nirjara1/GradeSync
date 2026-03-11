from django.urls import path
from . import views
from . import api
from grading.views import professor_course_view

urlpatterns = [
    path('dashboard/', views.dashboard, name='professor_dashboard'),
    path('profile/', views.profile, name='professor_profile'),
    path('create-course/', views.create_course, name='create_course'),
    path('classes/<int:course_id>/', professor_course_view, name='professor_course'),
    
    # API endpoints
    path('api/courses/<int:course_id>/students/', api.add_students_api, name='api_add_students'),
    path('api/courses/<int:course_id>/graders/', api.add_graders_api, name='api_add_graders'),
    path('api/courses/<int:course_id>/roster/', api.course_roster_api, name='api_course_roster'),
]
