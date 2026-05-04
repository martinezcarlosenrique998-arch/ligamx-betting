"""
Módulo ligero de auditoría de apuestas: logging, CLV y métricas (SQLite + pandas).
Uso: importar desde la app Streamlit y llamar log_bet / update_closing_odds / update_bet_result.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_BET_KEYS = (
    "date",
    "match_id",
    "league",
    "market",
    "selection",
    "model_probability",
    "implied_probability_market",
    "edge",
    "entry_odds",
    "stake",
    "result",
)


def get_db_path(db_path: Optional[Path] = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("BET_LOG_DB", str(Path(__file__).resolve().parent / "bet_clv_audit.sqlite")))


def _migrate_bet_log_columns(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(bet_log)").fetchall()}
    if "fixture_name" not in existing:
        conn.execute("ALTER TABLE bet_log ADD COLUMN fixture_name TEXT")


def init_bet_log_db(db_path: Optional[Path] = None) -> Path:
    """Crea tabla e índice único si no existen."""
    p = get_db_path(db_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(p) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bet_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    match_id TEXT NOT NULL,
                    league TEXT NOT NULL,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    fixture_name TEXT,
                    model_probability REAL NOT NULL,
                    implied_probability_market REAL NOT NULL,
                    edge REAL NOT NULL,
                    entry_odds REAL NOT NULL,
                    closing_odds REAL,
                    clv REAL,
                    stake REAL NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(match_id, market, selection)
                )
                """
            )
            _migrate_bet_log_columns(conn)
            conn.commit()
    except OSError as e:
        logger.warning("init_bet_log_db: no se pudo crear DB en %s: %s", p, e)
        raise
    return p


def _normalize_result(result: str) -> str:
    r = (result or "pending").strip().lower()
    aliases = {
        "ganada": "win",
        "perdida": "loss",
        "pendiente": "pending",
        "w": "win",
        "l": "loss",
        "p": "pending",
    }
    r = aliases.get(r, r)
    if r not in ("win", "loss", "pending"):
        raise ValueError(f"result inválido: {result!r} (use win|loss|pending)")
    return r


