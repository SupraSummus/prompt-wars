import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0060_gamescore_game'),
    ]

    operations = [
        # Both drops leave the plain `battle` foreign key index in place,
        # which is what WarriorArena.update_rating still prefetches by
        # until the reader cut-over of docs/game-migration.md.
        migrations.RemoveIndex(
            model_name='gamescore',
            name='warriors_ga_battle__5058d4_idx',
        ),
        migrations.AlterUniqueTogether(
            name='gamescore',
            unique_together=set(),
        ),
        # A production verify_games run reports no score-link finding,
        # so no row is left for this to reject — and once the column is
        # not-null, unique_game_algorithm covers every score rather than
        # exempting the unlinked ones.
        migrations.AlterField(
            model_name='gamescore',
            name='game',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='scores',
                to='warriors.dbgame',
            ),
        ),
    ]
