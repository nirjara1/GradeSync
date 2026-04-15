from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('professor', '0012_remove_userprofile_cwid'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='year',
            field=models.CharField(blank=True, max_length=4, null=True),
        ),
    ]
