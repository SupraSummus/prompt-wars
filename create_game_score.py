from django.db.models import Exists, OuterRef

from warriors.battles import LLM, Battle
from warriors.score import GameScore, ScoreAlgorithm, _ensure_score


def migrate_scores_batch(direction, batch_size=100):
    # Find battles that don't have a GameScore for the specified direction
    existing_scores = GameScore.objects.filter(
        battle=OuterRef('pk'),
        direction=direction,
        algorithm=ScoreAlgorithm.EMBEDDINGS,
    )

    battles_missing_scores = Battle.objects.annotate(
        has_score=Exists(existing_scores),
    ).filter(
        has_score=False,
        llm=LLM.GOOGLE_GEMINI,
        text_unit_1_2__isnull=False,
        text_unit_2_1__isnull=False,
    )[:batch_size]

    processed_count = 0
    for battle in battles_missing_scores:
        gs = GameScore(
            battle=battle,
            direction=direction,
            algorithm=ScoreAlgorithm.EMBEDDINGS,
        )
        _ensure_score(gs, save=False)
        gs.save()
        processed_count += 1

    return processed_count


for i in range(100):
    print(f"Batch {i + 1}")
    for direction in ('1_2', '2_1'):
        processed = migrate_scores_batch(direction, batch_size=100)
        print(f"Processed {processed} battles for direction {direction}")