def log_bet(bet_data: dict, db_path: Optional[Path] = None) -> None:
    """
    Inserta una apuesta. Evita duplicados por (match_id, market, selection).
    closing_odds puede ser None; clv se deja NULL hasta update_closing_odds.
    """
    try:
        init_bet_log_db(db_path)
        p = get_db_path(db_path)
        missing = [k for k in REQUIRED_BET_KEYS if k not in bet_data]
        if missing:
            raise ValueError(f"bet_data faltan claves: {missing}")

        date = str(bet_data["date"])
        match_id = str(bet_data["match_id"])
        league = str(bet_data["league"])
        market = str(bet_data["market"])
        selection = str(bet_data["selection"])
        model_probability = float(bet_data["model_probability"])
        implied_probability_market = float(bet_data["implied_probability_market"])
        edge = float(bet_data["edge"])
        entry_odds = float(bet_data["entry_odds"])
        closing_odds = bet_data.get("closing_odds")
        closing_odds = float(closing_odds) if closing_odds is not None and closing_odds == closing_odds else None
        stake = float(bet_data["stake"])
        result = _normalize_result(str(bet_data["result"]))

        if entry_odds <= 1.0:
            raise ValueError("entry_odds debe ser > 1.0 (decimal)")
        if stake < 0:
            raise ValueError("stake no puede ser negativo")

        clv = None
        if closing_odds is not None and closing_odds > 1.0:
            clv = (closing_odds / entry_odds) - 1.0

        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        fixture_name = bet_data.get("fixture_name")
        fixture_str = None if fixture_name is None else str(fixture_name).strip()
        fixture_str = fixture_str if fixture_str else None

        with sqlite3.connect(p) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO bet_log (
                    date, match_id, league, market, selection, fixture_name,
                    model_probability, implied_probability_market, edge,
                    entry_odds, closing_odds, clv, stake, result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    match_id,
                    league,
                    market,
                    selection,
                    fixture_str,
                    model_probability,
                    implied_probability_market,
                    edge,
                    entry_odds,
                    closing_odds,
                    clv,
                    stake,
                    result,
                    created_at,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.warning("log_bet falló: %s", e, exc_info=True)


def update_closing_odds(
    match_id: str,
    market: str,
    selection: str,
    closing_odds: float,
    db_path: Optional[Path] = None,
) -> int:
    """Actualiza closing_odds y clv en la fila existente. Devuelve filas afectadas."""
    try:
        init_bet_log_db(db_path)
        p = get_db_path(db_path)
        cid = float(closing_odds)
        if cid <= 1.0:
            raise ValueError("closing_odds debe ser > 1.0")
        mid, mkt, sel = str(match_id), str(market), str(selection)
        with sqlite3.connect(p) as conn:
            cur = conn.execute(
                """
                UPDATE bet_log
                SET closing_odds = ?,
                    clv = CASE WHEN entry_odds > 1.0 THEN (? / entry_odds) - 1.0 ELSE NULL END
                WHERE match_id = ? AND market = ? AND selection = ?
                """,
                (cid, cid, mid, mkt, sel),
            )
            conn.commit()
            return int(cur.rowcount)
    except Exception as e:
        logger.warning("update_closing_odds falló: %s", e, exc_info=True)
        return 0


def update_bet_result(
    match_id: str,
    market: str,
    selection: str,
    result: str,
    db_path: Optional[Path] = None,
) -> int:
    """Actualiza resultado (win / loss / pending)."""
    try:
        init_bet_log_db(db_path)
        p = get_db_path(db_path)
        r = _normalize_result(result)
        with sqlite3.connect(p) as conn:
            cur = conn.execute(
                """
                UPDATE bet_log SET result = ?
                WHERE match_id = ? AND market = ? AND selection = ?
                """,
                (r, str(match_id), str(market), str(selection)),
            )
            conn.commit()
            return int(cur.rowcount)
    except Exception as e:
        logger.warning("update_bet_result falló: %s", e, exc_info=True)
        return 0


def load_bets_df(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Carga log completo como DataFrame (vacío si no hay tabla/archivo)."""
    p = get_db_path(db_path)
    if not p.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(p) as conn:
            return pd.read_sql_query("SELECT * FROM bet_log ORDER BY date ASC, id ASC", conn)
    except Exception as e:
        logger.warning("load_bets_df falló: %s", e, exc_info=True)
        return pd.DataFrame()


def calculate_clv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade columna CLV = (closing_odds / entry_odds) - 1.
    Filas sin closing_odds válido reciben NaN en CLV.
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    clo = pd.to_numeric(out.get("closing_odds"), errors="coerce")
    ent = pd.to_numeric(out.get("entry_odds"), errors="coerce")
    out["CLV"] = np.where(
        clo.notna() & ent.notna() & (ent > 1.0) & (clo > 1.0),
        (clo / ent) - 1.0,
        np.nan,
    )
    return out


def compute_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Métricas agregadas. ROI según:
    profit = stake * (entry_odds - 1) si win, else -stake
    roi = total_profit / total_stake
    """
    empty = {
        "total_bets": 0,
        "avg_clv": 0.0,
        "pct_positive_clv": 0.0,
        "roi": 0.0,
        "total_profit": 0.0,
        "win_rate": 0.0,
        "settled_bets": 0,
        "total_stake_settled": 0.0,
    }
    if df is None or df.empty:
        return empty

    d = calculate_clv(df) if "CLV" not in df.columns else df.copy()
    total_bets = int(len(d))

    clv_series = d["CLV"].dropna() if "CLV" in d.columns else pd.Series(dtype=float)
    avg_clv = float(clv_series.mean()) if len(clv_series) else 0.0
    pct_positive_clv = float((clv_series > 0).mean() * 100.0) if len(clv_series) else 0.0

    if "result" not in d.columns:
        return {**empty, "total_bets": total_bets, "avg_clv": avg_clv, "pct_positive_clv": pct_positive_clv}

    res = d["result"].astype(str).str.lower()
    settled_mask = res.isin(("win", "loss"))
    settled = d.loc[settled_mask].copy()
    settled_bets = int(len(settled))

    stake = pd.to_numeric(settled.get("stake"), errors="coerce").fillna(0.0)
    ent = pd.to_numeric(settled.get("entry_odds"), errors="coerce").fillna(1.0)
    wins = res.loc[settled_mask].eq("win")
    profit = np.where(wins.values, stake.values * (ent.values - 1.0), -stake.values)
    total_profit = float(np.nansum(profit))
    total_stake = float(np.nansum(stake.values))
    roi = (total_profit / total_stake) if total_stake > 0 else 0.0
    win_rate = float(wins.sum() / settled_bets) if settled_bets > 0 else 0.0

    return {
        "total_bets": total_bets,
        "avg_clv": avg_clv,
        "pct_positive_clv": pct_positive_clv,
        "roi": roi,
        "total_profit": total_profit,
        "win_rate": win_rate,
        "settled_bets": settled_bets,
        "total_stake_settled": total_stake,
    }


def _norm_tokens(name: str) -> set:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if len(t) > 1]
    return set(tokens)


def _token_overlap_similarity(a: str, b: str) -> float:
    wa, wb = _norm_tokens(a), _norm_tokens(b)
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    return inter / float(max(len(wa), len(wb)))


def split_fixture(fixture_name: str) -> tuple[str, str]:
    s = (fixture_name or "").strip()
    for sep in (" vs ", " v ", " – ", " - "):
        if sep in s:
            lh, rh = s.split(sep, 1)
            return lh.strip(), rh.strip()
    return "", ""


def fixture_match_score(fixture_name: str, api_home: str, api_away: str) -> float:
    """Score 0–1; admite orden invertido."""
    fh, fa = split_fixture(fixture_name)
    if not fh or not fa:
        return 0.0
    s_ord = (
        _token_overlap_similarity(fh, api_home) + _token_overlap_similarity(fa, api_away)
    ) / 2.0
    s_swap = (
        _token_overlap_similarity(fh, api_away) + _token_overlap_similarity(fa, api_home)
    ) / 2.0
    return float(max(s_ord, s_swap))


def pick_best_odds_game(live_games: List[dict], fixture_name: str, threshold: float = 0.55):
    """Elige evento Odds API que mejor coincide con fixture_name."""
    if not isinstance(live_games, list) or not fixture_name.strip():
        return None, 0.0
    best_g, best_s = None, 0.0
    for g in live_games:
        gh = str(g.get("home_team") or "")
        ga = str(g.get("away_team") or "")
        sc = fixture_match_score(fixture_name, gh, ga)
        if sc > best_s:
            best_s, best_g = sc, g
    if best_g is not None and best_s >= threshold:
        return best_g, float(best_s)
    return None, float(best_s)


def extract_closing_decimal_from_odds_game(game: dict, market: str, selection: str) -> Optional[float]:
    """
    Mejor décimal por libro para la selección dada.
    market: match_winner | totals
    selection: home | draw | away | over_2.5
    """
    if not game:
        return None
    home = str(game.get("home_team") or "")
    away = str(game.get("away_team") or "")
    sel = (selection or "").strip().lower()
    mkt = (market or "").strip().lower()
    best_val: Optional[float] = None

    for bm in game.get("bookmakers", []) or []:
        for mk in bm.get("markets", []) or []:
            key = mk.get("key")
            outs = mk.get("outcomes", []) or []
            if mkt in ("match_winner", "h2h", "moneyline") and key == "h2h":
                for oc in outs:
                    nm = oc.get("name")
                    try:
                        dec = float(oc.get("price", 0))
                    except (TypeError, ValueError):
                        continue
                    if dec <= 1.0:
                        continue
                    if sel == "home" and nm == home:
                        best_val = max(best_val or 0.0, dec)
                    elif sel == "away" and nm == away:
                        best_val = max(best_val or 0.0, dec)
                    elif sel == "draw" and nm == "Draw":
                        best_val = max(best_val or 0.0, dec)
            if mkt in ("totals", "total_goals") and key == "totals" and sel == "over_2.5":
                for oc in outs:
                    if oc.get("point") != 2.5:
                        continue
                    if oc.get("name") != "Over":
                        continue
                    try:
                        dec = float(oc.get("price", 0))
                    except (TypeError, ValueError):
                        continue
                    if dec > 1.0:
                        best_val = max(best_val or 0.0, dec)

    return best_val if best_val and best_val > 1.0 else None


def refresh_pending_closing_odds(
    live_odds_by_league: Dict[str, List[dict]],
    db_path: Optional[Path] = None,
    match_threshold: float = 0.55,
) -> Dict[str, int]:
    """
    Actualiza closing_odds (y CLV en DB) para apuestas pending sin closing.
    live_odds_by_league: { league_code: lista de games de The Odds API }
    """
    init_bet_log_db(db_path)
    p = get_db_path(db_path)
    updated = 0
    skipped = 0
    try:
        with sqlite3.connect(p) as conn:
            rows = conn.execute(
                """
                SELECT match_id, league, market, selection, fixture_name
                FROM bet_log
                WHERE closing_odds IS NULL
                  AND lower(result) = 'pending'
                """
            ).fetchall()
            for mid, lg, mk, sel, fx in rows:
                games = live_odds_by_league.get(str(lg)) or []
                if not fx or not str(fx).strip():
                    skipped += 1
                    continue
                game, score = pick_best_odds_game(games, str(fx).strip(), threshold=match_threshold)
                if game is None:
                    skipped += 1
                    continue
                clo = extract_closing_decimal_from_odds_game(game, str(mk), str(sel))
                if clo is None:
                    skipped += 1
                    continue
                n = update_closing_odds(str(mid), str(mk), str(sel), float(clo), db_path=db_path)
                updated += int(n)
                if int(n) == 0:
                    skipped += 1
    except Exception as e:
        logger.warning("refresh_pending_closing_odds falló: %s", e, exc_info=True)
        return {"updated": updated, "skipped": skipped}

    return {"updated": updated, "skipped": skipped}


def selection_from_labels(mercado: str, home_team: str, away_team: str) -> str:
    """Codigo estable para deduplicación: home | draw | away | over_2.5 | ..."""
    m = (mercado or "").strip()
    if m == "Empate":
        return "draw"
    if m == "Over 2.5":
        return "over_2.5"
    if m.startswith("Gana "):
        side = m.replace("Gana ", "").strip()
        if side == (home_team or "").strip():
            return "home"
        if side == (away_team or "").strip():
            return "away"
    return "_".join(m.lower().replace(".", "").split())


def market_from_group(market_group: str) -> str:
    mg = (market_group or "").lower()
    if mg == "goles":
        return "totals"
    if mg == "resultado":
        return "match_winner"
    return mg or "unknown"
