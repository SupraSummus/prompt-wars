from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0064_gamescore_game_no_index'),
    ]

    operations = [
        # The ALTER needs an exclusive lock on the battle table,
        # which queues behind every battle resolution holding it open
        # over an LLM call, and stalls the site's queries queued behind it.
        # Failing fast fails the deploy while the previous release keeps serving
        # (it gets no traffic until postdeploy succeeds), so it can be retried.
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '5s'",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # A constant database default makes ADD COLUMN metadata-only:
        # no table rewrite, and the default stays in place for writers
        # from the previous release.
        migrations.AddField(
            model_name='battle',
            name='rated',
            field=models.BooleanField(db_default=True),
        ),
    ]
