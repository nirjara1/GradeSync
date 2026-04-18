from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0018_sync_assignment_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='RubricCriterionCommentPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score_value', models.DecimalField(decimal_places=2, max_digits=6)),
                ('comment_text', models.TextField()),
                ('criterion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comment_presets', to='grading.rubriccriterion')),
            ],
            options={
                'ordering': ['criterion_id', 'score_value'],
                'unique_together': {('criterion', 'score_value')},
            },
        ),
    ]

