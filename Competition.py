"""Validated, atomic JSON persistence for the Pirate Whist league."""

import io
import hashlib
import json
import math
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from PIL import Image, ImageOps, UnidentifiedImageError

import GitBackup
from LeagueScore import (
    ALGORITHM_NAME, ALGORITHM_VERSION, MAX_COMPETITION_PLAYERS,
    MIN_COMPETITION_PLAYERS, is_eligible_player_count, is_koleskabsgame,
    performance_score, placements_from_scores,
)
from Scoring import generate_round_sequence, valid_scores_for_round

DEFAULT_PLAYERS = ["Anders", "Ankersø", "AV"]
_DATA_DIR = Path(os.environ["PIRATE_WHIST_DATA_DIR"]) if os.environ.get("PIRATE_WHIST_DATA_DIR") else Path(__file__).parent
DEFAULT_PATH = _DATA_DIR / "competition_data.json"
AVATAR_DIR = _DATA_DIR / "avatars"

if GitBackup.enabled():
    # Runs once per fresh container: hydrate the (otherwise empty) local
    # disk from the GitHub-backed copy before any code reads DEFAULT_PATH.
    if not DEFAULT_PATH.exists():
        GitBackup.pull_file(DEFAULT_PATH, GitBackup.DATA_REPO_PATH)
    if not AVATAR_DIR.exists():
        GitBackup.pull_directory(AVATAR_DIR, GitBackup.AVATAR_REPO_DIR)
SCHEMA_VERSION = 6
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
AVATAR_SIZE = 512
MAX_NAME_LENGTH = 80
MAX_LOCATION_LENGTH = 200
MAX_PARTICIPANTS = 20
MAX_CARDS = 13
MAX_ROUNDS = MAX_CARDS * 2
ALLOWED_AVATARS = {"image/jpeg": ("JPEG", ".jpg"), "image/png": ("PNG", ".png"), "image/webp": ("WEBP", ".webp")}

_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_CACHE: Dict[str, tuple[int, int, str, Dict]] = {}


class DataCorruptionError(RuntimeError):
    """The persisted league cannot be read or validated safely."""


