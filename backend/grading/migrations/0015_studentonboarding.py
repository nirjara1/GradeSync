# Generated manually for GradeSync admin student provisioning

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0014_coursegroupset_coursegroup_coursegroupmember_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentOnboarding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('welcome_email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('welcome_email_last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'student',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='onboarding',
                        to='grading.student',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Student onboarding',
                'verbose_name_plural': 'Student onboarding',
            },
        ),
    ]
