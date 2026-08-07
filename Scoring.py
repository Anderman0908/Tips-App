"""
Core scoring logic for Tips (aka Piratwhist).

No UI, no state, no classes here on purpose — just pure functions.
Get this right first, everything else builds on top of it.
"""

from typing import List


def generate_round_sequence(max_cards: int) -> List[int]:
    """
    Build the sequence of "cards dealt this round" for a full game.

    max_cards, ..., 2, 1, 1, 2, ..., max_cards.

    The 1-card round appears twice.
    """
    if max_cards < 1:
        raise ValueError("max_cards must be at least 1")

    down = list(range(max_cards, 0, -1))
    up = list(range(1, max_cards + 1))
    return down + up


def valid_scores_for_round(cards: int, neutral_score: int = 7) -> List[int]:
    """
    Every possible score a player could truthfully call out in a round of this size.

    No bid is stored anywhere in this game (players track their own bid in their head),
    so this is what drives the quick-tap button grid: given how many cards are in play,
    what are all the numbers someone could legitimately report?

    Hits: the configured neutral score (bid was 0), plus 10+bid for bid = 1..cards
    Misses: -1 down to -cards (max possible distance between a 0 bid and a full-cards actual, or vice versa)
    """
    if cards < 1:
        raise ValueError("cards must be at least 1")

    if not 0 <= neutral_score <= 10:
        raise ValueError("neutral_score must be between 0 and 10")
    hits = [neutral_score] + [10 + bid for bid in range(1, cards + 1)]
    misses = [-d for d in range(1, cards + 1)]
    return sorted(hits + misses)


def calculate_score(bid: int, actual: int, neutral_score: int = 7) -> int:
    """
    Score a single player's single round.

    - bid == 0 and actual == 0  -> the configured neutral score
    - bid == actual (bid > 0)   -> 10 + bid
    - anything else (a miss)    -> -(how many tricks off you were)
    """
    if bid < 0 or actual < 0:
        raise ValueError("bid and actual must be zero or positive")
    if not 0 <= neutral_score <= 10:
        raise ValueError("neutral_score must be between 0 and 10")

    if bid == 0 and actual == 0:
        return neutral_score
    if bid == actual:
        return 10 + bid
    return -abs(actual - bid)


# ---------------------------------------------------------------------------
# Self-tests. Run this file directly (`python scoring.py`) to check the logic.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Round sequences
    assert generate_round_sequence(7) == [7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7]
    assert generate_round_sequence(1) == [1, 1]
    assert len(generate_round_sequence(7)) == 2 * 7

    # Valid score sets (drives the button grid)
    assert valid_scores_for_round(1) == [-1, 7, 11]
    assert valid_scores_for_round(2) == [-2, -1, 7, 11, 12]
    assert valid_scores_for_round(7) == [-7, -6, -5, -4, -3, -2, -1, 7, 11, 12, 13, 14, 15, 16, 17]

    # Scoring — basic cases
    assert calculate_score(1, 1) == 11
    assert calculate_score(2, 2) == 12
    assert calculate_score(7, 7) == 17
    assert calculate_score(0, 0) == 7          # the special case
    assert calculate_score(1, 2) == -1
    assert calculate_score(1, 5) == -4
    assert calculate_score(4, 2) == -2
    assert calculate_score(0, 3) == -3

    # John's worked example from the conversation, played out round by round
    total = 0
    total += calculate_score(2, 2)   # round 1: bid 2, got 2 -> 12
    assert total == 12
    total += calculate_score(0, 0)   # round 2: bid 0, got 0 -> 7
    assert total == 19
    total += calculate_score(4, 2)   # round 3: bid 4, got 2 -> -2
    assert total == 17

    print("All tests passed. John's running totals: 12 -> 19 -> 17")
