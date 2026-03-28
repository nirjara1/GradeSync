from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0009_submission_plagiarism_match'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='cwid',
            field=models.CharField(
                blank=True,
                help_text='Unique campus-wide ID for this student. Set by administrators only.',
                max_length=32,
                null=True,
                unique=True,
            ),
        ),
    ]
