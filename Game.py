"""
Game state layer for Tips (aka Piratwhist).

Wraps scoring.py with actual game state: players, rounds, and each player's
self-reported score per round. No bid is stored anywhere -- players track
their own bid in their head, and just call out the resulting score.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from Scoring import generate_round_sequence, valid_scores_for_round


@dataclass
class Player:
    id: int
    name: str


@dataclass
class Round:
    cards: int
    neutral_score: int = 7
    scores: Dict[int, int] = field(default_factory=dict)  # player_id -> called-out score

    def is_complete(self, player_ids: List[int]) -> bool:
        return all(pid in self.scores for pid in player_ids)

    def valid_scores(self) -> List[int]:
        return valid_scores_for_round(self.cards, self.neutral_score)


class Game:
    def __init__(self, max_cards: int = 7, neutral_score: int = 7):
        if not isinstance(max_cards, int) or isinstance(max_cards, bool) or not 1 <= max_cards <= 13:
            raise ValueError("max_cards must be between 1 and 13")
        if not isinstance(neutral_score, int) or isinstance(neutral_score, bool) or not 0 <= neutral_score <= 10:
            raise ValueError("neutral_score must be between 0 and 10")
        self.max_cards = max_cards
        self.neutral_score = neutral_score
        self.players: List[Player] = []
        self.round_sequence: List[int] = generate_round_sequence(max_cards)
        self.rounds: List[Round] = [Round(cards=c, neutral_score=neutral_score) for c in self.round_sequence]
        self.current_round_index: int = 0

    # -- setup ---------------------------------------------------------------

    def add_player(self, name: str) -> Player:
        if self.current_round_index > 0 or self.rounds[0].scores:
            raise RuntimeError("Can't add players after the game has started")
        name = name.strip()
        if not name:
            raise ValueError("Player name cannot be empty")
        if any(player.name.casefold() == name.casefold() for player in self.players):
            raise ValueError(f"A player named {name!r} already exists")
        if len(self.players) >= 20:
            raise ValueError("A game cannot have more than 20 players")
        next_id = len(self.players) + 1
        player = Player(id=next_id, name=name)
        self.players.append(player)
        return player

    # -- recording -------------------------------------------------------------

    def record_score(self, player_id: int, score: int, round_index: Optional[int] = None) -> None:
        idx = self.current_round_index if round_index is None else round_index
        if not 0 <= idx < len(self.rounds):
            raise IndexError(f"Round index {idx} is out of range")
        if idx != self.current_round_index:
            raise RuntimeError("Scores can only be recorded for the current round")
        if not any(player.id == player_id for player in self.players):
            raise ValueError(f"Unknown player id: {player_id}")
        round_ = self.rounds[idx]
        if player_id in round_.scores:
            raise ValueError("A score is already recorded for this player and round")
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError("Score must be a whole number")
        valid = round_.valid_scores()
        if score not in valid:
            raise ValueError(f"{score} isn't a possible score for a {round_.cards}-card round. Valid: {valid}")
        round_.scores[player_id] = score

    def remove_score(self, player_id: int, round_index: int) -> None:
        """Remove one recorded score so the latest input can be corrected."""
        if not 0 <= round_index < len(self.rounds):
            raise IndexError(f"Round index {round_index} is out of range")
        if player_id not in self.rounds[round_index].scores:
            raise ValueError("No score is recorded for that player and round")
        del self.rounds[round_index].scores[player_id]
        self.current_round_index = round_index

    def advance_round(self) -> bool:
        """Move to the next round. Returns False if the game is already over."""
        if len(self.players) < 2:
            raise RuntimeError("At least two players are required to play")
        player_ids = [p.id for p in self.players]
        if not self.rounds[self.current_round_index].is_complete(player_ids):
            raise RuntimeError("Current round isn't complete for all players yet")
        if self.current_round_index + 1 >= len(self.rounds):
            return False
        self.current_round_index += 1
        return True

    @property
    def is_finished(self) -> bool:
        player_ids = [p.id for p in self.players]
        last = self.rounds[-1]
        return (
            self.current_round_index == len(self.rounds) - 1
            and last.is_complete(player_ids)
        )

    # -- reading ---------------------------------------------------------------

    def totals(self) -> Dict[int, int]:
        """player_id -> running total across all completed rounds."""
        totals = {p.id: 0 for p in self.players}
        for round_ in self.rounds:
            for pid, score in round_.scores.items():
                totals[pid] += score
        return totals

    def standings(self) -> List[Player]:
        """Players sorted by score, highest first."""
        totals = self.totals()
        return sorted(self.players, key=lambda p: totals[p.id], reverse=True)

    def snapshot(self) -> Dict:
        """Return the minimal validated state needed to resume an active game."""
        return {
            "max_cards": self.max_cards,
            "neutral_score": self.neutral_score,
            "players": [player.name for player in self.players],
            "scores": [
                [round_.scores.get(player.id) for player in self.players]
                for round_ in self.rounds
            ],
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict) -> tuple["Game", List[Dict[str, int]], int]:
        """Restore a game and its undo history from a strictly sequential snapshot."""
        if not isinstance(snapshot, dict):
            raise ValueError("Game snapshot must be an object")
        game = cls(max_cards=snapshot.get("max_cards"), neutral_score=snapshot.get("neutral_score"))
        names = snapshot.get("players")
        scores = snapshot.get("scores")
        if not isinstance(names, list) or not 2 <= len(names) <= 20:
            raise ValueError("Game snapshot must contain 2-20 players")
        if any(not isinstance(name, str) or len(name) > 80 or any(ord(char) < 32 for char in name) for name in names):
            raise ValueError("Game snapshot contains an invalid player name")
        for name in names:
            game.add_player(name)
        if not isinstance(scores, list) or len(scores) != len(game.rounds):
            raise ValueError("Game snapshot contains an invalid round count")
        if any(not isinstance(row, list) or len(row) != len(game.players) for row in scores):
            raise ValueError("Game snapshot contains an invalid score row")

        history: List[Dict[str, int]] = []
        reached_incomplete_round = False
        current_player_idx = 0
        for round_index, row in enumerate(scores):
            missing_score = False
            for player_index, (player, score) in enumerate(zip(game.players, row)):
                if score is None:
                    missing_score = True
                    current_player_idx = player_index
                    if any(value is not None for value in row[player_index + 1:]):
                        raise ValueError("Game snapshot scores must be sequential")
                    break
                if reached_incomplete_round:
                    raise ValueError("Game snapshot contains scores after an incomplete round")
                game.record_score(player.id, score)
                history.append({"round": round_index, "player_id": player.id, "player_idx": player_index})
            if missing_score:
                reached_incomplete_round = True
                if any(any(value is not None for value in later) for later in scores[round_index + 1:]):
                    raise ValueError("Game snapshot contains scores after an incomplete round")
                break
            current_player_idx = 0
            if round_index + 1 < len(game.rounds):
                game.advance_round()
        return game, history, current_player_idx


# ---------------------------------------------------------------------------
# Self-tests / smoke test. Run with `python game.py`.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    game = Game(max_cards=7)
    john = game.add_player("John")
    christian = game.add_player("Christian")

    assert game.round_sequence[0] == 7
    assert len(game.rounds) == 14

    # Round 1 (1 card)
    game.record_score(john.id, 11)
    game.record_score(christian.id, 7)

    assert game.rounds[0].is_complete([john.id, christian.id])
    assert game.advance_round() is True
    assert game.current_round_index == 1

    totals = game.totals()
    assert totals[john.id] == 11
    assert totals[christian.id] == 7

    # Round 2 (2 cards) -- John's worked example continues
    game.record_score(john.id, 7, round_index=1)   # e.g. bid 0, got 0 -> +7 (total 18)
    game.record_score(christian.id, -1, round_index=1)

    standings = game.standings()
    assert standings[0].name == "John"

    # Invalid score in the current round should be rejected
    try:
        game.record_score(john.id, 99)
        raise AssertionError("Should have rejected an impossible score")
    except ValueError:
        pass

    print("All smoke tests passed.")
    print("Round sequence (max 7):", game.round_sequence)
    print("Standings after 2 rounds:", [(p.name, game.totals()[p.id]) for p in standings])
    print("Valid scores for a 3-card round:", valid_scores_for_round(3))
