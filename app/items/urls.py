from django.urls import path
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
    path("", HomeView.as_view(), name="home"),

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
