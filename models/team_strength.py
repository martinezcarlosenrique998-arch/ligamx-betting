"""Team strength utilities (dynamic ELO) for soccer modeling."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, Tuple


def _parse_date(value: str) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _iter_finished_matches(matches: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for match in matches:
        score = match.get("score", {}).get("fullTime", {})
        home_goals = score.get("home")
        away_goals = score.get("away")
        if home_goals is None or away_goals is None:
            continue
        yield match


def build_dynamic_elo_ratings(
    matches: Iterable[Dict[str, Any]],
    base_rating: float = 1500.0,
    k_factor: float = 24.0,
    home_advantage_elo: float = 55.0,
) -> Tuple[Dict[int, float], float]:
    """
    Build dynamic team ratings from completed matches.

    Returns:
        - ratings by team id
        - dynamic league average rating
    """
    deduped: Dict[Any, Dict[str, Any]] = {}
    for m in _iter_finished_matches(matches):
        deduped[m.get("id", id(m))] = m

    ordered = sorted(deduped.values(), key=lambda x: _parse_date(x.get("utcDate", "")))
    ratings: Dict[int, float] = {}

    for m in ordered:
        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")
        if home_id is None or away_id is None:
            continue

        home_rating = ratings.get(home_id, base_rating)
        away_rating = ratings.get(away_id, base_rating)

        expected_home = 1.0 / (1.0 + 10.0 ** (((away_rating + home_advantage_elo) - home_rating) / 400.0))
        expected_away = 1.0 - expected_home

        score = m.get("score", {}).get("fullTime", {})
        hg = float(score.get("home", 0.0))
        ag = float(score.get("away", 0.0))
        if hg > ag:
            actual_home = 1.0
        elif hg == ag:
            actual_home = 0.5
        else:
            actual_home = 0.0
        actual_away = 1.0 - actual_home

        # Goal-difference scaling reduces noise from marginal 1-goal games.
        goal_diff = abs(hg - ag)
        rating_gap = abs(home_rating - away_rating)
        g_mult = math.log(goal_diff + 1.0) * (2.2 / (0.001 * rating_gap + 2.2))
        g_mult = max(0.6, g_mult)

        ratings[home_id] = home_rating + (k_factor * g_mult) * (actual_home - expected_home)
        ratings[away_id] = away_rating + (k_factor * g_mult) * (actual_away - expected_away)

    if not ratings:
        return {}, base_rating
    league_avg = sum(ratings.values()) / len(ratings)
    return ratings, float(league_avg)


def matchup_strength_multipliers(
    home_team_id: int,
    away_team_id: int,
    ratings: Dict[int, float],
    league_avg: float,
    slope: float = 0.35,
) -> Tuple[float, float]:
    """Translate ELO spread into bounded xG multipliers."""
    home_r = ratings.get(home_team_id, league_avg)
    away_r = ratings.get(away_team_id, league_avg)
    diff = (home_r - away_r) / 400.0
    home_mult = math.exp(slope * diff)
    away_mult = math.exp(-slope * diff)

    home_mult = float(min(1.22, max(0.82, home_mult)))
    away_mult = float(min(1.22, max(0.82, away_mult)))
    return home_mult, away_mult
