import django.db.models
from django.db import migrations


def fix_zero_max_points(apps, schema_editor):
    RubricCriterion = apps.get_model("grading", "RubricCriterion")
    for c in RubricCriterion.objects.filter(max_points=0):
        c.max_points = 5
        c.save(update_fields=["max_points"])


class Migration(migrations.Migration):

    dependencies = [
        ("grading", "0012_assignment_max_group_size_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="rubriccriterion",
            old_name="points",
            new_name="max_points",
        ),
        migrations.AlterField(
            model_name="rubriccriterion",
            name="max_points",
            field=django.db.models.DecimalField(
                decimal_places=2,
                default=5,
                help_text="Maximum points for this criterion (faculty scores 0–max; e.g. 5 for a 0–5 scale).",
                max_digits=6,
            ),
        ),
        migrations.RunPython(fix_zero_max_points, migrations.RunPython.noop),
    ]
