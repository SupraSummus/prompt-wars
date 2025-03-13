from warriors.battles import Battle
from warriors.score import GameScore, ScoreAlgorithm


def validate_scores(direction, sample_size=100):
    """
    Validate a random sample of GameScores to ensure they match Battle data.

    Args:
        direction: The direction to validate ('1_2' or '2_1')
        sample_size: Number of GameScores to randomly sample for validation
    """
    assert direction in ('1_2', '2_1'), "Direction must be '1_2' or '2_1'"

    # Sample random GameScores for the specified direction
    game_scores = GameScore.objects.filter(
        direction=direction, algorithm=ScoreAlgorithm.LCS
    ).order_by('?')[:sample_size]

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

        # Get the appropriate battle values based on direction
        if direction == '1_2':
            battle_value_1 = battle.lcs_len_1_2_1
            battle_value_2 = battle.lcs_len_1_2_2
        else:  # direction == '2_1'
            battle_value_1 = battle.lcs_len_2_1_2
            battle_value_2 = battle.lcs_len_2_1_1

        battle_value_1 = float(battle_value_1)
        battle_value_2 = float(battle_value_2)

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
    total_battles = Battle.objects.count()
    total_game_scores = GameScore.objects.filter(
        direction=direction, algorithm=ScoreAlgorithm.LCS
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