class ConflictError(ValueError):
    """An idempotency key was reused for a different operation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise DataCorruptionError("Et tidspunkt mangler")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataCorruptionError(f"Ugyldigt tidspunkt: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _clean_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Spillernavnet skal være tekst")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Spillernavnet må ikke være tomt")
    if len(name) > MAX_NAME_LENGTH or any(ord(char) < 32 for char in name):
        raise ValueError(f"Spillernavnet må højst være {MAX_NAME_LENGTH} tegn")
    return name


def _clean_location(location: Optional[str]) -> Optional[str]:
    if location is None:
        return None
    if not isinstance(location, str):
        raise ValueError("Lokationen skal være tekst")
    location = " ".join(location.split())
    if len(location) > MAX_LOCATION_LENGTH:
        raise ValueError(f"Lokationen må højst være {MAX_LOCATION_LENGTH} tegn")
    return location or None


def _new_player(name: str) -> Dict:
    return {"id": uuid.uuid4().hex, "name": _clean_name(name), "avatar": None, "joined_at": _now()}


def _process_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _data_lock(path: Path):
    """Serialize readers and writers across threads and local processes."""
    path = Path(path)
    lock = _process_lock(path)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> Dict:
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise DataCorruptionError("Ligafilen skal indeholde et JSON-objekt")
    return value


def _migrate_rounds(rounds: object, players_by_name: Dict[str, Dict], player_ids: set[str]) -> List[Dict]:
    if not isinstance(rounds, list):
        return []
    migrated = []
    for old_round in rounds:
        if not isinstance(old_round, dict):
            continue
        row = {"cards": old_round.get("cards")}
        for key, score in old_round.items():
            if key == "cards":
                continue
            player_id = key if key in player_ids else players_by_name.get(str(key).casefold(), {}).get("id")
            if player_id:
                row[player_id] = score
        migrated.append(row)
    return migrated


def _migrate(raw: Dict) -> Dict:
    players = raw.get("players", DEFAULT_PLAYERS.copy())
    if not isinstance(players, list) or not players:
        players = DEFAULT_PLAYERS.copy()
    if players and isinstance(players[0], str):
        players = [_new_player(name) for name in players]
    else:
        migrated_players = []
        for old in players:
            if not isinstance(old, dict):
                continue
            migrated_players.append({
                "id": str(old.get("id") or uuid.uuid4().hex),
                "name": old.get("name", "Ukendt spiller"),
                "avatar": old.get("avatar"),
                "joined_at": _canonical_timestamp(old.get("joined_at") or _now()),
            })
        players = migrated_players or [_new_player(name) for name in DEFAULT_PLAYERS]

    by_name = {str(player["name"]).casefold(): player for player in players}
    player_ids = {player["id"] for player in players}
    migrated_games = []
    games = raw.get("games", []) if isinstance(raw.get("games", []), list) else []
    for old_game in games:
        if not isinstance(old_game, dict):
            continue
        if "results" not in old_game:
            scores = old_game.get("scores", {}) if isinstance(old_game.get("scores", {}), dict) else {}
            for name in scores:
                if str(name).casefold() not in by_name:
                    player = _new_player(str(name))
                    players.append(player)
                    by_name[player["name"].casefold()] = player
                    player_ids.add(player["id"])
            results = [{"player_id": by_name[str(name).casefold()]["id"], "score": score} for name, score in scores.items()]
        else:
            results = old_game.get("results", [])
        migrated_results = []
        for old_result in results:
            if not isinstance(old_result, dict):
                continue
            result = dict(old_result)
            legacy_values = {
                "before": result.pop("elo_before", None),
                "change": result.pop("elo_change", None),
                "after": result.pop("elo_after", None),
            }
            if "legacy_elo" not in result and any(value is not None for value in legacy_values.values()):
                result["legacy_elo"] = legacy_values
            for field in ("mu_before", "sigma_before", "mu_after", "sigma_after"):
                result.pop(field, None)
            migrated_results.append(result)
        migrated = dict(old_game)
        for field in ("rating_processed", "rating_algorithm", "rating_version"):
            migrated.pop(field, None)
        legacy_game = migrated.get("legacy_elo")
        old_processed = migrated.pop("elo_processed", None)
        old_version = migrated.pop("elo_version", None)
        if legacy_game is None and (old_processed is not None or old_version is not None):
            migrated["legacy_elo"] = {"processed": old_processed, "version": old_version}
        migrated.update({
            "id": str(old_game.get("id") or uuid.uuid4().hex),
            "completed_at": _canonical_timestamp(old_game.get("completed_at") or _now()),
            "location": old_game.get("location"),
            "status": "completed",
            "results": migrated_results,
            "rounds": _migrate_rounds(old_game.get("rounds", []), by_name, player_ids),
            "neutral_score": old_game.get("neutral_score", 7),
        })
        migrated_games.append(migrated)

    settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
    settings = {**settings, "neutral_score": settings.get("neutral_score", 7)}
    return {"schema_version": SCHEMA_VERSION, "players": players, "games": migrated_games, "settings": settings}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _parse_date(value: object) -> None:
    _canonical_timestamp(value)


def _validate_data(data: Dict, require_league_score: bool = True) -> None:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise DataCorruptionError("Ukendt skemaversion")
    players = data.get("players")
    games = data.get("games")
    settings = data.get("settings")
    if not isinstance(players, list) or not isinstance(games, list) or not isinstance(settings, dict):
        raise DataCorruptionError("Ligaens grundstruktur er ugyldig")
    neutral = settings.get("neutral_score")
    if not _is_int(neutral) or not 0 <= neutral <= 10:
        raise DataCorruptionError("Neutralværdien er ugyldig")

    ids, names = set(), set()
    for player in players:
        if not isinstance(player, dict):
            raise DataCorruptionError("En spillerpost er ugyldig")
        if not {"id", "name", "avatar", "joined_at"}.issubset(player):
            raise DataCorruptionError("En spillerpost mangler obligatoriske felter")
        player_id = player.get("id")
        if not isinstance(player_id, str) or not player_id or len(player_id) > 128 or player_id in ids:
            raise DataCorruptionError("Spiller-ID'er skal være unikke")
        try:
            clean_name = _clean_name(player.get("name"))
        except ValueError as error:
            raise DataCorruptionError(str(error)) from error
        if clean_name.casefold() in names:
            raise DataCorruptionError("Spillernavne skal være unikke")
        _parse_date(player.get("joined_at"))
        avatar = player.get("avatar")
        if avatar is not None:
            if not isinstance(avatar, str):
                raise DataCorruptionError("Avatarstien er ugyldig")
            avatar_path = Path(avatar)
            if avatar_path.is_absolute() or avatar_path.parent != Path("avatars") or not avatar_path.name:
                raise DataCorruptionError("Avatarstien er ugyldig")
        ids.add(player_id)
        names.add(clean_name.casefold())

    game_ids = set()
    for game in games:
        if not isinstance(game, dict) or not isinstance(game.get("id"), str) or not game["id"] or game["id"] in game_ids:
            raise DataCorruptionError("Spil-ID'er skal være unikke")
        if not {"completed_at", "location", "status", "results", "rounds", "neutral_score"}.issubset(game):
            raise DataCorruptionError("Et spil mangler obligatoriske felter")
        game_ids.add(game["id"])
        _parse_date(game.get("completed_at"))
        if game.get("status") != "completed":
            raise DataCorruptionError("Kun gennemførte spil må ligge i historikken")
        if game.get("source") not in (None, "simulation"):
            raise DataCorruptionError("Et spil har en ukendt kilde")
        try:
            _clean_location(game.get("location"))
        except ValueError as error:
            raise DataCorruptionError(str(error)) from error
        game_neutral = game.get("neutral_score", 7)
        if not _is_int(game_neutral) or not 0 <= game_neutral <= 10:
            raise DataCorruptionError("Et spil har en ugyldig neutralværdi")
        results = game.get("results")
        if not isinstance(results, list) or not 2 <= len(results) <= MAX_PARTICIPANTS:
            raise DataCorruptionError("Et gennemført spil kræver mindst to resultater")
        participant_ids = []
        scores = {}
        for result in results:
            player_id = result.get("player_id") if isinstance(result, dict) else None
            if not isinstance(result, dict) or not {"player_id", "score"}.issubset(result):
                raise DataCorruptionError("Et resultat mangler obligatoriske felter")
            if not isinstance(player_id, str) or player_id not in ids or player_id in participant_ids:
                raise DataCorruptionError("Et spil har ukendte eller gentagne spillere")
            if not _is_int(result.get("score")):
                raise DataCorruptionError("Scores skal være heltal")
            participant_ids.append(player_id)
            scores[player_id] = result["score"]
            if require_league_score:
                if not _is_int(result.get("placement")) or result["placement"] < 1:
                    raise DataCorruptionError("Resultatet mangler en gyldig placement")
                if not _is_int(result.get("eligible_game_number")) or result["eligible_game_number"] < 0:
                    raise DataCorruptionError("Resultatet mangler et gyldigt eligible_game_number")
                for field in ("league_score_before", "league_score_after"):
                    if not _is_number(result.get(field)):
                        raise DataCorruptionError(f"Resultatet mangler gyldig {field}")
                eligible = result.get("league_score_eligible")
                performance = result.get("performance_score")
                if not isinstance(eligible, bool):
                    raise DataCorruptionError("Resultatet mangler liga-score-status")
                if eligible and not _is_number(performance):
                    raise DataCorruptionError("Resultatet mangler en gyldig præstationsscore")
                if not eligible and performance is not None:
                    raise DataCorruptionError("Et ikke-kvalificeret spil må ikke give præstationsscore")
        rounds = game.get("rounds", [])
        if not isinstance(rounds, list):
            raise DataCorruptionError("Runder skal være en liste")
        if len(rounds) > MAX_ROUNDS:
            raise DataCorruptionError("Et spil har for mange runder")
        if rounds:
            totals = {player_id: 0 for player_id in participant_ids}
            cards_sequence = []
            for round_ in rounds:
                if not isinstance(round_, dict) or not _is_int(round_.get("cards")) or not 1 <= round_["cards"] <= MAX_CARDS:
                    raise DataCorruptionError("En runde har ugyldigt kortantal")
                cards_sequence.append(round_["cards"])
                round_players = {key for key in round_ if key != "cards"}
                if round_players != set(participant_ids):
                    raise DataCorruptionError("En gemt runde skal have præcis én score pr. deltager")
                valid = set(valid_scores_for_round(round_["cards"], game_neutral))
                for player_id in participant_ids:
                    score = round_[player_id]
                    if not _is_int(score) or score not in valid:
                        raise DataCorruptionError("En rundescore er ugyldig")
                    totals[player_id] += score
            if cards_sequence != generate_round_sequence(max(cards_sequence)):
                raise DataCorruptionError("Rundehistorikken er ikke et komplet spilforløb")
            if totals != scores:
                raise DataCorruptionError("Slutresultatet stemmer ikke med rundehistorikken")
        if require_league_score and (
            game.get("league_score_processed") is not True
            or game.get("league_score_algorithm") != ALGORITHM_NAME
            or game.get("league_score_version") != ALGORITHM_VERSION
        ):
            raise DataCorruptionError("Liga-score-historikken har en forkert algoritmeversion")

    if require_league_score:
        expected = deepcopy(data)
        _rebuild_league_scores(expected)
        derived_fields = (
            "placement", "league_score_eligible", "league_score_before",
            "performance_score", "league_score_after", "eligible_game_number",
        )
        for game, expected_game in zip(games, expected["games"]):
            for field in ("league_score_processed", "league_score_algorithm", "league_score_version"):
                if game.get(field) != expected_game.get(field):
                    raise DataCorruptionError("Liga-score-historikken er inkonsistent")
            for result, expected_result in zip(game["results"], expected_game["results"]):
                if any(result.get(field) != expected_result.get(field) for field in derived_fields):
                    raise DataCorruptionError("Et afledt liga-score-resultat er inkonsistent")


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".backup")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path) -> Tuple[int, int, str]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size, _file_digest(path)


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (2 ** attempt))


def _atomic_verified_copy(source: Path, destination: Path) -> None:
    """Rotate a recoverable backup without ever exposing a partial destination."""
    before = source.stat()
    temporary = destination.with_suffix(destination.suffix + f".tmp.{uuid.uuid4().hex}")
    try:
        with source.open("rb") as input_file, temporary.open("wb") as output_file:
            shutil.copyfileobj(input_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
        after = source.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise DataCorruptionError("Ligafilen ændrede sig under backup")
        if temporary.stat().st_size != after.st_size or _file_digest(temporary) != _file_digest(source):
            raise DataCorruptionError("Backupkopien kunne ikke verificeres")
        try:
            _prepare_data(_read_json(temporary))
        except (json.JSONDecodeError, UnicodeDecodeError, DataCorruptionError) as error:
            raise DataCorruptionError("Den eksisterende ligafil kan ikke sikkerhedskopieres") from error
        _replace_with_retry(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _save_unlocked(data: Dict, path: Path, create_backup: bool = True) -> None:
    _validate_data(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        if create_backup and path.exists() and path.stat().st_size:
            _atomic_verified_copy(path, _backup_path(path))
        _replace_with_retry(temporary, path)
        fingerprint = _fingerprint(path)
        _CACHE[str(path.resolve())] = (*fingerprint, deepcopy(data))
        if GitBackup.enabled() and path.resolve() == DEFAULT_PATH.resolve():
            GitBackup.push_file(path, GitBackup.DATA_REPO_PATH, "Opdater liga-data")
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_explicit_legacy_structure(raw: Dict) -> None:
    """Reject malformed versioned legacy data instead of silently dropping records."""
    if not isinstance(raw.get("players"), list) or not raw["players"]:
        raise DataCorruptionError("Den gamle spillerliste er ugyldig")
    if any(not isinstance(player, (str, dict)) for player in raw["players"]):
        raise DataCorruptionError("En gammel spillerpost er ugyldig")
    if not isinstance(raw.get("games"), list) or not isinstance(raw.get("settings"), dict):
        raise DataCorruptionError("Den gamle ligastruktur er ugyldig")
    for game in raw["games"]:
        if not isinstance(game, dict):
            raise DataCorruptionError("En gammel spilpost er ugyldig")
        if "results" in game:
            if not isinstance(game["results"], list) or any(
                not isinstance(result, dict) for result in game["results"]
            ):
                raise DataCorruptionError("Et gammelt resultat er ugyldigt")
        elif not isinstance(game.get("scores"), dict):
            raise DataCorruptionError("Et gammelt spil mangler resultater")
        if "rounds" in game and (
            not isinstance(game["rounds"], list)
            or any(not isinstance(round_, dict) for round_ in game["rounds"])
        ):
            raise DataCorruptionError("En gammel rundehistorik er ugyldig")


def _prepare_data(raw: Dict) -> Dict:
    if not isinstance(raw, dict):
        raise DataCorruptionError("Ligafilen skal indeholde et JSON-objekt")
    version = raw.get("schema_version")
    if version == SCHEMA_VERSION:
        data = deepcopy(raw)
        _validate_data(data, require_league_score=False)
    else:
        if version is not None and (
            not _is_int(version) or version < 0 or version > SCHEMA_VERSION
        ):
            raise DataCorruptionError("Ukendt skemaversion")
        if version is not None:
            _validate_explicit_legacy_structure(raw)
        try:
            data = _migrate(raw)
        except (TypeError, ValueError, KeyError) as error:
            raise DataCorruptionError("Ligaens data kan ikke migreres sikkert") from error
        _validate_data(data, require_league_score=False)
    _rebuild_league_scores(data)
    _validate_data(data)
    return data


def _load_unlocked(path: Path) -> Dict:
    recovered = False
    primary_error = None
    backup = _backup_path(path)
    cache_key = str(path.resolve())
    if path.exists() and path.stat().st_size:
        fingerprint = _fingerprint(path)
        cached = _CACHE.get(cache_key)
        if cached and cached[:3] == fingerprint:
            return deepcopy(cached[3])
        try:
            raw = _read_json(path)
            data = _prepare_data(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, DataCorruptionError) as error:
            primary_error = error
    elif path.exists():
        _CACHE.pop(cache_key, None)
        primary_error = DataCorruptionError("Ligafilen er tom")
    elif backup.exists():
        _CACHE.pop(cache_key, None)
        primary_error = DataCorruptionError("Ligafilen mangler")
    else:
        raw = {"players": DEFAULT_PLAYERS.copy(), "games": [], "settings": {"neutral_score": 7}}
        data = _prepare_data(raw)

    if primary_error is not None:
        if not backup.exists():
            raise DataCorruptionError("Ligafilen er beskadiget, og der findes ingen gyldig backup") from primary_error
        try:
            raw = _read_json(backup)
            data = _prepare_data(raw)
            recovered = True
        except (json.JSONDecodeError, UnicodeDecodeError, DataCorruptionError) as backup_error:
            raise DataCorruptionError("Både ligafilen og dens backup er beskadiget") from backup_error
    changed = recovered or data != raw
    if not path.exists():
        _save_unlocked(data, path, create_backup=False)
    elif changed:
        if raw.get("schema_version") != SCHEMA_VERSION:
            migration_backup = path.with_suffix(path.suffix + f".pre-v{SCHEMA_VERSION}.backup")
            if not migration_backup.exists() and not recovered:
                _atomic_verified_copy(path, migration_backup)
        _save_unlocked(data, path, create_backup=not recovered)
    else:
        fingerprint = _fingerprint(path)
        _CACHE[cache_key] = (*fingerprint, deepcopy(data))
    return data


def load_data(path: Path = DEFAULT_PATH) -> Dict:
    path = Path(path)
    with _data_lock(path):
        return deepcopy(_load_unlocked(path))


def save_data(data: Dict, path: Path = DEFAULT_PATH) -> None:
    path = Path(path)
    with _data_lock(path):
        _save_unlocked(deepcopy(data), path)


def add_player(name: str, path: Path = DEFAULT_PATH) -> Dict:
    name = _clean_name(name)
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        if any(player["name"].casefold() == name.casefold() for player in data["players"]):
            raise ValueError("Spilleren findes allerede")
        player = _new_player(name)
        data["players"].append(player)
        _save_unlocked(data, path)
        return deepcopy(player)


def update_player(player_id: str, name: str, path: Path = DEFAULT_PATH) -> Dict:
    name = _clean_name(name)
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        if any(p["id"] != player_id and p["name"].casefold() == name.casefold() for p in data["players"]):
            raise ValueError("Spilleren findes allerede")
        player = next((p for p in data["players"] if p["id"] == player_id), None)
        if player is None:
            raise ValueError("Ukendt spiller")
        player["name"] = name
        _save_unlocked(data, path)
        return deepcopy(player)


def update_settings(neutral_score: int, path: Path = DEFAULT_PATH) -> Dict:
    if not _is_int(neutral_score) or not 0 <= neutral_score <= 10:
        raise ValueError("Neutralværdien skal være mellem 0 og 10")
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        data["settings"]["neutral_score"] = neutral_score
        _save_unlocked(data, path)
        return deepcopy(data["settings"])


def _safe_avatar_path(relative_path: str) -> Optional[Path]:
    relative = Path(relative_path)
    if relative.is_absolute() or relative.parent != Path("avatars") or not relative.name:
        return None
    candidate = (AVATAR_DIR / relative.name).resolve()
    root = AVATAR_DIR.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _normalize_avatar(content: bytes, mime_type: str) -> bytes:
    if mime_type not in ALLOWED_AVATARS:
        raise ValueError("Brug JPG, PNG eller WebP")
    if not content or len(content) > MAX_AVATAR_BYTES:
        raise ValueError("Billedet må højst fylde 2 MB")
    expected_format, _ = ALLOWED_AVATARS[mime_type]
    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_AVATAR_PIXELS
    try:
        with Image.open(io.BytesIO(content)) as probe:
            if probe.format != expected_format or probe.width * probe.height > MAX_AVATAR_PIXELS:
                raise ValueError("Billedets format eller dimensioner er ugyldige")
            probe.verify()
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            if expected_format == "JPEG":
                image = image.convert("RGB")
            elif image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            output = io.BytesIO()
            options = {"quality": 88, "optimize": True} if expected_format in ("JPEG", "WEBP") else {"optimize": True}
            image.save(output, format=expected_format, **options)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Filen er ikke et gyldigt billede") from error
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit


def normalize_avatar_upload(content: bytes, mime_type: str) -> bytes:
    """Validate and resize an upload for safe preview or persistence."""
    return _normalize_avatar(content, mime_type)


def save_avatar(player_id: str, content: bytes, mime_type: str, path: Path = DEFAULT_PATH) -> str:
    normalized = _normalize_avatar(content, mime_type)
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        player = next((p for p in data["players"] if p["id"] == player_id), None)
        if player is None:
            raise ValueError("Ukendt spiller")
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        _, extension = ALLOWED_AVATARS[mime_type]
        filename = f"{uuid.uuid4().hex}{extension}"
        final_path = AVATAR_DIR / filename
        temporary = AVATAR_DIR / f".{filename}.tmp"
        old_path = _safe_avatar_path(player["avatar"]) if player.get("avatar") else None
        try:
            with temporary.open("wb") as file:
                file.write(normalized)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, final_path)
            player["avatar"] = str(Path("avatars") / filename)
            _save_unlocked(data, path)
            if GitBackup.enabled():
                GitBackup.push_file(
                    final_path, f"{GitBackup.AVATAR_REPO_DIR}/{filename}", f"Tilføj avatar {filename}",
                )
        except Exception:
            if final_path.exists():
                final_path.unlink()
            raise
        finally:
            if temporary.exists():
                temporary.unlink()
        if old_path and old_path.exists() and old_path != final_path:
            try:
                old_path.unlink()
            except OSError:
                pass  # The new reference is committed; an orphan is safer than a failed retry.
        return player["avatar"]


def remove_avatar(player_id: str, path: Path = DEFAULT_PATH) -> None:
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        player = next((p for p in data["players"] if p["id"] == player_id), None)
        if player is None:
            raise ValueError("Ukendt spiller")
        avatar_path = _safe_avatar_path(player["avatar"]) if player.get("avatar") else None
        player["avatar"] = None
        _save_unlocked(data, path)
        if avatar_path and avatar_path.exists():
            try:
                avatar_path.unlink()
            except OSError:
                pass
            if GitBackup.enabled():
                GitBackup.delete_file(
                    f"{GitBackup.AVATAR_REPO_DIR}/{avatar_path.name}", f"Fjern avatar {avatar_path.name}",
                )


def _apply_league_score(game: Dict, totals: Dict[str, float], counts: Dict[str, int]) -> None:
    scores = {result["player_id"]: result["score"] for result in game["results"]}
    placements = placements_from_scores(scores)
    eligible = is_eligible_player_count(len(scores))
    rounds = game.get("rounds", [])
    for result in game["results"]:
        player_id = result["player_id"]
        before = totals.get(player_id, 0.0) / counts.get(player_id, 1) if counts.get(player_id) else 0.0
        performance = None
        if eligible:
            fridge = is_koleskabsgame(player_id, placements[player_id], scores[player_id], rounds)
            performance = performance_score(placements[player_id], len(scores), fridge)
            totals[player_id] = totals.get(player_id, 0.0) + performance
            counts[player_id] = counts.get(player_id, 0) + 1
        after = totals.get(player_id, 0.0) / counts.get(player_id, 1) if counts.get(player_id) else 0.0
        for field in ("mu_before", "sigma_before", "mu_after", "sigma_after"):
            result.pop(field, None)
        result.update({
            "placement": placements[player_id],
            "league_score_eligible": eligible,
            "league_score_before": round(before, 12),
            "performance_score": round(performance, 12) if performance is not None else None,
            "league_score_after": round(after, 12),
            "eligible_game_number": counts.get(player_id, 0),
        })
    for field in ("rating_processed", "rating_algorithm", "rating_version"):
        game.pop(field, None)
    game["league_score_processed"] = True
    game["league_score_algorithm"] = ALGORITHM_NAME
    game["league_score_version"] = ALGORITHM_VERSION


def _rebuild_league_scores(data: Dict) -> None:
    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for game in sorted(data["games"], key=lambda item: (item["completed_at"], item["id"])):
        _apply_league_score(game, totals, counts)


def _resolve_scores(data: Dict, scores: Dict[str, int]) -> Dict[str, int]:
    if not isinstance(scores, dict) or not 2 <= len(scores) <= MAX_PARTICIPANTS:
        raise ValueError("Et spil kræver mindst to spillere")
    by_id = {p["id"]: p for p in data["players"]}
    by_name = {p["name"].casefold(): p for p in data["players"]}
    resolved = {}
    for key, score in scores.items():
        if not isinstance(key, str):
            raise ValueError("Spiller-ID'et er ugyldigt")
        player = by_id.get(key) or by_name.get(key.casefold())
        if player is None:
            raise ValueError(f"Ukendt spiller: {key}")
        if player["id"] in resolved:
            raise ValueError("Den samme spiller må kun optræde én gang")
        if not _is_int(score):
            raise ValueError("Scores skal være heltal")
        resolved[player["id"]] = score
    if len(resolved) < 2:
        raise ValueError("Et spil kræver mindst to forskellige spillere")
    return resolved


def _normalized_rounds(rounds: Optional[List]) -> List[Dict]:
    return deepcopy(rounds) if rounds is not None else []


def _same_submission(game: Dict, scores: Dict[str, int], rounds: List[Dict], location: Optional[str],
                     neutral_score: int, source: Optional[str]) -> bool:
    existing_scores = {result["player_id"]: result["score"] for result in game["results"]}
    return (
        existing_scores == scores and game.get("rounds", []) == rounds and
        game.get("location") == location and game.get("neutral_score", 7) == neutral_score and
        game.get("source") == source
    )


def record_game(
    scores: Dict[str, int], path: Path = DEFAULT_PATH, game_id: Optional[str] = None,
    rounds: Optional[List] = None, location: Optional[str] = None, neutral_score: int = 7,
    source: Optional[str] = None, *, return_created: bool = False,
) -> Union[Dict, Tuple[Dict, bool]]:
    if not isinstance(return_created, bool):
        raise ValueError("return_created skal være boolsk")
    if not _is_int(neutral_score) or not 0 <= neutral_score <= 10:
        raise ValueError("Neutralværdien skal være mellem 0 og 10")
    if source not in (None, "simulation"):
        raise ValueError("Spilkilden er ugyldig")
    location = _clean_location(location)
    path = Path(path)
    game_id = game_id or uuid.uuid4().hex
    if not isinstance(game_id, str) or not game_id or len(game_id) > 128:
        raise ValueError("Spil-ID'et er ugyldigt")
    with _data_lock(path):
        data = _load_unlocked(path)
        resolved = _resolve_scores(data, scores)
        if not is_eligible_player_count(len(resolved)):
            raise ValueError(
                f"Et konkurrencespil kræver mellem {MIN_COMPETITION_PLAYERS} og {MAX_COMPETITION_PLAYERS} spillere"
            )
        normalized_rounds = _normalized_rounds(rounds)
        existing = next((game for game in data["games"] if game["id"] == game_id), None)
        if existing:
            if _same_submission(existing, resolved, normalized_rounds, location, neutral_score, source):
                saved = deepcopy(existing)
                return (saved, False) if return_created else saved
            raise ConflictError("Spil-ID'et er allerede brugt til et andet resultat")
        game = {
            "id": game_id, "completed_at": _now(), "location": location,
            "status": "completed", "league_score_processed": False,
            "results": [{"player_id": pid, "score": score} for pid, score in resolved.items()],
            "rounds": normalized_rounds, "neutral_score": neutral_score,
        }
        if source:
            game["source"] = source
        data["games"].append(game)
        _rebuild_league_scores(data)
        _validate_data(data)
        _save_unlocked(data, path)
        saved = deepcopy(next(item for item in data["games"] if item["id"] == game_id))
        return (saved, True) if return_created else saved


def update_game(
    game_id: str, scores: Dict[str, int], path: Path = DEFAULT_PATH,
    rounds: Optional[List] = None, location: Optional[str] = None,
    neutral_score: Optional[int] = None, completed_at: Optional[str] = None,
) -> Dict:
    """Replace a completed game and deterministically rebuild league-score history."""
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        game = next((item for item in data["games"] if item["id"] == game_id), None)
        if game is None:
            raise ValueError("Spillet findes ikke")
        resolved = _resolve_scores(data, scores)
        previous_count = len(game["results"])
        if is_eligible_player_count(previous_count) and not is_eligible_player_count(len(resolved)):
            raise ValueError(
                f"Et kvalificeret konkurrencespil skal fortsat have mellem "
                f"{MIN_COMPETITION_PLAYERS} og {MAX_COMPETITION_PLAYERS} spillere"
            )
        if len(resolved) > MAX_COMPETITION_PLAYERS:
            raise ValueError(f"Et konkurrencespil kan højst have {MAX_COMPETITION_PLAYERS} spillere")
        game_neutral = game.get("neutral_score", 7) if neutral_score is None else neutral_score
        if not _is_int(game_neutral) or not 0 <= game_neutral <= 10:
            raise ValueError("Neutralværdien skal være mellem 0 og 10")
        game["results"] = [{"player_id": pid, "score": score} for pid, score in resolved.items()]
        game["rounds"] = _normalized_rounds(rounds)
        game["location"] = _clean_location(location)
        game["neutral_score"] = game_neutral
        if completed_at is not None:
            game["completed_at"] = _canonical_timestamp(completed_at)
        _rebuild_league_scores(data)
        _validate_data(data)
        _save_unlocked(data, path)
        return deepcopy(game)


def get_player(player_id: str, path: Path = DEFAULT_PATH) -> Optional[Dict]:
    return next((p for p in load_data(path)["players"] if p["id"] == player_id), None)


def get_game(game_id: str, path: Path = DEFAULT_PATH) -> Optional[Dict]:
    return next((g for g in load_data(path)["games"] if g["id"] == game_id), None)


def delete_game(game_id: str, path: Path = DEFAULT_PATH, required_source: Optional[str] = None) -> None:
    path = Path(path)
    with _data_lock(path):
        data = _load_unlocked(path)
        target = next((game for game in data["games"] if game["id"] == game_id), None)
        if target is None:
            raise ValueError("Spillet findes ikke")
        if required_source is not None and target.get("source") != required_source:
            raise ValueError("Spillet har ikke den krævede kilde")
        games = [game for game in data["games"] if game["id"] != game_id]
        data["games"] = games
        _rebuild_league_scores(data)
        _validate_data(data)
        _save_unlocked(data, path)