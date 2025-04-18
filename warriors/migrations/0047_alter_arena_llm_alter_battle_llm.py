# Generated by Django 4.2.17 on 2025-02-05 21:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0046_battle_llm'),
    ]

    operations = [
        migrations.AlterField(
            model_name='arena',
            name='llm',
            field=models.CharField(choices=[
                ('openai-gpt', 'OpenAI GPT'),
                ('claude-3-haiku', 'Anthropic Claude'),
                ('google-gemini', 'Google Gemini'),
            ], max_length=20),
        ),
        migrations.AlterField(
            model_name='battle',
            name='llm',
            field=models.CharField(choices=[
                ('openai-gpt', 'OpenAI GPT'),
                ('claude-3-haiku', 'Anthropic Claude'),
                ('google-gemini', 'Google Gemini'),
            ], max_length=20),
        ),
    ]
