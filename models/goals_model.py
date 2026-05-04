"""Goal expectation model with xG fallback/proxy and mean reversion."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, Optional


def _parse_date(value: str) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _pull_xg(match: Dict[str, Any], team_side: str) -> Optional[float]:
    """
    Extract xG from several possible payload structures.
    Supports fields often used by Understat-like APIs.
    """
    score = match.get("score", {})
    stats = match.get("statistics", {})
    candidates = []
    if team_side == "home":
        candidates = [
            score.get("xg", {}).get("home"),
            score.get("xg_home"),
            match.get("xg_home"),
            match.get("home_xg"),
            stats.get("home", {}).get("xg"),
            stats.get("xg_home"),
            match.get("expectedGoals", {}).get("home"),
        ]
    else:
        candidates = [
            score.get("xg", {}).get("away"),
            score.get("xg_away"),
            match.get("xg_away"),
            match.get("away_xg"),
            stats.get("away", {}).get("xg"),
            stats.get("xg_away"),
            match.get("expectedGoals", {}).get("away"),
        ]
    for val in candidates:
        num = _as_float(val)
        if num is not None and num >= 0:
            return num
    return None


def _pull_shots_proxy(match: Dict[str, Any], team_side: str) -> Optional[float]:
    stats = match.get("statistics", {})
    side_stats = stats.get(team_side, {})
    shots = _as_float(side_stats.get("shots")) or _as_float(side_stats.get("totalShots"))
    shots_ot = _as_float(side_stats.get("shotsOnTarget")) or _as_float(side_stats.get("onTarget"))
    if shots is None and shots_ot is None:
        return None
    shots = 0.0 if shots is None else shots
    shots_ot = 0.0 if shots_ot is None else shots_ot
    # Empirical low-bias conversion to expected goals proxy.
    return 0.10 * shots + 0.32 * shots_ot


def _expected_for_team(
    match: Dict[str, Any],
    is_home_team: bool,
    goals_for: float,
    league_half_goal: float,
) -> float:
    side = "home" if is_home_team else "away"
    xg = _pull_xg(match, side)
    if xg is not None:
        return xg

    proxy = _pull_shots_proxy(match, side)
    if proxy is not None:
        blended = 0.70 * proxy + 0.30 * goals_for
    else:
        blended = goals_for

    # Mean reversion against league baseline controls noisy short samples.
    return 0.65 * blended + 0.35 * league_half_goal


def build_team_goal_profile(
    matches: Iterable[Dict[str, Any]],
    team_id: int,
    league_avg_goals: float,
    opponent_ratings: Dict[int, float],
    league_rating_avg: float,
    decay_lambda: float = 0.22,
) -> Dict[str, float]:
    """
    Build venue-aware attack/defense profile for one team.
    Returns rates in expected goals scale.
    """
    league_half = league_avg_goals / 2.0
    finished = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        if score.get("home") is None or score.get("away") is None:
            continue
        finished.append(m)
    if not finished:
        return {
            "for_home": league_half,
            "against_home": league_half,
            "for_away": league_half,
            "against_away": league_half,
            "sos_factor": 1.0,
        }

    finished = sorted(finished, key=lambda x: _parse_date(x.get("utcDate", "")), reverse=True)[:18]

    agg = {
        "for_home": 0.0,
        "against_home": 0.0,
        "w_home": 0.0,
        "for_away": 0.0,
        "against_away": 0.0,
        "w_away": 0.0,
    }
    sos_weighted = 0.0
    sos_w = 0.0

    for idx, m in enumerate(finished):
        w = math.exp(-decay_lambda * idx)
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})
        score = m.get("score", {}).get("fullTime", {})
        hg = float(score.get("home", 0.0))
        ag = float(score.get("away", 0.0))

        is_home = home.get("id") == team_id
        goals_for = hg if is_home else ag
        goals_against = ag if is_home else hg
        exp_for = _expected_for_team(m, is_home, goals_for, league_half)

        if is_home:
            agg["for_home"] += exp_for * w
            agg["against_home"] += goals_against * w
            agg["w_home"] += w
            opp_id = away.get("id")
        else:
            agg["for_away"] += exp_for * w
            agg["against_away"] += goals_against * w
            agg["w_away"] += w
            opp_id = home.get("id")

        opp_rating = opponent_ratings.get(opp_id, league_rating_avg)
        sos_weighted += (opp_rating / league_rating_avg) * w
        sos_w += w

    for_side = lambda num, den: (num / den) if den > 0 else league_half
    sos_factor = (sos_weighted / sos_w) if sos_w > 0 else 1.0
    sos_factor = float(min(1.15, max(0.87, sos_factor)))

    return {
        "for_home": for_side(agg["for_home"], agg["w_home"]),
        "against_home": for_side(agg["against_home"], agg["w_home"]),
        "for_away": for_side(agg["for_away"], agg["w_away"]),
        "against_away": for_side(agg["against_away"], agg["w_away"]),
        "sos_factor": sos_factor,
    }


def project_match_xg(
    home_profile: Dict[str, float],
    away_profile: Dict[str, float],
    league_avg_goals: float,
    strength_home_mult: float,
    strength_away_mult: float,
) -> Dict[str, float]:
    """Project xG for both teams from venue splits and strength multipliers."""
    norm = league_avg_goals / 2.0
    raw_h = (home_profile["for_home"] * away_profile["against_away"]) / max(0.25, norm)
    raw_a = (away_profile["for_away"] * home_profile["against_home"]) / max(0.25, norm)

    xg_h = raw_h * 1.10 * home_profile["sos_factor"] * strength_home_mult
    xg_a = raw_a * 0.92 * away_profile["sos_factor"] * strength_away_mult

    return {
        "xg_h": float(min(4.2, max(0.25, xg_h))),
        "xg_a": float(min(4.2, max(0.20, xg_a))),
    }
