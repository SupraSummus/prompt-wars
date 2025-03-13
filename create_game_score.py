from django.db.models import Exists, OuterRef

from warriors.battles import Battle
from warriors.score import GameScore, ScoreAlgorithm


def migrate_scores_batch(direction, batch_size=100):
    # Find battles that don't have a GameScore for the specified direction
    existing_scores = GameScore.objects.filter(
        battle=OuterRef('pk'),
        direction=direction,
        algorithm=ScoreAlgorithm.LCS,
    )

    battles_missing_scores = Battle.objects.annotate(
        has_score=Exists(existing_scores)
    ).filter(
        has_score=False,
        lcs_len_1_2_1__isnull=False,
        lcs_len_1_2_2__isnull=False,
        lcs_len_2_1_1__isnull=False,
        lcs_len_2_1_2__isnull=False,
    )[:batch_size]

    processed_count = 0
    for battle in battles_missing_scores:
        # Get the appropriate LCS length values based on direction
        if direction == '1_2':
            warrior_1_similarity = battle.lcs_len_1_2_1
            warrior_2_similarity = battle.lcs_len_1_2_2
        else:  # direction == '2_1'
            warrior_1_similarity = battle.lcs_len_2_1_2
            warrior_2_similarity = battle.lcs_len_2_1_1

        # Create GameScore
        GameScore.objects.create(
            battle=battle,
            direction=direction,
            algorithm=ScoreAlgorithm.LCS,
            warrior_1_similarity=warrior_1_similarity,
            warrior_2_similarity=warrior_2_similarity,
        )
        processed_count += 1

    return processed_count


for i in range(10):
    print(f"Batch {i + 1}")
    for direction in ('1_2', '2_1'):
        processed = migrate_scores_batch(direction, batch_size=1000)
        print(f"Processed {processed} battles for direction {direction}")
