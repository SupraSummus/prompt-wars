import numpy as np
import pytest
from django_goals.models import worker

from .score import ScoreAlgorithm, get_or_create_game_score
from .tests.factories import TextUnitFactory


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('direction', ['1_2', '2_1'])
def test_gamescore_embeddings_integration(battle, direction):
    """
    Test the full integration flow for Embeddings algorithm:
    1. Create a GameScore
    2. Process it with django-goals worker
    3. Verify results match expected embedding calculations
    """
    # Set up embeddings for our test
    result_embedding = [0.7, 0.3, 0.2]  # More similar to warrior_1
    warrior_1_embedding = [0.8, 0.2, 0.1]
    warrior_2_embedding = [0.1, 0.3, 0.9]

    # Set up text unit and warrior embeddings
    setattr(battle, f'text_unit_{direction}', TextUnitFactory(
        voyage_3_embedding=result_embedding,
    ))
    battle.save(update_fields=[f'text_unit_{direction}'])
    battle.warrior_1.voyage_3_embedding = warrior_1_embedding if direction == '1_2' else warrior_2_embedding
    battle.warrior_1.save(update_fields=['voyage_3_embedding'])
    battle.warrior_2.voyage_3_embedding = warrior_2_embedding if direction == '1_2' else warrior_1_embedding
    battle.warrior_2.save(update_fields=['voyage_3_embedding'])

    # Create a game score with Embeddings algorithm
    game_score = get_or_create_game_score(
        battle=battle,
        direction=direction,
        algorithm=ScoreAlgorithm.EMBEDDINGS,
    )

    # Verify initial state - before processing
    assert game_score.is_processing
    assert game_score.warrior_1_similarity is None
    assert game_score.warrior_2_similarity is None
    assert game_score.score is None

    worker(once=True)

    # Verify final state - after processing
    game_score.refresh_from_db()
    assert game_score.is_completed

    # Verify the similarities were set correctly (with small float tolerance)
    expected_sim_1 = np.dot(np.array(result_embedding), np.array(warrior_1_embedding))
    expected_sim_2 = np.dot(np.array(result_embedding), np.array(warrior_2_embedding))
    assert abs(game_score.warrior_1_similarity - expected_sim_1) < 1e-10
    assert abs(game_score.warrior_2_similarity - expected_sim_2) < 1e-10

    # Since expected_sim_1 > expected_sim_2, warrior_1 should win
    assert game_score.score == 1.0
    assert game_score.score_rev == 0.0
