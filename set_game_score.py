from warriors.battles import LLM, Battle, Game
from warriors.score import GameScore, ScoreAlgorithm, _warrior_similarity


def validate_scores(direction, sample_size=100):
    """
    Validate a random sample of GameScores to ensure they match Battle data.

    Args:
        direction: The direction to validate ('1_2' or '2_1')
        sample_size: Number of GameScores to randomly sample for validation
    """
    assert direction in ('1_2', '2_1'), "Direction must be '1_2' or '2_1'"

    # Sample random GameScores for the specified direction
    random_ids = GameScore.objects.filter(
        direction=direction,
        algorithm=ScoreAlgorithm.EMBEDDINGS,
        battle__llm=LLM.GOOGLE_GEMINI,
    ).values_list('id', flat=True).order_by('?')[:sample_size]
    game_scores = GameScore.objects.filter(
        id__in=random_ids,
    ).select_related(
        'battle',
        'battle__warrior_1',
        'battle__warrior_2',
        'battle__text_unit_1_2',
        'battle__text_unit_2_1',
    )

    # Initialize counters
    checked = 0
    matching = 0
    mismatched = 0

    print(f"Validation Results for Direction {direction}")
    print(f"Sample Size: {sample_size}")

    # Check each GameScore
    for gs in game_scores:
        checked += 1
        battle = gs.battle
        game = Game(battle, direction, score_algorithm=ScoreAlgorithm.EMBEDDINGS)
        battle_value_1 = _warrior_similarity(game.text_unit, game.warrior_1)
        battle_value_2 = _warrior_similarity(game.text_unit, game.warrior_2)

        # Check if the values match
        if (
            gs.warrior_1_similarity == battle_value_1 and
            gs.warrior_2_similarity == battle_value_2
        ):
            matching += 1
        else:
            mismatched += 1
            # Print discrepancy immediately
            print(f"  Battle {battle.id}: ", end="")
            print(f"Battle values ({battle_value_1}, {battle_value_2}) ≠ ", end="")
            print(
                f"GameScore values ({gs.warrior_1_similarity}, {gs.warrior_2_similarity})"
            )

    # Get coverage data
    total_battles = Battle.objects.filter(
        llm=LLM.GOOGLE_GEMINI,
    ).count()
    total_game_scores = GameScore.objects.filter(
        direction=direction,
        algorithm=ScoreAlgorithm.EMBEDDINGS,
        battle__llm=LLM.GOOGLE_GEMINI,
    ).count()
    missing = total_battles - total_game_scores

    # Calculate percentages (handle division by zero cases)
    match_percent = (matching / checked * 100) if checked else 0
    mismatch_percent = (mismatched / checked * 100) if checked else 0
    coverage_percent = (total_game_scores / total_battles * 100) if total_battles else 0
    missing_percent = (missing / total_battles * 100) if total_battles else 0

    # Print summary statistics
    print(f"GameScores checked: {checked}")
    print(f"Matching data: {matching} ({match_percent:.1f}%)")
    print(f"Mismatched data: {mismatched} ({mismatch_percent:.1f}%)")

    # Data coverage
    print("\nData Coverage:")
    print(f"Total Battles: {total_battles}")
    print(
        f"GameScores for direction {direction}: {total_game_scores} ({coverage_percent:.1f}% coverage)"
    )
    print(f"Missing GameScores: {missing} ({missing_percent:.1f}%)")


for direction in ('1_2', '2_1'):
    print('')
    print("=" * 60)
    validate_scores(direction, sample_size=100)
