"""Deterministic, presentation-independent league statistics."""

from statistics import median, pstdev
from typing import Dict, List

from LeagueScore import OFFICIAL_GAMES_REQUIRED, is_koleskabsgame

CHAMPION_TITLE = "Den Polerede Gud"
LAST_PLACE_TITLE = "Den Menneskelige Skraldespand"
SHOT_PRICE_DKK = 5
SHOTS_PER_VODKA_BOTTLE = 18


def initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"


def shots_from_score(score: int) -> Dict[str, int]:
    """Return shots given/received for one round score."""
    return {
        "given": max(score - 10, 0) if score >= 11 else 0,
        "received": abs(score) if score < 0 else 0,
    }


def _context(data: Dict):
    players = {player["id"]: player for player in data["players"]}
    games = sorted(data["games"], key=lambda game: (game["completed_at"], game["id"]))
    return players, games


def _statistics_context(data: Dict):
    players, games = _context(data)
    entries = {player_id: [] for player_id in players}
    for game in games:
        results = game["results"]
        minimum_score = min(result["score"] for result in results)
        shot_totals = {result["player_id"]: {"given": 0, "received": 0} for result in results}
        round_wins = {result["player_id"]: 0 for result in results}
        rounds = game.get("rounds", [])
        for round_ in rounds:
            highest_score = max(round_[player_id] for player_id in shot_totals)
            for player_id in shot_totals:
                if player_id in round_:
                    shots = shots_from_score(round_[player_id])
                    shot_totals[player_id]["given"] += shots["given"]
                    shot_totals[player_id]["received"] += shots["received"]
                    round_wins[player_id] += round_[player_id] == highest_score
        for result in results:
            player_id = result["player_id"]
            has_complete_rounds = bool(rounds) and all(player_id in round_ for round_ in rounds)
            entries[player_id].append({
                **result, "game_id": game["id"], "date": game["completed_at"],
                "participants": len(results), "last_place": result["score"] == minimum_score,
                "rounds_played": len(rounds) if has_complete_rounds else 0,
                "rounds_won": round_wins[player_id] if has_complete_rounds else 0,
                "koleskabsgame": is_koleskabsgame(
                    player_id, result["placement"], result["score"], rounds,
                ),
                "shots_given": shot_totals[player_id]["given"],
                "shots_received": shot_totals[player_id]["received"],
                "league_score_eligible": result["league_score_eligible"],
                "league_score_before": result["league_score_before"],
                "performance_score": result["performance_score"],
                "league_score_after": result["league_score_after"],
                "eligible_game_number": result["eligible_game_number"],
            })
    league_year = games[-1]["completed_at"][:4] if games else ""
    return players, games, entries, league_year


