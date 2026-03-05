import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from professor.models import Course

def seed():
    user, _ = User.objects.get_or_create(username='poudelb2')
    user.first_name = "Kapil"
    user.last_name = "Paudel"
    user.save()

    # Clear old
    Course.objects.all().delete()

    # Create mock courses mirroring the screenshot
    Course.objects.create(
        code="CSCI4060",
        section="64251",
        title="Princ of Software Engineering",
        professor=user,
        term="Lon Smith, Ph.D.", # Sticking professor name in term to trick layout into matching screenshot exactly since the mockup has weird formatting
        image_url=""
    )

    Course.objects.create(
        code="MATH4009",
        section="63396",
        title="CRYPTOLOGY",
        professor=user,
        term="Jemin Shim",
        image_url=""
    )

    Course.objects.create(
        code="Comp Sci News",
        section="Majors",
        title="",
        professor=user,
        term="Spring 2026",
        image_url=""
    )
    print("Seeded successfully.")

if __name__ == '__main__':
    seed()
