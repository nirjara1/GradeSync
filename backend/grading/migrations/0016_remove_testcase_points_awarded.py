from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0015_studentonboarding'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='testcase',
            name='points_awarded',
        ),
        migrations.AlterField(
            model_name='testresult',
            name='points_earned',
            field=models.IntegerField(
                default=0,
                help_text='Binary pass flag stored as 1 (pass) or 0 (fail)',
            ),
        ),
    ]