def _player_statistics(players: Dict, games: List, entries_by_player: Dict, league_year: str, player_id: str) -> Dict:
    if player_id not in players:
        raise ValueError("Ukendt spiller")
    player = players[player_id]
    entries = entries_by_player[player_id]
    placements = [entry["placement"] for entry in entries]
    scores = [entry["score"] for entry in entries]
    eligible_entries = [entry for entry in entries if entry["league_score_eligible"]]
    wins = sum(place == 1 for place in placements)
    longest_without_win = current = longest = drought = 0
    longest_streak_entry = None
    for entry in entries:
        place = entry["placement"]
        if place == 1:
            current += 1
            if current > longest:
                longest = current
                longest_streak_entry = entry
            drought = 0
        else:
            current = 0; drought += 1; longest_without_win = max(longest_without_win, drought)
    league_score_values = [entry["league_score_after"] for entry in eligible_entries]
    no_last = longest_no_last = 0
    for entry in entries:
        if not entry["last_place"]:
            no_last += 1; longest_no_last = max(longest_no_last, no_last)
        else:
            no_last = 0
    active_since = min(player["joined_at"], entries[0]["date"]) if entries else player["joined_at"]
    eligible_games = sum(game["completed_at"] >= active_since for game in games)
    normalized_placements = [
        (entry["placement"] - 1) / (entry["participants"] - 1)
        for entry in entries if entry["participants"] > 1
    ]
    rounds_played = sum(entry["rounds_played"] for entry in entries)
    rounds_won = sum(entry["rounds_won"] for entry in entries)
    round_wins_by_player = {
        pid: sum(entry["rounds_won"] for entry in player_entries)
        for pid, player_entries in entries_by_player.items()
    }
    round_rank = 1 + sum(total > rounds_won for total in round_wins_by_player.values()) if rounds_played else None
    koleskab_entries = [entry for entry in entries if entry["koleskabsgame"]]
    official_score_entries = eligible_entries[OFFICIAL_GAMES_REQUIRED - 1:]
    highest_official_entry = max(official_score_entries, key=lambda entry: entry["league_score_after"], default=None)
    current_league_score = eligible_entries[-1]["league_score_after"] if eligible_entries else 0.0
    return {
        **player, "league_score": current_league_score,
        "latest_change": (
            eligible_entries[-1]["league_score_after"] - eligible_entries[-1]["league_score_before"]
            if eligible_entries else 0
        ),
        "highest_league_score": max(league_score_values, default=0),
        "highest_official_league_score": max(
            (entry["league_score_after"] for entry in official_score_entries), default=0
        ),
        "lowest_league_score": min(league_score_values, default=0),
        "games": len(entries), "eligible_games": len(eligible_entries),
        "wins": wins, "seconds": placements.count(2), "thirds": placements.count(3),
        "last_places": sum(entry["last_place"] for entry in entries),
        "win_rate": wins / len(entries) * 100 if entries else 0,
        "top2_rate": sum(p <= 2 for p in placements) / len(entries) * 100 if entries else 0,
        "podium_rate": sum(p <= 3 for p in placements) / len(entries) * 100 if entries else 0,
        "average_placement": sum(placements) / len(placements) if placements else 0,
        "median_placement": median(placements) if placements else 0,
        "best_score": max(scores) if scores else 0, "worst_score": min(scores) if scores else 0,
        "average_score": sum(scores) / len(scores) if scores else 0, "total_score": sum(scores),
        "shots_given": sum(entry["shots_given"] for entry in entries),
        "shots_received": sum(entry["shots_received"] for entry in entries),
        "rounds_played": rounds_played, "rounds_won": rounds_won,
        "round_win_rate": rounds_won / rounds_played * 100 if rounds_played else 0,
        "rounds_won_rank": round_rank,
        "koleskabsgames": len(koleskab_entries),
        "first_koleskabsgame": koleskab_entries[0] if koleskab_entries else None,
        "latest_koleskabsgame": koleskab_entries[-1] if koleskab_entries else None,
        "podium_finishes": sum(p <= 3 for p in placements),
        "seasonal_points": sum(entry["score"] for entry in entries if entry["date"].startswith(league_year)),
        "participation_rate": len(entries) / eligible_games * 100 if eligible_games else 0,
        "longest_win_streak": longest, "longest_without_win": longest_without_win,
        "longest_win_streak_achievement": longest_streak_entry,
        "longest_without_last": longest_no_last, "current_streak": current,
        "provisional": len(eligible_entries) < OFFICIAL_GAMES_REQUIRED,
        "highest_official_league_score_achievement": highest_official_entry,
        "placement_volatility": pstdev(normalized_placements) if len(normalized_placements) > 1 else 0,
        "recent_form": placements[-5:], "history": entries,
    }


def player_statistics(data: Dict, player_id: str) -> Dict:
    return _player_statistics(*_statistics_context(data), player_id)


def leaderboard(data: Dict) -> Dict[str, List[Dict]]:
    context = _statistics_context(data)
    rows = [_player_statistics(*context, player["id"]) for player in data["players"]]
    for row in rows:
        row["league_title"] = None
        row["league_title_kind"] = None
    official = [row for row in rows if not row["provisional"]]
    official.sort(key=lambda row: (-row["league_score"], row["name"].casefold(), row["id"]))
    for rank, row in enumerate(official, 1):
        row["rank"] = rank
    if official:
        official[0]["league_title"] = CHAMPION_TITLE
        official[0]["league_title_kind"] = "champion"
    if len(official) > 1:
        official[-1]["league_title"] = LAST_PLACE_TITLE
        official[-1]["league_title_kind"] = "last"
    provisional = [row for row in rows if row["provisional"]]
    provisional.sort(key=lambda row: (-row["league_score"], row["name"].casefold(), row["id"]))
    return {"official": official, "provisional": provisional}


