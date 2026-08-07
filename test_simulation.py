import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Competition import add_player, load_data, record_game
from LeagueScore import ALGORITHM_NAME, ALGORITHM_VERSION
from Scoring import valid_scores_for_round
from Simulation import (
    TEST_MODE_ENV,
    delete_all_simulated_games,
    delete_simulated_game,
    generate_simulated_games,
    save_simulated_games,
    test_mode_enabled,
)
from Statistics import hall_of_fame, player_statistics


class SimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "league.json"
        self.players = [add_player(f"Player {index}", self.path) for index in range(7)]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_every_simulation_action_rejects_when_test_mode_is_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(test_mode_enabled())
            data = load_data(self.path)
            with self.assertRaises(PermissionError):
                generate_simulated_games(data, [p["id"] for p in self.players[:5]], seed=1)
            with self.assertRaises(PermissionError):
                save_simulated_games([{}], self.path)
            with self.assertRaises(PermissionError):
                delete_simulated_game("anything", self.path)
            with self.assertRaises(PermissionError):
                delete_all_simulated_games(self.path)

    def test_seeded_generation_is_deterministic_valid_and_realistic(self) -> None:
        with patch.dict(os.environ, {TEST_MODE_ENV: "1"}):
            data = load_data(self.path)
            ids = [player["id"] for player in self.players]
            first = generate_simulated_games(data, ids, count=20, seed=6700)
            second = generate_simulated_games(data, ids, count=20, seed=6700)
            self.assertEqual(first, second)

            all_scores = []
            negative_player_games = 0
            for game in first:
                self.assertEqual(set(game["scores"]), set(ids))
                totals = {player_id: 0 for player_id in ids}
                for round_ in game["rounds"]:
                    for player_id in ids:
                        self.assertIn(round_[player_id], valid_scores_for_round(round_["cards"], 7))
                        totals[player_id] += round_[player_id]
                        all_scores.append(round_[player_id])
                self.assertEqual(totals, game["scores"])
                expected_places = {
                    player_id: 1 + sum(other > score for other in totals.values())
                    for player_id, score in totals.items()
                }
                self.assertEqual(game["placements"], expected_places)
                negative_player_games += sum(
                    any(round_[player_id] < 0 for round_ in game["rounds"])
                    for player_id in ids
                )

            core_share = sum(score in {-2, -1, 7, 11, 12} for score in all_scores) / len(all_scores)
            self.assertGreaterEqual(core_share, 0.95)
            self.assertGreater(negative_player_games / (len(first) * len(ids)), 0.80)
            average_winner = sum(max(game["scores"].values()) for game in first) / len(first)
            average_last = sum(min(game["scores"].values()) for game in first) / len(first)
            self.assertTrue(85 <= average_winner <= 125)
            self.assertTrue(35 <= average_last <= 70)

    def test_supported_player_counts_and_preview_cancellation(self) -> None:
        with patch.dict(os.environ, {TEST_MODE_ENV: "true"}):
            data = load_data(self.path)
            before = load_data(self.path)
            for count in (5, 6, 7):
                games = generate_simulated_games(
                    data, [player["id"] for player in self.players[:count]], count=1, seed=count,
                )
                self.assertEqual(len(games[0]["scores"]), count)
            with self.assertRaises(ValueError):
                generate_simulated_games(
                    data, [player["id"] for player in self.players[:4]], count=1, seed=4,
                )
            self.assertEqual(load_data(self.path), before)

    def test_save_uses_production_league_score_and_statistics_pipeline(self) -> None:
        a, b, c, d, e = self.players[:5]
        rounds = [
            {
                "cards": cards,
                a["id"]: 11,
                b["id"]: 7,
                c["id"]: -1,
                d["id"]: -1,
                e["id"]: 7,
            }
            for cards in (7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7)
        ]
        preview = {
            "id": "sim-fridge",
            "source": "simulation",
            "scores": {
                a["id"]: 154,
                b["id"]: 98,
                c["id"]: -14,
                d["id"]: -14,
                e["id"]: 98,
            },
            "placements": {
                a["id"]: 1,
                b["id"]: 2,
                c["id"]: 3,
                d["id"]: 4,
                e["id"]: 5,
            },
            "rounds": rounds,
            "neutral_score": 7,
            "koleskab_player_ids": [a["id"]],
        }
        with patch.dict(os.environ, {TEST_MODE_ENV: "on"}):
            saved = save_simulated_games([preview], self.path)[0]

        self.assertEqual(saved["source"], "simulation")
        self.assertTrue(saved["league_score_processed"])
        self.assertEqual(
            (saved["league_score_algorithm"], saved["league_score_version"]),
            (ALGORITHM_NAME, ALGORITHM_VERSION),
        )
        winner = next(result for result in saved["results"] if result["player_id"] == a["id"])
        self.assertEqual(winner["performance_score"], 160.0)
        stats = player_statistics(load_data(self.path), a["id"])
        self.assertEqual((stats["games"], stats["rounds_won"], stats["koleskabsgames"]), (1, 14, 1))
        fridge_record = next(
            record for record in hall_of_fame(load_data(self.path))
            if record["title"] == "Flest Køleskabsgames"
        )
        self.assertEqual(fridge_record["game_id"], "sim-fridge")

    def test_batch_cleanup_never_deletes_real_games_and_replays_league_scores(self) -> None:
        group = self.players[:5]
        ids = [player["id"] for player in group]
        a = group[0]
        real = record_game(dict(zip(ids, [100, 80, 60, 40, 20])), self.path, game_id="real")
        real_score = next(
            result["league_score_after"]
            for result in real["results"]
            if result["player_id"] == a["id"]
        )
        with patch.dict(os.environ, {TEST_MODE_ENV: "1"}):
            previews = generate_simulated_games(load_data(self.path), ids, count=5, seed=9)
            saved = save_simulated_games(previews, self.path)
            self.assertEqual(len(saved), 5)
            with self.assertRaises(ValueError):
                delete_simulated_game("real", self.path)
            delete_simulated_game(saved[0]["id"], self.path)
            self.assertEqual(delete_all_simulated_games(self.path), 4)

        data = load_data(self.path)
        self.assertEqual([game["id"] for game in data["games"]], ["real"])
        restored_score = next(
            result["league_score_after"]
            for result in data["games"][0]["results"]
            if result["player_id"] == a["id"]
        )
        self.assertAlmostEqual(restored_score, real_score)


if __name__ == "__main__":
    unittest.main()
