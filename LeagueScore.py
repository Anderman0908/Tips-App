"""Authoritative placement-based Pirate Whist league score."""

from typing import Dict, Iterable

from Scoring import generate_round_sequence

ALGORITHM_NAME = "placement-average"
ALGORITHM_VERSION = 2
MIN_COMPETITION_PLAYERS = 5
MAX_COMPETITION_PLAYERS = 7
OFFICIAL_GAMES_REQUIRED = 5
WIN_BONUS = 10.0
KOLESKAB_BONUS = 50.0


def placements_from_scores(scores: Dict[str, int]) -> Dict[str, int]:
    """Return competition placements; equal scores share a placement."""
    return {
        player_id: 1 + sum(other > score for other in scores.values())
        for player_id, score in scores.items()
    }


def is_eligible_player_count(player_count: int) -> bool:
    return MIN_COMPETITION_PLAYERS <= player_count <= MAX_COMPETITION_PLAYERS


def is_koleskabsgame(player_id: str, placement: int, total_score: int,
                     rounds: Iterable[Dict]) -> bool:
    rounds = list(rounds)
    if not rounds or any(not isinstance(round_, dict) for round_ in rounds):
        return False
    cards = [round_.get("cards") for round_ in rounds]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in cards):
        return False
    if cards != generate_round_sequence(max(cards)):
        return False
    return (
        placement == 1 and total_score >= 125
        and all(
            isinstance(round_.get(player_id), int)
            and not isinstance(round_.get(player_id), bool)
            and round_[player_id] >= 0
            for round_ in rounds
        )
    )


def performance_score(placement: int, player_count: int, koleskabsgame: bool = False) -> float:
    """Calculate one eligible game's opponent-independent performance score."""
    if not is_eligible_player_count(player_count):
        raise ValueError("Liga-score kræver mellem 5 og 7 spillere")
    if not isinstance(placement, int) or isinstance(placement, bool) or not 1 <= placement <= player_count:
        raise ValueError("Placeringen er ugyldig")
    base = 100.0 * (player_count - placement) / (player_count - 1)
    field_bonus = 5.0 * (player_count - MIN_COMPETITION_PLAYERS) if placement == 1 else 0.0
    win_bonus = WIN_BONUS if placement == 1 else 0.0
    return base + win_bonus + field_bonus + (KOLESKAB_BONUS if koleskabsgame else 0.0)
