# Generated by Django 4.2.16 on 2024-09-22 21:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0030_rename_warrior_warriorarena'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='warrioruserpermission',
            name='warrior_user_unique',
        ),
        migrations.RenameField(
            model_name='warrioruserpermission',
            old_name='warrior',
            new_name='warrior_arena',
        ),
        migrations.AddConstraint(
            model_name='warrioruserpermission',
            constraint=models.UniqueConstraint(fields=('warrior_arena', 'user'), name='warrior_user_unique'),
        ),
    ]
