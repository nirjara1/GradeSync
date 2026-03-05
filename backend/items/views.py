from .models import Employee, Department
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.db.models import Avg, Sum, Count, Max


class EmployeeListView(ListView):
    model = Employee
    template_name = "items/employee_list.html"
    context_object_name = "employees"

    SORT_MAP = {
        "salary": "salary",
        "name": "last_name",          # alphabetical by last name
        "department": "department__name",
        "hire_date": "hire_date",
    }

    def get_queryset(self):
        qs = Employee.objects.select_related("department")

        # optional filter by department
        dept_id = self.request.GET.get("department")
        if dept_id:
            qs = qs.filter(department_id=dept_id)

        sort = self.request.GET.get("sort", "salary")
        direction = self.request.GET.get("dir", "desc")

        field = self.SORT_MAP.get(sort, "salary")
        order_by = f"-{field}" if direction == "desc" else field

        # for name sort, also include first name as a tie-breaker
        if sort == "name":
            qs = qs.order_by(order_by, "first_name")
        else:
            qs = qs.order_by(order_by)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.order_by("name")
        ctx["current_sort"] = self.request.GET.get("sort", "salary")
        ctx["current_dir"] = self.request.GET.get("dir", "desc")
        ctx["current_department"] = self.request.GET.get("department", "")
        return ctx



class EmployeeDetailView(DetailView):
    model = Employee
    template_name = "items/employee_detail.html"

class EmployeeCreateView(CreateView):
    model = Employee
    fields = ["department", "first_name", "last_name", "job_title", "salary", "hire_date", "is_active"]
    template_name = "items/employee_form.html"
    success_url = reverse_lazy("employee_list")

class EmployeeUpdateView(UpdateView):
    model = Employee
    fields = ["department", "first_name", "last_name", "job_title", "salary", "hire_date", "is_active"]
    template_name = "items/employee_form.html"
    success_url = reverse_lazy("employee_list")

class EmployeeDeleteView(DeleteView):
    model = Employee
    template_name = "items/employee_delete.html"
    success_url = reverse_lazy("employee_list")

class DepartmentEmployeeListView(ListView):
    model = Employee
    template_name = "items/department_employees.html"
    context_object_name = "employees"

    def get_queryset(self):
        dept_id = self.kwargs["department_id"]
        return (
            Employee.objects
            .select_related("department")
            .filter(department_id=dept_id)
            .order_by("-salary")  # ✅ ranked by salary
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dept_id = self.kwargs["department_id"]

        department = Department.objects.get(id=dept_id)

        stats = Employee.objects.filter(department_id=dept_id).aggregate(
            headcount=Count("id"),
            avg_salary=Avg("salary"),
            total_payroll=Sum("salary"),
            max_salary=Max("salary"),
        )

        top_earner = (
            Employee.objects
            .filter(department_id=dept_id)
            .order_by("-salary")
            .first()
        )

        context["department"] = department
        context["stats"] = stats
        context["top_earner"] = top_earner

        return context
    
class DepartmentListView(ListView):
    model = Department
    template_name = "items/department_list.html"
    context_object_name = "departments"

    def get_queryset(self):
        return Department.objects.order_by("name")

class HomeView(TemplateView):
    template_name = "items/home.html"