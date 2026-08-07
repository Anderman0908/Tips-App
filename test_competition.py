import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import Competition
from PIL import Image

from Competition import (
    ConflictError, DataCorruptionError, add_player, delete_game, load_data,
    normalize_avatar_upload, record_game, remove_avatar, save_avatar, update_game,
    update_player, update_settings,
)
from LeagueScore import ALGORITHM_NAME, ALGORITHM_VERSION
from Statistics import (
    CHAMPION_TITLE, LAST_PLACE_TITLE, drunkenbolten, hall_of_fame, initials,
    leaderboard, player_statistics, shots_from_score,
)


class LeaguePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "league.json"
        self.players = [add_player(name, self.path) for name in ("Alice", "Bob", "Cara", "Drew", "Eli", "Fay", "Gus")]
        self.a, self.b, self.c, self.d, self.e, self.f, self.g = self.players

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def scores(self, values=(100, 80, 60, 40, 20), players=None):
        chosen = players or self.players[:len(values)]
        return {player["id"]: value for player, value in zip(chosen, values)}

    def test_new_games_require_five_to_seven_existing_players(self) -> None:
        with self.assertRaises(ValueError):
            record_game(self.scores((30, 20, 10)), self.path)
        extra = add_player("Hank", self.path)
        with self.assertRaises(ValueError):
            record_game(self.scores((80, 70, 60, 50, 40, 30, 20), self.players) | {extra["id"]: 10}, self.path)
        self.assertEqual(len(record_game(self.scores(), self.path)["results"]), 5)
        self.assertEqual(len(record_game(self.scores((120, 100, 80, 60, 40, 20, 0)), self.path)["results"]), 7)

    def test_idempotency_and_stable_player_ids(self) -> None:
        game = record_game(self.scores(), self.path, game_id="fixed")
        self.assertEqual(game, record_game(self.scores(), self.path, game_id="fixed"))
        with self.assertRaises(ConflictError):
            record_game(self.scores((20, 40, 60, 80, 100)), self.path, game_id="fixed")
        update_player(self.a["id"], "Alicia", self.path)
        data = load_data(self.path)
        self.assertEqual(data["games"][0]["results"][0]["player_id"], self.a["id"])

    def test_record_game_can_report_exactly_one_atomic_creation(self) -> None:
        def submit():
            return record_game(
                self.scores(), self.path, game_id="atomic-created", return_created=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(created for _, created in outcomes), [False, True])
        self.assertEqual(sum(game["id"] == "atomic-created" for game in load_data(self.path)["games"]), 1)

    def test_current_schema_is_not_permissively_migrated(self) -> None:
        current = load_data(self.path)
        current["players"][0].pop("name")
        strict_path = Path(self.temp_dir.name) / "strict-current.json"
        strict_path.write_text(json.dumps(current), encoding="utf-8")
        with self.assertRaises(DataCorruptionError):
            load_data(strict_path)

    def test_malformed_explicit_legacy_schema_fails_closed(self) -> None:
        malformed = {
            "schema_version": 5,
            "players": ["Alice", "Bob"],
            "games": [{"results": ["not-a-result"], "rounds": []}],
            "settings": {"neutral_score": 7},
        }
        legacy_path = Path(self.temp_dir.name) / "malformed-v5.json"
        legacy_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaises(DataCorruptionError):
            load_data(legacy_path)

    def test_derived_history_is_rebuilt_and_strictly_validated(self) -> None:
        record_game(self.scores(), self.path, game_id="derived")
        current = load_data(self.path)
        current["games"][0]["results"][0]["placement"] = 99
        rebuilt_path = Path(self.temp_dir.name) / "rebuilt.json"
        rebuilt_path.write_text(json.dumps(current), encoding="utf-8")
        rebuilt = load_data(rebuilt_path)
        self.assertEqual(rebuilt["games"][0]["results"][0]["placement"], 1)

        rebuilt["games"][0]["results"][0]["eligible_game_number"] = True
        with self.assertRaises(DataCorruptionError):
            Competition.save_data(rebuilt, rebuilt_path)

    def test_cache_detects_same_size_and_mtime_external_change(self) -> None:
        cached = load_data(self.path)
        self.assertEqual(next(p for p in cached["players"] if p["id"] == self.a["id"])["name"], "Alice")
        stat = self.path.stat()
        content = self.path.read_bytes()
        changed = content.replace(b'"name": "Alice"', b'"name": "Aline"', 1)
        self.assertEqual(len(content), len(changed))
        self.path.write_bytes(changed)
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        changed_data = load_data(self.path)
        self.assertEqual(next(p for p in changed_data["players"] if p["id"] == self.a["id"])["name"], "Aline")

    def test_processing_uses_only_league_score_fields(self) -> None:
        game = record_game(self.scores(), self.path)
        self.assertEqual((game["league_score_algorithm"], game["league_score_version"]),
                         (ALGORITHM_NAME, ALGORITHM_VERSION))
        self.assertTrue(game["league_score_processed"])
        for result in game["results"]:
            self.assertTrue(result["league_score_eligible"])
            self.assertNotIn("mu_before", result)
            self.assertNotIn("sigma_after", result)
        self.assertNotIn("rating_algorithm", game)

    def test_five_eligible_games_create_official_titles(self) -> None:
        for index in range(5):
            record_game(self.scores((100, 80, 60, 40, 20, 10, 0)), self.path, game_id=f"game-{index}")
        board = leaderboard(load_data(self.path))
        self.assertEqual(len(board["official"]), 7)
        self.assertEqual(board["official"][0]["id"], self.a["id"])
        self.assertEqual(board["official"][0]["league_title"], CHAMPION_TITLE)
        self.assertEqual(board["official"][-1]["league_title"], LAST_PLACE_TITLE)
        self.assertEqual(board["official"][0]["league_score"], 120)

    def test_titles_transfer_when_average_performance_changes(self) -> None:
        for index in range(5):
            record_game(self.scores((100, 80, 60, 40, 20)), self.path, game_id=f"a-{index}")
        self.assertEqual(leaderboard(load_data(self.path))["official"][0]["id"], self.a["id"])
        for index in range(7):
            record_game(self.scores((80, 100, 60, 40, 20)), self.path, game_id=f"b-{index}")
        board = leaderboard(load_data(self.path))
        self.assertEqual(board["official"][0]["id"], self.b["id"])
        self.assertEqual(board["official"][0]["league_title"], CHAMPION_TITLE)

    def test_attendance_alone_does_not_change_player_score(self) -> None:
        for index in range(5):
            record_game(self.scores((90, 100, 60, 40, 20)), self.path, game_id=f"base-{index}")
        before = player_statistics(load_data(self.path), self.a["id"])["league_score"]
        absent_group = [self.b, self.c, self.d, self.e, self.f]
        for index in range(5):
            record_game(self.scores((100, 80, 60, 40, 20), absent_group), self.path, game_id=f"absent-{index}")
        after = player_statistics(load_data(self.path), self.a["id"])["league_score"]
        self.assertEqual((before, after), (75, 75))

    def test_delete_and_historical_edit_replay_following_history(self) -> None:
        first = record_game(self.scores(), self.path, game_id="first")
        record_game(self.scores((80, 100, 60, 40, 20)), self.path, game_id="second")
        update_game("first", self.scores((80, 100, 60, 40, 20)), self.path)
        changed = load_data(self.path)
        second_a = next(r for r in changed["games"][1]["results"] if r["player_id"] == self.a["id"])
        self.assertEqual(second_a["league_score_before"], 75)
        delete_game("first", self.path)
        remaining_a = next(r for r in load_data(self.path)["games"][0]["results"] if r["player_id"] == self.a["id"])
        self.assertEqual((remaining_a["league_score_before"], remaining_a["eligible_game_number"]), (0, 1))
        self.assertNotEqual(first["results"][0]["league_score_after"], remaining_a["league_score_after"])

    def test_replay_is_deterministic_with_equal_timestamps(self) -> None:
        timestamp = "2026-01-01T20:00:00+00:00"
        record_game(self.scores(), self.path, game_id="b-game")
        record_game(self.scores((80, 100, 60, 40, 20)), self.path, game_id="a-game")
        update_game("b-game", self.scores(), self.path, completed_at=timestamp)
        update_game("a-game", self.scores((80, 100, 60, 40, 20)), self.path, completed_at=timestamp)
        data = load_data(self.path)
        Competition._rebuild_league_scores(data)
        first = json.dumps(data, sort_keys=True)
        Competition._rebuild_league_scores(data)
        self.assertEqual(first, json.dumps(data, sort_keys=True))
        self.assertEqual([game["id"] for game in sorted(data["games"], key=lambda g: (g["completed_at"], g["id"]))],
                         ["a-game", "b-game"])

    def test_old_openskill_history_migrates_and_under_five_is_excluded(self) -> None:
        old_path = Path(self.temp_dir.name) / "old.json"
        players = [
            {"id": f"p{i}", "name": f"Old {i}", "avatar": None, "joined_at": "2025-01-01T00:00:00+00:00"}
            for i in range(4)
        ]
        results = [
            {"player_id": player["id"], "score": 40 - index * 10, "placement": index + 1,
             "mu_before": 25, "sigma_before": 7, "mu_after": 26, "sigma_after": 6.5}
            for index, player in enumerate(players)
        ]
        raw = {"schema_version": 5, "players": players, "settings": {"neutral_score": 7}, "games": [{
            "id": "legacy", "completed_at": "2025-02-01T20:00:00+00:00", "location": None,
            "status": "completed", "results": results, "rounds": [], "neutral_score": 7,
            "rating_processed": True, "rating_algorithm": "openskill-thurstone-mosteller-part", "rating_version": 2,
        }]}
        old_path.write_text(json.dumps(raw), encoding="utf-8")
        data = load_data(old_path)
        result = data["games"][0]["results"][0]
        self.assertEqual(data["schema_version"], 6)
        self.assertFalse(result["league_score_eligible"])
        self.assertIsNone(result["performance_score"])
        self.assertEqual(result["league_score_after"], 0)
        self.assertNotIn("mu_after", result)
        self.assertEqual(leaderboard(data)["official"], [])
        self.assertEqual(player_statistics(data, "p0")["games"], 1)

    def test_koleskab_round_wins_and_hall_of_fame_share_raw_rounds(self) -> None:
        rounds = [
            {"cards": cards, self.a["id"]: 11, self.b["id"]: 7, self.c["id"]: -1,
             self.d["id"]: 7, self.e["id"]: 7}
            for cards in (7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7)
        ]
        game = record_game(self.scores((154, 98, -14, 98, 98)), self.path, game_id="fridge", rounds=rounds)
        a_result = next(result for result in game["results"] if result["player_id"] == self.a["id"])
        self.assertEqual(a_result["performance_score"], 160)
        stats = player_statistics(load_data(self.path), self.a["id"])
        self.assertEqual((stats["koleskabsgames"], stats["rounds_won"], stats["round_win_rate"]), (1, 14, 100))
        record = next(item for item in hall_of_fame(load_data(self.path)) if item["title"] == "Flest Køleskabsgames")
        self.assertEqual(record["game_id"], "fridge")
        rounds_record = next(
            item for item in hall_of_fame(load_data(self.path))
            if item["title"].startswith("Flest vundne")
        )
        self.assertEqual(rounds_record["game_id"], "fridge")

    def test_no_round_history_never_awards_koleskab_bonus(self) -> None:
        game = record_game(self.scores((144, 132, 84, 40, 20)), self.path)
        winner = next(result for result in game["results"] if result["placement"] == 1)
        self.assertEqual(winner["performance_score"], 110)
        self.assertEqual(player_statistics(load_data(self.path), winner["player_id"])["koleskabsgames"], 0)

    def test_tied_winners_share_first_place_and_bonus(self) -> None:
        game = record_game(self.scores((100, 100, 80, 60, 40, 20, 0)), self.path)
        winners = [result for result in game["results"] if result["placement"] == 1]
        self.assertEqual(len(winners), 2)
        self.assertTrue(all(result["performance_score"] == 120 for result in winners))

    def test_statistics_and_hall_of_fame_agree_with_history(self) -> None:
        for index in range(5):
            record_game(self.scores((100, 80, 60, 40, 20)), self.path, game_id=f"chain-{index}")
        data = load_data(self.path)
        result = data["games"][-1]["results"][0]
        stats = player_statistics(data, result["player_id"])
        board_row = next(row for row in leaderboard(data)["official"] if row["id"] == result["player_id"])
        record = next(item for item in hall_of_fame(data) if item["title"] == "Højeste liga-score")
        self.assertEqual(stats["league_score"], result["league_score_after"])
        self.assertEqual(board_row["league_score"], result["league_score_after"])
        self.assertEqual(record["value"], stats["highest_official_league_score"])

    def test_ordinary_statistics(self) -> None:
        games = [
            (100, 80, 60, 40, 20), (80, 100, 60, 40, 20),
            (100, 100, 60, 40, 20), (60, 80, 100, 40, 20),
        ]
        for index, values in enumerate(games):
            record_game(self.scores(values), self.path, game_id=f"stats-{index}")
        stats = player_statistics(load_data(self.path), self.a["id"])
        self.assertEqual((stats["games"], stats["wins"], stats["average_placement"]), (4, 2, 1.75))

    def test_drunkenbolten_calculation_and_shared_title(self) -> None:
        rounds = [{
            "cards": 1, self.a["id"]: -1, self.b["id"]: -1, self.c["id"]: 7,
            self.d["id"]: 11, self.e["id"]: 11,
        } for _ in range(2)]
        record_game(self.scores((-2, -2, 14, 22, 22)), self.path, rounds=rounds)
        record = drunkenbolten(load_data(self.path))
        self.assertEqual({holder["id"] for holder in record["holders"]}, {self.a["id"], self.b["id"]})
        self.assertEqual((record["shots"], record["estimated_cost_dkk"]), (2, 10))
        self.assertAlmostEqual(record["vodka_bottles"], 2 / 18)

    def test_drunkenbolten_has_no_holder_before_any_shots(self) -> None:
        record = drunkenbolten(load_data(self.path))
        self.assertEqual((record["holders"], record["shots"], record["estimated_cost_dkk"]), ([], 0, 0))

    def test_one_official_player_gets_only_the_champion_title(self) -> None:
        opponents = self.players[1:]
        opponents.extend(add_player(f"Guest {index}", self.path) for index in range(14))
        for index in range(5):
            group = [self.a, *opponents[index * 4:(index + 1) * 4]]
            record_game(self.scores((100, 80, 60, 40, 20), group), self.path, game_id=f"solo-{index}")
        official = leaderboard(load_data(self.path))["official"]
        self.assertEqual(len(official), 1)
        self.assertEqual(official[0]["league_title"], CHAMPION_TITLE)
        self.assertNotEqual(official[0]["league_title"], LAST_PLACE_TITLE)

    def test_tied_last_places_each_count_as_a_lost_game(self) -> None:
        record_game(self.scores((100, 80, 60, 20, 20)), self.path)
        data = load_data(self.path)
        self.assertEqual(player_statistics(data, self.d["id"])["last_places"], 1)
        self.assertEqual(player_statistics(data, self.e["id"])["last_places"], 1)

    def test_round_totals_and_participants_are_validated(self) -> None:
        partial = [{"cards": 1, **self.scores((11, 7, -1, 11, 7))}]
        with self.assertRaises(DataCorruptionError):
            record_game(self.scores((11, 7, -1, 11, 7)), self.path, rounds=partial)
        bad_rounds = [{"cards": 1, **self.scores((11, 7, -1, 11, 7))}]
        with self.assertRaises(DataCorruptionError):
            record_game(self.scores((99, 7, -1, 11, 7)), self.path, rounds=bad_rounds)
        missing = [{"cards": 1, **self.scores((11, 7, -1, 11))}]
        with self.assertRaises(DataCorruptionError):
            record_game(self.scores((11, 7, -1, 11, 7)), self.path, rounds=missing)

    def test_shot_statistics(self) -> None:
        self.assertEqual(shots_from_score(12), {"given": 2, "received": 0})
        self.assertEqual(shots_from_score(-2), {"given": 0, "received": 2})

    def test_neutral_score_setting_persists(self) -> None:
        update_settings(9, self.path)
        self.assertEqual(load_data(self.path)["settings"]["neutral_score"], 9)

    def test_avatar_validation_replacement_and_removal(self) -> None:
        original_dir = Competition.AVATAR_DIR
        Competition.AVATAR_DIR = Path(self.temp_dir.name) / "avatars"
        try:
            with self.assertRaises(ValueError):
                save_avatar(self.a["id"], b"bad", "image/png", self.path)
            content = io.BytesIO(); Image.new("RGB", (32, 32), "red").save(content, "PNG")
            normalized = normalize_avatar_upload(content.getvalue(), "image/png")
            with Image.open(io.BytesIO(normalized)) as preview:
                self.assertLessEqual(max(preview.size), Competition.AVATAR_SIZE)
            relative = save_avatar(self.a["id"], content.getvalue(), "image/png", self.path)
            self.assertTrue((Competition.AVATAR_DIR / Path(relative).name).exists())
            remove_avatar(self.a["id"], self.path)
            self.assertIsNone(next(p for p in load_data(self.path)["players"] if p["id"] == self.a["id"])["avatar"])
            self.assertEqual(initials("Anders Vig"), "AV")
        finally:
            Competition.AVATAR_DIR = original_dir

    def test_concurrent_player_writes_are_not_lost(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda index: add_player(f"Concurrent {index}", self.path), range(4)))
        names = {player["name"] for player in load_data(self.path)["players"]}
        self.assertTrue(all(f"Concurrent {index}" in names for index in range(4)))

    def test_corruption_recovers_backup_and_fails_closed_without_one(self) -> None:
        record_game(self.scores(), self.path, game_id="safe")
        update_settings(9, self.path)
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(load_data(self.path)["games"][0]["id"], "safe")
        broken = Path(self.temp_dir.name) / "only-broken.json"
        broken.write_text("{broken", encoding="utf-8")
        with self.assertRaises(DataCorruptionError):
            load_data(broken)

    def test_empty_or_missing_primary_uses_backup_or_fails_closed(self) -> None:
        valid_content = self.path.read_bytes()
        expected_player_count = len(load_data(self.path)["players"])

        empty = Path(self.temp_dir.name) / "empty.json"
        empty.write_bytes(b"")
        empty.with_suffix(".json.backup").write_bytes(valid_content)
        self.assertEqual(len(load_data(empty)["players"]), expected_player_count)

        missing = Path(self.temp_dir.name) / "missing.json"
        missing.with_suffix(".json.backup").write_bytes(valid_content)
        self.assertEqual(len(load_data(missing)["players"]), expected_player_count)

        no_backup = Path(self.temp_dir.name) / "empty-no-backup.json"
        no_backup.write_bytes(b"")
        with self.assertRaises(DataCorruptionError):
            load_data(no_backup)

    def test_backup_rotation_is_complete_and_loadable(self) -> None:
        update_settings(9, self.path)
        backup = self.path.with_suffix(".json.backup")
        self.assertTrue(backup.exists())
        Competition._prepare_data(json.loads(backup.read_text(encoding="utf-8")))
        self.assertEqual(list(self.path.parent.glob("league.json.backup.tmp.*")), [])

    def test_update_cannot_turn_new_eligible_game_into_small_game(self) -> None:
        record_game(self.scores(), self.path, game_id="eligible")
        with self.assertRaises(ValueError):
            update_game("eligible", self.scores((30, 20, 10, 0)), self.path)


if __name__ == "__main__":
    unittest.main()
