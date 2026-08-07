"""
Bare-bones CLI for Tips -- proves the Game loop works end to end.
No bid is entered anywhere; each player just calls out their score,
and the CLI checks it against the set of numbers that are actually possible.

Run: python cli.py
"""

from Game import Game


def prompt_int(prompt: str, min_val: int = None, max_val: int = None) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            val = int(raw)
        except ValueError:
            print("  -> please enter a whole number.")
            continue
        if min_val is not None and val < min_val:
            print(f"  -> must be at least {min_val}.")
            continue
        if max_val is not None and val > max_val:
            print(f"  -> must be at most {max_val}.")
            continue
        return val


def prompt_score(prompt: str, valid: list) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            val = int(raw)
        except ValueError:
            print(f"  -> please enter a whole number. Options: {valid}")
            continue
        if val not in valid:
            print(f"  -> not a possible score for this round. Options: {valid}")
            continue
        return val


def main() -> None:
    print("=== Tips Scorekeeper (CLI prototype) ===\n")

    max_cards = prompt_int("Max cards per round (e.g. 7): ", min_val=1)
    game = Game(max_cards=max_cards)

    print("\nAdd players (blank name to finish, need at least 2):")
    while True:
        name = input(f"  Player {len(game.players) + 1} name: ").strip()
        if name == "":
            if len(game.players) >= 2:
                break
            print("  -> need at least 2 players.")
            continue
        game.add_player(name)

    print(f"\nStarting game: {len(game.rounds)} rounds, max {max_cards} cards\n")

    while True:
        idx = game.current_round_index
        round_ = game.rounds[idx]
        valid = round_.valid_scores()
        print(f"--- Round {idx + 1}/{len(game.rounds)} -- {round_.cards} card(s) ---")
        print(f"Possible scores this round: {valid}")

        for p in game.players:
            score = prompt_score(f"  {p.name} got: ", valid)
            game.record_score(p.id, score)

        totals = game.totals()
        print(f"\nStandings after round {idx + 1}:")
        for p in game.standings():
            print(f"  {p.name}: {totals[p.id]}")
        print()

        if game.is_finished:
            break
        game.advance_round()

    print("=== GAME OVER ===")
    standings = game.standings()
    totals = game.totals()
    for i, p in enumerate(standings, 1):
        print(f"{i}. {p.name} -- {totals[p.id]} points")


if __name__ == "__main__":
    main()
