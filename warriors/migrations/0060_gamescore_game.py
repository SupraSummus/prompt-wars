import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0059_dbgame_battle_not_null'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamescore',
            name='game',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='scores',
                to='warriors.dbgame',
            ),
        ),
        # Null game rows are exempt from the constraint,
        # so it guards the dual-write in get_or_create_game_score
        # from day one while legacy rows await backfill_game_score_game.
        migrations.AddConstraint(
            model_name='gamescore',
            constraint=models.UniqueConstraint(
                fields=('game', 'algorithm'),
                name='unique_game_algorithm',
            ),
        ),
    ]
