import streamlit as st
import pandas as pd
import requests
import random
import json
import math
import time
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

from models.goals_model import build_team_goal_profile, project_match_xg
from models.team_strength import build_dynamic_elo_ratings, matchup_strength_multipliers

try:
    from bet_logging import (
        log_bet as audit_log_bet,
        update_closing_odds as audit_update_closing_odds,
        update_bet_result as audit_update_bet_result,
        calculate_clv as audit_calculate_clv,
        compute_metrics as audit_compute_metrics,
        load_bets_df as audit_load_bets_df,
        refresh_pending_closing_odds as audit_refresh_pending_closing_odds,
        init_bet_log_db,
        selection_from_labels as audit_selection_from_labels,
        market_from_group as audit_market_from_group,
    )
    _BET_AUDIT_AVAILABLE = True
except ImportError:
    _BET_AUDIT_AVAILABLE = False

    def audit_log_bet(*_a, **_k):
        return None

    def audit_update_closing_odds(*_a, **_k):
        return 0

    def audit_update_bet_result(*_a, **_k):
        return 0

    def audit_calculate_clv(df):
        return df

    def audit_compute_metrics(df):
        return {
            "total_bets": 0,
            "avg_clv": 0.0,
            "pct_positive_clv": 0.0,
            "roi": 0.0,
            "total_profit": 0.0,
            "win_rate": 0.0,
            "settled_bets": 0,
            "total_stake_settled": 0.0,
        }

    def audit_load_bets_df():
        return pd.DataFrame()

    def audit_refresh_pending_closing_odds(*_a, **_k):
        return {"updated": 0, "skipped": 0}

    def init_bet_log_db():
        return None

    def audit_selection_from_labels(mercado, home_team, away_team):
        return (mercado or "").replace(" ", "_").lower()

    def audit_market_from_group(market_group):
        return (market_group or "unknown").lower()

if _BET_AUDIT_AVAILABLE:
    try:
        init_bet_log_db()
    except Exception:
        pass

# rapidfuzz — se usa en _team_similarity y _find_best_game
try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False
    _rapidfuzz_fuzz = None

