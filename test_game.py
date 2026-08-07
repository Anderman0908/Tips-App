import unittest

from Game import Game
from Scoring import calculate_score, generate_round_sequence, valid_scores_for_round


class ScoringTests(unittest.TestCase):
    def test_round_sequences(self) -> None:
        self.assertEqual(generate_round_sequence(3), [3, 2, 1, 1, 2, 3])

    def test_scores(self) -> None:
        self.assertEqual(calculate_score(0, 0), 7)
        self.assertEqual(calculate_score(3, 3), 13)
        self.assertEqual(calculate_score(3, 1), -2)
        self.assertEqual(valid_scores_for_round(2), [-2, -1, 7, 11, 12])
        self.assertEqual(valid_scores_for_round(2, neutral_score=9), [-2, -1, 9, 11, 12])
        self.assertEqual(calculate_score(0, 0, neutral_score=9), 9)


class GameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(max_cards=2)
        self.anna = self.game.add_player(" Anna ")
        self.bo = self.game.add_player("Bo")

    def test_names_are_clean_and_unique(self) -> None:
        self.assertEqual(self.anna.name, "Anna")
        with self.assertRaises(ValueError):
            self.game.add_player("anna")
        with self.assertRaises(ValueError):
            Game().add_player("  ")

    def test_rejects_unknown_player_and_wrong_round(self) -> None:
        with self.assertRaises(ValueError):
            self.game.record_score(999, 7)
        with self.assertRaises(RuntimeError):
            self.game.record_score(self.anna.id, 7, round_index=1)
        with self.assertRaises(IndexError):
            self.game.record_score(self.anna.id, 7, round_index=99)
        with self.assertRaises(ValueError):
            self.game.record_score(self.anna.id, True)

    def test_duplicate_score_submission_is_rejected(self) -> None:
        self.game.record_score(self.anna.id, 11)
        with self.assertRaises(ValueError):
            self.game.record_score(self.anna.id, 7)

    def test_game_limits_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            Game(max_cards=14)
        with self.assertRaises(ValueError):
            Game(neutral_score=11)

    def test_complete_game_flow(self) -> None:
        self.game.record_score(self.anna.id, 11)
        self.game.record_score(self.bo.id, 7)
        self.assertTrue(self.game.advance_round())
        self.game.record_score(self.anna.id, 11)
        self.game.record_score(self.bo.id, -1)
        self.assertEqual(self.game.totals(), {self.anna.id: 22, self.bo.id: 6})
        self.assertEqual(self.game.standings()[0], self.anna)

    def test_cannot_advance_without_every_score(self) -> None:
        self.game.record_score(self.anna.id, 7)
        with self.assertRaises(RuntimeError):
            self.game.advance_round()

    def test_last_score_can_be_removed_after_advancing(self) -> None:
        self.game.record_score(self.anna.id, 11)
        self.game.record_score(self.bo.id, 7)
        self.game.advance_round()
        self.game.remove_score(self.bo.id, 0)
        self.assertEqual(self.game.current_round_index, 0)
        self.assertNotIn(self.bo.id, self.game.rounds[0].scores)

    def test_custom_neutral_score(self) -> None:
        game = Game(max_cards=1, neutral_score=9)
        player = game.add_player("A")
        game.add_player("B")
        game.record_score(player.id, 9)
        self.assertEqual(game.neutral_score, 9)

    def test_active_game_snapshot_round_trip_and_undo_history(self) -> None:
        self.game.record_score(self.anna.id, 11)
        restored, history, player_index = Game.from_snapshot(self.game.snapshot())
        self.assertEqual(restored.snapshot(), self.game.snapshot())
        self.assertEqual(history, [{"round": 0, "player_id": 1, "player_idx": 0}])
        self.assertEqual(player_index, 1)

        restored.record_score(restored.players[player_index].id, 7)
        restored.advance_round()
        restored.record_score(restored.players[0].id, 11)
        second_restore, second_history, second_player_index = Game.from_snapshot(restored.snapshot())
        self.assertEqual(second_restore.snapshot(), restored.snapshot())
        self.assertEqual(len(second_history), 3)
        self.assertEqual(second_player_index, 1)

    def test_active_game_snapshot_rejects_nonsequential_scores(self) -> None:
        snapshot = self.game.snapshot()
        snapshot["scores"][0] = [None, 7]
        with self.assertRaises(ValueError):
            Game.from_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