def drunkenbolten(data: Dict) -> Dict:
    """Return every holder of the league's shared most-shots-received title."""
    context = _statistics_context(data)
    rows = [_player_statistics(*context, player["id"]) for player in data["players"]]
    shots = max((row["shots_received"] for row in rows), default=0)
    holders = sorted(
        (row for row in rows if shots > 0 and row["shots_received"] == shots),
        key=lambda row: (row["name"].casefold(), row["id"]),
    )
    return {
        "holders": holders,
        "shots": shots,
        "estimated_cost_dkk": shots * SHOT_PRICE_DKK,
        "vodka_bottles": shots / SHOTS_PER_VODKA_BOTTLE,
    }


def hall_of_fame(data: Dict) -> List[Dict]:
    """Return the small, authoritative set of explorable league records."""
    if not data.get("games"):
        return []
    context = _statistics_context(data)
    stats = [_player_statistics(*context, player["id"]) for player in data["players"]]
    played = [row for row in stats if row["games"]]
    if not played:
        return []

    def make_record(title: str, row: Dict, key: str, achievement: Dict | None,
                    unit: str, related: List[Dict] | None = None) -> Dict:
        return {
            "title": title, "player_id": row["id"], "name": row["name"],
            "value": row[key], "unit": unit,
            "date": achievement["date"] if achievement else None,
            "game_id": achievement["game_id"] if achievement else None,
            "related": related or [],
        }

    wins_holder = max(played, key=lambda row: row["wins"])
    games_holder = max(played, key=lambda row: row["games"])
    streak_holder = max(played, key=lambda row: row["longest_win_streak"])
    rounds_holder = max(played, key=lambda row: row["rounds_won"])
    fridge_holder = max(played, key=lambda row: row["koleskabsgames"])
    fridge_record = make_record(
        "Flest Køleskabsgames", fridge_holder, "koleskabsgames",
        fridge_holder["latest_koleskabsgame"], "Køleskabsgames",
        [{"label": "Første", "value": fridge_holder["first_koleskabsgame"]["date"][:10]}]
        if fridge_holder["first_koleskabsgame"] else [],
    )
    if not fridge_record["value"]:
        fridge_record.update({"player_id": None, "name": "Ingen endnu", "date": None, "game_id": None})

    rounds_record = make_record(
        "Flest vundne runder", rounds_holder, "rounds_won",
        next((entry for entry in reversed(rounds_holder["history"]) if entry["rounds_won"] > 0), None),
        "runder", [{"label": "Andel", "value": f'{rounds_holder["round_win_rate"]:.1f}%'}],
    )
    if not rounds_holder["rounds_played"]:
        rounds_record.update({
            "player_id": None, "name": "Ingen registrerede runder", "date": None,
            "game_id": None, "related": [],
        })

    output = [
        make_record(
            "Flest sejre", wins_holder, "wins",
            next((entry for entry in reversed(wins_holder["history"]) if entry["placement"] == 1), None),
            "sejre", [{"label": "Win rate", "value": f'{wins_holder["win_rate"]:.1f}%'}],
        ),
        fridge_record,
        rounds_record,
        make_record(
            "Længste winstreak", streak_holder, "longest_win_streak",
            streak_holder["longest_win_streak_achievement"], "sejre i træk",
        ),
        make_record("Flest spil", games_holder, "games", games_holder["history"][-1], "spil"),
    ]

    officially_ranked = [row for row in stats if not row["provisional"]]
    if officially_ranked:
        score_holder = max(officially_ranked, key=lambda row: row["highest_official_league_score"])
        output.insert(0, make_record(
            "Højeste liga-score", score_holder, "highest_official_league_score",
            score_holder["highest_official_league_score_achievement"], "liga-score",
            [{"label": "Nuværende", "value": f'{score_holder["league_score"]:.1f}'}],
        ))

    winning_results = [
        (game, result) for game in context[1] for result in game["results"]
        if result["placement"] == 1
    ]
    if winning_results:
        game, result = max(winning_results, key=lambda item: item[1]["score"])
        winner = next(row for row in played if row["id"] == result["player_id"])
        output.insert(3, {
            "title": "Højeste vinderscore", "player_id": winner["id"], "name": winner["name"],
            "value": result["score"], "unit": "point", "date": game["completed_at"],
            "game_id": game["id"], "related": [{"label": "Spillere", "value": len(game["results"])}],
        })
    return output
