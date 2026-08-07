"""Development-only Pirate Whist game generation.

This module generates raw game results only. Persistence, league-score updates and all
derived statistics continue through the production Competition pipeline.
"""

import os
import random
from pathlib import Path
from typing import Dict, List, Optional

from Competition import DEFAULT_PATH, MAX_CARDS, delete_game, load_data, record_game
from LeagueScore import (
    MAX_COMPETITION_PLAYERS,
    MIN_COMPETITION_PLAYERS,
    is_koleskabsgame,
    placements_from_scores,
)
from Scoring import generate_round_sequence, valid_scores_for_round
from Statistics import leaderboard

TEST_MODE_ENV = "PIRATE_WHIST_TEST_MODE"
MAX_SIMULATED_GAMES = 20


def test_mode_enabled() -> bool:
    return os.environ.get(TEST_MODE_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}


def _require_test_mode() -> None:
    if not test_mode_enabled():
        raise PermissionError(f"Simulation kræver {TEST_MODE_ENV}=1")


def _selected_players(data: Dict, player_ids: List[str]) -> List[Dict]:
    if not isinstance(player_ids, list) or not MIN_COMPETITION_PLAYERS <= len(player_ids) <= MAX_COMPETITION_PLAYERS:
        raise ValueError(f"Vælg mellem {MIN_COMPETITION_PLAYERS} og {MAX_COMPETITION_PLAYERS} spillere")
    if len(set(player_ids)) != len(player_ids):
        raise ValueError("Den samme spiller må kun vælges én gang")
    by_id = {player["id"]: player for player in data["players"]}
    if any(not isinstance(player_id, str) or player_id not in by_id for player_id in player_ids):
        raise ValueError("Alle deltagere skal være eksisterende spillere")
    return [by_id[player_id] for player_id in player_ids]


def _pick_round_score(rng: random.Random, cards: int, neutral_score: int, performance: float) -> int:
    valid = valid_scores_for_round(cards, neutral_score)
    positive_probability = min(0.38, max(0.08, 0.23 + 0.065 * performance))
    negative_probability = min(0.44, max(0.16, 0.30 - 0.05 * performance))
    rare_probability = 0.015
    draw = rng.random()

    if draw < negative_probability:
        if cards == 1 or rng.random() < 0.88:
            return -1
        if cards >= 2 and rng.random() < 0.84:
            return -2
        return rng.choice([score for score in valid if score < -2] or [-2])
    if draw < negative_probability + positive_probability:
        if cards == 1 or rng.random() < 0.82:
            return 11
        if cards >= 2 and rng.random() < 0.84:
            return 12
        return rng.choice([score for score in valid if score > 12] or [12])
    if draw < negative_probability + positive_probability + rare_probability:
        unusual = [score for score in valid if score not in {-2, -1, neutral_score, 11, 12}]
        if unusual:
            return rng.choice(unusual)
    return neutral_score


def generate_simulated_games(
    data: Dict, player_ids: List[str], count: int = 1, seed: Optional[int] = None,
    max_cards: int = 7, neutral_score: Optional[int] = None,
) -> List[Dict]:
    """Generate deterministic, unsaved game previews when test mode is enabled."""
    _require_test_mode()
    players = _selected_players(data, player_ids)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_SIMULATED_GAMES:
        raise ValueError(f"Antal testspil skal være mellem 1 og {MAX_SIMULATED_GAMES}")
    if not isinstance(max_cards, int) or isinstance(max_cards, bool) or not 1 <= max_cards <= MAX_CARDS:
        raise ValueError(f"Højeste antal kort skal være mellem 1 og {MAX_CARDS}")
    neutral = data.get("settings", {}).get("neutral_score", 7) if neutral_score is None else neutral_score
    if not isinstance(neutral, int) or isinstance(neutral, bool) or not 0 <= neutral <= 10:
        raise ValueError("Neutralværdien skal være mellem 0 og 10")

    board = leaderboard(data)
    league_scores = {row["id"]: row["league_score"] for row in board["official"] + board["provisional"]}
    mean_score = sum(league_scores[player["id"]] for player in players) / len(players)
    rng = random.Random(seed)
    games = []
    for _ in range(count):
        performances = {
            player["id"]: 0.35 * (league_scores[player["id"]] - mean_score) / 25.0 + rng.gauss(0, 1)
            for player in players
        }
        rounds = []
        totals = {player["id"]: 0 for player in players}
        for cards in generate_round_sequence(max_cards):
            round_ = {"cards": cards}
            for player in players:
                score = _pick_round_score(rng, cards, neutral, performances[player["id"]])
                round_[player["id"]] = score
                totals[player["id"]] += score
            rounds.append(round_)
        placements = placements_from_scores(totals)
        fridge_players = [
            player["id"] for player in players
            if is_koleskabsgame(
                player["id"], placements[player["id"]], totals[player["id"]], rounds,
            )
        ]
        games.append({
            "id": f"sim-{rng.getrandbits(128):032x}", "source": "simulation",
            "scores": totals, "placements": placements, "rounds": rounds,
            "neutral_score": neutral, "koleskab_player_ids": fridge_players,
        })
    return games


def save_simulated_games(games: List[Dict], path: Path = DEFAULT_PATH) -> List[Dict]:
    """Confirm and persist previews through the normal completed-game pipeline."""
    _require_test_mode()
    if not isinstance(games, list) or not 1 <= len(games) <= MAX_SIMULATED_GAMES:
        raise ValueError("Der er ingen gyldige testspil at gemme")
    saved = []
    for game in games:
        if not isinstance(game, dict) or game.get("source") != "simulation":
            raise ValueError("Testspillet mangler simulationsmærket")
        saved.append(record_game(
            game["scores"], path=path, game_id=game["id"], rounds=game["rounds"],
            location="Simuleret testspil", neutral_score=game["neutral_score"], source="simulation",
        ))
    return saved


def delete_simulated_game(game_id: str, path: Path = DEFAULT_PATH) -> None:
    _require_test_mode()
    delete_game(game_id, path, required_source="simulation")


def delete_all_simulated_games(path: Path = DEFAULT_PATH) -> int:
    _require_test_mode()
    game_ids = [game["id"] for game in load_data(path)["games"] if game.get("source") == "simulation"]
    for game_id in game_ids:
        delete_game(game_id, path, required_source="simulation")
    return len(game_ids)
