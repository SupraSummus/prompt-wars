import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    # DROP INDEX CONCURRENTLY refuses to run inside a transaction.
    atomic = False

    dependencies = [
        ('warriors', '0063_rename_dbgame_game'),
    ]

    operations = [
        # AlterField alone would drop and re-add the foreign key around the index,
        # and re-adding it validates every score row under write locks on both tables.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX CONCURRENTLY "warriors_gamescore_game_id_a97fad0c"',
                    reverse_sql=(
                        'CREATE INDEX CONCURRENTLY "warriors_gamescore_game_id_a97fad0c" '
                        'ON "warriors_gamescore" ("game_id")'
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='gamescore',
                    name='game',
                    field=models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='scores',
                        to='warriors.game',
                    ),
                ),
            ],
        ),
    ]
