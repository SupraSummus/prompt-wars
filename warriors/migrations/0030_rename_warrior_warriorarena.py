# Generated by Django 4.2.16 on 2024-09-22 19:48

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('warriors', '0029_arenastats_remove_warrior_rating_index_and_more'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Warrior',
            new_name='WarriorArena',
        ),
    ]