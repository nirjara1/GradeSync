from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import date

from items.models import Department, Employee


def build_email(first_name: str, last_name: str) -> str:
    """
    Rule: last name + first initial @gradesync.com
    Example: Alex Turner -> turnera@gradesync.com
    """
    first_initial = (first_name or "").strip()[:1].lower()
    last = (last_name or "").strip().lower().replace(" ", "")
    return f"{last}{first_initial}@gradesync.com"


class Command(BaseCommand):
    help = "Seed starter departments and employees (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Seeding departments + employees..."))

        # 1) Departments (name, location)
        departments_data = [
            ("Software Development", "Baton Rouge, LA"),
            ("Cybersecurity", "Monroe, LA"),
            ("Data Analytics", "New Orleans, LA"),
            ("Infrastructure & Systems", "Jacksonville, FL"),
            ("Technology & Operations", "Remote"),
        ]

        dept_map = {}
        for name, location in departments_data:
            dept, created = Department.objects.get_or_create(
                name=name,
                defaults={"location": location},
            )
            # If it existed but location is blank/outdated, update it
            if not created and getattr(dept, "location", None) != location:
                dept.location = location
                dept.save(update_fields=["location"])

            dept_map[name] = dept

        # 2) Employees
        # NOTE: Adjust field names below if your model differs.
        employees_data = [
            # dept_name, first, last, job_title, salary, hire_date(YYYY,MM,DD), is_active
            ("Technology & Operations", "Alex", "Turner", "IT Manager", 105000, date(2019, 3, 12), True),
            ("Technology & Operations", "Megan", "Brooks", "Operations Analyst", 72000, date(2021, 7, 19), True),
            ("Technology & Operations", "Caleb", "Price", "Systems Coordinator", 68000, date(2022, 2, 7), True),

            ("Software Development", "Jordan", "Hayes", "Senior Software Engineer", 125000, date(2018, 10, 1), True),
            ("Software Development", "Sophie", "Reed", "Software Engineer", 98000, date(2020, 5, 18), True),
            ("Software Development", "Ethan", "Cole", "Junior Developer", 72000, date(2023, 8, 14), True),
            ("Software Development", "Ava", "Morgan", "QA Engineer", 85000, date(2021, 11, 8), True),

            ("Cybersecurity", "Noah", "Bennett", "Security Analyst", 92000, date(2021, 4, 26), True),
            ("Cybersecurity", "Grace", "Foster", "Incident Response Lead", 118000, date(2019, 9, 9), True),
            ("Cybersecurity", "Liam", "Watson", "GRC Specialist", 88000, date(2022, 6, 20), True),

            ("Data Analytics", "Olivia", "Stone", "Data Analyst", 90000, date(2020, 1, 13), True),
            ("Data Analytics", "Mason", "Perez", "BI Developer", 102000, date(2019, 6, 3), True),
            ("Data Analytics", "Emily", "Nguyen", "Data Scientist", 130000, date(2018, 4, 16), True),

            ("Infrastructure & Systems", "Lucas", "Turner", "Network Engineer", 97000, date(2020, 8, 24), True),
            ("Infrastructure & Systems", "Chloe", "Adams", "Cloud Engineer", 112000, date(2021, 3, 29), True),
            ("Infrastructure & Systems", "Benjamin", "Knight", "SysAdmin", 86000, date(2022, 10, 10), True),
        ]

        created_count = 0
        updated_count = 0

        for dept_name, first, last, job_title, salary, hire_dt, is_active in employees_data:
            dept = dept_map[dept_name]
            email = build_email(first, last)

            # Unique key for idempotency: email
            emp, created = Employee.objects.get_or_create(
                email=email,
                defaults={
                    "department": dept,
                    "first_name": first,
                    "last_name": last,
                    "job_title": job_title,
                    "salary": salary,
                    "hire_date": hire_dt,
                    "is_active": is_active,
                },
            )

            if created:
                created_count += 1
            else:
                # Update fields in case you tweak starter data later
                changed = False
                updates = {}

                if emp.department_id != dept.id:
                    updates["department"] = dept
                    changed = True
                if emp.first_name != first:
                    updates["first_name"] = first
                    changed = True
                if emp.last_name != last:
                    updates["last_name"] = last
                    changed = True
                if emp.job_title != job_title:
                    updates["job_title"] = job_title
                    changed = True
                if emp.salary != salary:
                    updates["salary"] = salary
                    changed = True
                if emp.hire_date != hire_dt:
                    updates["hire_date"] = hire_dt
                    changed = True
                if emp.is_active != is_active:
                    updates["is_active"] = is_active
                    changed = True

                if changed:
                    for k, v in updates.items():
                        setattr(emp, k, v)
                    emp.save()
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS("✅ Seed complete."))
        self.stdout.write(f"Departments: {Department.objects.count()}")
        self.stdout.write(f"Employees created: {created_count}")
        self.stdout.write(f"Employees updated: {updated_count}")
