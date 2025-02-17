# Generated by Django 4.2.19 on 2025-02-17 00:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0048_battle_attempts_1_2_battle_attempts_2_1'),
    ]

    operations = [
        migrations.AddField(
            model_name='arena',
            name='score_algorithm',
            field=models.CharField(choices=[('lcs', 'Longest Common Subsequence'), ('embeddings', 'Embeddings')], default='lcs', max_length=20),
        ),
    ]
