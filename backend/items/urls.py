from django.urls import path
from django.contrib.auth.views import LoginView
from django.views.generic import TemplateView
from .views import (
    HomeView,
    EmployeeListView,
    EmployeeDetailView,
    EmployeeCreateView,
    EmployeeUpdateView,
    EmployeeDeleteView,
    DepartmentListView,
    DepartmentEmployeeListView,
)

urlpatterns = [
    # Home / Portal
    path("", LoginView.as_view(template_name="registration/login.html"), name="home"),
    
    # Portal Prototypes
    path("portal/profile/", TemplateView.as_view(template_name="portal/profile.html"), name="portal_profile"),
    path("portal/dashboard/", TemplateView.as_view(template_name="portal/dashboard.html"), name="portal_dashboard"),
    path("portal/courses/", TemplateView.as_view(template_name="portal/courses.html"), name="portal_courses"),
    path("portal/assignments/", TemplateView.as_view(template_name="portal/assignments.html"), name="portal_assignments"),
    path("portal/help/", TemplateView.as_view(template_name="portal/help.html"), name="portal_help"),

    # Employees
    path("employees/", EmployeeListView.as_view(), name="employee_list"),
    path("employees/new/", EmployeeCreateView.as_view(), name="employee_create"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="employee_detail"),
    path("employees/<int:pk>/edit/", EmployeeUpdateView.as_view(), name="employee_update"),
    path("employees/<int:pk>/delete/", EmployeeDeleteView.as_view(), name="employee_delete"),

    # Departments
    path("employees/departments/", DepartmentListView.as_view(), name="department_list"),
    path(
        "employees/department/<int:department_id>/",
        DepartmentEmployeeListView.as_view(),
        name="department-employees",
    ),
]
