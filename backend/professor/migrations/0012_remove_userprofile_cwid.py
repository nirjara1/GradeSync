from django.db import migrations, models


def copy_cwid_to_student_records(apps, schema_editor):
    UserProfile = apps.get_model('professor', 'UserProfile')
    Student = apps.get_model('grading', 'Student')
    for up in UserProfile.objects.all():
        raw = (getattr(up, 'cwid', None) or '').strip()
        if not raw:
            continue
        if getattr(up, 'role', None) != 'STUDENT':
            continue
        student, _ = Student.objects.get_or_create(user_id=up.user_id)
        student.cwid = raw
        student.save(update_fields=['cwid'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('professor', '0011_userprofile_cwid'),
        ('grading', '0010_student_cwid'),
    ]

    operations = [
        migrations.RunPython(copy_cwid_to_student_records, noop_reverse),
        migrations.RemoveField(
            model_name='userprofile',
            name='cwid',
        ),
    ]
