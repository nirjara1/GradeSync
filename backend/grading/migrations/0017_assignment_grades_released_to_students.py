from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("grading", "0016_remove_testcase_points_awarded"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="grades_released_to_students",
            field=models.BooleanField(
                default=True,
                help_text="When off, students see submissions and feedback labels but numeric scores stay hidden until released.",
            ),
        ),
    ]