UNDERSTAT_AVAILABLE = True

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(page_title="Quant Betting Analytics V8", page_icon="⚽", layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────
#  CASAS Y LIGAS (CON PROMEDIOS DE GOLES REALES POR LIGA)
# ─────────────────────────────────────────────
MX_BOOKMAKERS = {
    "Bet365":        {"key": "bet365",        "url": "bet365.mx",         "flag": "🟢"},
    "1xBet":         {"key": "onexbet",       "url": "1xbet.mx",           "flag": "🟡"},
    "Betway":        {"key": "betway",        "url": "betway.mx",          "flag": "🟢"},
    "William Hill":  {"key": "williamhill",   "url": "williamhill.com",    "flag": "🟢"},
    "888sport":      {"key": "sport888",      "url": "888sport.mx",        "flag": "🟢"},
    "Pinnacle":      {"key": "pinnacle",      "url": "pinnacle.com",       "flag": "🟢"},
}
MX_BOOKMAKER_KEYS = ",".join(v["key"] for v in MX_BOOKMAKERS.values())
MX_REGIONS = "eu,uk"

# FIX #5: avg_goals por liga — referencia ~temporada reciente (ajustable).
# code = football-data.org (lookup tables v4). odds_key = The Odds API (GET /v4/sports/ si dudas).
LEAGUES = {
    # Big 5 + UCL
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"code": "PL",  "odds_key": "soccer_epl",                    "understat": "EPL",        "clubelo": True, "avg_goals": 2.84, "v8_params": {"div_min": 1.0, "div_max": 6.0}},
    "🇪🇸 La Liga":              {"code": "PD",  "odds_key": "soccer_spain_la_liga",          "understat": "La_liga",    "clubelo": True, "avg_goals": 2.68, "v8_params": {"div_min": 1.5, "div_max": 7.0}},
    "🇩🇪 Bundesliga":           {"code": "BL1", "odds_key": "soccer_germany_bundesliga",     "understat": "Bundesliga", "clubelo": True, "avg_goals": 3.08, "v8_params": {"div_min": 1.5, "div_max": 8.0}},
    "🇮🇹 Serie A":              {"code": "SA",  "odds_key": "soccer_italy_serie_a",          "understat": "Serie_A",    "clubelo": True, "avg_goals": 2.73, "v8_params": {"div_min": 1.0, "div_max": 6.0}},
    "🇫🇷 Ligue 1":              {"code": "FL1", "odds_key": "soccer_france_ligue_1",         "understat": "Ligue_1",    "clubelo": True, "avg_goals": 2.62, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🏆 Champions League":      {"code": "CL",  "odds_key": "soccer_uefa_champs_league",     "understat": None,         "clubelo": True, "avg_goals": 2.75, "v8_params": {"div_min": 0.5, "div_max": 5.0}},
    # UEFA + UK
    "🇪🇺 UEFA Europa League":   {"code": "EL",  "odds_key": "soccer_uefa_europa_league",     "understat": None,         "clubelo": True, "avg_goals": 2.65, "v8_params": {"div_min": 0.5, "div_max": 5.5}},
    "🇪🇺 UEFA Conference League": {"code": "UCL", "odds_key": "soccer_uefa_conference_league", "understat": None,       "clubelo": True, "avg_goals": 2.55, "v8_params": {"div_min": 0.5, "div_max": 5.5}},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship":       {"code": "ELC", "odds_key": "soccer_efl_championship",       "understat": None,         "clubelo": True, "avg_goals": 2.72, "v8_params": {"div_min": 1.0, "div_max": 7.0}},
    "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish Premiership": {"code": "SPL", "odds_key": "soccer_spl",                    "understat": None,         "clubelo": True, "avg_goals": 2.65, "v8_params": {"div_min": 1.0, "div_max": 7.0}},
    "🇳🇱 Eredivisie":           {"code": "DED", "odds_key": "soccer_netherlands_eredivisie", "understat": None,         "clubelo": True, "avg_goals": 3.05, "v8_params": {"div_min": 1.5, "div_max": 8.0}},
    "🇵🇹 Primeira Liga":        {"code": "PPL", "odds_key": "soccer_portugal_primeira_liga", "understat": None,         "clubelo": True, "avg_goals": 2.58, "v8_params": {"div_min": 1.0, "div_max": 7.0}},
    "🇧🇪 Jupiler Pro League":   {"code": "BJL", "odds_key": "soccer_belgium_first_div",      "understat": None,         "clubelo": True, "avg_goals": 2.75, "v8_params": {"div_min": 1.0, "div_max": 7.5}},
    "🇦🇹 Bundesliga (AT)":      {"code": "ABL", "odds_key": "soccer_austria_bundesliga",     "understat": None,         "clubelo": True, "avg_goals": 2.85, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🇬🇷 Super League":         {"code": "GSL", "odds_key": "soccer_greece_super_league",    "understat": None,         "clubelo": True, "avg_goals": 2.35, "v8_params": {"div_min": 0.8, "div_max": 6.5}},
    "🇹🇷 Süper Lig":            {"code": "TSL", "odds_key": "soccer_turkey_super_league",    "understat": None,         "clubelo": True, "avg_goals": 2.85, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🇩🇰 Superliga":            {"code": "DSU", "odds_key": "soccer_denmark_superliga",      "understat": None,         "clubelo": True, "avg_goals": 2.78, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🇳🇴 Eliteserien":          {"code": "TIP", "odds_key": "soccer_norway_eliteserien",     "understat": None,         "clubelo": True, "avg_goals": 2.95, "v8_params": {"div_min": 1.2, "div_max": 8.5}},
    "🇸🇪 Allsvenskan":          {"code": "ALL", "odds_key": "soccer_sweden_allsvenskan",     "understat": None,         "clubelo": True, "avg_goals": 2.72, "v8_params": {"div_min": 1.0, "div_max": 7.5}},
    # Alemania / Francia / Italia / España 2ª
    "🇩🇪 2. Bundesliga":        {"code": "BL2", "odds_key": "soccer_germany_bundesliga2",    "understat": None,         "clubelo": True, "avg_goals": 2.85, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🇫🇷 Ligue 2":              {"code": "FL2", "odds_key": "soccer_france_ligue_two",       "understat": None,         "clubelo": True, "avg_goals": 2.38, "v8_params": {"div_min": 0.8, "div_max": 6.5}},
    "🇮🇹 Serie B":              {"code": "SB",  "odds_key": "soccer_italy_serie_b",          "understat": None,         "clubelo": True, "avg_goals": 2.52, "v8_params": {"div_min": 1.0, "div_max": 7.0}},
    "🇪🇸 La Liga 2":            {"code": "SD",  "odds_key": "soccer_spain_segunda_division", "understat": None,         "clubelo": True, "avg_goals": 2.42, "v8_params": {"div_min": 0.8, "div_max": 6.5}},
    # Américas + Brasil
    "🇧🇷 Brasileirão A":        {"code": "BSA", "odds_key": "soccer_brazil_campeonato",      "understat": None,         "clubelo": True, "avg_goals": 2.62, "v8_params": {"div_min": 1.0, "div_max": 7.5}},
    "🇺🇸 MLS":                  {"code": "MLS", "odds_key": "soccer_usa_mls",                "understat": None,         "clubelo": True, "avg_goals": 2.82, "v8_params": {"div_min": 1.0, "div_max": 8.0}},
    "🇲🇽 Liga MX":              {"code": "LMX", "odds_key": "soccer_mexico_ligamx",          "understat": None,         "clubelo": True, "avg_goals": 2.72, "v8_params": {"div_min": 1.0, "div_max": 7.5}},
    # Asia / Oceanía
    "🇯🇵 J1 League":            {"code": "JJL", "odds_key": "soccer_japan_j_league",         "understat": None,         "clubelo": True, "avg_goals": 2.55, "v8_params": {"div_min": 1.0, "div_max": 7.0}},
    "🇦🇺 A-League":             {"code": "AAL", "odds_key": "soccer_australia_aleague",      "understat": None,         "clubelo": True, "avg_goals": 2.68, "v8_params": {"div_min": 1.0, "div_max": 7.5}},
}
LEAGUE_CODE_TO_ODDS_KEY = {cfg["code"]: cfg["odds_key"] for cfg in LEAGUES.values()}
BASE_URL = "https://api.football-data.org/v4"

# ─────────────────────────────────────────────
#  ESTILOS CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&family=DM+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 2px; }
.stApp { background: #0a0a0f; color: #e8e8e8; }
.metric-card { background: linear-gradient(135deg,#12121a,#1a1a2e); border:1px solid #2a2a40; border-radius:12px; padding:20px; margin:8px 0; transition:all .3s ease; }
.value-neutral { color:#ffcc44; font-family:'Space Mono'; font-size:1.4em; font-weight:700; }
.bet-row-positive { background:rgba(0,255,136,.08); border-left:3px solid #00ff88; padding:12px; border-radius:6px; margin:6px 0; }
.bet-row-negative { background:rgba(255,68,102,.08); border-left:3px solid #ff4466; padding:12px; border-radius:6px; margin:6px 0; }
.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:.75em; font-weight:600; margin:2px; }
.tag-green  { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red    { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow { background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }
.section-header { font-family:'Bebas Neue'; font-size:1.8em; letter-spacing:3px; color:#00ff88; border-bottom:1px solid #2a2a40; padding-bottom:8px; margin:24px 0 16px 0; }
</style>
""", unsafe_allow_html=True)

DB_PATH = "quant_betting_v8.db"

def log_event(context, error):
    """Log simple para depuración sin romper el flujo de la app."""
    msg = f"{context}: {error}"
    logs = st.session_state.setdefault("system_logs", [])
    logs.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "msg": msg})
    if len(logs) > 100:
        st.session_state["system_logs"] = logs[-100:]

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades_v8 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                partido TEXT NOT NULL,
                prob_modelo REAL NOT NULL,
                momio_americano REAL NOT NULL,
                resultado TEXT NOT NULL,
                stake REAL NOT NULL DEFAULT 0,
                cuota_cierre REAL,
                clv_pct REAL,
                pnl REAL NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_ratings_cache_v8 (
                league_code TEXT NOT NULL,
                team_id INTEGER NOT NULL,
                rating REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_code, team_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edge_samples_v8 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                league_code TEXT NOT NULL,
                match_key TEXT NOT NULL,
                market TEXT NOT NULL,
                market_group TEXT NOT NULL,
                div_dyn REAL NOT NULL,
                ev REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bets_execution_log_v8 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                fecha TEXT NOT NULL,
                liga TEXT,
                partido TEXT NOT NULL,
                mercado TEXT NOT NULL,
                market_group TEXT,
                prob_modelo REAL NOT NULL,
                uncertainty REAL,
                edge_pct REAL,
                entry_odds REAL NOT NULL,
                closing_odds REAL,
                clv REAL,
                stake REAL NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT 'Pendiente',
                pnl REAL NOT NULL DEFAULT 0,
                brier_error REAL,
                simulated_delay_min REAL DEFAULT 0,
                slippage_pct REAL DEFAULT 0,
                was_rejected INTEGER DEFAULT 0,
                execution_notes TEXT
            )
        """)
        _ensure_column(conn, "paper_trades_v8", "liga", "TEXT")
        _ensure_column(conn, "paper_trades_v8", "mercado", "TEXT")
        _ensure_column(conn, "paper_trades_v8", "entry_odds_dec", "REAL")
        _ensure_column(conn, "paper_trades_v8", "closing_odds_dec", "REAL")
        _ensure_column(conn, "paper_trades_v8", "uncertainty", "REAL")
        _ensure_column(conn, "paper_trades_v8", "edge_pct", "REAL")
        conn.commit()


def _ensure_column(conn, table_name: str, col_name: str, col_type: str):
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {c[1] for c in cols}
    if col_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")


def load_team_ratings_cache(league_code: str) -> Dict[int, float]:
    """Load cached ELO ratings by league to stabilize cold starts."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT team_id, rating FROM team_ratings_cache_v8 WHERE league_code = ?",
            (league_code,),
        ).fetchall()
    return {int(team_id): float(rating) for team_id, rating in rows}


def save_team_ratings_cache(league_code: str, ratings: Dict[int, float]) -> None:
    if not ratings:
        return
    init_db()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO team_ratings_cache_v8 (league_code, team_id, rating, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(league_code, team_id)
            DO UPDATE SET rating = excluded.rating, updated_at = excluded.updated_at
            """,
            [(league_code, int(team_id), float(rating), ts) for team_id, rating in ratings.items()],
        )
        conn.commit()


def save_edge_sample(
    league_code: str,
    match_key: str,
    market: str,
    market_group: str,
    div_dyn: float,
    ev: float,
) -> None:
    """Persist edge observations for data-driven threshold learning."""
    init_db()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        dup = conn.execute(
            """
            SELECT 1
            FROM edge_samples_v8
            WHERE league_code = ?
              AND match_key = ?
              AND market = ?
              AND ABS(div_dyn - ?) < 0.05
              AND ts >= datetime('now', '-6 hours')
            LIMIT 1
            """,
            (league_code, match_key, market, float(div_dyn)),
        ).fetchone()
        if dup:
            return
        conn.execute(
            """
            INSERT INTO edge_samples_v8 (
                ts, league_code, match_key, market, market_group, div_dyn, ev
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, league_code, match_key, market, market_group, float(div_dyn), float(ev)),
        )
        conn.commit()


def learn_divergence_thresholds(
    league_code: str,
    fallback_min: float,
    fallback_max: float,
    min_samples: int = 120,
) -> Tuple[float, float, int]:
    """
    Learn divergence thresholds from historical edge samples by league.
    Strategy: percentiles on positive-EV samples to avoid hardcoded values.
    """
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT div_dyn
            FROM edge_samples_v8
            WHERE league_code = ? AND ev > 0
            """,
            (league_code,),
        ).fetchall()

    vals = np.array([float(r[0]) for r in rows if r[0] is not None], dtype=float)
    vals = vals[np.isfinite(vals)]
    vals = vals[vals > 0.0]
    sample_n = int(len(vals))
    if sample_n < min_samples:
        return float(fallback_min), float(fallback_max), sample_n

    p70 = float(np.percentile(vals, 70))
    p97 = float(np.percentile(vals, 97))
    learned_min = max(0.25, p70)
    learned_max = max(learned_min + 0.5, p97)
    learned_max = min(30.0, learned_max)
    return round(learned_min, 2), round(learned_max, 2), sample_n

def load_trades_db():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM paper_trades_v8 ORDER BY id DESC", conn)
    if df.empty:
        return []
    return [{
        "ID": int(r["id"]),
        "Fecha": r["fecha"],
        "Partido": r["partido"],
        "Liga": r["liga"] if "liga" in df.columns else "N/A",
        "Mercado": r["mercado"] if "mercado" in df.columns else "N/A",
        "Prob Modelo": float(r["prob_modelo"]),
        "Momio": float(r["momio_americano"]),
        "Resultado": r["resultado"],
        "Stake": float(r["stake"]),
        "Uncertainty": None if ("uncertainty" in df.columns and pd.isna(r["uncertainty"])) else (float(r["uncertainty"]) if "uncertainty" in df.columns else None),
        "Edge %": None if ("edge_pct" in df.columns and pd.isna(r["edge_pct"])) else (float(r["edge_pct"]) if "edge_pct" in df.columns else None),
        "Entry Odds Dec": None if ("entry_odds_dec" in df.columns and pd.isna(r["entry_odds_dec"])) else (float(r["entry_odds_dec"]) if "entry_odds_dec" in df.columns else None),
        "Closing Odds Dec": None if ("closing_odds_dec" in df.columns and pd.isna(r["closing_odds_dec"])) else (float(r["closing_odds_dec"]) if "closing_odds_dec" in df.columns else None),
        "Cuota Cierre": None if pd.isna(r["cuota_cierre"]) else float(r["cuota_cierre"]),
        "CLV %": None if pd.isna(r["clv_pct"]) else float(r["clv_pct"]),
        "PnL": float(r["pnl"]),
    } for _, r in df.iterrows()]

def _calc_trade_pnl(stake, american_odd, result):
    dec = american_to_decimal(american_odd)
    if result == "Ganada":
        return (dec - 1.0) * stake
    if result == "Perdida":
        return -stake
    return 0.0

def build_reliability_table(closed_trades, n_bins=10):
    rows = []
    if not closed_trades:
        return pd.DataFrame(rows)
    n_bins = max(3, min(20, int(n_bins)))
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i < n_bins - 1:
            bucket = [t for t in closed_trades if lo <= t["Prob Modelo"] < hi]
        else:
            bucket = [t for t in closed_trades if lo <= t["Prob Modelo"] <= hi]
        if not bucket:
            continue
        avg_pred = float(np.mean([t["Prob Modelo"] for t in bucket]))
        avg_real = float(np.mean([1.0 if t["Resultado"] == "Ganada" else 0.0 for t in bucket]))
        rows.append({
            "Bin": f"{int(lo*100)}-{int(hi*100)}%",
            "N": len(bucket),
            "Prob Promedio": avg_pred,
            "Frecuencia Real": avg_real,
            "Gap": avg_pred - avg_real,
        })
    return pd.DataFrame(rows)

def calc_ece(rel_df):
    if rel_df.empty:
        return 0.0
    total_n = rel_df["N"].sum()
    if total_n <= 0:
        return 0.0
    ece = (np.abs(rel_df["Gap"]) * (rel_df["N"] / total_n)).sum()
    return float(ece)

def _clip_prob(p):
    return float(min(0.99, max(0.01, p)))


def _log_loss_score(y_true, y_prob):
    eps = 1e-9
    p = np.clip(np.array(y_prob, dtype=float), eps, 1.0 - eps)
    y = np.array(y_true, dtype=float)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def fit_bin_calibrator(closed_trades, n_bins=10, min_bin_size=8):
    """Bins calibrator: probability -> observed frequency mapping."""
    if not closed_trades:
        return []
    rel_df = build_reliability_table(closed_trades, n_bins=n_bins)
    if rel_df.empty:
        return []
    rel_df = rel_df.sort_values("Prob Promedio")
    rel_df = rel_df[rel_df["N"] >= min_bin_size].copy()
    if rel_df.empty:
        return []
    return [(float(r["Prob Promedio"]), float(r["Frecuencia Real"])) for _, r in rel_df.iterrows()]


def apply_bin_calibration(prob, calibrator_points):
    p = _clip_prob(float(prob))
    if not calibrator_points or len(calibrator_points) < 2:
        return p
    points = sorted(calibrator_points, key=lambda x: x[0])
    if p <= points[0][0]:
        return _clip_prob(points[0][1])
    if p >= points[-1][0]:
        return _clip_prob(points[-1][1])
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if x0 <= p <= x1:
            if x1 == x0:
                return _clip_prob(y0)
            t = (p - x0) / (x1 - x0)
            return _clip_prob(y0 + t * (y1 - y0))
    return p


def fit_platt_calibrator(closed_trades, lr=0.08, epochs=350):
    """Fit Platt scaling via logistic regression on raw probabilities."""
    if len(closed_trades) < 25:
        return None
    x = np.array([_clip_prob(float(t["Prob Modelo"])) for t in closed_trades], dtype=float)
    y = np.array([1.0 if t["Resultado"] == "Ganada" else 0.0 for t in closed_trades], dtype=float)
    z = np.log(x / (1.0 - x))
    a, b = 1.0, 0.0
    for _ in range(int(epochs)):
        logits = a * z + b
        preds = 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))
        err = preds - y
        grad_a = float(np.mean(err * z))
        grad_b = float(np.mean(err))
        a -= lr * grad_a
        b -= lr * grad_b
    return {"a": float(a), "b": float(b)}


def apply_platt_calibration(prob, params):
    if not params:
        return _clip_prob(prob)
    p = _clip_prob(prob)
    z = math.log(p / (1.0 - p))
    out = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, params["a"] * z + params["b"]))))
    return _clip_prob(out)


def fit_isotonic_calibrator(closed_trades):
    """Fit isotonic regression using PAV (monotonic non-parametric)."""
    if len(closed_trades) < 25:
        return None
    pairs = sorted(
        [(_clip_prob(float(t["Prob Modelo"])), 1.0 if t["Resultado"] == "Ganada" else 0.0) for t in closed_trades],
        key=lambda x: x[0],
    )
    blocks = [{"x_lo": p, "x_hi": p, "sum_y": y, "w": 1.0} for p, y in pairs]
    i = 0
    while i < len(blocks) - 1:
        mean_i = blocks[i]["sum_y"] / blocks[i]["w"]
        mean_n = blocks[i + 1]["sum_y"] / blocks[i + 1]["w"]
        if mean_i > mean_n:
            merged = {
                "x_lo": blocks[i]["x_lo"],
                "x_hi": blocks[i + 1]["x_hi"],
                "sum_y": blocks[i]["sum_y"] + blocks[i + 1]["sum_y"],
                "w": blocks[i]["w"] + blocks[i + 1]["w"],
            }
            blocks[i : i + 2] = [merged]
            i = max(i - 1, 0)
        else:
            i += 1
    return [{"x_lo": b["x_lo"], "x_hi": b["x_hi"], "y": float(b["sum_y"] / b["w"])} for b in blocks]


def apply_isotonic_calibration(prob, blocks):
    p = _clip_prob(prob)
    if not blocks:
        return p
    for b in blocks:
        if b["x_lo"] <= p <= b["x_hi"]:
            return _clip_prob(b["y"])
    if p < blocks[0]["x_lo"]:
        return _clip_prob(blocks[0]["y"])
    return _clip_prob(blocks[-1]["y"])


def build_best_calibrator(closed_trades, min_train_size=40):
    """
    Select best calibrator on holdout split using Brier then LogLoss.
    Applies only if it improves baseline.
    """
    ordered = sorted(closed_trades, key=lambda x: (x.get("Fecha", ""), x.get("ID", 0)))
    if len(ordered) < max(50, min_train_size + 15):
        return {"method": "none", "meta": {"reason": "insufficient_data"}}

    split_idx = max(min_train_size, int(len(ordered) * 0.7))
    if split_idx >= len(ordered) - 8:
        return {"method": "none", "meta": {"reason": "insufficient_validation"}}
    train_slice = ordered[:split_idx]
    val_slice = ordered[split_idx:]

    y_val = np.array([1.0 if t["Resultado"] == "Ganada" else 0.0 for t in val_slice], dtype=float)
    p_base = np.array([_clip_prob(float(t["Prob Modelo"])) for t in val_slice], dtype=float)
    base_brier = float(np.mean((p_base - y_val) ** 2))
    base_logloss = _log_loss_score(y_val, p_base)

    candidates = [{"method": "none", "params": None, "p_val": p_base}]

    bin_points = fit_bin_calibrator(train_slice, n_bins=10, min_bin_size=8)
    if len(bin_points) >= 2:
        p_bin = np.array([apply_bin_calibration(p, bin_points) for p in p_base], dtype=float)
        candidates.append({"method": "bin", "params": bin_points, "p_val": p_bin})

    platt = fit_platt_calibrator(train_slice)
    if platt:
        p_platt = np.array([apply_platt_calibration(p, platt) for p in p_base], dtype=float)
        candidates.append({"method": "platt", "params": platt, "p_val": p_platt})

    isotonic = fit_isotonic_calibrator(train_slice)
    if isotonic:
        p_iso = np.array([apply_isotonic_calibration(p, isotonic) for p in p_base], dtype=float)
        candidates.append({"method": "isotonic", "params": isotonic, "p_val": p_iso})

    scored = []
    for c in candidates:
        brier = float(np.mean((c["p_val"] - y_val) ** 2))
        ll = _log_loss_score(y_val, c["p_val"])
        scored.append((c, brier, ll))
    scored.sort(key=lambda x: (x[1], x[2]))
    best, best_brier, best_ll = scored[0]

    if best["method"] == "none" or best_brier >= base_brier:
        return {
            "method": "none",
            "meta": {"brier_before": round(base_brier, 5), "brier_after": round(base_brier, 5), "logloss_before": round(base_logloss, 5), "logloss_after": round(base_logloss, 5)},
        }
    return {
        "method": best["method"],
        "params": best["params"],
        "meta": {"brier_before": round(base_brier, 5), "brier_after": round(best_brier, 5), "logloss_before": round(base_logloss, 5), "logloss_after": round(best_ll, 5)},
    }


def apply_selected_calibration(prob, calibrator):
    method = (calibrator or {}).get("method", "none")
    params = (calibrator or {}).get("params")
    p = _clip_prob(prob)
    if method == "bin":
        return apply_bin_calibration(p, params)
    if method == "platt":
        return apply_platt_calibration(p, params)
    if method == "isotonic":
        return apply_isotonic_calibration(p, params)
    return p


def walk_forward_backtest(closed_trades, min_train_size=20, test_window=10):
    """Leakage-safe rolling-window evaluation with optional recalibration."""
    if len(closed_trades) < (min_train_size + test_window):
        return pd.DataFrame([])
    ordered = sorted(closed_trades, key=lambda x: (x.get("Fecha", ""), x.get("ID", 0)))
    folds = []
    fold_id = 1
    start = min_train_size
    while start < len(ordered):
        train_slice = ordered[:start]
        test_slice = ordered[start:start + test_window]
        if not test_slice:
            break

        calibrator = build_best_calibrator(train_slice, min_train_size=max(30, min_train_size))
        y = np.array([1.0 if t["Resultado"] == "Ganada" else 0.0 for t in test_slice], dtype=float)
        p_raw = np.array([_clip_prob(float(t["Prob Modelo"])) for t in test_slice], dtype=float)
        p_cal = np.array([apply_selected_calibration(p, calibrator) for p in p_raw], dtype=float)

        brier_raw = float(np.mean((p_raw - y) ** 2))
        brier_cal = float(np.mean((p_cal - y) ** 2))
        ll_raw = _log_loss_score(y, p_raw)
        ll_cal = _log_loss_score(y, p_cal)
        pnl = float(np.sum([t.get("PnL", 0.0) for t in test_slice]))
        staked = float(np.sum([max(0.0, t.get("Stake", 0.0)) for t in test_slice]))
        roi = (pnl / staked * 100.0) if staked > 0 else 0.0
        clv_vals = [t.get("CLV %") for t in test_slice if t.get("CLV %") is not None]
        avg_clv = float(np.mean(clv_vals)) if clv_vals else 0.0

        folds.append({
            "Fold": fold_id,
            "Train Size": len(train_slice),
            "Test Size": len(test_slice),
            "Calibrator": calibrator.get("method", "none"),
            "Brier Raw": round(brier_raw, 4),
            "Brier Cal": round(brier_cal, 4),
            "LogLoss Raw": round(ll_raw, 4),
            "LogLoss Cal": round(ll_cal, 4),
            "ROI %": round(roi, 2),
            "CLV %": round(avg_clv, 2),
            "PnL": round(pnl, 2),
        })
        start += test_window
        fold_id += 1
    return pd.DataFrame(folds)

def save_trade_db(trade):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO paper_trades_v8 (
                fecha, partido, liga, mercado, prob_modelo, momio_americano, resultado, stake,
                cuota_cierre, clv_pct, pnl, entry_odds_dec, closing_odds_dec, uncertainty, edge_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["Fecha"], trade["Partido"], trade.get("Liga"), trade.get("Mercado"),
                trade["Prob Modelo"], trade["Momio"], trade["Resultado"], trade["Stake"],
                trade.get("Cuota Cierre"), trade.get("CLV %"), trade["PnL"], trade.get("Entry Odds Dec"),
                trade.get("Closing Odds Dec"), trade.get("Uncertainty"), trade.get("Edge %")
            )
        )
        conn.commit()
    save_execution_log(trade)


def save_execution_log(trade):
    """Detailed logging for continuous monitoring and CLV audits."""
    init_db()
    y = 1.0 if trade.get("Resultado") == "Ganada" else 0.0
    p = float(trade.get("Prob Modelo", 0.0))
    brier_error = (p - y) ** 2 if trade.get("Resultado") in ("Ganada", "Perdida") else None
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bets_execution_log_v8 (
                ts, fecha, liga, partido, mercado, market_group, prob_modelo, uncertainty, edge_pct,
                entry_odds, closing_odds, clv, stake, result, pnl, brier_error,
                simulated_delay_min, slippage_pct, was_rejected, execution_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                trade.get("Fecha"),
                trade.get("Liga"),
                trade.get("Partido"),
                trade.get("Mercado", "N/A"),
                trade.get("Market Group"),
                float(trade.get("Prob Modelo", 0.0)),
                trade.get("Uncertainty"),
                trade.get("Edge %"),
                trade.get("Entry Odds Dec") or american_to_decimal(trade.get("Momio", 0)),
                trade.get("Closing Odds Dec"),
                trade.get("CLV %"),
                float(trade.get("Stake", 0.0)),
                trade.get("Resultado", "Pendiente"),
                float(trade.get("PnL", 0.0)),
                brier_error,
                float(trade.get("Sim Delay Min", 0.0)),
                float(trade.get("Slippage Pct", 0.0)),
                int(trade.get("Was Rejected", 0)),
                trade.get("Execution Notes"),
            )
        )
        conn.commit()


def update_trade_closing_odds(trade_id: int, closing_american: float, closing_dec: float, clv_pct: Optional[float]):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE paper_trades_v8
            SET cuota_cierre = ?, closing_odds_dec = ?, clv_pct = ?
            WHERE id = ?
            """,
            (closing_american, closing_dec, clv_pct, int(trade_id)),
        )
        conn.commit()


def _parse_match_name_from_trade(trade_partido: str):
    txt = (trade_partido or "").strip()
    if " vs " in txt:
        left, right = txt.split(" vs ", 1)
        return left.strip(), right.strip()
    if " v " in txt:
        left, right = txt.split(" v ", 1)
        return left.strip(), right.strip()
    if " - " in txt:
        left, right = txt.split(" - ", 1)
        return left.strip(), right.strip()
    return None, None


def _get_market_closing_from_game(game: dict, trade: dict) -> Optional[float]:
    """
    Returns closing decimal odd for a trade market.
    Supports 1X2 and totals 2.5.
    """
    market_label = (trade.get("Mercado") or "").strip().lower()
    home_name, away_name = _parse_match_name_from_trade(trade.get("Partido", ""))
    if not game:
        return None

    best = None
    for bm in game.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            key = mkt.get("key")
            outcomes = mkt.get("outcomes", [])
            if key == "totals" and ("over 2.5" in market_label or "under 2.5" in market_label):
                for oc in outcomes:
                    if oc.get("point") != 2.5:
                        continue
                    name = (oc.get("name") or "").lower()
                    if "over 2.5" in market_label and name == "over":
                        best = max(best or 0.0, float(oc["price"]))
                    if "under 2.5" in market_label and name == "under":
                        best = max(best or 0.0, float(oc["price"]))
            if key == "h2h":
                for oc in outcomes:
                    name = oc.get("name", "")
                    dec = float(oc["price"])
                    if market_label == "empate" and name == "Draw":
                        best = max(best or 0.0, dec)
                    elif market_label.startswith("gana ") and home_name and away_name:
                        team = market_label.replace("gana ", "").strip()
                        if _team_similarity(team, home_name.lower()) >= 0.75 and name == game.get("home_team"):
                            best = max(best or 0.0, dec)
                        if _team_similarity(team, away_name.lower()) >= 0.75 and name == game.get("away_team"):
                            best = max(best or 0.0, dec)
    return best


def refresh_pending_closing_odds():
    """
    Pull latest market prices for pending trades and write closing odds + CLV.
    Best effort only for well-formed trade labels.
    """
    trades = load_trades_db()
    pending = [t for t in trades if t.get("Resultado") == "Pendiente" and not t.get("Cuota Cierre")]
    if not pending:
        return {"updated": 0, "skipped": 0, "errors": 0}

    updated, skipped, errors = 0, 0, 0
    by_league = {}
    for t in pending:
        league_code = str(t.get("Liga") or "").strip()
        if not league_code:
            skipped += 1
            continue
        by_league.setdefault(league_code, []).append(t)

    for league_code, league_trades in by_league.items():
        odds_key = LEAGUE_CODE_TO_ODDS_KEY.get(league_code)
        if not odds_key:
            skipped += len(league_trades)
            continue
        try:
            live = get_live_odds(_get_odds_keys_pool()[0] if _get_odds_keys_pool() else "", odds_key)
            if not isinstance(live, list) or not live:
                skipped += len(league_trades)
                continue
            for t in league_trades:
                home, away = _parse_match_name_from_trade(t.get("Partido", ""))
                if not home or not away:
                    skipped += 1
                    continue
                game, score = _find_best_game(live, home, away, threshold=0.60)
                if not game or score < 0.60:
                    skipped += 1
                    continue
                close_dec = _get_market_closing_from_game(game, t)
                if not close_dec or close_dec <= 1.0:
                    skipped += 1
                    continue
                close_am = normalize_to_american(close_dec)
                entry_dec = t.get("Entry Odds Dec") or american_to_decimal(t.get("Momio", 0))
                clv_raw = calc_clv(float(entry_dec), float(close_dec))
                clv_pct = (clv_raw * 100.0) if clv_raw is not None else None
                update_trade_closing_odds(t["ID"], float(close_am), float(close_dec), clv_pct)
                updated += 1
        except Exception as e:
            log_event(f"refresh_pending_closing_odds::{league_code}", e)
            errors += len(league_trades)
    return {"updated": updated, "skipped": skipped, "errors": errors}

def clear_trades_db():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM paper_trades_v8")
        conn.commit()

# ─────────────────────────────────────────────
#  NÚCLEO MATEMÁTICO V8
# ─────────────────────────────────────────────

# FIX #3: calcular margen real de la casa en lugar de asumir 5% fijo
def calc_market_margin(all_dec_odds_for_market: list) -> float:
    """
    Calcula el margen real (overround) de la casa sumando las probs implícitas
    de todos los outcomes del mismo mercado. Ej: [home_dec, draw_dec, away_dec].
    Si no hay datos suficientes, devuelve 1.05 como fallback.
    """
    if not all_dec_odds_for_market or len(all_dec_odds_for_market) < 2:
        return 1.05
    total = sum(1.0 / o for o in all_dec_odds_for_market if o > 1.0)
    return max(total, 1.001)  # nunca menor que 1

def get_vig_free_prob(dec_odds, market_margin=1.05):
    """Calcula probabilidad real quitando el margen dinámico de la casa."""
    if dec_odds <= 1.0:
        return 0.0
    prob_con_vig = 1.0 / dec_odds
    prob_sin_vig = prob_con_vig / market_margin
    return min(prob_sin_vig, 0.99)

def calc_v8_metrics(my_prob_pct, dec_odds, market_margin=1.05):
    """Calcula Divergencia Absoluta y Dinámica con margen dinámico."""
    my_prob = my_prob_pct / 100.0
    market_prob_vf = get_vig_free_prob(dec_odds, market_margin)

    div_abs = (my_prob - market_prob_vf) * 100
    div_dinamica = ((my_prob - market_prob_vf) / market_prob_vf) * 100 if market_prob_vf > 0 else 0.0
    ev_vigfree = (my_prob * dec_odds) - 1.0

    return round(div_abs, 2), round(div_dinamica, 2), round(market_prob_vf * 100, 2), round(ev_vigfree, 4)


def _book_margin_key_for_mercado(mercado: str, home_team: str, away_team: str) -> str:
    """Mapeo mercado etiquetado → clave del dict de márgenes (Home/Draw/Away/O25)."""
    if mercado == "Empate":
        return "Draw"
    if mercado == "Over 2.5":
        return "O25"
    if mercado.startswith("Gana "):
        side = mercado.replace("Gana ", "").strip()
        if side == home_team:
            return "Home"
        if side == away_team:
            return "Away"
    return "Home"


def calc_clv(entry_odds_dec: Optional[float], closing_odds_dec: Optional[float]) -> Optional[float]:
    """CLV principal: (closing / entry) - 1."""
    if entry_odds_dec is None or closing_odds_dec is None:
        return None
    if entry_odds_dec <= 1.0 or closing_odds_dec <= 1.0:
        return None
    return float((closing_odds_dec / entry_odds_dec) - 1.0)


def confidence_uncertainty(prob_pct: float) -> float:
    """Normalized uncertainty in [0,1]. Higher means lower confidence."""
    p = max(0.01, min(0.99, float(prob_pct) / 100.0))
    return float(4.0 * p * (1.0 - p))


def apply_execution_frictions(
    entry_odds_dec: float,
    slippage_pct: float = 0.0,
    rejection_rate: float = 0.0,
    max_stake_market: Optional[float] = None,
    desired_stake: float = 0.0,
):
    """
    Simulate realistic execution:
    - Slippage worsens odds
    - Random rejection
    - Stake cap by market
    """
    slippage = max(0.0, float(slippage_pct))
    effective_odds = max(1.01, float(entry_odds_dec) * (1.0 - slippage))
    rejected = 1 if random.random() < max(0.0, min(1.0, float(rejection_rate))) else 0
    stake_after_limits = float(desired_stake)
    if max_stake_market is not None:
        stake_after_limits = min(stake_after_limits, float(max_stake_market))
    if rejected:
        stake_after_limits = 0.0
    return effective_odds, stake_after_limits, rejected


def summarize_clv_segments(closed_trades):
    rows = []
    for t in closed_trades:
        clv = t.get("CLV %")
        if clv is None:
            continue
        odd = t.get("Entry Odds Dec") or american_to_decimal(t.get("Momio", 0))
        p = float(t.get("Prob Modelo", 0.0))
        rows.append({
            "Liga": t.get("Liga", "N/A"),
            "Mercado": t.get("Mercado", "N/A"),
            "CLV %": float(clv),
            "Odd": float(odd) if odd else None,
            "Prob": p,
        })
    if not rows:
        return pd.DataFrame([])
    df = pd.DataFrame(rows).dropna(subset=["Odd"])
    df["Odds Bucket"] = pd.cut(df["Odd"], bins=[1.0, 1.6, 2.0, 2.5, 5.0, 50.0], labels=["1.01-1.60", "1.61-2.00", "2.01-2.50", "2.51-5.00", "5.01+"])
    df["Prob Bucket"] = pd.cut(df["Prob"], bins=[0.0, 0.40, 0.50, 0.60, 1.0], labels=["0-40%", "40-50%", "50-60%", "60-100%"])
    return df


def build_clv_gate(closed_trades, min_samples=15):
    """
    Keep only segments with positive historical CLV.
    Returns allowed segments by (Liga, Odds Bucket, Prob Bucket).
    """
    df = summarize_clv_segments(closed_trades)
    if df.empty:
        return set(), pd.DataFrame([])
    grp = (
        df.groupby(["Liga", "Odds Bucket", "Prob Bucket"], dropna=False)["CLV %"]
        .agg(["count", "mean"])
        .reset_index()
        .rename(columns={"count": "N", "mean": "Avg CLV %"})
    )
    reliable = grp[(grp["N"] >= int(min_samples)) & (grp["Avg CLV %"] > 0.0)]
    allow = set((r["Liga"], str(r["Odds Bucket"]), str(r["Prob Bucket"])) for _, r in reliable.iterrows())
    return allow, grp.sort_values(["Avg CLV %", "N"], ascending=[False, False])


def kelly_performance_multiplier(avg_clv_pct, ece, drawdown_pct, overfit_penalty):
    """Adaptive risk control from realized execution quality."""
    clv_adj = 1.0 if avg_clv_pct >= 0 else 0.60
    cal_adj = 0.85 if ece > 0.08 else 1.0
    dd_adj = 0.75 if drawdown_pct > 8.0 else 1.0
    of_adj = max(0.5, 1.0 - overfit_penalty)
    return max(0.25, min(1.1, clv_adj * cal_adj * dd_adj * of_adj))


def compute_overfit_penalty(cerradas):
    """
    Compare train/validation/oos by chronological thirds.
    Penalize strong degradation in OOS.
    """
    if len(cerradas) < 60:
        return 0.0, {}
    ordered = sorted(cerradas, key=lambda x: (x.get("Fecha", ""), x.get("ID", 0)))
    n = len(ordered)
    tr = ordered[: n // 3]
    va = ordered[n // 3 : (2 * n) // 3]
    oos = ordered[(2 * n) // 3 :]

    def _roi(arr):
        pnl = float(np.sum([t.get("PnL", 0.0) for t in arr]))
        staked = float(np.sum([max(0.0, t.get("Stake", 0.0)) for t in arr]))
        return (pnl / staked * 100.0) if staked > 0 else 0.0

    roi_tr, roi_va, roi_oos = _roi(tr), _roi(va), _roi(oos)
    degradation = max(0.0, roi_va - roi_oos)
    penalty = min(0.5, degradation / 20.0)
    return penalty, {"ROI Train %": round(roi_tr, 2), "ROI Val %": round(roi_va, 2), "ROI OOS %": round(roi_oos, 2)}


def filter_correlated_candidates(candidates, max_per_match=1):
    """
    Keep highest-EV candidate when markets are correlated by group.
    Optionally keep only one candidate per match.
    """
    if not candidates:
        return []

    best_by_match_group = {}
    for c in candidates:
        key = (c.get("match_key", ""), c.get("market_group", "other"))
        prev = best_by_match_group.get(key)
        if prev is None or c.get("ev", -999) > prev.get("ev", -999):
            best_by_match_group[key] = c

    reduced = list(best_by_match_group.values())
    if max_per_match <= 0:
        return reduced

    by_match = {}
    for c in reduced:
        by_match.setdefault(c.get("match_key", ""), []).append(c)

    final = []
    for _, rows in by_match.items():
        rows = sorted(rows, key=lambda x: (x.get("ev", -999), x.get("div_dyn", -999)), reverse=True)
        final.extend(rows[:max_per_match])
    return final

def smart_kelly_v8(my_prob_pct, dec_odds, max_absolute_stake, bankroll, lm_factor=1.0):
    """Kelly 12.5% + Line Movement + Techo de Stake."""
    p = my_prob_pct / 100.0
    b = dec_odds - 1.0
    if b <= 0:
        return 0.0, 0.0, "N/A"

    kelly_puro = (b * p - (1 - p)) / b
    if kelly_puro <= 0:
        return 0.0, 0.0, "Sin Edge"

    kelly_base_pct = (kelly_puro * 0.125) * 100  # 1/8 de Kelly
    kelly_ajustado_pct = kelly_base_pct * lm_factor

    apuesta_teorica = (kelly_ajustado_pct / 100) * bankroll
    apuesta_final = min(apuesta_teorica, max_absolute_stake)  # HARD CAP

    kelly_efectivo = (apuesta_final / bankroll) * 100

    riesgo = "🔴 Riesgo LM" if lm_factor < 0.5 else ("🟢 Seguro" if kelly_efectivo < 2.0 else "🟡 Medio-Alto")
    if apuesta_final == max_absolute_stake:
        riesgo = "🛑 Cap Máximo"

    return round(kelly_efectivo, 2), round(apuesta_final, 2), riesgo

def apply_line_movement_penalty(prob_apertura, prob_actual):
    if prob_apertura is None or prob_actual is None:
        return 1.0
    diferencia = prob_actual - prob_apertura
    if diferencia < -0.03:   return 0.25
    elif diferencia < -0.01: return 0.60
    elif diferencia > 0.02:  return 1.10
    return 1.0

def normalize_to_american(price):
    price = float(price)
    if 1.01 <= price <= 30.0:
        if price >= 2.0: return int(round((price - 1) * 100))
        else:            return int(round(-100 / (price - 1)))
    return int(price)

# FIX #2: american_to_decimal reescrita con lógica clara y sin ambigüedad
def american_to_decimal(a):
    """
    Convierte momio americano a decimal.
    - Si 'a' ya parece un decimal (1.01–30.0 con fracción), lo devuelve tal cual.
    - Si a >= 100 → favorito: (a/100) + 1
    - Si a <= -100 → perder: (100/|a|) + 1
    - Valores entre -99 y 99 (no válidos en americano estándar) → fallback 1.0
    """
    a = float(a)
    # Ya es formato decimal (ej: 1.91, 2.50)
    if 1.01 <= a <= 30.0 and not a.is_integer():
        return round(a, 4)
    # Americano positivo (+150, +200, etc.)
    if a >= 100:
        return round((a / 100) + 1, 4)
    # Americano negativo (-110, -200, etc.)
    if a <= -100:
        return round((100 / abs(a)) + 1, 4)
    # Valores extraños (ej: -50 o +50) — no son americanos válidos, fallback
    return 1.0

def implied_prob(dec):
    return round((1 / dec) * 100, 2) if dec > 1 else 0

# ─────────────────────────────────────────────
#  SISTEMA DE ROTACIÓN Y LLAMADAS A API
# ─────────────────────────────────────────────
def _get_odds_keys_pool():
    pool = []
    if hasattr(st, "secrets"):
        for suffix in ["", "_2", "_3"]:
            k = st.secrets.get(f"ODDS_API_KEY{suffix}", "")
            if k and k not in pool: pool.append(k)
    extra = st.session_state.get("odds_keys_pool", [])
    for k in extra:
        if k and k not in pool: pool.append(k)
    return pool

def odds_request(url, params, timeout=12):
    pool = _get_odds_keys_pool()
    if not pool:
        single_key = params.get("apiKey", "")
        if not single_key:
            return {"error_code": 401, "message": "Sin Odds API key"}, 401, ""
        pool = [single_key]
    active_idx = st.session_state.get("odds_active_key_idx", 0) % len(pool)
    for attempt in range(len(pool)):
        idx = (active_idx + attempt) % len(pool)
        key = pool[idx]
        p = {**params, "apiKey": key}
        try:
            r = requests.get(url, params=p, timeout=timeout)
            if r.status_code == 200:
                if attempt > 0: st.session_state["odds_active_key_idx"] = idx
                return r.json(), 200, key
            elif r.status_code in (401, 429): continue
            else: return r.json(), r.status_code, key
        except Exception as e:
            log_event("odds_request", e)
            continue
    return {"error_code": 429, "message": "Todas las keys agotadas"}, 429, ""

def fd_get(endpoint, api_key, params=None):
    headers = {"X-Auth-Token": api_key}
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=12)
        if r.status_code == 429:
            return {"error": "Límite requests FB-Data"}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=3600)
def get_upcoming_matches(api_key, comp_code):
    today  = datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
    data   = fd_get(f"competitions/{comp_code}/matches", api_key, {"status": "SCHEDULED", "dateFrom": today, "dateTo": future})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_team_matches(api_key, team_id, last=14):
    data = fd_get(f"teams/{team_id}/matches", api_key, {"status": "FINISHED", "limit": last})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_competition_teams(api_key, comp_code):
    data = fd_get(f"competitions/{comp_code}/teams", api_key)
    return data.get("teams", [])

def get_live_odds(api_key, sport_key, markets="h2h,totals"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": api_key, "bookmakers": MX_BOOKMAKER_KEYS, "markets": markets, "oddsFormat": "decimal"}
    data, status, _ = odds_request(url, params)
    if status == 200 and isinstance(data, list) and len(data) > 0: return data
    params2 = {"apiKey": api_key, "regions": MX_REGIONS, "markets": markets, "oddsFormat": "decimal"}
    data2, status2, _ = odds_request(url, params2)
    return data2 if status2 == 200 else []

# FIX #1: _team_similarity usa rapidfuzz cuando está disponible
def _team_similarity(name_a, name_b):
    """
    Compara dos nombres de equipo con fuzzy matching si rapidfuzz está disponible.
    Limpia prefijos/sufijos comunes antes de comparar.
    Retorna score entre 0.0 y 1.0.
    """
    def clean(n):
        return (n.lower()
                 .replace("fc", "").replace("cf", "").replace("afc", "")
                 .replace("sc", "").replace("ac", "").replace("ss", "")
                 .replace(".", "").replace("-", " ").strip())

    a = clean(name_a)
    b = clean(name_b)

    if not a or not b:
        return 0.0

    # Coincidencia exacta o substring
    if a == b or a in b or b in a:
        return 1.0

    # rapidfuzz para nombres parecidos (ej: "Man City" vs "Manchester City")
    if _RAPIDFUZZ_AVAILABLE and _rapidfuzz_fuzz is not None:
        score = max(
            _rapidfuzz_fuzz.ratio(a, b),
            _rapidfuzz_fuzz.partial_ratio(a, b),
            _rapidfuzz_fuzz.token_sort_ratio(a, b),
        )
        return score / 100.0

    # Fallback sin rapidfuzz: comparación de palabras comunes
    words_a = set(a.split())
    words_b = set(b.split())
    common = words_a & words_b
    if common:
        return len(common) / max(len(words_a), len(words_b))
    return 0.0

def _find_best_game(live_data, home_name, away_name, threshold=0.65):
    """
    Busca el partido en live_data que mejor coincide con home_name y away_name.
    Usa un umbral de similitud (threshold) para evitar falsos positivos.
    Retorna (game, score) o (None, 0.0).
    """
    best_game, best_score = None, 0.0
    for game in (live_data if isinstance(live_data, list) else []):
        gh = game.get("home_team", "")
        ga = game.get("away_team", "")
        # Score combinado: exige que AMBOS equipos tengan similitud aceptable
        sh = _team_similarity(home_name, gh)
        sa = _team_similarity(away_name, ga)
        combined = (sh + sa) / 2.0
        if combined > best_score:
            best_score = combined
            best_game = game
    if best_score >= threshold:
        return best_game, best_score
    return None, 0.0

def _extract_best_prices_and_margins(game):
    """
    Extrae mejores cuotas decimales/americanas y asigna el margen real del bookmaker
    donde se tomó cada mejor precio (evita mezclar márgenes entre casas).
    """
    best_odds = {"Home": -999, "Draw": -999, "Away": -999, "O25": -999, "U25": -999}
    best_decs = {"Home": 1.0,  "Draw": 1.0,  "Away": 1.0,  "O25": 1.0,  "U25": 1.0}
    best_margins = {"Home": 1.05, "Draw": 1.05, "Away": 1.05, "O25": 1.05, "U25": 1.05}

    for bm in game.get("bookmakers", []):
        bm_h2h = {}
        bm_o25 = None
        bm_u25 = None

        for mkt in bm.get("markets", []):
            if mkt.get("key") == "h2h":
                for oc in mkt.get("outcomes", []):
                    dec_val = float(oc["price"])
                    name = oc.get("name")
                    if name == game.get("home_team"):
                        bm_h2h["Home"] = dec_val
                    elif name == "Draw":
                        bm_h2h["Draw"] = dec_val
                    elif name == game.get("away_team"):
                        bm_h2h["Away"] = dec_val
            elif mkt.get("key") == "totals":
                for oc in mkt.get("outcomes", []):
                    if oc.get("point") != 2.5:
                        continue
                    dec_val = float(oc["price"])
                    if oc.get("name") == "Over":
                        bm_o25 = dec_val if bm_o25 is None else max(bm_o25, dec_val)
                    elif oc.get("name") == "Under":
                        bm_u25 = dec_val if bm_u25 is None else max(bm_u25, dec_val)

        if len(bm_h2h) == 3:
            margin_h2h_bm = calc_market_margin([bm_h2h["Home"], bm_h2h["Draw"], bm_h2h["Away"]])
            for key in ("Home", "Draw", "Away"):
                am_val = normalize_to_american(bm_h2h[key])
                if am_val > best_odds[key]:
                    best_odds[key] = am_val
                    best_decs[key] = bm_h2h[key]
                    best_margins[key] = margin_h2h_bm

        if bm_o25 is not None and bm_u25 is not None:
            margin_totals_bm = calc_market_margin([bm_o25, bm_u25])
            for key, dec_val in (("O25", bm_o25), ("U25", bm_u25)):
                am_val = normalize_to_american(dec_val)
                if am_val > best_odds[key]:
                    best_odds[key] = am_val
                    best_decs[key] = dec_val
                    best_margins[key] = margin_totals_bm

    return best_odds, best_decs, best_margins

# ─────────────────────────────────────────────
#  APIS EXTERNAS (CLIMA, CLAUDE, TELEGRAM)
# ─────────────────────────────────────────────

# FIX #6: clima real con Open-Meteo (gratis, sin API key)
STADIUM_COORDS = {
    # Premier League
    "Arsenal": (51.5549, -0.1084), "Chelsea": (51.4816, -0.1910),
    "Manchester City": (53.4831, -2.2004), "Manchester United": (53.4631, -2.2913),
    "Liverpool": (53.4308, -2.9608), "Tottenham": (51.6042, -0.0665),
    "Newcastle": (54.9756, -1.6217), "Aston Villa": (52.5090, -1.8847),
    # La Liga
    "Real Madrid": (40.4530, -3.6883), "Barcelona": (41.3809, 2.1228),
    "Atletico Madrid": (40.4361, -3.5994), "Athletic Club": (43.2642, -2.9494),
    "Sevilla": (37.3840, -5.9706), "Valencia": (39.4748, -0.3583),
    # Bundesliga
    "Bayern Munich": (48.2188, 11.6248), "Borussia Dortmund": (51.4926, 7.4519),
    "RB Leipzig": (51.3458, 12.3484), "Bayer Leverkusen": (51.0380, 7.0023),
    # Serie A
    "Juventus": (45.1096, 7.6413), "Inter Milan": (45.4781, 9.1240),
    "AC Milan": (45.4781, 9.1240), "Napoli": (40.8279, 14.1931),
    "Roma": (41.9340, 12.4547), "Lazio": (41.9340, 12.4547),
    # Ligue 1
    "Paris Saint-Germain": (48.8414, 2.2530), "Marseille": (43.2697, 5.3962),
    "Lyon": (45.7653, 4.9822), "Monaco": (43.7275, 7.4154),
}

@st.cache_data(ttl=1800)
def get_match_weather(team_name, match_date_str):
    """
    Obtiene clima real de Open-Meteo para el estadio del equipo local.
    Fallback a valores neutros si no hay coordenadas o la API falla.
    """
    # Buscar coordenadas del estadio
    coords = None
    for key, val in STADIUM_COORDS.items():
        if _team_similarity(team_name, key) >= 0.7:
            coords = val
            break

    if coords is None:
        # Coordenadas genéricas (centro de Europa) si no se encuentra el estadio
        coords = (48.8566, 2.3522)

    lat, lon = coords
    try:
        # Parsear fecha del partido
        match_dt = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
        date_str = match_dt.strftime("%Y-%m-%d")

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,precipitation_sum,windspeed_10m_max,weathercode"
            f"&start_date={date_str}&end_date={date_str}&timezone=auto"
        )
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            d = r.json().get("daily", {})
            temp = (d.get("temperature_2m_max") or [18.0])[0]
            precip = (d.get("precipitation_sum") or [0.0])[0]
            wind = (d.get("windspeed_10m_max") or [10.0])[0]
            wcode = (d.get("weathercode") or [0])[0]
            # Interpretar WMO weather code
            if wcode == 0:         cond = "☀️ Despejado"
            elif wcode <= 3:       cond = "🌤️ Parcialmente nublado"
            elif wcode <= 49:      cond = "🌫️ Niebla"
            elif wcode <= 67:      cond = "🌧️ Lluvia"
            elif wcode <= 77:      cond = "❄️ Nieve"
            elif wcode <= 82:      cond = "🌦️ Chubascos"
            elif wcode <= 99:      cond = "⛈️ Tormenta"
            else:                  cond = "🌥️ Nublado"
            return {"temp_c": round(temp, 1), "precip_mm": round(precip, 1),
                    "wind_kmh": round(wind, 1), "condition": cond, "wcode": wcode}
    except Exception as e:
        log_event("get_match_weather", e)

    # Fallback neutro
    return {"temp_c": 18.0, "precip_mm": 0.0, "wind_kmh": 12.0, "condition": "☀️ Despejado", "wcode": 0}

def calc_weather_factor(weather):
    if not weather: return 1.0, "Sin datos"
    if weather["precip_mm"] >= 5.0: return 0.88, "Lluvia intensa"
    if weather["wind_kmh"] >= 35:   return 0.95, "Viento fuerte"
    return 1.0, "Ideal"

# FIX #7: modelo de Claude actualizado a claude-haiku-4-5
def generate_ai_analysis(home_team, away_team, data, pred, anthropic_key):
    if not anthropic_key:
        return "Se requiere API Key de Anthropic para generar el análisis."
    prompt = (
        f"Analiza el partido {home_team} vs {away_team} desde una perspectiva de apuestas deportivas. "
        f"El modelo cuantitativo asigna: {home_team} {pred['home_win_pct']}% | "
        f"Empate {pred['draw_pct']}% | {away_team} {pred['away_win_pct']}%. "
        f"xG local: {pred['xg_h']} | xG visitante: {pred['xg_a']}. "
        f"Explica brevemente (máx. 150 palabras) qué factores justifican estas probabilidades "
        f"y si hay algún riesgo no capturado por el modelo estadístico."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",  # FIX: modelo actualizado
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return r.json().get("content", [{}])[0].get("text", "Error al obtener respuesta.")
    except Exception as e:
        log_event("generate_ai_analysis", e)
        return str(e)

def format_bet_alert(partido, liga, mercado, prob_modelo, momio_am, div_dyn, kelly_pct, stake):
    momio_str = f"+{int(momio_am)}" if momio_am > 0 else str(int(momio_am))
    icon = "🟢" if float(div_dyn) >= 10 else "🟡"
    return (
        f"{icon} <b>VALOR V8 DETECTADO — {liga}</b>\n"
        f"⚽ {partido}\n"
        f"🎯 {mercado}\n"
        f"📊 Modelo: {prob_modelo:.1f}% | Momio: {momio_str}\n"
        f"🔥 Divergencia Dinámica: <b>+{div_dyn:.1f}%</b>\n"
        f"💰 Kelly(12.5%): {kelly_pct}% | Stake Sugerido: <b>${stake:.2f}</b>"
    )

def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id: return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
        )
        return r.status_code == 200
    except Exception as e:
        log_event("send_telegram_alert", e)
        return False

# ─────────────────────────────────────────────
#  MODELO POISSON (PREDICCIÓN)
# ─────────────────────────────────────────────
def poisson_prob(lam, k):
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * lam**k) / math.factorial(min(k, 15))

def dixon_coles_tau(i, j, xg_h, xg_a, rho=0.18):
    if i == 0 and j == 0:   return 1 - xg_h * xg_a * rho
    elif i == 1 and j == 0: return 1 + xg_a * rho
    elif i == 0 and j == 1: return 1 + xg_h * rho
    elif i == 1 and j == 1: return 1 - rho
    return 1.0

def build_matrix_dc(xg_h, xg_a, max_goals=9):
    M = [
        [poisson_prob(xg_h, i) * poisson_prob(xg_a, j) * dixon_coles_tau(i, j, xg_h, xg_a)
         for j in range(max_goals)]
        for i in range(max_goals)
    ]
    total = sum(M[i][j] for i in range(max_goals) for j in range(max_goals))
    return [[M[i][j] / total for j in range(max_goals)] for i in range(max_goals)] if total > 0 else M

# FIX ROBUSTEZ #1/#2: xG/proxy + decaimiento exponencial + ELO dinámico con cache
def calc_all_predictions(matches_home, matches_away, home_id, away_id, league_avg_goals=2.75, league_code="GEN"):
    all_matches = list(matches_home) + list(matches_away)

    dynamic_ratings, rating_avg = build_dynamic_elo_ratings(all_matches)
    cached_ratings = load_team_ratings_cache(league_code)
    merged_ratings = {**cached_ratings, **dynamic_ratings}
    if merged_ratings:
        rating_avg = float(np.mean(list(merged_ratings.values())))
    else:
        rating_avg = 1500.0

    save_team_ratings_cache(league_code, dynamic_ratings)

    home_profile = build_team_goal_profile(
        matches=matches_home,
        team_id=home_id,
        league_avg_goals=league_avg_goals,
        opponent_ratings=merged_ratings,
        league_rating_avg=rating_avg,
    )
    away_profile = build_team_goal_profile(
        matches=matches_away,
        team_id=away_id,
        league_avg_goals=league_avg_goals,
        opponent_ratings=merged_ratings,
        league_rating_avg=rating_avg,
    )

    strength_home_mult, strength_away_mult = matchup_strength_multipliers(
        home_team_id=home_id,
        away_team_id=away_id,
        ratings=merged_ratings,
        league_avg=rating_avg,
    )

    projected = project_match_xg(
        home_profile=home_profile,
        away_profile=away_profile,
        league_avg_goals=league_avg_goals,
        strength_home_mult=strength_home_mult,
        strength_away_mult=strength_away_mult,
    )
    xg_h, xg_a = projected["xg_h"], projected["xg_a"]

    M = build_matrix_dc(xg_h, xg_a, 9)
    hw   = sum(M[i][j] for i in range(9) for j in range(9) if i > j) * 100
    dr   = sum(M[i][j] for i in range(9) for j in range(9) if i == j) * 100
    aw   = sum(M[i][j] for i in range(9) for j in range(9) if i < j) * 100
    o25  = sum(M[i][j] for i in range(9) for j in range(9) if i + j > 2) * 100
    u25  = 100 - o25
    btts = sum(M[i][j] for i in range(9) for j in range(9) if i > 0 and j > 0) * 100

    return {
        "home_win_pct": round(hw, 1), "draw_pct": round(dr, 1), "away_win_pct": round(aw, 1),
        "over_25": round(o25, 1), "under_25": round(u25, 1),
        "btts_yes": round(btts, 1), "btts_no": round(100 - btts, 1),
        "xg_h": round(xg_h, 2), "xg_a": round(xg_a, 2),
        "strength_home_mult": round(strength_home_mult, 3),
        "strength_away_mult": round(strength_away_mult, 3),
    }

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("# ⚽ Betting Analytics V8")

    selected_league_name = st.selectbox("Liga a analizar", list(LEAGUES.keys()))
    league_cfg  = LEAGUES[selected_league_name]
    COMP_CODE   = league_cfg["code"]
    ODDS_SPORT  = league_cfg["odds_key"]
    V8_PARAMS   = league_cfg["v8_params"]
    LEAGUE_AVG  = league_cfg["avg_goals"]  # FIX #5: promedio real de goles

    st.markdown("### 🔑 API Keys")
    football_api_key = st.text_input("football-data.org Token", type="password")

    _odds_manual = st.text_input("The Odds API Key (Principal)", type="password")
    if _odds_manual: st.session_state["odds_keys_pool"] = [_odds_manual]

    st.markdown("### 💰 Bankroll (V8)")
    bankroll      = st.number_input("Bankroll Actual ($)", min_value=100, value=1000, step=100)
    max_stake_cap = st.number_input("Límite Máximo por Apuesta ($)", min_value=10.0, value=50.0, step=5.0, help="Techo duro para evitar ruina.")
    daily_exposure_pct = st.slider("Exposición máxima diaria (% bankroll)", min_value=2, max_value=25, value=8)
    weekly_drawdown_stop_pct = st.slider("Stop de drawdown semanal (%)", min_value=3, max_value=30, value=10)
    max_bets_per_day = st.slider("Máx apuestas por día", min_value=1, max_value=25, value=8)
    confidence_max_uncertainty = st.slider("Umbral máximo de incertidumbre", min_value=0.20, max_value=1.0, value=0.82, step=0.01, help="Menor valor = más selectivo.")
    top_edge_pct = st.slider("Tomar sólo top % de edges", min_value=5, max_value=100, value=20, step=5)

    st.markdown("### 🧪 Ejecución Realista")
    sim_slippage_pct = st.slider("Slippage simulado (%)", min_value=0.0, max_value=0.05, value=0.01, step=0.005)
    sim_delay_min = st.slider("Delay simulado (min)", min_value=0, max_value=30, value=2, step=1)
    sim_reject_rate = st.slider("Probabilidad de rechazo (%)", min_value=0, max_value=40, value=5, step=1) / 100.0
    max_stake_market = st.number_input("Máx stake por mercado ($)", min_value=1.0, value=40.0, step=1.0)

    st.markdown("### ⚙️ Umbrales V8 de Divergencia")
    st.caption(f"Optimizado para {COMP_CODE} (avg {LEAGUE_AVG} goles/partido):")
    colA, colB = st.columns(2)
    div_min_ovr = colA.number_input("Min Div (%)", value=V8_PARAMS["div_min"])
    div_max_ovr = colB.number_input("Max Div (%)", value=V8_PARAMS["div_max"])
    use_dynamic_div_thresholds = st.checkbox("Aprender umbrales desde histórico (percentiles)", value=True)
    div_min_eff, div_max_eff, div_samples_n = learn_divergence_thresholds(
        COMP_CODE,
        fallback_min=div_min_ovr,
        fallback_max=div_max_ovr,
        min_samples=120,
    ) if use_dynamic_div_thresholds else (float(div_min_ovr), float(div_max_ovr), 0)
    if use_dynamic_div_thresholds:
        st.caption(
            f"Umbrales dinámicos activos: {div_min_eff:.2f}% a {div_max_eff:.2f}% "
            f"(muestras EV+ usadas: {div_samples_n})."
        )

    st.markdown("### 🤖 Extras")
    anthropic_key   = st.text_input("Claude AI Key (Opcional)", type="password")
    telegram_token  = st.text_input("Telegram Bot Token", type="password")
    telegram_chat_id = st.text_input("Telegram Chat ID", type="password")
    show_logs = st.checkbox("Mostrar logs técnicos", value=False)
    auto_calibrate_probs = st.checkbox("Auto-calibrar probabilidades (histórico)", value=True)

# ─────────────────────────────────────────────
#  TABS DE LA APLICACIÓN
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🎯 1. Análisis", "📡 2. Momios & V8 Eval", "🧮 3. Calculadora", "📊 4. Paper Trading", "🔍 5. Scanner V8",
    "📈 6. CLV Audit",
])

# ══════════════════════════════════════════════
#  TAB 1 — ANÁLISIS
# ══════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🎯 ANÁLISIS — GENERAR BASELINE</div>', unsafe_allow_html=True)

    # FIX #8: st.stop() reemplazado por st.error + flag para no romper otros tabs
    if not football_api_key:
        st.warning("👈 Ingresa tu token de football-data.org en el sidebar.")
    else:
        matches = get_upcoming_matches(football_api_key, COMP_CODE)
        if not matches:
            st.error("No se encontraron partidos próximos. Verifica tu token.")
        else:
            opts = {
                f"J{m.get('matchday','?')} · {m['utcDate'][:10]} — {m['homeTeam']['name']} vs {m['awayTeam']['name']}": m
                for m in matches
            }
            sel = opts[st.selectbox("Selecciona un Partido", list(opts.keys()))]
            match_id, home_team_id, away_team_id = sel["id"], sel["homeTeam"]["id"], sel["awayTeam"]["id"]
            home_team_name, away_team_name = sel["homeTeam"]["name"], sel["awayTeam"]["name"]

            if st.button("🔮 ANALIZAR PARTIDO", type="primary", use_container_width=True):
                with st.spinner("Descargando historial y calculando Poisson..."):
                    h_matches = get_team_matches(football_api_key, home_team_id)
                    a_matches = get_team_matches(football_api_key, away_team_id)

                    # FIX #5: pasar avg_goals de la liga al modelo
                    pred = calc_all_predictions(
                        h_matches, a_matches, home_team_id, away_team_id, LEAGUE_AVG, COMP_CODE
                    )
                    wx   = get_match_weather(home_team_name, sel["utcDate"])  # FIX #6: clima real

                    st.session_state.update({
                        "pred": pred, "home_team": home_team_name, "away_team": away_team_name,
                        "odds_sport_key": ODDS_SPORT, "match_date": sel["utcDate"], "wx": wx,
                        "current_match_id": int(sel["id"]),
                    })
                st.success("✅ Baseline generado correctamente.")

    if "pred" in st.session_state:
        pred, ht, at, wx = (
            st.session_state["pred"], st.session_state["home_team"],
            st.session_state["away_team"], st.session_state["wx"],
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"xG {ht}", pred["xg_h"])
        c2.metric(f"xG {at}", pred["xg_a"])
        c3.metric("Clima", wx["condition"])
        c4.metric("Temp", f"{wx['temp_c']}°C")

        # Mostrar factor climático si aplica
        wx_factor, wx_desc = calc_weather_factor(wx)
        if wx_factor < 1.0:
            st.info(f"⚠️ Clima: {wx_desc} — factor de penalización {wx_factor:.2f}x sobre el modelo.")

        st.markdown("#### ⚽ Predicciones del Modelo (Antes de evaluar al Mercado)")
        col1, col2, col3 = st.columns(3)
        col1.markdown(f'<div class="metric-card"><p>🏠 Local</p><h2 style="color:#00ff88">{pred["home_win_pct"]}%</h2></div>', unsafe_allow_html=True)
        col2.markdown(f'<div class="metric-card"><p>🤝 Empate</p><h2 style="color:#00ff88">{pred["draw_pct"]}%</h2></div>', unsafe_allow_html=True)
        col3.markdown(f'<div class="metric-card"><p>✈️ Visita</p><h2 style="color:#00ff88">{pred["away_win_pct"]}%</h2></div>', unsafe_allow_html=True)

        if anthropic_key:
            if st.button("✨ Generar Análisis con Claude AI"):
                with st.spinner("Analizando..."):
                    st.session_state["ai_text"] = generate_ai_analysis(ht, at, None, pred, anthropic_key)
            if "ai_text" in st.session_state:
                st.info(st.session_state["ai_text"])

# ══════════════════════════════════════════════
#  TAB 2 — EVALUADOR V8 (Divergencia Dinámica y Vig-Free)
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 EVALUADOR V8 — MODELO VS MERCADO</div>', unsafe_allow_html=True)

    if "pred" not in st.session_state:
        st.info("Primero analiza un partido en el Tab 1.")
    else:
        ht, at = st.session_state["home_team"], st.session_state["away_team"]
        pred   = st.session_state["pred"]
        pred_eval = pred.copy()
        closed_hist = [t for t in load_trades_db() if t["Resultado"] != "Pendiente"]
        clv_allow_segments, clv_segment_table = build_clv_gate(closed_hist, min_samples=12)
        selected_calibrator = {"method": "none"}
        if auto_calibrate_probs:
            selected_calibrator = build_best_calibrator(closed_hist, min_train_size=40)
            if selected_calibrator.get("method") != "none":
                pred_eval["home_win_pct"] = round(apply_selected_calibration(pred["home_win_pct"] / 100.0, selected_calibrator) * 100.0, 1)
                pred_eval["draw_pct"] = round(apply_selected_calibration(pred["draw_pct"] / 100.0, selected_calibrator) * 100.0, 1)
                pred_eval["away_win_pct"] = round(apply_selected_calibration(pred["away_win_pct"] / 100.0, selected_calibrator) * 100.0, 1)
                pred_eval["over_25"] = round(apply_selected_calibration(pred["over_25"] / 100.0, selected_calibrator) * 100.0, 1)

        st.markdown(f"#### 🏟️ Buscando momios para: **{ht} vs {at}**")

        if st.button("🔄 Descargar Momios en Vivo"):
            with st.spinner("Conectando con The Odds API..."):
                live_data = get_live_odds(
                    _get_odds_keys_pool()[0] if _get_odds_keys_pool() else "",
                    st.session_state["odds_sport_key"],
                )
                game, score = _find_best_game(live_data, ht, at)

                if game:
                    st.success(f"✅ Momios encontrados en {len(game['bookmakers'])} casas (similitud: {score:.0%}).")
                    best_odds, best_decs, best_margins = _extract_best_prices_and_margins(game)

                    st.session_state["current_best_odds"] = best_odds
                    st.session_state["current_best_decs"]  = best_decs
                    st.session_state["current_best_margins"] = best_margins

                    h2h_margins = [best_margins[k] for k in ("Home", "Draw", "Away") if best_odds[k] != -999]
                    totals_margins = [best_margins[k] for k in ("O25", "U25") if best_odds[k] != -999]
                    h2h_margin_avg = float(np.mean(h2h_margins)) if h2h_margins else 1.05
                    totals_margin_avg = float(np.mean(totals_margins)) if totals_margins else 1.05
                    st.caption(f"Margen H2H (origen cuota): {(h2h_margin_avg-1)*100:.1f}% | Margen Totales (origen cuota): {(totals_margin_avg-1)*100:.1f}%")
                else:
                    st.error("No se encontraron momios para este partido. Verifica que el partido esté en el calendario de The Odds API.")

        if "current_best_odds" in st.session_state:
            b_odds        = st.session_state["current_best_odds"]
            b_decs        = st.session_state.get("current_best_decs", {})
            b_margins     = st.session_state.get("current_best_margins", {})

            st.markdown("---")
            st.markdown("#### 📉 Ajuste por Line Movement (CLV)")
            st.caption("Si el mercado se mueve en tu contra, el sistema penaliza tu Stake.")
            clv_mod = st.radio(
                "Simular Line Movement para la apuesta seleccionada:",
                ["Sin movimiento", "A mi favor (El momio bajó)", "En mi contra (El momio subió)"],
                horizontal=True,
            )
            lm_penalty = 1.0
            if clv_mod == "A mi favor (El momio bajó)":    lm_penalty = 1.10
            elif clv_mod == "En mi contra (El momio subió)": lm_penalty = 0.25

            st.markdown("---")
            st.markdown("#### 🎯 Resultados del Filtro V8")
            max_daily_exposure = bankroll * (daily_exposure_pct / 100.0)
            used_exposure = 0.0
            max_one_pick_match = st.checkbox("Máximo 1 pick por partido (anti-correlación fuerte)", value=True, key="tab2_max1")
            avg_clv_hist = float(np.mean([t["CLV %"] for t in closed_hist if t.get("CLV %") is not None])) if closed_hist else 0.0
            rel_df_hist = build_reliability_table(closed_hist, n_bins=10) if closed_hist else pd.DataFrame([])
            ece_hist = calc_ece(rel_df_hist) if not rel_df_hist.empty else 0.0
            eq_hist = np.cumsum([t.get("PnL", 0.0) for t in sorted(closed_hist, key=lambda x: x["Fecha"])]) if closed_hist else np.array([0.0])
            peaks_hist = np.maximum.accumulate(eq_hist) if len(eq_hist) else np.array([0.0])
            dd_hist = (peaks_hist - eq_hist) if len(eq_hist) else np.array([0.0])
            dd_hist_pct = (float(np.max(dd_hist)) / bankroll * 100.0) if bankroll > 0 else 0.0
            overfit_penalty, overfit_meta = compute_overfit_penalty(closed_hist)
            perf_mult = kelly_performance_multiplier(avg_clv_hist, ece_hist, dd_hist_pct, overfit_penalty)

            candidates = []
            match_key_tab2 = f"{ht} vs {at}"
            market_configs = [
                (f"Gana {ht}", pred_eval["home_win_pct"], b_odds["Home"], b_decs.get("Home", 1.9), b_margins.get("Home", 1.05), "resultado"),
                ("Empate",     pred_eval["draw_pct"],     b_odds["Draw"], b_decs.get("Draw", 3.5), b_margins.get("Draw", 1.05), "resultado"),
                (f"Gana {at}", pred_eval["away_win_pct"], b_odds["Away"], b_decs.get("Away", 2.5), b_margins.get("Away", 1.05), "resultado"),
                ("Over 2.5",   pred_eval["over_25"],      b_odds["O25"],  b_decs.get("O25", 1.9),  b_margins.get("O25", 1.05), "goles"),
            ]

            for mkt, my_p, am_odd, dec, margin, market_group in market_configs:
                if am_odd == -999:
                    continue
                # FIX #3: usar margen real del mercado
                div_abs, div_dyn, vf_prob, ev = calc_v8_metrics(my_p, dec, margin)
                in_range = (div_min_eff <= div_dyn <= div_max_eff)
                uncertainty = confidence_uncertainty(my_p)
                odd_bucket = pd.cut(pd.Series([dec]), bins=[1.0, 1.6, 2.0, 2.5, 5.0, 50.0], labels=["1.01-1.60", "1.61-2.00", "2.01-2.50", "2.51-5.00", "5.01+"]).astype(str).iloc[0]
                prob_bucket = pd.cut(pd.Series([my_p / 100.0]), bins=[0.0, 0.40, 0.50, 0.60, 1.0], labels=["0-40%", "40-50%", "50-60%", "60-100%"]).astype(str).iloc[0]
                pass_clv_gate = (not clv_allow_segments) or ((COMP_CODE, odd_bucket, prob_bucket) in clv_allow_segments)
                candidates.append({
                    "match_key": match_key_tab2,
                    "market_group": market_group,
                    "Mercado": mkt,
                    "Momio": f"{am_odd:+d}" if am_odd > 0 else str(am_odd),
                    "Prob Modelo": f"{my_p}%",
                    "Mkt (Vig-Free)": f"{vf_prob}%",
                    "Margen Casa": f"{(margin-1)*100:.1f}%",
                    "my_p": my_p,
                    "dec": dec,
                    "div_dyn": div_dyn,
                    "ev": ev,
                    "in_range": in_range,
                    "uncertainty": uncertainty,
                    "pass_clv_gate": pass_clv_gate,
                })
                save_edge_sample(COMP_CODE, match_key_tab2, mkt, market_group, div_dyn, ev)

            ranked = sorted(candidates, key=lambda x: x["div_dyn"], reverse=True)
            top_n = max(1, int(math.ceil(len(ranked) * (top_edge_pct / 100.0))))
            top_keys = {(x["match_key"], x["Mercado"]) for x in ranked[:top_n]}
            selected = filter_correlated_candidates(
                [
                    c for c in candidates
                    if c["in_range"] and c["ev"] > 0
                    and c["uncertainty"] <= confidence_max_uncertainty
                    and c["pass_clv_gate"]
                    and (c["match_key"], c["Mercado"]) in top_keys
                ],
                max_per_match=(1 if max_one_pick_match else 2),
            )
            selected_keys = {(c["match_key"], c["Mercado"]) for c in selected}
            eval_rows = []
            bets_count_tab2 = 0

            for c in sorted(candidates, key=lambda x: (x["in_range"], x["ev"]), reverse=True):
                if c["div_dyn"] < div_min_eff:
                    estado = "➖ Edge Débil"
                    k, stake, r = 0, 0, "Ignorar"
                elif c["div_dyn"] > div_max_eff:
                    estado = "🛑 Sobreconfianza"
                    k, stake, r = 0, 0, "Ignorar"
                elif c["uncertainty"] > confidence_max_uncertainty:
                    estado = "🧪 Alta Incertidumbre"
                    k, stake, r = 0, 0, "Filtrado"
                elif not c["pass_clv_gate"]:
                    estado = "📉 Segmento CLV-"
                    k, stake, r = 0, 0, "Filtrado"
                elif (c["match_key"], c["Mercado"]) not in top_keys:
                    estado = "🎯 Fuera Top Edges"
                    k, stake, r = 0, 0, "Filtrado"
                elif (c["match_key"], c["Mercado"]) not in selected_keys:
                    estado = "🧩 Correlacionado"
                    k, stake, r = 0, 0, "Filtrado"
                else:
                    if bets_count_tab2 >= max_bets_per_day:
                        estado = "🛑 Límite diario"
                        k, stake, r = 0, 0, "Cap diario"
                        eval_rows.append({
                            "Mercado": c["Mercado"],
                            "Momio": c["Momio"],
                            "Prob Modelo": c["Prob Modelo"],
                            "Mkt (Vig-Free)": c["Mkt (Vig-Free)"],
                            "Margen Casa": c["Margen Casa"],
                            "Div. Dinámica": f"{c['div_dyn']:+.1f}%",
                            "Uncertainty": f"{c['uncertainty']:.2f}",
                            "Estado": estado,
                            "Kelly (12.5%)": f"{k}%",
                            "Stake": f"${stake:.2f}",
                            "Riesgo": r,
                        })
                        continue
                    estado = "✅ Confirmado"
                    k, stake, r = smart_kelly_v8(c["my_p"], c["dec"], max_stake_cap, bankroll, lm_penalty * perf_mult)
                    sim_dec, sim_stake, sim_rejected = apply_execution_frictions(
                        c["dec"], sim_slippage_pct, sim_reject_rate, max_stake_market=max_stake_market, desired_stake=stake
                    )
                    stake = sim_stake
                    if sim_rejected:
                        r = "🚫 Rechazo simulado"
                    if stake > 0 and sim_dec != c["dec"]:
                        r = f"{r} | slip {sim_slippage_pct*100:.1f}%"
                    remaining = max(0.0, max_daily_exposure - used_exposure)
                    if stake > remaining:
                        stake = remaining
                        k = round((stake / bankroll) * 100, 2) if bankroll > 0 else 0.0
                        r = "🛑 Cap Exposición Diaria"
                    used_exposure += stake
                    if stake > 0:
                        bets_count_tab2 += 1
                        if _BET_AUDIT_AVAILABLE and not sim_rejected:
                            mid = str(st.session_state.get("current_match_id") or "").strip()
                            if not mid:
                                mid = f"syn_{COMP_CODE}_{match_key_tab2}".replace(" ", "_")[:120]
                            bk = _book_margin_key_for_mercado(c["Mercado"], ht, at)
                            margin_audit = float(b_margins.get(bk, 1.05))
                            implied_audit = float(get_vig_free_prob(float(sim_dec), margin_audit))
                            audit_log_bet({
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "match_id": mid,
                                "league": COMP_CODE,
                                "market": audit_market_from_group(c["market_group"]),
                                "selection": audit_selection_from_labels(c["Mercado"], ht, at),
                                "fixture_name": match_key_tab2,
                                "model_probability": float(c["my_p"]) / 100.0,
                                "implied_probability_market": implied_audit,
                                "edge": float(c["ev"]),
                                "entry_odds": float(sim_dec),
                                "closing_odds": None,
                                "stake": float(stake),
                                "result": "pending",
                            })

                eval_rows.append({
                    "Mercado": c["Mercado"],
                    "Momio": c["Momio"],
                    "Prob Modelo": c["Prob Modelo"],
                    "Mkt (Vig-Free)": c["Mkt (Vig-Free)"],
                    "Margen Casa": c["Margen Casa"],
                    "Div. Dinámica": f"{c['div_dyn']:+.1f}%",
                    "Uncertainty": f"{c['uncertainty']:.2f}",
                    "Estado": estado,
                    "Kelly (12.5%)": f"{k}%",
                    "Stake": f"${stake:.2f}",
                    "Riesgo": r,
                })

            df_eval = pd.DataFrame(eval_rows)
            st.dataframe(df_eval, use_container_width=True)
            st.caption(
                f"Exposición sugerida total: ${used_exposure:.2f} / ${max_daily_exposure:.2f} "
                f"({daily_exposure_pct}% bankroll) | Umbral efectivo: {div_min_eff:.2f}%–{div_max_eff:.2f}%"
            )
            st.caption(
                f"Kelly adaptativo: x{perf_mult:.2f} | CLV hist {avg_clv_hist:+.2f}% | "
                f"ECE {ece_hist:.3f} | DD {dd_hist_pct:.2f}% | Overfit penalty {overfit_penalty:.2f}"
            )
            if overfit_meta:
                st.caption(
                    f"Train/Val/OOS ROI: {overfit_meta['ROI Train %']:+.2f}% / "
                    f"{overfit_meta['ROI Val %']:+.2f}% / {overfit_meta['ROI OOS %']:+.2f}%"
                )
            if not clv_segment_table.empty:
                st.markdown("##### Segmentos CLV (liga/odds/prob)")
                st.dataframe(clv_segment_table.head(12), use_container_width=True)
            if auto_calibrate_probs:
                meta = selected_calibrator.get("meta", {})
                st.caption(
                    "Calibración automática: "
                    f"{selected_calibrator.get('method','none')} | "
                    f"Brier val {meta.get('brier_before', 'n/a')} -> {meta.get('brier_after', 'n/a')} | "
                    f"LogLoss val {meta.get('logloss_before', 'n/a')} -> {meta.get('logloss_after', 'n/a')}"
                )

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA V8
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA MANUAL V8</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    calc_am   = col1.number_input("Momio (Americano)", value=120)
    calc_my_p = col2.number_input("Probabilidad Modelo (%)", value=50.0)
    calc_lm   = col3.selectbox("Line Movement", ["Normal (1.0x)", "A mi favor (1.1x)", "En mi contra Fuerte (0.25x)", "En mi contra Ligero (0.60x)"])

    lm_dict = {
        "Normal (1.0x)": 1.0, "A mi favor (1.1x)": 1.1,
        "En mi contra Fuerte (0.25x)": 0.25, "En mi contra Ligero (0.60x)": 0.6,
    }

    if st.button("Calcular Inversión", type="primary"):
        dec_odd = american_to_decimal(calc_am)
        if dec_odd <= 1.0:
            st.error("Momio inválido. Ingresa un valor americano válido (ej: +120, -110).")
        else:
            div_abs, div_dyn, vf_prob, ev = calc_v8_metrics(calc_my_p, dec_odd)
            k, stake, riesgo = smart_kelly_v8(calc_my_p, dec_odd, max_stake_cap, bankroll, lm_dict[calc_lm])
            daily_cap = bankroll * (daily_exposure_pct / 100.0)
            if stake > daily_cap:
                stake = daily_cap
                k = round((stake / bankroll) * 100, 2) if bankroll > 0 else 0.0
                riesgo = "🛑 Cap Exposición Diaria"

            color = "#00ff88" if div_min_eff <= div_dyn <= div_max_eff else "#ff4466"
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid {color}">
                <h3>Métricas V8</h3>
                <p><b>Mercado Real (Sin Vig):</b> {vf_prob}%</p>
                <p><b>EV Vig-Free:</b> {ev:+.4f}</p>
                <p><b>Divergencia Dinámica:</b> <span style="color:{color}">{div_dyn:+.2f}%</span>
                   &nbsp; (Rango óptimo: {div_min_eff}% a {div_max_eff}%)</p>
                <hr>
                <h2>Stake Sugerido: ${stake:.2f} <span style="font-size:0.5em; color:#888">({riesgo})</span></h2>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════
#  TAB 4 — PAPER TRADING (BRIER SCORE)
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📊 PAPER TRADING (Brier / PnL / ROI / CLV)</div>', unsafe_allow_html=True)
    if _get_odds_keys_pool():
        c_sync1, c_sync2 = st.columns([1, 2])
        if c_sync1.button("🔄 Actualizar Closing Odds (pendientes)"):
            with st.spinner("Consultando mercados para actualizar CLV..."):
                sync_stats = refresh_pending_closing_odds()
            st.success(
                f"Closing actualizado: {sync_stats['updated']} | "
                f"omitidas: {sync_stats['skipped']} | errores: {sync_stats['errors']}"
            )
            st.rerun()
        c_sync2.caption("Usa este botón al cierre de mercado para registrar CLV real automáticamente.")
    else:
        st.caption("Para actualizar closing odds automáticamente, agrega tu The Odds API Key en el sidebar.")
    trades = load_trades_db()
    cerradas = [t for t in trades if t["Resultado"] != "Pendiente"]

    if cerradas:
        brier_sum = sum((t["Prob Modelo"] - (1.0 if t["Resultado"] == "Ganada" else 0.0)) ** 2 for t in cerradas)
        brier_score = brier_sum / len(cerradas)
        b_color = "#00ff88" if brier_score < 0.24 else "#ff4466"
        ganadas = sum(1 for t in cerradas if t["Resultado"] == "Ganada")
        win_rate = ganadas / len(cerradas) * 100

        total_pnl = sum(t.get("PnL", 0.0) for t in cerradas)
        total_staked = sum(max(0.0, t.get("Stake", 0.0)) for t in cerradas)
        roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0

        eq = np.cumsum([t.get("PnL", 0.0) for t in sorted(cerradas, key=lambda x: x["Fecha"])])
        peaks = np.maximum.accumulate(eq) if len(eq) else np.array([0.0])
        dd = (peaks - eq) if len(eq) else np.array([0.0])
        max_drawdown_abs = float(np.max(dd)) if len(dd) else 0.0
        max_drawdown_pct = (max_drawdown_abs / bankroll * 100.0) if bankroll > 0 else 0.0

        clv_vals = [t["CLV %"] for t in cerradas if t.get("CLV %") is not None]
        avg_clv = float(np.mean(clv_vals)) if clv_vals else 0.0
        pos_clv_pct = (sum(1 for x in clv_vals if x > 0) / len(clv_vals) * 100.0) if clv_vals else 0.0

        col_b1, col_b2, col_b3, col_b4 = st.columns(4)
        col_b1.metric("Brier Score", f"{brier_score:.4f}")
        col_b2.metric("Win Rate", f"{win_rate:.1f}%")
        col_b3.metric("ROI", f"{roi:+.2f}%")
        col_b4.metric("PnL", f"${total_pnl:+.2f}")
        st.caption(
            f"CLV promedio: {avg_clv:+.2f}% | %CLV positivo: {pos_clv_pct:.1f}% | "
            f"Drawdown Máx.: ${max_drawdown_abs:.2f} ({max_drawdown_pct:.2f}% bankroll)"
        )

        st.markdown("#### 🧬 Validación de Edge Real (CLV primero)")
        clv_enriched = [t for t in cerradas if t.get("CLV %") is not None]
        if clv_enriched:
            vc1, vc2 = st.columns(2)
            vc1.metric("ROI vs CLV", "🟢 Alineado" if (roi > 0 and avg_clv > 0) or (roi <= 0 and avg_clv <= 0) else "🟡 Divergente")
            vc2.metric("Brier vs CLV", "🟢 Robusto" if (brier_score < 0.25 and avg_clv > 0) else "🔴 Revisar")
            if roi > 0 and avg_clv < 0:
                st.error("Backtest con ROI positivo pero CLV negativo: posible falso edge / sobreajuste.")
            elif roi <= 0 and avg_clv > 0:
                st.warning("CLV positivo con ROI bajo: la señal de precio existe, pero puede faltar muestra.")
            else:
                st.info("ROI y CLV están razonablemente alineados.")

            clv_df = pd.DataFrame(clv_enriched).copy()
            clv_df["Fecha"] = pd.to_datetime(clv_df["Fecha"], errors="coerce")
            clv_df = clv_df.sort_values("Fecha")
            clv_df["CLV Rolling"] = clv_df["CLV %"].rolling(window=20, min_periods=5).mean()
            st.line_chart(clv_df.set_index("Fecha")[["CLV %", "CLV Rolling"]], height=220)
            st.bar_chart(clv_df["CLV %"], height=180)
            by_market = clv_df.groupby("Mercado", dropna=False)["CLV %"].agg(["count", "mean"]).reset_index()
            by_league = clv_df.groupby("Liga", dropna=False)["CLV %"].agg(["count", "mean"]).reset_index()
            mk1, mk2 = st.columns(2)
            mk1.dataframe(by_market.rename(columns={"count": "N", "mean": "Avg CLV %"}), use_container_width=True)
            mk2.dataframe(by_league.rename(columns={"count": "N", "mean": "Avg CLV %"}), use_container_width=True)

        if max_drawdown_pct >= weekly_drawdown_stop_pct:
            st.error(f"🛑 Drawdown de {max_drawdown_pct:.2f}% supera el stop semanal ({weekly_drawdown_stop_pct}%). Reducir riesgo.")
        else:
            st.info("✅ Drawdown semanal bajo control.")

        st.markdown("#### 🚨 Monitoreo Continuo")
        if avg_clv < 0:
            st.error("Alerta CLV: CLV promedio debajo de 0.")
        if roi < -2.0:
            st.error("Alerta ROI: caída relevante de rentabilidad.")
        if max_drawdown_pct > weekly_drawdown_stop_pct * 0.8:
            st.warning("Alerta Drawdown: cerca del límite de riesgo semanal.")

        st.markdown("#### 🧭 Calibración Avanzada")
        c_cfg1, c_cfg2 = st.columns(2)
        n_bins = c_cfg1.slider("Bins de calibración", min_value=5, max_value=20, value=10, key="cal_bins")
        show_only_well_populated = c_cfg2.checkbox("Ocultar bins con N < 3", value=True, key="cal_hide_sparse")

        rel_df = build_reliability_table(cerradas, n_bins=n_bins)
        if show_only_well_populated and not rel_df.empty:
            rel_df = rel_df[rel_df["N"] >= 3].copy()

        if not rel_df.empty:
            ece = calc_ece(rel_df)
            mae_cal = float(np.mean(np.abs(rel_df["Gap"])))
            c_m1, c_m2 = st.columns(2)
            c_m1.metric("ECE (Expected Calibration Error)", f"{ece:.4f}")
            c_m2.metric("MAE de calibración por bin", f"{mae_cal:.4f}")

            chart_df = pd.DataFrame({
                "Prob Promedio": rel_df["Prob Promedio"].astype(float).values,
                "Frecuencia Real": rel_df["Frecuencia Real"].astype(float).values
            }).sort_values("Prob Promedio")
            st.line_chart(chart_df, x="Prob Promedio", y=["Prob Promedio", "Frecuencia Real"], height=220)
            st.dataframe(rel_df, use_container_width=True)
        else:
            st.caption("Aún no hay suficientes datos para curva de calibración.")

        st.markdown("#### ⏩ Backtesting Walk-Forward")
        w1, w2 = st.columns(2)
        wf_train = w1.number_input("Tamaño mínimo de entrenamiento", min_value=10, max_value=500, value=20, step=5)
        wf_test = w2.number_input("Ventana de test por fold", min_value=5, max_value=100, value=10, step=5)
        wf_df = walk_forward_backtest(cerradas, min_train_size=int(wf_train), test_window=int(wf_test))

        if not wf_df.empty:
            wf_avg_brier_raw = float(wf_df["Brier Raw"].mean())
            wf_avg_brier_cal = float(wf_df["Brier Cal"].mean())
            wf_avg_ll_raw = float(wf_df["LogLoss Raw"].mean())
            wf_avg_ll_cal = float(wf_df["LogLoss Cal"].mean())
            wf_avg_roi = float(wf_df["ROI %"].mean())
            wf_avg_clv = float(wf_df["CLV %"].mean())
            wf_m1, wf_m2, wf_m3, wf_m4 = st.columns(4)
            wf_m1.metric("Brier WF (Raw -> Cal)", f"{wf_avg_brier_raw:.4f} -> {wf_avg_brier_cal:.4f}")
            wf_m2.metric("LogLoss WF (Raw -> Cal)", f"{wf_avg_ll_raw:.4f} -> {wf_avg_ll_cal:.4f}")
            wf_m3.metric("ROI Promedio WF", f"{wf_avg_roi:+.2f}%")
            wf_m4.metric("CLV Promedio WF", f"{wf_avg_clv:+.2f}%")

            st.line_chart(wf_df.set_index("Fold")[["Brier Raw", "Brier Cal", "ROI %"]], height=220)
            st.dataframe(wf_df, use_container_width=True)
        else:
            st.caption("No hay datos suficientes para walk-forward con la configuración actual.")

    with st.form("add_pt"):
        f1, f2, f3, f4 = st.columns(4)
        p_name = f1.text_input("Partido / Mercado")
        p_mod = f2.number_input("Prob Modelo (%)", value=50.0, min_value=1.0, max_value=99.0)
        p_odd = f3.number_input("Momio Entrada (Americano)", value=-110.0)
        p_res = f4.selectbox("Resultado", ["Pendiente", "Ganada", "Perdida"])

        h1, h2 = st.columns(2)
        p_liga = h1.text_input("Liga", value=COMP_CODE)
        p_market = h2.text_input("Mercado", value="Manual")

        g1, g2, g3 = st.columns(3)
        p_stake = g1.number_input("Stake ($)", min_value=1.0, value=20.0, step=1.0)
        p_close = g2.number_input("Momio Cierre (Americano, opcional)", value=0.0, step=1.0, help="0 = sin dato de cierre")
        _ = g3.caption("CLV = mejora de precio vs cierre.")

        if st.form_submit_button("Guardar Trade"):
            if not p_name.strip():
                st.warning("Ingresa el nombre del partido/mercado.")
            else:
                entry_dec = american_to_decimal(p_odd)
                close_dec = american_to_decimal(p_close) if p_close != 0 else None
                clv_raw = calc_clv(entry_dec, close_dec)
                clv_pct = (clv_raw * 100.0) if clv_raw is not None else None
                unc = confidence_uncertainty(p_mod)
                trade = {
                    "Fecha": datetime.now().strftime("%Y-%m-%d"),
                    "Partido": p_name,
                    "Liga": p_liga.strip() if p_liga.strip() else "N/A",
                    "Mercado": p_market.strip() if p_market.strip() else "Manual",
                    "Prob Modelo": p_mod / 100.0,
                    "Momio": p_odd,
                    "Resultado": p_res,
                    "Stake": p_stake,
                    "Uncertainty": unc,
                    "Edge %": None,
                    "Entry Odds Dec": entry_dec,
                    "Closing Odds Dec": close_dec,
                    "Cuota Cierre": p_close if p_close != 0 else None,
                    "CLV %": clv_pct,
                    "PnL": _calc_trade_pnl(p_stake, p_odd, p_res),
                }
                save_trade_db(trade)
                st.rerun()

    if trades:
        st.dataframe(pd.DataFrame(trades), use_container_width=True)
        col_del, _ = st.columns([1, 3])
        if col_del.button("🗑️ Limpiar todos los trades"):
            clear_trades_db()
            st.rerun()

# ══════════════════════════════════════════════
#  TAB 5 — SCANNER V8 (LÍMITES POR LIGA)
# ══════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-header">🔍 SCANNER V8</div>', unsafe_allow_html=True)

    if not football_api_key or not _get_odds_keys_pool():
        st.warning("Se requieren las APIs de FB-Data y The Odds para usar el escáner.")
    else:
        sc_leagues = st.multiselect("Ligas a Escanear", list(LEAGUES.keys()), default=[list(LEAGUES.keys())[0]])
        max_picks_per_league = st.slider("Máximo picks por liga", min_value=1, max_value=10, value=3)
        avoid_team_correlation = st.checkbox("Evitar picks con equipos repetidos", value=True)

        if st.button("🚀 Iniciar Escaneo V8", type="primary"):
            st.info("Escaneando y cruzando predicciones con el mercado real...")
            results = []
            teams_used = set()
            daily_exposure_cap = bankroll * (daily_exposure_pct / 100.0)
            exposure_used = 0.0
            bets_used = 0
            selected_calibrator_sc = {"method": "none"}

            closed_trades = [t for t in load_trades_db() if t["Resultado"] != "Pendiente"]
            if auto_calibrate_probs:
                selected_calibrator_sc = build_best_calibrator(closed_trades, min_train_size=40)
            eq = np.cumsum([t.get("PnL", 0.0) for t in sorted(closed_trades, key=lambda x: x["Fecha"])]) if closed_trades else np.array([0.0])
            peaks = np.maximum.accumulate(eq) if len(eq) else np.array([0.0])
            dd = (peaks - eq) if len(eq) else np.array([0.0])
            dd_pct = (float(np.max(dd)) / bankroll * 100.0) if bankroll > 0 else 0.0
            if dd_pct >= weekly_drawdown_stop_pct:
                st.error("🛑 Scanner pausado: drawdown semanal sobre límite configurado.")
                st.stop()

            for lname in sc_leagues:
                cfg  = LEAGUES[lname]
                vmin_manual, vmax_manual = cfg["v8_params"]["div_min"], cfg["v8_params"]["div_max"]
                if use_dynamic_div_thresholds:
                    vmin, vmax, _ = learn_divergence_thresholds(
                        cfg["code"],
                        fallback_min=vmin_manual,
                        fallback_max=vmax_manual,
                        min_samples=120,
                    )
                else:
                    vmin, vmax = float(vmin_manual), float(vmax_manual)
                l_avg = cfg["avg_goals"]  # FIX #5
                picks_this_league = 0

                matches = get_upcoming_matches(football_api_key, cfg["code"])
                if not matches: continue

                live_odds = get_live_odds(_get_odds_keys_pool()[0], cfg["odds_key"])
                if not live_odds: continue

                for m in matches[:5]:
                    h_name, a_name = m["homeTeam"]["name"], m["awayTeam"]["name"]
                    h_id,   a_id   = m["homeTeam"]["id"],   m["awayTeam"]["id"]

                    if picks_this_league >= max_picks_per_league:
                        continue
                    if avoid_team_correlation and (h_name in teams_used or a_name in teams_used):
                        continue

                    game, sim_score = _find_best_game(live_odds, h_name, a_name)
                    if not game: continue

                    h_matches = get_team_matches(football_api_key, h_id)
                    a_matches = get_team_matches(football_api_key, a_id)
                    # FIX #5: pasar promedio de goles de la liga
                    pred = calc_all_predictions(h_matches, a_matches, h_id, a_id, l_avg, cfg["code"])
                    pred_over = pred["over_25"]
                    if auto_calibrate_probs and selected_calibrator_sc.get("method") != "none":
                        pred_over = round(apply_selected_calibration(pred_over / 100.0, selected_calibrator_sc) * 100.0, 1)

                    # Extraer cuotas Over/Under 2.5 en decimal de forma robusta
                    over_prices, under_prices, bm_margins = [], [], []
                    for bm in game["bookmakers"]:
                        bm_o25, bm_u25 = [], []
                        for mkt in bm["markets"]:
                            if mkt["key"] == "totals":
                                for oc in mkt["outcomes"]:
                                    if oc.get("point") == 2.5:
                                        if oc["name"] == "Over":
                                            bm_o25.append(float(oc["price"]))
                                        if oc["name"] == "Under":
                                            bm_u25.append(float(oc["price"]))
                        if bm_o25:
                            over_prices.extend(bm_o25)
                        if bm_u25:
                            under_prices.extend(bm_u25)
                        if bm_o25 and bm_u25:
                            bm_margins.append(calc_market_margin([max(bm_o25), max(bm_u25)]))

                    o25_dec = max(over_prices) if over_prices else None
                    u25_dec = max(under_prices) if under_prices else None

                    if o25_dec and u25_dec:
                        # Margen conservador: máximo entre margen del best-price y promedio por bookmaker
                        best_pair_margin = calc_market_margin([o25_dec, u25_dec])
                        avg_bm_margin = float(np.mean(bm_margins)) if bm_margins else best_pair_margin
                        margin_sc = max(best_pair_margin, avg_bm_margin)
                        o25_am    = normalize_to_american(o25_dec)
                        div_abs, div_dyn, vf_prob, ev = calc_v8_metrics(pred_over, o25_dec, margin_sc)
                        save_edge_sample(cfg["code"], f"{h_name} vs {a_name}", "Over 2.5", "goles", div_dyn, ev)

                        if vmin <= div_dyn <= vmax:
                            # FIX #4: lm_penalty por defecto (neutral) en el scanner
                            k, stake, _ = smart_kelly_v8(pred_over, o25_dec, max_stake_cap, bankroll, lm_factor=1.0)
                            unc = confidence_uncertainty(pred_over)
                            if unc > confidence_max_uncertainty:
                                continue
                            if bets_used >= max_bets_per_day:
                                continue
                            exec_dec, exec_stake, exec_rejected = apply_execution_frictions(
                                o25_dec, sim_slippage_pct, sim_reject_rate, max_stake_market=max_stake_market, desired_stake=stake
                            )
                            stake = exec_stake
                            remaining = max(0.0, daily_exposure_cap - exposure_used)
                            if remaining <= 0:
                                continue
                            stake = min(stake, remaining)
                            if stake <= 0:
                                continue

                            results.append({
                                "Liga": cfg["code"],
                                "Partido": f"{h_name} vs {a_name}",
                                "Mercado": "Over 2.5",
                                "Mi Prob": f"{pred_over}%",
                                "Mkt VF": f"{vf_prob}%",
                                "Margen": f"{(margin_sc-1)*100:.1f}%",
                                "Div Dinámica": f"{div_dyn:+.1f}%",
                                "Uncertainty": f"{unc:.2f}",
                                "Momio": f"{o25_am:+d}" if o25_am > 0 else str(o25_am),
                                "Momio Exec": f"{normalize_to_american(exec_dec):+d}",
                                "Rechazada": "Sí" if exec_rejected else "No",
                                "Stake": f"${stake:.2f}",
                            })
                            exposure_used += stake
                            bets_used += 1
                            picks_this_league += 1
                            teams_used.update([h_name, a_name])

                            if _BET_AUDIT_AVAILABLE and not exec_rejected:
                                vf_frac = float(get_vig_free_prob(exec_dec if exec_dec > 1.0 else o25_dec, margin_sc))
                                audit_log_bet({
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                    "match_id": str(m["id"]),
                                    "league": cfg["code"],
                                    "market": "totals",
                                    "selection": "over_2.5",
                                    "fixture_name": f"{h_name} vs {a_name}",
                                    "model_probability": float(pred_over) / 100.0,
                                    "implied_probability_market": vf_frac,
                                    "edge": float(ev),
                                    "entry_odds": float(exec_dec),
                                    "closing_odds": None,
                                    "stake": float(stake),
                                    "result": "pending",
                                })

                            if telegram_token and telegram_chat_id:
                                msg = format_bet_alert(
                                    f"{h_name} vs {a_name}", cfg["code"],
                                    "Over 2.5", pred_over, o25_am, div_dyn, k, stake,
                                )
                                send_telegram_alert(telegram_token, telegram_chat_id, msg)

            if results:
                st.success(f"🎯 Se encontraron {len(results)} apuestas con divergencia óptima.")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
                st.caption(f"Exposición sugerida scanner: ${exposure_used:.2f} / ${daily_exposure_cap:.2f} | Apuestas: {bets_used}/{max_bets_per_day}")
                if auto_calibrate_probs:
                    st.caption(f"Scanner con calibración automática: {selected_calibrator_sc.get('method', 'none')}.")
            else:
                st.warning("El escáner no encontró ninguna apuesta segura hoy. (El bankroll está protegido).")

with tab6:
    st.markdown('<div class="section-header">📈 CLV AUDIT — LOG AUTOMÁTICO</div>', unsafe_allow_html=True)

    if not _BET_AUDIT_AVAILABLE:
        st.warning(
            "Coloca `bet_logging.py` en el mismo directorio que esta app para activar "
            "el log automático SQLite."
        )
    else:
        st.caption(
            "Se registran picks confirmados desde el evaluador (Tab 2) y el scanner (Tab 5). "
            "Puedes sincronizar cierres vía Odds API (automático limitado por tiempo) y resultados cuando cierren."
        )

        bets_raw = audit_load_bets_df()

        sync_col_a, sync_col_b = st.columns(2)
        auto_clv_odds = sync_col_a.checkbox(
            "Auto-sincronizar closing pendientes vía Odds API (intervalo ≥ 30 min)",
            value=True,
            key="audit_auto_odds_sync",
            help="Requiere The Odds API Key en sidebar. Une partidos por texto 'Local vs Visita'.",
        )
        if sync_col_b.button("🔄 Sincronizar closing ahora"):
            st.session_state["audit_force_odds_sync"] = True

        def _audit_build_live_odds_map(leagues_set):
            mmap = {}
            pool = _get_odds_keys_pool()
            if not pool or not leagues_set:
                return mmap
            k0 = pool[0]
            for lc in leagues_set:
                odds_key = LEAGUE_CODE_TO_ODDS_KEY.get(str(lc))
                if not odds_key:
                    continue
                try:
                    data = get_live_odds(k0, odds_key)
                    mmap[str(lc)] = data if isinstance(data, list) else []
                except Exception as e:
                    log_event("_audit_build_live_odds_map", e)
                    mmap[str(lc)] = []
            return mmap

        if not bets_raw.empty:
            pend_odds = bets_raw[
                bets_raw["closing_odds"].isna()
                & (bets_raw["result"].astype(str).str.lower() == "pending")
            ]
            need_leagues = set(pend_odds["league"].dropna().astype(str).unique().tolist())

            forced = bool(st.session_state.pop("audit_force_odds_sync", False))
            pool_ok = bool(_get_odds_keys_pool())
            if pend_odds.shape[0] > 0 and pool_ok:
                cooldown = 30 * 60
                last_ts = float(st.session_state.get("_audit_odds_sync_ts") or 0.0)
                now_ts = time.time()
                elapsed = now_ts - last_ts
                if forced or (auto_clv_odds and elapsed >= cooldown):
                    with st.spinner("Sincronizando cuotas de cierre (Odds API)..."):
                        live_map = _audit_build_live_odds_map(need_leagues)
                        sync_stats = audit_refresh_pending_closing_odds(live_map)
                        st.session_state["_audit_odds_sync_ts"] = now_ts
                    st.success(
                        f"Closing Odds sync: actualizadas {sync_stats.get('updated', 0)}, "
                        f"omitidas {sync_stats.get('skipped', 0)}."
                    )
                    st.rerun()
            elif pend_odds.shape[0] > 0 and not pool_ok:
                st.caption("Para sync automático de closing, configura una Odds API key en el sidebar.")
        bets_df = audit_calculate_clv(bets_raw) if not bets_raw.empty else bets_raw.copy()
        m = audit_compute_metrics(bets_df)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total apuestas", int(m["total_bets"]))
        k2.metric("CLV medio", f"{m['avg_clv']:.4f}")
        k3.metric("% CLV > 0", f"{m['pct_positive_clv']:.1f}%")
        k4.metric("ROI (cerradas)", f"{m['roi']*100:.2f}%")
        k5.metric("Win rate", f"{m['win_rate']*100:.1f}%")

        st.caption(
            f"P&L cerradas: ${m['total_profit']:+.2f} | Stakes cerrados: ${m['total_stake_settled']:.2f} | "
            f"Cerradas: {m['settled_bets']}"
        )

        if not bets_df.empty and bets_df["CLV"].notna().any():
            time_df = bets_df[bets_df["CLV"].notna()].copy()
            time_df["date"] = pd.to_datetime(time_df["date"], errors="coerce")
            time_df = time_df.dropna(subset=["date"]).sort_values("date")
            st.markdown("##### CLV en el tiempo")
            st.line_chart(time_df.set_index("date")["CLV"], height=220)
            st.markdown("##### Distribución CLV")
            st.bar_chart(time_df["CLV"], height=200)

            c_a, c_b = st.columns(2)
            with c_a:
                st.markdown("**Por liga**")
                by_league = time_df.groupby("league", dropna=False)["CLV"].agg(["mean", "count"]).reset_index()
                st.dataframe(by_league, use_container_width=True)
            with c_b:
                st.markdown("**Por mercado**")
                by_mkt = time_df.groupby("market", dropna=False)["CLV"].agg(["mean", "count"]).reset_index()
                st.dataframe(by_mkt, use_container_width=True)

        st.markdown("##### Actualización manual")
        u1, u2, u3, u4 = st.columns(4)
        uc_mid = u1.text_input("match_id", key="audit_close_mid")
        uc_mkt = u2.text_input("market (match_winner / totals)", key="audit_close_mkt")
        uc_sel = u3.text_input("selection (home / draw / away / over_2.5)", key="audit_close_sel")
        uc_co = u4.number_input("closing_odds decimal", min_value=1.01, value=2.0, step=0.01, key="audit_close_odds")
        if st.button("Aplicar closing odds"):
            n = audit_update_closing_odds(uc_mid.strip(), uc_mkt.strip(), uc_sel.strip(), float(uc_co))
            st.success(f"Filas actualizadas: {n}")
            st.rerun()

        r1, r2, r3, r4 = st.columns(4)
        ur_mid = r1.text_input("match_id ", key="audit_res_mid")
        ur_mkt = r2.text_input("market ", key="audit_res_mkt")
        ur_sel = r3.text_input("selection ", key="audit_res_sel")
        ur_res = r4.selectbox("resultado", ["pending", "win", "loss"], key="audit_res_val")
        if st.button("Aplicar resultado"):
            n = audit_update_bet_result(ur_mid.strip(), ur_mkt.strip(), ur_sel.strip(), ur_res)
            st.success(f"Filas actualizadas: {n}")
            st.rerun()

        if bets_raw.empty:
            st.info("Sin registros aún. Ejecuta el evaluador o el scanner cuando haya picks confirmados.")
        else:
            st.dataframe(bets_df, use_container_width=True)

if show_logs:
    st.markdown("---")
    st.markdown("#### 🧪 Logs técnicos recientes")
    logs_df = pd.DataFrame(st.session_state.get("system_logs", []))
    if logs_df.empty:
        st.caption("Sin eventos de error registrados.")
    else:
        st.dataframe(logs_df.tail(30), use_container_width=True)
