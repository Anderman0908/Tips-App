import unittest

from LeagueScore import (
    KOLESKAB_BONUS, WIN_BONUS, is_koleskabsgame, performance_score,
    placements_from_scores,
)


class LeagueScoreTests(unittest.TestCase):
    def test_normalized_scores_for_five_six_and_seven_players(self) -> None:
        expected = {
            5: [110, 75, 50, 25, 0],
            6: [115, 80, 60, 40, 20, 0],
            7: [120, 100 * 5 / 6, 100 * 4 / 6, 50, 100 * 2 / 6, 100 / 6, 0],
        }
        for count, scores in expected.items():
            for placement, score in enumerate(scores, 1):
                self.assertAlmostEqual(performance_score(placement, count), score)

    def test_koleskab_adds_exactly_fifty_points(self) -> None:
        self.assertEqual(KOLESKAB_BONUS, 50)
        self.assertEqual(WIN_BONUS, 10)
        self.assertEqual(performance_score(1, 5, True), 160)
        self.assertEqual(performance_score(1, 6, True), 165)
        self.assertEqual(performance_score(1, 7, True), 170)

    def test_opponent_identity_and_strength_are_not_inputs(self) -> None:
        self.assertEqual(performance_score(2, 7), performance_score(2, 7))
        with self.assertRaises(ValueError):
            performance_score(1, 4)
        with self.assertRaises(ValueError):
            performance_score(1, 8)

    def test_ties_share_placement(self) -> None:
        placements = placements_from_scores({"a": 100, "b": 100, "c": 80, "d": 60, "e": 40})
        self.assertEqual(placements, {"a": 1, "b": 1, "c": 3, "d": 4, "e": 5})
        self.assertEqual(performance_score(placements["a"], 5), performance_score(placements["b"], 5))

    def test_koleskab_requires_rounds_win_125_and_no_negative_score(self) -> None:
        clean = [{"cards": 1, "a": 11}, {"cards": 1, "a": 11}]
        negative = [{"cards": 1, "a": -1}] + clean[1:]
        self.assertTrue(is_koleskabsgame("a", 1, 132, clean))
        self.assertFalse(is_koleskabsgame("a", 1, 124, clean))
        self.assertFalse(is_koleskabsgame("a", 2, 132, clean))
        self.assertFalse(is_koleskabsgame("a", 1, 132, negative))
        self.assertFalse(is_koleskabsgame("a", 1, 132, []))


if __name__ == "__main__":
    unittest.main()
