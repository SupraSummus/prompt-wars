# Generated by Django 4.2.10 on 2024-03-14 20:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0020_arena_site'),
    ]

    operations = [
        migrations.AddField(
            model_name='arena',
            name='llm',
            field=models.CharField(
                choices=[
                    ('openai-gpt', 'OpenAI GPT'),
                    ('claude-3-haiku', 'Claude 3 Haiku'),
                ],
                max_length=20,
            ),
        ),
    ]
