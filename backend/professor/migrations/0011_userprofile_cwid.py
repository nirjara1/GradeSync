from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('professor', '0010_todoitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='cwid',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Campus-wide ID. Set by administrators only; users cannot edit this in the portal.',
                max_length=32,
            ),
        ),
    ]
