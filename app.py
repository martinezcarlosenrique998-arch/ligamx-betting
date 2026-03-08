import streamlit as st
import pandas as pd
import requests
import random
import json
import math
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Football Betting Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"code": "PL",  "odds_key": "soccer_epl"},
    "🇪🇸 La Liga":              {"code": "PD",  "odds_key": "soccer_spain_la_liga"},
    "🇩🇪 Bundesliga":           {"code": "BL1", "odds_key": "soccer_germany_bundesliga"},
    "🇮🇹 Serie A":              {"code": "SA",  "odds_key": "soccer_italy_serie_a"},
    "🇫🇷 Ligue 1":              {"code": "FL1", "odds_key": "soccer_france_ligue_1"},
    "🏆 Champions League":      {"code": "CL",  "odds_key": "soccer_uefa_champs_league"},
}
BASE_URL = "https://api.football-data.org/v4"

# ─────────────────────────────────────────────
#  ESTILOS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&family=DM+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 2px; }
.stApp { background: #0a0a0f; color: #e8e8e8; }
.metric-card { background: linear-gradient(135deg,#12121a,#1a1a2e); border:1px solid #2a2a40; border-radius:12px; padding:20px; margin:8px 0; transition:all .3s ease; }
.metric-card:hover { border-color:#00ff88; transform:translateY(-2px); }
.value-neutral { color:#ffcc44; font-family:'Space Mono'; font-size:1.4em; font-weight:700; }
.bet-row-positive { background:rgba(0,255,136,.08); border-left:3px solid #00ff88; padding:12px; border-radius:6px; margin:6px 0; }
.bet-row-negative { background:rgba(255,68,102,.08); border-left:3px solid #ff4466; padding:12px; border-radius:6px; margin:6px 0; }
.bet-row-neutral  { background:rgba(255,204,68,.08);  border-left:3px solid #ffcc44; padding:12px; border-radius:6px; margin:6px 0; }
.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:.75em; font-weight:600; margin:2px; }
.tag-green  { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red    { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow { background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }
.section-header { font-family:'Bebas Neue'; font-size:1.8em; letter-spacing:3px; color:#00ff88; border-bottom:1px solid #2a2a40; padding-bottom:8px; margin:24px 0 16px 0; }
.ai-analysis { background:linear-gradient(135deg,#0d1a0d,#0a1a2e); border:1px solid #00ff8844; border-radius:12px; padding:20px; margin:16px 0; font-size:.95em; line-height:1.7; }
.ai-analysis b { color:#00ff88; }
.market-section { background:#12121a; border:1px solid #2a2a40; border-radius:10px; padding:16px; margin:10px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  FOOTBALL-DATA.ORG
# ─────────────────────────────────────────────

def fd_get(endpoint, api_key, params=None):
    headers = {"X-Auth-Token": api_key}
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=12)
        if r.status_code == 429:
            return {"error": "Límite de requests alcanzado. Espera 1 minuto."}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=3600)
def get_upcoming_matches(api_key, comp_code):
    today  = datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
    data   = fd_get(f"competitions/{comp_code}/matches", api_key,
                    {"status": "SCHEDULED", "dateFrom": today, "dateTo": future})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_team_matches(api_key, team_id, last=10):
    data = fd_get(f"teams/{team_id}/matches", api_key, {"status": "FINISHED", "limit": last})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_h2h(api_key, match_id):
    data = fd_get(f"matches/{match_id}/head2head", api_key, {"limit": 10})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_standings(api_key, comp_code):
    data   = fd_get(f"competitions/{comp_code}/standings", api_key)
    tables = data.get("standings", [])
    for t in tables:
        if t.get("type") == "TOTAL":
            return t.get("table", [])
    return []

@st.cache_data(ttl=3600)
def get_competition_teams(api_key, comp_code):
    data = fd_get(f"competitions/{comp_code}/teams", api_key)
    return data.get("teams", [])

# ─────────────────────────────────────────────
#  THE ODDS API
# ─────────────────────────────────────────────

def get_live_odds(api_key, sport_key, markets="h2h,totals,btts"):
    url    = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": api_key, "regions": "us,eu,uk",
              "markets": markets, "oddsFormat": "american"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return []

def extract_odds_for_match(live_data, home_name, away_name):
    home_lower = home_name.lower()
    away_lower = away_name.lower()
    best_game, best_score = None, 0
    for game in live_data:
        gh    = game.get("home_team", "").lower()
        ga    = game.get("away_team", "").lower()
        score = sum(2 for w in home_lower.split() if len(w) > 3 and w in gh)
        score += sum(2 for w in away_lower.split() if len(w) > 3 and w in ga)
        if score > best_score:
            best_score, best_game = score, game
    if not best_game or best_score == 0:
        return []
    casas = []
    hn = best_game.get("home_team", "")
    an = best_game.get("away_team", "")
    for bm in best_game.get("bookmakers", []):
        casa = {"nombre": bm["title"], "local": None, "empate": None, "visita": None}
        for mkt in bm.get("markets", []):
            if mkt["key"] == "h2h":
                oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                casa["local"]  = float(oc.get(hn, 200))
                casa["empate"] = float(oc.get("Draw", 230))
                casa["visita"] = float(oc.get(an, -150))
        if casa["local"]:
            casas.append(casa)
    return casas

# ─────────────────────────────────────────────
#  PROCESAMIENTO STATS
# ─────────────────────────────────────────────

def calc_form_fd(matches, team_id):
    results = []
    for m in matches[-5:]:
        s  = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        results.append(3 if mg > rg else (1 if mg == rg else 0))
    if not results: return 0.5
    return round(sum(results) / (len(results) * 3), 3)

def get_recent_results_str(matches, team_id, n=5):
    res = []
    for m in reversed(matches[-n:]):
        s  = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        res.append("W" if mg > rg else ("D" if mg == rg else "L"))
    return " ".join(res)

def calc_avg_goals_fd(matches, team_id):
    gf, ga = [], []
    for m in matches:
        s  = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        if m.get("status") != "FINISHED": continue
        ih = m.get("homeTeam", {}).get("id") == team_id
        gf.append(hg if ih else ag)
        ga.append(ag if ih else hg)
    if not gf: return 1.2, 1.2
    return round(sum(gf)/len(gf), 2), round(sum(ga)/len(ga), 2)

def calc_btts_rate(matches):
    """% de partidos donde ambos equipos anotaron."""
    btts, total = 0, 0
    for m in matches:
        if m.get("status") != "FINISHED": continue
        s  = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        total += 1
        if hg > 0 and ag > 0: btts += 1
    return round(btts / total, 3) if total else 0.5

def calc_over_rate(matches, threshold=2.5):
    """% de partidos con más de N goles."""
    over, total = 0, 0
    for m in matches:
        if m.get("status") != "FINISHED": continue
        s   = m.get("score", {}).get("fullTime", {})
        tot = (s.get("home", 0) or 0) + (s.get("away", 0) or 0)
        total += 1
        if tot > threshold: over += 1
    return round(over / total, 3) if total else 0.5

def calc_halftime_rate(matches, team_id):
    """% de partidos ganados/empatados/perdidos al descanso."""
    hw = hd = hl = 0
    total = 0
    for m in matches:
        if m.get("status") != "FINISHED": continue
        ht = m.get("score", {}).get("halfTime", {})
        hg = ht.get("home", 0) or 0
        ag = ht.get("away", 0) or 0
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        total += 1
        if mg > rg: hw += 1
        elif mg == rg: hd += 1
        else: hl += 1
    if not total: return 0.33, 0.33, 0.34
    return round(hw/total,3), round(hd/total,3), round(hl/total,3)

def calc_h2h_stats_fd(h2h_matches, home_id, away_id):
    hw = aw = dr = 0
    for m in h2h_matches:
        if m.get("status") != "FINISHED": continue
        s        = m.get("score", {}).get("fullTime", {})
        hg       = s.get("home", 0) or 0
        ag       = s.get("away", 0) or 0
        mid_home = m.get("homeTeam", {}).get("id")
        if hg > ag:
            if mid_home == home_id: hw += 1
            else: aw += 1
        elif ag > hg:
            if mid_home == away_id: aw += 1
            else: hw += 1
        else:
            dr += 1
    return hw, aw, dr

# ─────────────────────────────────────────────
#  MODELO EXTENDIDO
# ─────────────────────────────────────────────

def poisson_prob(lam, k):
    """Probabilidad de Poisson: P(X=k) dado lambda."""
    return (math.exp(-lam) * lam**k) / math.factorial(k)

def calc_all_predictions(home_form, away_form, home_gf, away_gf,
                          home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr,
                          home_btts, away_btts, home_over25, away_over25,
                          home_ht_w, home_ht_d, home_ht_l,
                          away_ht_w, away_ht_d, away_ht_l,
                          is_clasico=False):
    # ── 1X2 base ──
    h = a = d = 0.0
    h += home_form * 0.35
    a += away_form * 0.35
    h += min((home_gf / max(away_ga, 0.5)) / 3, 0.30)
    a += min((away_gf / max(home_ga, 0.5)) / 3, 0.30)
    total_h2h = h2h_hw + h2h_aw + h2h_dr
    if total_h2h > 0:
        h += (h2h_hw / total_h2h) * 0.20
        a += (h2h_aw / total_h2h) * 0.20
        d += (h2h_dr / total_h2h) * 0.20
    h += 0.15
    if is_clasico:
        avg = (h + a) / 2
        h = h * 0.85 + avg * 0.15
        a = a * 0.85 + avg * 0.15
        d += 0.05
    total = h + a + d
    home_pct = round((h / total) * 100, 1)
    away_pct = round((a / total) * 100, 1)
    draw_pct = round(100 - home_pct - away_pct, 1)

    # ── Goles esperados (xG aproximado con Poisson) ──
    exp_h = round(home_gf * (away_ga / max(away_gf, 0.5)), 2)
    exp_a = round(away_gf * (home_ga / max(home_gf, 0.5)), 2)
    exp_t = round(exp_h + exp_a, 2)

    # ── Over/Under con distribución de Poisson ──
    max_goals = 8
    prob_matrix = [[poisson_prob(exp_h, i) * poisson_prob(exp_a, j)
                    for j in range(max_goals)] for i in range(max_goals)]

    over_15 = round(sum(prob_matrix[i][j]
                        for i in range(max_goals) for j in range(max_goals)
                        if i + j > 1.5) * 100, 1)
    over_25 = round(sum(prob_matrix[i][j]
                        for i in range(max_goals) for j in range(max_goals)
                        if i + j > 2.5) * 100, 1)
    over_35 = round(sum(prob_matrix[i][j]
                        for i in range(max_goals) for j in range(max_goals)
                        if i + j > 3.5) * 100, 1)
    under_15 = round(100 - over_15, 1)
    under_25 = round(100 - over_25, 1)
    under_35 = round(100 - over_35, 1)

    # ── BTTS (Ambos Equipos Anotan) ──
    # Probabilidad de que el local NO anote: P(X=0)
    p_home_no_score = poisson_prob(exp_h, 0)
    p_away_no_score = poisson_prob(exp_a, 0)
    btts_yes = round((1 - p_home_no_score) * (1 - p_away_no_score) * 100, 1)
    btts_no  = round(100 - btts_yes, 1)
    # Ajuste con historial real
    btts_hist = round((home_btts + away_btts) / 2 * 100, 1)
    btts_yes  = round(btts_yes * 0.6 + btts_hist * 0.4, 1)
    btts_no   = round(100 - btts_yes, 1)

    # ── Hándicap Asiático ──
    goal_diff_exp = exp_h - exp_a
    # -0.5 local gana (sin empate)
    ha_home_minus05 = round(sum(prob_matrix[i][j]
                                for i in range(max_goals) for j in range(max_goals)
                                if i > j) * 100, 1)
    # +0.5 visitante (si empata o gana)
    ha_away_plus05  = round(100 - ha_home_minus05, 1)
    # -1.5 local gana por 2+
    ha_home_minus15 = round(sum(prob_matrix[i][j]
                                for i in range(max_goals) for j in range(max_goals)
                                if i - j >= 2) * 100, 1)
    # +1.5 visitante (si pierde por 1, empata o gana)
    ha_away_plus15  = round(100 - ha_home_minus15, 1)

    # ── Resultado al Descanso (HT) ──
    # Combinación ponderada de historial de ambos equipos
    ht_home_win  = round((home_ht_w * 0.6 + (1 - away_ht_l) * 0.4) * 100, 1)
    ht_draw      = round((home_ht_d * 0.5 + away_ht_d * 0.5) * 100, 1)
    ht_away_win  = round(max(0, 100 - ht_home_win - ht_draw), 1)

    # ── Doble Oportunidad ──
    do_1x = round(home_pct + draw_pct, 1)
    do_x2 = round(draw_pct + away_pct, 1)
    do_12 = round(home_pct + away_pct, 1)

    return {
        # 1X2
        "home_win_pct": home_pct,
        "draw_pct": draw_pct,
        "away_win_pct": away_pct,
        # Goles
        "exp_home_goals": exp_h,
        "exp_away_goals": exp_a,
        "exp_total_goals": exp_t,
        # Over/Under
        "over_15": over_15, "under_15": under_15,
        "over_25": over_25, "under_25": under_25,
        "over_35": over_35, "under_35": under_35,
        # BTTS
        "btts_yes": btts_yes, "btts_no": btts_no,
        # Hándicap Asiático
        "ha_home_minus05": ha_home_minus05,
        "ha_away_plus05":  ha_away_plus05,
        "ha_home_minus15": ha_home_minus15,
        "ha_away_plus15":  ha_away_plus15,
        # HT
        "ht_home_win": ht_home_win,
        "ht_draw":     ht_draw,
        "ht_away_win": ht_away_win,
        # Doble oportunidad
        "do_1x": do_1x, "do_x2": do_x2, "do_12": do_12,
        # Goal diff esperado
        "goal_diff_exp": round(goal_diff_exp, 2),
    }

# ─────────────────────────────────────────────
#  ANÁLISIS IA (Claude API)
# ─────────────────────────────────────────────

def generate_ai_analysis(home_team, away_team, data, pred, anthropic_key):
    """Llama a Claude para generar el análisis explicativo."""
    prompt = f"""Eres un analista deportivo experto en apuestas de fútbol. Analiza el siguiente partido y explica en español, de forma clara y concisa, por qué el modelo arroja esos porcentajes. Sé directo, usa datos concretos, y menciona los factores clave que favorecen o perjudican a cada equipo.

PARTIDO: {home_team} (local) vs {away_team} (visitante)

DATOS ESTADÍSTICOS:
- Forma reciente {home_team} (últ.5): {round(data['home_form']*100)}% ({data.get('home_results','')})
- Forma reciente {away_team} (últ.5): {round(data['away_form']*100)}% ({data.get('away_results','')})
- {home_team} promedio goles: {data['home_gf']} anotados / {data['home_ga']} recibidos por partido
- {away_team} promedio goles: {data['away_gf']} anotados / {data['away_ga']} recibidos por partido
- H2H últimos 10: {home_team} {data['h2h_hw']} victorias — {data['h2h_dr']} empates — {data['h2h_aw']} victorias {away_team}
- BTTS histórico {home_team}: {round(data.get('home_btts',0.5)*100)}% de partidos
- BTTS histórico {away_team}: {round(data.get('away_btts',0.5)*100)}% de partidos
- Over 2.5 histórico {home_team}: {round(data.get('home_over25',0.5)*100)}%
- Over 2.5 histórico {away_team}: {round(data.get('away_over25',0.5)*100)}%

PREDICCIONES DEL MODELO:
- Victoria local: {pred['home_win_pct']}% | Empate: {pred['draw_pct']}% | Victoria visitante: {pred['away_win_pct']}%
- Goles esperados: {pred['exp_home_goals']} - {pred['exp_away_goals']} (total: {pred['exp_total_goals']})
- Over 2.5: {pred['over_25']}% | BTTS: {pred['btts_yes']}%
- Hándicap {home_team} -0.5: {pred['ha_home_minus05']}%

Escribe un análisis de 4-5 párrafos cortos que explique:
1. Por qué el modelo favorece a quien favorece (o por qué está equilibrado)
2. Qué dice el H2H y la forma reciente
3. Por qué los goles esperados son esos (¿partido abierto o cerrado?)
4. Una apuesta que destaque como interesante basada en los datos
5. Un factor de riesgo o advertencia

Usa **negritas** para los datos clave. No uses emojis. Sé analítico y objetivo."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        r.raise_for_status()
        content = r.json().get("content", [])
        return content[0].get("text", "") if content else "No se pudo generar el análisis."
    except Exception as e:
        return f"Error al generar análisis: {str(e)}"

# ─────────────────────────────────────────────
#  MATH APUESTAS
# ─────────────────────────────────────────────

def american_to_decimal(a):
    return round((a/100)+1, 4) if a > 0 else round((100/abs(a))+1, 4)

def implied_prob(dec):
    return round((1/dec)*100, 2) if dec > 0 else 0

def calc_ev(my_prob_pct, dec_odds):
    return round((my_prob_pct/100 * dec_odds) - 1, 4)

def kelly_criterion(my_prob_pct, dec_odds):
    p = my_prob_pct / 100
    b = dec_odds - 1
    if b <= 0: return 0
    return max(0, round(((b*p - (1-p)) / b) * 100, 2))

def build_all_markets(pred, ht, at):
    """Construye la lista completa de mercados con probabilidades."""
    return [
        # 1X2
        ("1X2", f"🏠 {ht} gana",        pred["home_win_pct"]),
        ("1X2", "🤝 Empate",             pred["draw_pct"]),
        ("1X2", f"✈️ {at} gana",         pred["away_win_pct"]),
        # Doble oportunidad
        ("Doble oportunidad", f"1X ({ht} o Empate)", pred["do_1x"]),
        ("Doble oportunidad", f"X2 (Empate o {at})", pred["do_x2"]),
        ("Doble oportunidad", f"12 ({ht} o {at})",   pred["do_12"]),
        # Over/Under
        ("Over/Under", "⚽ Over 1.5",  pred["over_15"]),
        ("Over/Under", "⚽ Under 1.5", pred["under_15"]),
        ("Over/Under", "⚽ Over 2.5",  pred["over_25"]),
        ("Over/Under", "⚽ Under 2.5", pred["under_25"]),
        ("Over/Under", "⚽ Over 3.5",  pred["over_35"]),
        ("Over/Under", "⚽ Under 3.5", pred["under_35"]),
        # BTTS
        ("BTTS", "✅ Ambos anotan (Sí)", pred["btts_yes"]),
        ("BTTS", "❌ Ambos anotan (No)", pred["btts_no"]),
        # Hándicap Asiático
        ("Hándicap Asiático", f"🏠 {ht} -0.5 (gana partido)",      pred["ha_home_minus05"]),
        ("Hándicap Asiático", f"✈️ {at} +0.5 (empata o gana)",     pred["ha_away_plus05"]),
        ("Hándicap Asiático", f"🏠 {ht} -1.5 (gana por 2+)",       pred["ha_home_minus15"]),
        ("Hándicap Asiático", f"✈️ {at} +1.5 (pierde por 1, E o G)", pred["ha_away_plus15"]),
        # HT
        ("Resultado HT", f"🏠 {ht} gana al descanso",  pred["ht_home_win"]),
        ("Resultado HT", "🤝 Empate al descanso",       pred["ht_draw"]),
        ("Resultado HT", f"✈️ {at} gana al descanso",  pred["ht_away_win"]),
    ]

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("# ⚽ Betting Analytics")
    st.markdown("---")
    st.markdown("### 🏆 Liga")
    selected_league_name = st.selectbox("Liga", list(LEAGUES.keys()))
    league_cfg = LEAGUES[selected_league_name]
    COMP_CODE  = league_cfg["code"]
    ODDS_SPORT = league_cfg["odds_key"]

    st.markdown("---")
    st.markdown("### 🔑 API Keys")

    # Cargar desde Streamlit Secrets si existen
    _secret_football = st.secrets.get("FOOTBALL_API_KEY", "") if hasattr(st, "secrets") else ""
    _secret_odds     = st.secrets.get("ODDS_API_KEY", "")     if hasattr(st, "secrets") else ""

    if _secret_football:
        st.success("✅ football-data.org: cargada desde Secrets")
        football_api_key = _secret_football
        # Opción para sobreescribir manualmente
        _override_football = st.text_input("Sobreescribir token (opcional)", type="password", key="ov_football")
        if _override_football:
            football_api_key = _override_football
    else:
        football_api_key = st.text_input(
            "football-data.org Token", type="password",
            help="Gratis en football-data.org/client/register"
        )

    if _secret_odds:
        st.success("✅ The Odds API: cargada desde Secrets")
        odds_api_key = _secret_odds
        _override_odds = st.text_input("Sobreescribir Odds Key (opcional)", type="password", key="ov_odds")
        if _override_odds:
            odds_api_key = _override_odds
    else:
        odds_api_key = st.text_input(
            "The Odds API Key", type="password",
            help="Gratis en the-odds-api.com"
        )

    if not _secret_football and not _secret_odds:
        with st.expander("💾 ¿Cómo guardar mis keys permanentemente?"):
            st.markdown("""
1. Ve a tu app en **share.streamlit.io**
2. Clic en **⋮ → Settings → Secrets**
3. Pega esto con tus keys reales:
```toml
FOOTBALL_API_KEY = "tu-token-aqui"
ODDS_API_KEY = "tu-key-aqui"
```
4. Clic en **Save** — listo, no volverás a ingresarlas
            """)

    st.markdown("---")
    st.markdown("### 💰 Bankroll")
    bankroll = st.number_input("Bankroll ($)", min_value=100, value=1000, step=100)
    st.markdown("### ⚙️ Filtros EV")
    min_ev        = st.slider("EV mínimo (%)", -20, 30, 5)
    max_kelly_pct = st.slider("Kelly máximo (%)", 1, 30, 10)

    st.markdown("---")
    if football_api_key:
        if st.button("🗑️ Limpiar caché"):
            st.cache_data.clear()
            st.success("Caché limpiado")
    st.caption("v5.1 · football-data.org · The Odds API · Claude AI")

# ─────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Análisis de Partido",
    "📡 Momios & EV",
    "🧮 Calculadora EV",
    "📖 Guía"
])

# ══════════════════════════════════════════════
#  TAB 1 — ANÁLISIS
# ══════════════════════════════════════════════
with tab1:
    st.markdown(f'<div class="section-header">🎯 ANÁLISIS — {selected_league_name}</div>', unsafe_allow_html=True)

    if not football_api_key:
        st.warning("👈 Ingresa tu token de football-data.org en el sidebar.")
        st.markdown("""
**Obtén tu token gratis:**
1. Ve a **https://www.football-data.org/client/register**
2. Regístrate — sin tarjeta de crédito
3. Recibirás el token en tu correo
        """)
        st.stop()

    # Selección partido
    st.markdown("### 1️⃣ Selecciona el partido")
    search_mode = st.radio("", ["📅 Ver próximos partidos", "🔍 Buscar por equipos"], horizontal=True)

    match_id = home_team_id = away_team_id = None
    home_team_name = away_team_name = ""

    if search_mode == "📅 Ver próximos partidos":
        with st.spinner("Cargando partidos..."):
            matches = get_upcoming_matches(football_api_key, COMP_CODE)
        if not matches:
            st.error("No se encontraron partidos. Verifica tu token.")
        else:
            opts = {}
            for m in matches[:30]:
                label = f"J{m.get('matchday','?')} · {m['utcDate'][:10]} — {m['homeTeam']['name']} vs {m['awayTeam']['name']}"
                opts[label] = m
            sel   = opts[st.selectbox("Partido", list(opts.keys()))]
            match_id       = sel["id"]
            home_team_id   = sel["homeTeam"]["id"]
            away_team_id   = sel["awayTeam"]["id"]
            home_team_name = sel["homeTeam"]["name"]
            away_team_name = sel["awayTeam"]["name"]
            c1, c2, c3 = st.columns(3)
            c1.metric("📅 Fecha",    sel["utcDate"][:10])
            c2.metric("🗓️ Jornada",  sel.get("matchday","?"))
            c3.metric("🔖 ID",       match_id)
    else:
        with st.spinner("Cargando equipos..."):
            teams_list = get_competition_teams(football_api_key, COMP_CODE)
        if teams_list:
            team_map   = {t["name"]: t["id"] for t in teams_list}
            team_names = sorted(team_map.keys())
            c1, c2 = st.columns(2)
            with c1: home_team_name = st.selectbox("🏠 Local",    team_names)
            with c2: away_team_name = st.selectbox("✈️ Visitante", [t for t in team_names if t != home_team_name])
            home_team_id = team_map[home_team_name]
            away_team_id = team_map[away_team_name]
            with st.spinner("Buscando fixture..."):
                upcoming = get_upcoming_matches(football_api_key, COMP_CODE)
                for m in upcoming:
                    if m["homeTeam"]["id"] == home_team_id and m["awayTeam"]["id"] == away_team_id:
                        match_id = m["id"]; break
            st.success(f"✅ Match ID: {match_id}") if match_id else st.info("No se encontró fixture próximo.")

    st.markdown("---")
    if home_team_id and away_team_id:
        is_clasico = st.checkbox("⚡ ¿Es Clásico?", value=False)

        if st.button("🔮 ANALIZAR AUTOMÁTICAMENTE", use_container_width=True, type="primary"):
            with st.spinner("Jalando datos estadísticos..."):
                home_matches = get_team_matches(football_api_key, home_team_id, 10)
                away_matches = get_team_matches(football_api_key, away_team_id, 10)
                h2h_matches  = get_h2h(football_api_key, match_id) if match_id else []

            # Calcular todas las stats
            home_form        = calc_form_fd(home_matches, home_team_id)
            away_form        = calc_form_fd(away_matches, away_team_id)
            home_gf, home_ga = calc_avg_goals_fd(home_matches, home_team_id)
            away_gf, away_ga = calc_avg_goals_fd(away_matches, away_team_id)
            h2h_hw, h2h_aw, h2h_dr = calc_h2h_stats_fd(h2h_matches, home_team_id, away_team_id)
            home_btts        = calc_btts_rate(home_matches)
            away_btts        = calc_btts_rate(away_matches)
            home_over25      = calc_over_rate(home_matches, 2.5)
            away_over25      = calc_over_rate(away_matches, 2.5)
            h_htw, h_htd, h_htl = calc_halftime_rate(home_matches, home_team_id)
            a_htw, a_htd, a_htl = calc_halftime_rate(away_matches, away_team_id)
            home_results     = get_recent_results_str(home_matches, home_team_id)
            away_results     = get_recent_results_str(away_matches, away_team_id)

            pred = calc_all_predictions(
                home_form, away_form, home_gf, away_gf,
                home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr,
                home_btts, away_btts, home_over25, away_over25,
                h_htw, h_htd, h_htl, a_htw, a_htd, a_htl,
                is_clasico
            )

            auto_data = {
                "home_form": home_form, "away_form": away_form,
                "home_gf": home_gf, "home_ga": home_ga,
                "away_gf": away_gf, "away_ga": away_ga,
                "h2h_hw": h2h_hw, "h2h_aw": h2h_aw, "h2h_dr": h2h_dr,
                "home_btts": home_btts, "away_btts": away_btts,
                "home_over25": home_over25, "away_over25": away_over25,
                "home_results": home_results, "away_results": away_results,
                "home_matches": home_matches, "away_matches": away_matches,
                "h2h_matches": h2h_matches,
            }

            st.session_state.update({
                "pred": pred, "auto_data": auto_data,
                "home_team": home_team_name, "away_team": away_team_name,
                "odds_sport_key": ODDS_SPORT,
            })
            st.success("✅ Listo. Revisa los resultados abajo y el Tab 📡 Momios & EV.")

    # ── RESULTADOS ──
    if "pred" in st.session_state and "auto_data" in st.session_state:
        pred = st.session_state["pred"]
        data = st.session_state["auto_data"]
        ht   = st.session_state.get("home_team", "Local")
        at   = st.session_state.get("away_team", "Visitante")

        st.markdown("---")
        st.markdown(f'<div class="section-header">📊 {ht.upper()} VS {at.upper()}</div>', unsafe_allow_html=True)

        # Datos clave auto-jalados
        d1, d2, d3 = st.columns(3)
        with d1:
            fp = round(data['home_form']*100)
            fc = "#00ff88" if fp>=60 else ("#ffcc44" if fp>=40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">🏠 Forma {ht} (últ.5)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fc}">{fp}%</div>
                <div style="font-size:.82em;color:#aaa">⚽ {data['home_gf']} anotados · 🛡️ {data['home_ga']} recibidos/pj</div>
                <div style="font-size:.8em;color:#666;font-family:'Space Mono'">{data['home_results']}</div>
            </div>""", unsafe_allow_html=True)
        with d2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">⚔️ H2H (últ.10)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:#ffcc44">{data['h2h_hw']}–{data['h2h_dr']}–{data['h2h_aw']}</div>
                <div style="font-size:.82em;color:#aaa">{ht} · Empates · {at}</div>
            </div>""", unsafe_allow_html=True)
        with d3:
            fpa = round(data['away_form']*100)
            fca = "#00ff88" if fpa>=60 else ("#ffcc44" if fpa>=40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">✈️ Forma {at} (últ.5)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fca}">{fpa}%</div>
                <div style="font-size:.82em;color:#aaa">⚽ {data['away_gf']} anotados · 🛡️ {data['away_ga']} recibidos/pj</div>
                <div style="font-size:.8em;color:#666;font-family:'Space Mono'">{data['away_results']}</div>
            </div>""", unsafe_allow_html=True)

        # Todos los mercados
        st.markdown("### 🎰 Predicciones por mercado")

        # 1X2
        st.markdown("#### 1X2 — Resultado final")
        p1, p2, p3 = st.columns(3)
        for col, label, val in [(p1,f"🏠 {ht}",pred['home_win_pct']),(p2,"🤝 Empate",pred['draw_pct']),(p3,f"✈️ {at}",pred['away_win_pct'])]:
            with col:
                st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">{label}</div><div class="value-neutral">{val}%</div></div>', unsafe_allow_html=True)

        # Goles esperados
        st.markdown("#### ⚽ Goles esperados (Modelo Poisson)")
        g1,g2,g3 = st.columns(3)
        g1.metric(f"xG {ht}", pred['exp_home_goals'])
        g2.metric(f"xG {at}", pred['exp_away_goals'])
        g3.metric("Total esperado", pred['exp_total_goals'])

        # Over/Under
        st.markdown("#### 📈 Over / Under")
        ou_cols = st.columns(3)
        for i,(label,over,under) in enumerate([
            ("1.5 goles", pred['over_15'], pred['under_15']),
            ("2.5 goles", pred['over_25'], pred['under_25']),
            ("3.5 goles", pred['over_35'], pred['under_35']),
        ]):
            with ou_cols[i]:
                st.markdown(f"""<div class="market-section">
                    <div style="font-weight:600;margin-bottom:8px">{label}</div>
                    <div>Over: <span style="color:#00ff88;font-family:'Space Mono'">{over}%</span></div>
                    <div>Under: <span style="color:#ff4466;font-family:'Space Mono'">{under}%</span></div>
                </div>""", unsafe_allow_html=True)

        # BTTS + HT + Hándicap
        bh1, bh2, bh3 = st.columns(3)
        with bh1:
            st.markdown(f"""<div class="market-section">
                <div style="font-weight:600;margin-bottom:8px">🔵 BTTS (Ambos anotan)</div>
                <div>Sí: <span style="color:#00ff88;font-family:'Space Mono'">{pred['btts_yes']}%</span></div>
                <div>No: <span style="color:#ff4466;font-family:'Space Mono'">{pred['btts_no']}%</span></div>
                <div style="font-size:.8em;color:#666;margin-top:6px">Hist. {ht}: {round(data['home_btts']*100)}% · {at}: {round(data['away_btts']*100)}%</div>
            </div>""", unsafe_allow_html=True)
        with bh2:
            st.markdown(f"""<div class="market-section">
                <div style="font-weight:600;margin-bottom:8px">⏱️ Resultado al Descanso</div>
                <div>{ht}: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ht_home_win']}%</span></div>
                <div>Empate: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ht_draw']}%</span></div>
                <div>{at}: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ht_away_win']}%</span></div>
            </div>""", unsafe_allow_html=True)
        with bh3:
            st.markdown(f"""<div class="market-section">
                <div style="font-weight:600;margin-bottom:8px">🎯 Hándicap Asiático</div>
                <div>{ht} -0.5: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ha_home_minus05']}%</span></div>
                <div>{at} +0.5: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ha_away_plus05']}%</span></div>
                <div>{ht} -1.5: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ha_home_minus15']}%</span></div>
                <div>{at} +1.5: <span style="color:#ffcc44;font-family:'Space Mono'">{pred['ha_away_plus15']}%</span></div>
            </div>""", unsafe_allow_html=True)

        # Doble Oportunidad
        st.markdown("#### 🔄 Doble Oportunidad")
        do1, do2, do3 = st.columns(3)
        for col, label, val in [(do1,f"1X ({ht}/Empate)",pred['do_1x']),(do2,f"X2 (Empate/{at})",pred['do_x2']),(do3,f"12 ({ht}/{at})",pred['do_12'])]:
            with col:
                st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">{label}</div><div class="value-neutral">{val}%</div></div>', unsafe_allow_html=True)

        # ── ANÁLISIS IA ──
        st.markdown("---")
        st.markdown("### 🤖 Análisis IA — Razonamiento del modelo")

        if st.button("✨ Generar análisis con IA", use_container_width=True):
            with st.spinner("Claude está analizando el partido..."):
                analysis = generate_ai_analysis(ht, at, data, pred, "")
            st.session_state["ai_analysis"] = analysis

        if "ai_analysis" in st.session_state:
            # Convertir **texto** en <b>texto</b> para HTML
            analysis_html = st.session_state["ai_analysis"].replace("**", "<b>", 1)
            count = 0
            result = ""
            for char in st.session_state["ai_analysis"]:
                result += char
            # Simple markdown to HTML
            text = st.session_state["ai_analysis"]
            import re
            text_html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            text_html = text_html.replace("\n\n", "</p><p>").replace("\n", "<br>")
            st.markdown(f'<div class="ai-analysis"><p>{text_html}</p></div>', unsafe_allow_html=True)

        # Últimos partidos
        with st.expander("📋 Últimos partidos"):
            lc1, lc2 = st.columns(2)
            for col, matches, tid, tname in [(lc1,data['home_matches'],home_team_id,ht),(lc2,data['away_matches'],away_team_id,at)]:
                with col:
                    st.markdown(f"**{tname}**")
                    shown = 0
                    for m in reversed(matches):
                        if m.get("status") != "FINISHED": continue
                        date = m["utcDate"][:10]
                        hn   = m["homeTeam"]["name"]
                        an   = m["awayTeam"]["name"]
                        s    = m.get("score",{}).get("fullTime",{})
                        hg   = s.get("home",0) or 0
                        ag   = s.get("away",0) or 0
                        ih   = m["homeTeam"]["id"] == tid
                        mg,rg = (hg,ag) if ih else (ag,hg)
                        em   = "🟢" if mg>rg else ("🟡" if mg==rg else "🔴")
                        ht_s = m.get("score",{}).get("halfTime",{})
                        htg  = f"({ht_s.get('home','?')}-{ht_s.get('away','?')} HT)" if ht_s else ""
                        st.markdown(f"`{date}` {em} **{hn} {hg}–{ag} {an}** {htg}")
                        shown += 1
                        if shown >= 7: break

        with st.expander("⚔️ H2H"):
            if data['h2h_matches']:
                for m in reversed(data['h2h_matches'][-8:]):
                    if m.get("status") != "FINISHED": continue
                    date = m["utcDate"][:10]
                    hn   = m["homeTeam"]["name"]
                    an   = m["awayTeam"]["name"]
                    s    = m.get("score",{}).get("fullTime",{})
                    hg   = s.get("home",0) or 0
                    ag   = s.get("away",0) or 0
                    st.markdown(f"`{date}` — **{hn} {hg}–{ag} {an}**")
            else:
                st.info("H2H no disponible.")

        with st.expander("📊 Tabla de posiciones"):
            with st.spinner("Cargando tabla..."):
                table = get_standings(football_api_key, COMP_CODE)
            if table:
                rows_t = [{"Pos":r["position"],"Equipo":r["team"]["name"],"PJ":r["playedGames"],
                           "G":r["won"],"E":r["draw"],"P":r["lost"],
                           "GF":r["goalsFor"],"GC":r["goalsAgainst"],"Pts":r["points"],
                           "Forma":r.get("form","")} for r in table]
                st.dataframe(pd.DataFrame(rows_t), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
#  TAB 2 — MOMIOS & EV
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 MOMIOS & VALOR ESPERADO</div>', unsafe_allow_html=True)

    if "pred" in st.session_state:
        pred = st.session_state["pred"]
        ht2  = st.session_state.get("home_team","Local")
        at2  = st.session_state.get("away_team","Visitante")
        my_home = pred['home_win_pct']
        my_draw = pred['draw_pct']
        my_away = pred['away_win_pct']
        st.markdown(f"#### 🎯 Predicción activa: **{ht2}** vs **{at2}**")
        pc1,pc2,pc3 = st.columns(3)
        pc1.metric(f"🏠 {ht2}", f"{my_home}%")
        pc2.metric("🤝 Empate", f"{my_draw}%")
        pc3.metric(f"✈️ {at2}", f"{my_away}%")
    else:
        st.warning("Primero analiza un partido en el Tab 🎯.")
        ht2,at2 = "Local","Visitante"
        pc1,pc2,pc3 = st.columns(3)
        my_home = pc1.number_input("Prob. Local (%)",    0.0,100.0,33.0)
        my_draw = pc2.number_input("Prob. Empate (%)",   0.0,100.0,33.0)
        my_away = pc3.number_input("Prob. Visitante (%)",0.0,100.0,34.0)
        pred = {"home_win_pct":my_home,"draw_pct":my_draw,"away_win_pct":my_away,
                "over_15":70,"under_15":30,"over_25":50,"under_25":50,
                "over_35":30,"under_35":70,"btts_yes":50,"btts_no":50,
                "ha_home_minus05":my_home,"ha_away_plus05":100-my_home,
                "ha_home_minus15":20,"ha_away_plus15":80,
                "ht_home_win":my_home*.7,"ht_draw":30,"ht_away_win":my_away*.7,
                "do_1x":my_home+my_draw,"do_x2":my_draw+my_away,"do_12":my_home+my_away}

    st.markdown("---")

    # Importar momios en vivo
    st.markdown("#### 📡 Momios en tiempo real")
    st.caption(f"Liga: **{selected_league_name}** · sport key: `{ODDS_SPORT}`")

    if st.button("🔄 Importar momios en vivo", use_container_width=True):
        if not odds_api_key:
            st.error("Ingresa tu The Odds API Key en el sidebar.")
        else:
            with st.spinner("Importando momios..."):
                live_data = get_live_odds(odds_api_key, ODDS_SPORT)
            if not live_data or not isinstance(live_data, list):
                st.warning("No hay momios en vivo para esta liga ahora mismo.")
            else:
                if "home_team" in st.session_state:
                    matched = extract_odds_for_match(live_data, st.session_state["home_team"], st.session_state["away_team"])
                    if matched:
                        st.session_state["casas"] = matched
                        st.success(f"✅ Momios importados de {len(matched)} casas para {ht2} vs {at2}")
                    else:
                        st.info(f"No se encontró '{ht2} vs {at2}' en los momios disponibles.")

                for game in live_data[:5]:
                    hn = game.get("home_team","")
                    an = game.get("away_team","")
                    with st.expander(f"📊 {hn} vs {an} — {game.get('commence_time','')[:10]}"):
                        rows_live = []
                        for bm in game.get("bookmakers",[])[:8]:
                            for mkt in bm.get("markets",[]):
                                if mkt["key"] == "h2h":
                                    oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                    rows_live.append({"Casa":bm["title"],"Local":oc.get(hn,"?"),"Empate":oc.get("Draw","?"),"Visita":oc.get(an,"?")})
                        if rows_live:
                            st.dataframe(pd.DataFrame(rows_live), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Tabla de momios
    st.markdown("#### 🏦 Casas de apuestas (1X2)")
    st.caption("Se rellenan automáticamente con los momios en vivo. También editables manualmente.")

    if "casas" not in st.session_state:
        st.session_state["casas"] = [
            {"nombre":"Caliente","local":240.0,"empate":230.0,"visita":-140.0},
            {"nombre":"Betcris", "local":220.0,"empate":240.0,"visita":-150.0},
            {"nombre":"Codere",  "local":250.0,"empate":220.0,"visita":-145.0},
            {"nombre":"Bet365",  "local":235.0,"empate":225.0,"visita":-142.0},
        ]

    for i, casa in enumerate(st.session_state["casas"]):
        cols = st.columns([2,1,1,1,0.4])
        with cols[0]: casa["nombre"] = st.text_input("Casa",   casa["nombre"],        key=f"cn_{i}")
        with cols[1]: casa["local"]  = st.number_input("Local",  float(casa["local"]),  key=f"cl_{i}", step=5.0)
        with cols[2]: casa["empate"] = st.number_input("Empate", float(casa["empate"]), key=f"ce_{i}", step=5.0)
        with cols[3]: casa["visita"] = st.number_input("Visita", float(casa["visita"]), key=f"cv_{i}", step=5.0)
        with cols[4]:
            if st.button("🗑", key=f"cd_{i}"):
                st.session_state["casas"].pop(i); st.rerun()

    if st.button("➕ Agregar casa"):
        st.session_state["casas"].append({"nombre":"Nueva","local":200.0,"empate":230.0,"visita":-160.0})
        st.rerun()

    st.markdown("---")

    # Mercados adicionales (momios manuales)
    st.markdown("#### 🎰 Mercados adicionales — Ingresa momios manualmente")
    st.caption("Aquí puedes ingresar los momios para Over/Under, BTTS y Hándicap para calcular EV en esos mercados también.")

    with st.expander("Over/Under — Ingresar momios"):
        ou1,ou2,ou3 = st.columns(3)
        with ou1:
            over15_odds  = st.number_input("Over 1.5",  value=-200.0, step=5.0, key="ou_o15")
            under15_odds = st.number_input("Under 1.5", value=160.0,  step=5.0, key="ou_u15")
        with ou2:
            over25_odds  = st.number_input("Over 2.5",  value=-110.0, step=5.0, key="ou_o25")
            under25_odds = st.number_input("Under 2.5", value=-110.0, step=5.0, key="ou_u25")
        with ou3:
            over35_odds  = st.number_input("Over 3.5",  value=160.0,  step=5.0, key="ou_o35")
            under35_odds = st.number_input("Under 3.5", value=-200.0, step=5.0, key="ou_u35")

    with st.expander("BTTS — Ingresar momios"):
        b1,b2 = st.columns(2)
        with b1: btts_yes_odds = st.number_input("Ambos anotan - SÍ", value=-120.0, step=5.0, key="btts_y")
        with b2: btts_no_odds  = st.number_input("Ambos anotan - NO", value=-110.0, step=5.0, key="btts_n")

    with st.expander("Hándicap Asiático — Ingresar momios"):
        ha1,ha2 = st.columns(2)
        with ha1:
            ha_hm05_odds = st.number_input(f"Local -0.5", value=-140.0, step=5.0, key="ha_hm05")
            ha_hm15_odds = st.number_input(f"Local -1.5", value=180.0,  step=5.0, key="ha_hm15")
        with ha2:
            ha_ap05_odds = st.number_input(f"Visitante +0.5", value=110.0,  step=5.0, key="ha_ap05")
            ha_ap15_odds = st.number_input(f"Visitante +1.5", value=-220.0, step=5.0, key="ha_ap15")

    st.markdown("---")

    if st.button("⚡ CALCULAR VALOR ESPERADO EN TODOS LOS MERCADOS", use_container_width=True, type="primary"):
        all_rows = []

        # 1X2
        for nombre_casa, american, my_prob, mercado in [
            *[(c["nombre"], c["local"],  my_home, f"🏠 {ht2} gana") for c in st.session_state["casas"]],
            *[(c["nombre"], c["empate"], my_draw, "🤝 Empate")      for c in st.session_state["casas"]],
            *[(c["nombre"], c["visita"], my_away, f"✈️ {at2} gana") for c in st.session_state["casas"]],
        ]:
            dec     = american_to_decimal(american)
            ev      = calc_ev(my_prob, dec)
            k       = min(kelly_criterion(my_prob, dec), max_kelly_pct)
            all_rows.append({"Categoría":"1X2","Casa":nombre_casa,"Mercado":mercado,
                             "Momio":f"{'+' if american>0 else ''}{int(american)}",
                             "Prob.Casa":f"{implied_prob(dec)}%","MiProb":f"{my_prob}%",
                             "EV":ev,"Kelly%":k,"Apostar($)":round((k/100)*bankroll,2)})

        # Mercados adicionales
        extra_markets = [
            ("Over/Under", "⚽ Over 1.5",   over15_odds,  pred.get("over_15",70)),
            ("Over/Under", "⚽ Under 1.5",  under15_odds, pred.get("under_15",30)),
            ("Over/Under", "⚽ Over 2.5",   over25_odds,  pred.get("over_25",50)),
            ("Over/Under", "⚽ Under 2.5",  under25_odds, pred.get("under_25",50)),
            ("Over/Under", "⚽ Over 3.5",   over35_odds,  pred.get("over_35",30)),
            ("Over/Under", "⚽ Under 3.5",  under35_odds, pred.get("under_35",70)),
            ("BTTS",       "✅ Ambos anotan Sí", btts_yes_odds, pred.get("btts_yes",50)),
            ("BTTS",       "❌ Ambos anotan No", btts_no_odds,  pred.get("btts_no",50)),
            ("Hándicap",   f"Local -0.5",    ha_hm05_odds,  pred.get("ha_home_minus05",50)),
            ("Hándicap",   f"Visitante +0.5",ha_ap05_odds,  pred.get("ha_away_plus05",50)),
            ("Hándicap",   f"Local -1.5",    ha_hm15_odds,  pred.get("ha_home_minus15",20)),
            ("Hándicap",   f"Visitante +1.5",ha_ap15_odds,  pred.get("ha_away_plus15",80)),
        ]
        for cat, mercado, american, my_prob in extra_markets:
            dec = american_to_decimal(american)
            ev  = calc_ev(my_prob, dec)
            k   = min(kelly_criterion(my_prob, dec), max_kelly_pct)
            all_rows.append({"Categoría":cat,"Casa":"(Manual)","Mercado":mercado,
                             "Momio":f"{'+' if american>0 else ''}{int(american)}",
                             "Prob.Casa":f"{implied_prob(dec)}%","MiProb":f"{my_prob}%",
                             "EV":ev,"Kelly%":k,"Apostar($)":round((k/100)*bankroll,2)})

        df   = pd.DataFrame(all_rows)
        best = df[df["EV"] >= (min_ev/100)].sort_values("EV", ascending=False)

        st.markdown("### 💡 Apuestas con valor — todos los mercados")
        if best.empty:
            st.warning(f"No hay apuestas con EV ≥ {min_ev}%.")
        else:
            for cat in best["Categoría"].unique():
                st.markdown(f"**{cat}**")
                for _, row in best[best["Categoría"]==cat].iterrows():
                    ev_pct = row["EV"] * 100
                    if ev_pct >= 10:   css,tc,em = "bet-row-positive","tag-green","🟢"
                    elif ev_pct >= 5:  css,tc,em = "bet-row-neutral","tag-yellow","🟡"
                    else:              css,tc,em = "bet-row-negative","tag-red","🔴"
                    st.markdown(f"""<div class="{css}">
                        <b>{em} {row['Casa']} — {row['Mercado']}</b>
                        &nbsp;<span class="tag {tc}">EV: {ev_pct:.1f}%</span>
                        &nbsp;<span class="tag {tc}">Kelly: {row['Kelly%']}%</span><br>
                        Momio: <span style="font-family:'Space Mono'">{row['Momio']}</span>
                        &emsp;Prob.casa: <b>{row['Prob.Casa']}</b>
                        &emsp;Mi prob.: <b>{row['MiProb']}</b>
                        &emsp;💰 Apostar: <b>${row['Apostar($)']:,.0f}</b>
                    </div>""", unsafe_allow_html=True)

        if not best.empty:
            top = best.iloc[0]
            st.session_state["calc_prefill"] = {
                "american": float(str(top["Momio"]).replace("+","")),
                "my_prob":  float(str(top["MiProb"]).replace("%",""))
            }
            st.info("💡 La mejor apuesta se cargó en la **Calculadora EV** (Tab 🧮)")

        st.markdown("---")
        st.markdown("#### 📋 Tabla completa")
        st.dataframe(df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA EV
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA DE VALOR ESPERADO</div>', unsafe_allow_html=True)

    prefill    = st.session_state.get("calc_prefill", {})
    default_am = prefill.get("american", 240.0)
    default_p  = prefill.get("my_prob",  28.0)
    if prefill: st.success("✅ Valores cargados automáticamente desde la mejor apuesta")

    c1,c2,c3 = st.columns(3)
    with c1: calc_am = st.number_input("Momio americano",    value=float(default_am), step=5.0)
    with c2: calc_p  = st.number_input("Mi probabilidad (%)", 0.0,100.0, float(default_p))
    with c3: calc_bk = st.number_input("Bankroll ($)",        min_value=100, value=bankroll, step=100)

    calc_dec     = american_to_decimal(calc_am)
    calc_impl    = implied_prob(calc_dec)
    calc_ev_v    = calc_ev(calc_p, calc_dec)
    calc_k       = min(kelly_criterion(calc_p, calc_dec), max_kelly_pct)
    calc_apuesta = round((calc_k/100)*calc_bk, 2)

    r1,r2,r3,r4 = st.columns(4)
    ev_color = "#00ff88" if calc_ev_v > 0 else "#ff4466"
    with r1: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Decimal</div><div style="font-family:Space Mono;font-size:1.3em">{calc_dec}</div></div>', unsafe_allow_html=True)
    with r2: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Prob. Implícita</div><div style="font-family:Space Mono;font-size:1.3em">{calc_impl}%</div></div>', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Expected Value</div><div style="font-family:Space Mono;font-size:1.3em;color:{ev_color}">{calc_ev_v*100:.1f}%</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Apostar (Kelly)</div><div style="font-family:Space Mono;font-size:1.3em;color:#00ff88">${calc_apuesta:,.0f}</div></div>', unsafe_allow_html=True)

    if calc_ev_v > 0.10:  st.success(f"✅ Buena apuesta — EV +{calc_ev_v*100:.1f}%")
    elif calc_ev_v > 0:   st.warning(f"🟡 Valor marginal (+{calc_ev_v*100:.1f}%)")
    else:                  st.error(f"❌ Sin valor ({calc_ev_v*100:.1f}%)")

    st.markdown("#### 📈 Simulación de rentabilidad")
    n_bets = st.slider("Número de apuestas", 10, 500, 100)
    bk_sim = [calc_bk]; current = calc_bk; p = calc_p/100
    for _ in range(n_bets):
        stake = (calc_k/100)*current
        current += stake*(calc_dec-1) if random.random()<p else -stake
        bk_sim.append(round(current,2))
    sim_df = pd.DataFrame({"#":range(n_bets+1),"Bankroll":bk_sim})
    st.line_chart(sim_df.set_index("#"))
    final = bk_sim[-1]; chg = round(((final-calc_bk)/calc_bk)*100,1)
    (st.success if final>calc_bk else st.error)(f"Resultado simulado: ${final:,.0f} ({'+' if chg>0 else ''}{chg}%)")
    st.caption("⚠️ Simulación aleatoria ilustrativa.")

# ══════════════════════════════════════════════
#  TAB 4 — GUÍA
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📖 GUÍA</div>', unsafe_allow_html=True)
    st.markdown(f"""
### 🔧 APIs necesarias

| API | Para qué | Precio | Registro |
|-----|----------|--------|---------|
| **football-data.org** | Fixtures, stats, H2H, tabla | Gratis | football-data.org/client/register |
| **The Odds API** | Momios en tiempo real | 500 req/mes gratis | the-odds-api.com |

### 📋 Flujo de uso

1. **Tab 🎯** → Selecciona liga y partido → Analizar automáticamente
2. **Tab 🎯** → Presiona "Generar análisis con IA" para el razonamiento en texto
3. **Tab 📡** → Importa momios en vivo → Se rellenan automáticamente
4. **Tab 📡** → Ingresa momios de Over/Under, BTTS, Hándicap → Calcular EV
5. **Tab 🧮** → La mejor apuesta se carga sola para simular

### 🎰 Mercados analizados

| Mercado | Cómo se calcula |
|---------|----------------|
| **1X2** | Forma reciente + H2H + Goles + Ventaja local |
| **Over/Under** | Distribución de Poisson con xG esperados |
| **BTTS** | Poisson (prob. de anotar) + historial real |
| **Hándicap Asiático** | Matriz de probabilidades Poisson |
| **Resultado HT** | Historial de resultados al descanso |
| **Doble Oportunidad** | Combinación de probabilidades 1X2 |

### 🤖 Análisis IA
El botón "Generar análisis con IA" usa **Claude** para leer todos los datos estadísticos del partido y escribir un análisis en español explicando por qué el modelo arroja esos porcentajes, qué factores favorecen a cada equipo, y qué apuesta destaca como interesante.

---
⚠️ *Herramienta de análisis estadístico. Las apuestas conllevan riesgo real. Juega responsablemente.*
    """)
