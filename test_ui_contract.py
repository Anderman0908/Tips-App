import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class UISimplificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = (ROOT / "App.py").read_text(encoding="utf-8")
        cls.statistics = (ROOT / "Statistics.py").read_text(encoding="utf-8")
        cls.requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    def test_graph_and_head_to_head_runtime_is_removed(self) -> None:
        for obsolete in (
            "import altair", "st.altair_chart", "st.bar_chart", "st.line_chart",
            "line_chart_with_points", "head_to_head", '"Graf"',
        ):
            self.assertNotIn(obsolete, self.app)
        self.assertNotIn("def head_to_head", self.statistics)
        self.assertNotIn("altair", self.requirements.casefold())

    def test_new_homepage_and_leaderboard_contract_is_present(self) -> None:
        self.assertIn("Drukkenbolten", self.app)
        self.assertIn("recent-game-card", self.app)
        self.assertIn("Gennemsnitsplacering", self.app)
        self.assertIn("Tabte spil", self.app)
        self.assertIn("score-change.negative", self.app)
        self.assertIn("#e27870", self.app)

    def test_mobile_and_saved_game_safety_contracts_are_present(self) -> None:
        self.assertIn("@media(max-width:950px)", self.app)
        self.assertIn("@media(pointer:coarse)", self.app)
        self.assertIn(".stFormSubmitButton>button", self.app)
        self.assertIn("competition_created_in_session", self.app)
        self.assertIn("return_created=True", self.app)
        self.assertIn("score-player-name", self.app)
        self.assertIn('"scroll_to_top": False', self.app)
        self.assertIn("st.iframe(", self.app)


if __name__ == "__main__":
    unittest.main()
