from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('grading', '0019_rubriccriterioncommentpreset'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RubricTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Faculty-facing label (e.g. 'CSCI 4038 standard 5-point rubric').", max_length=200)),
                ('description', models.TextField(blank=True, help_text='Optional notes / when to apply this rubric.')),
                ('is_weighted', models.BooleanField(default=False, help_text='True = criteria use weight %; False = criteria use points (must fit assignment total when applied).')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rubric_templates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at', 'name'],
                'unique_together': {('owner', 'name')},
            },
        ),
        migrations.CreateModel(
            name='RubricTemplateCriterion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('max_points', models.DecimalField(decimal_places=2, default=5, max_digits=6)),
                ('weight', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='criteria', to='grading.rubrictemplate')),
            ],
            options={
                'ordering': ['order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='RubricTemplateCriterionPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score_value', models.DecimalField(decimal_places=2, max_digits=6)),
                ('comment_text', models.TextField()),
                ('criterion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comment_presets', to='grading.rubrictemplatecriterion')),
            ],
            options={
                'ordering': ['criterion_id', 'score_value'],
                'unique_together': {('criterion', 'score_value')},
            },
        ),
    ]
