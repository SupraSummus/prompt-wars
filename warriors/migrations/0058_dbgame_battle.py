import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0057_remove_battle_lcs_len_1_2_1_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='dbgame',
            name='battle',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='games',
                to='warriors.battle',
            ),
        ),
        # Null battle rows are exempt from the constraint,
        # so it guards the dual-write in Battle.create_from_warriors
        # from day one while legacy rows await backfill_game_battles.
        migrations.AddConstraint(
            model_name='dbgame',
            constraint=models.UniqueConstraint(
                fields=('battle', 'warrior_1'),
                name='unique_battle_direction',
            ),
        ),
    ]
