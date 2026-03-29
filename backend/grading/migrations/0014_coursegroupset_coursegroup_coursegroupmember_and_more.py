from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0013_rename_rubriccriterion_points_to_max_points'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseGroupSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_sets', to='professor.course')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_course_group_sets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', 'id'],
                'unique_together': {('course', 'name')},
            },
        ),
        migrations.CreateModel(
            name='CourseGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('group_set', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='groups', to='grading.coursegroupset')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='CourseGroupMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='grading.coursegroup')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_group_memberships', to='grading.student')),
            ],
            options={
                'unique_together': {('group', 'student')},
            },
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.UniqueConstraint(condition=Q(('group__isnull', True)), fields=('assignment', 'student'), name='uniq_individual_submission_per_assignment'),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.UniqueConstraint(condition=Q(('group__isnull', False)), fields=('assignment', 'group'), name='uniq_group_submission_per_assignment'),
        ),
    ]
