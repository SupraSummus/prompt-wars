import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warriors', '0058_dbgame_battle'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dbgame',
            name='battle',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='games',
                to='warriors.battle',
            ),
        ),
    ]
