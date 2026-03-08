import streamlit as st
import pandas as pd
import requests
import random
import json
import math
import io
from datetime import datetime, timedelta

try:
    from understatapi import UnderstatClient
    UNDERSTAT_AVAILABLE = True
except ImportError:
    UNDERSTAT_AVAILABLE = False

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
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": {"code": "PL",  "odds_key": "soccer_epl",                    "understat": "EPL",         "clubelo": True},
    "🇪🇸 La Liga":              {"code": "PD",  "odds_key": "soccer_spain_la_liga",           "understat": "La_liga",     "clubelo": True},
    "🇩🇪 Bundesliga":           {"code": "BL1", "odds_key": "soccer_germany_bundesliga",      "understat": "Bundesliga",  "clubelo": True},
    "🇮🇹 Serie A":              {"code": "SA",  "odds_key": "soccer_italy_serie_a",           "understat": "Serie_A",     "clubelo": True},
    "🇫🇷 Ligue 1":              {"code": "FL1", "odds_key": "soccer_france_ligue_1",          "understat": "Ligue_1",     "clubelo": True},
    "🏆 Champions League":      {"code": "CL",  "odds_key": "soccer_uefa_champs_league",      "understat": None,          "clubelo": True},
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

def get_live_odds(api_key, sport_key, markets="h2h"):
    url    = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": api_key, "regions": "us,eu,uk",
              "markets": markets, "oddsFormat": "american"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if r.status_code != 200:
            # Devolver el error como dict para mostrarlo en la UI
            return {"error_code": r.status_code, "message": data.get("message", str(data))}
        return data
    except Exception as e:
        return {"error_code": "timeout", "message": str(e)}

def normalize_to_american(price):
    """Recibe precio raw (decimal o americano) y devuelve entero americano."""
    price = float(price)
    if price >= 100 or price <= -100:
        return int(price)
    if 1.01 < price < 15.0:
        if price >= 2.0:
            return int(round((price - 1) * 100))
        else:
            return int(round(-100 / (price - 1)))
    return int(price)

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
                raw_local  = oc.get(hn)
                raw_empate = oc.get("Draw")
                raw_visita = oc.get(an)
                if raw_local:
                    casa["local"]  = normalize_to_american(raw_local)
                if raw_empate:
                    casa["empate"] = normalize_to_american(raw_empate)
                if raw_visita:
                    casa["visita"] = normalize_to_american(raw_visita)
        if casa["local"] is not None:
            casas.append(casa)
    return casas

# ─────────────────────────────────────────────
#  UNDERSTAT — xG real con fuzzy matching
#  No depende de mapeos manuales de nombres
# ─────────────────────────────────────────────

def _fuzzy_score(a, b):
    """
    Score de similitud entre dos nombres de equipos (0-100).
    Compara palabras clave ignorando sufijos genéricos.
    """
    import re
    stopwords = {"fc", "cf", "ac", "afc", "sc", "bc", "de", "del", "la", "el",
                 "los", "club", "real", "atletico", "deportivo", "cd", "ud", "rc",
                 "rcd", "ca", "sd", "cp", "ss", "as", "us", "og", "rb", "vfb",
                 "tsg", "fsv", "ogc", "losc"}
    def tokenize(s):
        s = s.lower()
        # Normalizar acentos
        s = re.sub(r"[áàä]","a", re.sub(r"[éèë]","e", re.sub(r"[íìï]","i",
              re.sub(r"[óòö]","o", re.sub(r"[úùü]","u", s)))))
        # Expandir abreviaciones tipo "M.Gladbach" → "mgladbach"
        s = re.sub(r"\b([a-z])\.([a-z])", r"\1\2", s)
        tokens = {w for w in re.split(r"[\W_]+", s) if len(w) > 2 and w not in stopwords}
        return tokens

    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0
    intersection = ta & tb
    union = ta | tb
    jaccard = len(intersection) / len(union)
    bonus   = 0.3 if ta.issubset(tb) or tb.issubset(ta) else 0
    return round(min(1.0, jaccard + bonus) * 100)

@st.cache_data(ttl=3600)
def get_understat_xg(team_name, understat_league, season=None):
    """
    Obtiene xG real desde Understat.
    Método correcto: get_match_data(season=...) — no get_team_stats.
    Nombres en Understat usan guión bajo: Manchester_United, Real_Madrid, etc.
    """
    if not UNDERSTAT_AVAILABLE or not understat_league:
        return []

    # Temporada automática
    now = datetime.utcnow()
    year = now.year
    season_current = year - 1 if now.month < 8 else year
    seasons_to_try = [season_current, season_current - 1] if season is None else [season, season - 1]

    def name_variants(name):
        import unicodedata
        def strip_accents(s):
            return ''.join(c for c in unicodedata.normalize('NFD', s)
                          if unicodedata.category(c) != 'Mn')
        # Variantes específicas: football-data.org → Understat (con guión bajo)
        known = {
            # La Liga
            "Valencia CF":               ["Valencia"],
            "Deportivo Alavés":          ["Alaves"],
            "Club Atlético de Madrid":   ["Atletico_Madrid"],
            "Real Betis Balompié":       ["Real_Betis"],
            "Real Sociedad de Fútbol":   ["Real_Sociedad"],
            "Rayo Vallecano de Madrid":  ["Rayo_Vallecano"],
            "RC Celta de Vigo":          ["Celta_Vigo"],
            "RCD Espanyol de Barcelona": ["Espanyol"],
            "RCD Mallorca":              ["Mallorca"],
            "CA Osasuna":                ["Osasuna"],
            "UD Las Palmas":             ["Las_Palmas"],
            "CD Leganés":                ["Leganes"],
            "Real Valladolid CF":        ["Valladolid"],
            "Athletic Club":             ["Athletic_Club"],
            "Villarreal CF":             ["Villarreal"],
            "Sevilla FC":                ["Sevilla"],
            "Getafe CF":                 ["Getafe"],
            "Girona FC":                 ["Girona"],
            "Deportivo Alavés":          ["Alaves"],
            # Premier League
            "Arsenal FC":                ["Arsenal"],
            "Chelsea FC":                ["Chelsea"],
            "Liverpool FC":              ["Liverpool"],
            "Manchester City FC":        ["Manchester_City"],
            "Manchester United FC":      ["Manchester_United"],
            "Tottenham Hotspur FC":      ["Tottenham"],
            "Newcastle United FC":       ["Newcastle_United"],
            "Aston Villa FC":            ["Aston_Villa"],
            "West Ham United FC":        ["West_Ham"],
            "Brighton & Hove Albion FC": ["Brighton"],
            "Wolverhampton Wanderers FC":["Wolverhampton_Wanderers"],
            "Nottingham Forest FC":      ["Nottingham_Forest"],
            "Fulham FC":                 ["Fulham"],
            "Brentford FC":              ["Brentford"],
            "Crystal Palace FC":         ["Crystal_Palace"],
            "Everton FC":                ["Everton"],
            "Leicester City FC":         ["Leicester"],
            "AFC Bournemouth":           ["Bournemouth"],
            "Southampton FC":            ["Southampton"],
            "Ipswich Town FC":           ["Ipswich"],
            # Bundesliga
            "FC Bayern München":         ["Bayern_Munich"],
            "Borussia Dortmund":         ["Borussia_Dortmund"],
            "Bayer 04 Leverkusen":       ["Bayer_Leverkusen"],
            "RB Leipzig":                ["RasenBallsport_Leipzig"],
            "VfB Stuttgart":             ["Stuttgart"],
            "Eintracht Frankfurt":       ["Eintracht_Frankfurt"],
            "SC Freiburg":               ["Freiburg"],
            "Borussia Mönchengladbach":  ["Borussia_Moenchengladbach"],
            "FC Augsburg":               ["Augsburg"],
            "Werder Bremen":             ["Werder_Bremen"],
            "TSG 1899 Hoffenheim":       ["Hoffenheim"],
            "1. FC Union Berlin":        ["Union_Berlin"],
            "1. FSV Mainz 05":           ["Mainz"],
            "FC St. Pauli 1910":         ["St._Pauli"],
            # Serie A
            "AC Milan":                  ["AC_Milan"],
            "FC Internazionale Milano":  ["Internazionale"],
            "Juventus FC":               ["Juventus"],
            "AS Roma":                   ["Roma"],
            "SS Lazio":                  ["Lazio"],
            "SSC Napoli":                ["Napoli"],
            "ACF Fiorentina":            ["Fiorentina"],
            "Atalanta BC":               ["Atalanta"],
            "Torino FC":                 ["Torino"],
            "Bologna FC 1909":           ["Bologna"],
            "Udinese Calcio":            ["Udinese"],
            "Genoa CFC":                 ["Genoa"],
            "Cagliari Calcio":           ["Cagliari"],
            "US Lecce":                  ["Lecce"],
            "Hellas Verona FC":          ["Hellas_Verona"],
            "Empoli FC":                 ["Empoli"],
            "Venezia FC":                ["Venezia"],
            # Ligue 1
            "Paris Saint-Germain FC":    ["Paris_Saint_Germain"],
            "Olympique de Marseille":    ["Marseille"],
            "Olympique Lyonnais":        ["Lyon"],
            "AS Monaco FC":              ["Monaco"],
            "Stade Rennais FC 1901":     ["Rennes"],
            "LOSC Lille":                ["Lille"],
            "RC Lens":                   ["Lens"],
            "OGC Nice":                  ["Nice"],
            "Stade Brestois 29":         ["Brest"],
            "RC Strasbourg Alsace":      ["Strasbourg"],
            "Toulouse FC":               ["Toulouse"],
            "FC Nantes":                 ["Nantes"],
            "Stade de Reims":            ["Reims"],
            "AS Saint-Étienne":          ["Saint_Etienne"],
            "AJ Auxerre":                ["Auxerre"],
            "Le Havre AC":               ["Le_Havre"],
            "Montpellier HSC":           ["Montpellier"],
            "Angers SCO":                ["Angers"],
        }
        variants = []
        # 1. Variantes conocidas primero (más confiables)
        for v in known.get(name, []):
            if v not in variants: variants.append(v)
        # 2. Nombre limpio sin sufijos, con guión bajo
        clean = (name.replace(" FC","").replace(" CF","").replace(" AC","")
                 .replace(" AFC","").replace(" BC","").replace(" SC","")
                 .replace(" SL","").replace(" Balompié","").replace(" Balompie","")
                 .replace(" de Fútbol","").replace(" de Futbol","").strip())
        clean_u = clean.replace(" ", "_")
        if clean_u not in variants: variants.append(clean_u)
        # 3. Sin acentos + guión bajo
        clean_no_acc = strip_accents(clean).replace(" ", "_")
        if clean_no_acc not in variants: variants.append(clean_no_acc)
        # 4. Nombre original con guión bajo (fallback)
        orig_u = name.replace(" ", "_")
        if orig_u not in variants: variants.append(orig_u)
        return variants

    variants = name_variants(team_name)
    errors = []

    for s in seasons_to_try:
        for variant in variants:
            try:
                with UnderstatClient() as understat:
                    team_data = understat.team(team=variant).get_match_data(season=str(s))
                if not team_data or len(team_data) < 5:
                    errors.append(f"{variant}/{s}: vacío ({len(team_data) if team_data else 0})")
                    continue
                matches = []
                raw_keys = None
                for m in team_data:
                    try:
                        # Guardar claves del primer partido para debug
                        if raw_keys is None:
                            raw_keys = {k: str(m.get(k))[:60] for k in m.keys()}

                        # get_match_data puede tener distintos formatos según versión
                        # Intentar detectar is_home por todos los campos posibles
                        side = m.get("side") or m.get("h_a") or ""
                        if side in ("h", "home"):
                            is_home = True
                        elif side in ("a", "away"):
                            is_home = False
                        else:
                            # Comparar título del equipo local con variant
                            h_title = str(m.get("h", {}).get("title", ""))
                            is_home = (h_title == variant or
                                       h_title.replace("_"," ").lower() == variant.replace("_"," ").lower())

                        if is_home:
                            xg_team = float(m.get("xG", {}).get("h", 0) or 0)
                            xg_opp  = float(m.get("xG", {}).get("a", 0) or 0)
                            g_team  = int(m.get("goals", {}).get("h", 0) or 0)
                        else:
                            xg_team = float(m.get("xG", {}).get("a", 0) or 0)
                            xg_opp  = float(m.get("xG", {}).get("h", 0) or 0)
                            g_team  = int(m.get("goals", {}).get("a", 0) or 0)

                        matches.append({
                            "xg":       xg_team,
                            "xga":      xg_opp,
                            "is_home":  is_home,
                            "goals":    g_team,
                            "date":     m.get("datetime", ""),
                            "result":   m.get("result", ""),
                            "_variant": variant,
                            "_season":  s,
                        })
                    except:
                        continue
                if raw_keys:
                    errors.append(f"DEBUG_KEYS/{variant}: {raw_keys}")
                if len(matches) >= 5:
                    # Filtrar partidos futuros (xG=0 y fecha futura)
                    from datetime import datetime as dt
                    today_str = dt.utcnow().strftime("%Y-%m-%d")
                    played = [m for m in matches
                              if not (m["xg"] == 0 and m["xga"] == 0
                                      and m["date"][:10] > today_str)]
                    if len(played) >= 5:
                        return played[-14:]
                    else:
                        errors.append(f"{variant}/{s}: solo {len(played)} partidos jugados de {len(matches)}")
                        continue
                else:
                    errors.append(f"{variant}/{s}: solo {len(matches)} partidos procesados")
            except Exception as e:
                errors.append(f"{variant}/{s}: {type(e).__name__}: {str(e)[:80]}")
                continue

    return [{"_errors": errors}] if errors else []

def calc_xg_averages(understat_matches):
    """
    Calcula xG promedio como local y visitante.
    Retorna: (xgf_home, xga_home, xgf_away, xga_away, n_home, n_away)
    Si no hay suficientes partidos de un venue, usa el promedio global.
    """
    if not understat_matches:
        return None, None, None, None, 0, 0

    h_xgf = h_xga = h_w = 0.0
    a_xgf = a_xga = a_w = 0.0
    g_xgf = g_xga = g_w = 0.0  # global

    for i, m in enumerate(reversed(understat_matches)):
        w = max(0.25, 0.58 - i * 0.03)
        g_xgf += m["xg"]  * w
        g_xga += m["xga"] * w
        g_w   += w
        if m["is_home"]:
            h_xgf += m["xg"]  * w
            h_xga += m["xga"] * w
            h_w   += w
        else:
            a_xgf += m["xg"]  * w
            a_xga += m["xga"] * w
            a_w   += w

    # Global fallback
    global_xgf = round(g_xgf / g_w, 3) if g_w > 0 else None
    global_xga = round(g_xga / g_w, 3) if g_w > 0 else None

    # Venue split — si no hay datos de un venue, usar global
    xgf_h = round(h_xgf / h_w, 3) if h_w > 0 else global_xgf
    xga_h = round(h_xga / h_w, 3) if h_w > 0 else global_xga
    xgf_a = round(a_xgf / a_w, 3) if a_w > 0 else global_xgf
    xga_a = round(a_xga / a_w, 3) if a_w > 0 else global_xga

    return xgf_h, xga_h, xgf_a, xga_a, round(h_w, 1), round(a_w, 1)

def calc_xg_overperformance(understat_matches, last_n=6):
    """
    Detecta si el equipo está sobreperformando/subperformando su xG.
    Retorna factor de regresión: <1 si anota más de lo esperado (va a bajar), >1 si menos.
    """
    if not understat_matches or len(understat_matches) < 3:
        return 1.0
    recent = understat_matches[-last_n:]
    total_xg    = sum(m["xg"] for m in recent)
    total_goals = sum(m["goals"] for m in recent)
    if total_xg < 0.5:
        return 1.0
    ratio = total_goals / total_xg
    # Si anota 40% más que su xG → regresión hacia la media (factor 0.85-1.0)
    # Si anota 40% menos → factor 1.0-1.15 (esperamos que suba)
    regression = max(0.80, min(1.20, 1.0 / max(ratio, 0.3)))
    return round(regression, 3)

# ─────────────────────────────────────────────
#  CLUBELO — ELO dinámico
# ─────────────────────────────────────────────

CLUBELO_NAME_MAP = {
    # Premier League — nombres exactos football-data.org → clubelo slug
    "Arsenal FC":                  "Arsenal",
    "Chelsea FC":                  "Chelsea",
    "Manchester City FC":          "ManCity",
    "Manchester United FC":        "ManUtd",
    "Liverpool FC":                "Liverpool",
    "Tottenham Hotspur FC":        "Tottenham",
    "Newcastle United FC":         "Newcastle",
    "Aston Villa FC":              "AstonVilla",
    "West Ham United FC":          "WestHam",
    "Brighton & Hove Albion FC":   "Brighton",
    "Wolverhampton Wanderers FC":  "Wolves",
    "Nottingham Forest FC":        "Nottingham",
    "Fulham FC":                   "Fulham",
    "Brentford FC":                "Brentford",
    "Crystal Palace FC":           "CrystalPalace",
    "Everton FC":                  "Everton",
    "Leicester City FC":           "Leicester",
    "AFC Bournemouth":             "Bournemouth",
    "Southampton FC":              "Southampton",
    "Ipswich Town FC":             "Ipswich",
    "Leeds United FC":             "Leeds",
    "Burnley FC":                  "Burnley",
    # La Liga — nombres exactos football-data.org
    "FC Barcelona":                "Barcelona",
    "Real Madrid CF":              "RealMadrid",
    "Club Atlético de Madrid":     "Atletico",
    "Athletic Club":               "Athletic",
    "Real Sociedad de Fútbol":     "Sociedad",
    "Villarreal CF":               "Villarreal",
    "Real Betis Balompié":         "Betis",
    "Sevilla FC":                  "Sevilla",
    "Valencia CF":                 "Valencia",
    "Girona FC":                   "Girona",
    "Deportivo Alavés":            "Alaves",
    "Rayo Vallecano de Madrid":    "RayoVallecano",
    "CA Osasuna":                  "Osasuna",
    "RC Celta de Vigo":            "Celta",
    "Getafe CF":                   "Getafe",
    "RCD Espanyol de Barcelona":   "Espanyol",
    "RCD Mallorca":                "Mallorca",
    "UD Las Palmas":               "LasPalmas",
    "CD Leganés":                  "Leganes",
    "Real Valladolid CF":          "Valladolid",
    # Bundesliga
    "Borussia Dortmund":           "Dortmund",
    "FC Bayern München":           "Bayern",
    "Bayer 04 Leverkusen":         "Leverkusen",
    "RB Leipzig":                  "Leipzig",
    "VfB Stuttgart":               "Stuttgart",
    "Eintracht Frankfurt":         "Frankfurt",
    "SC Freiburg":                 "Freiburg",
    "Borussia Mönchengladbach":    "Moenchengladbach",
    "FC Augsburg":                 "Augsburg",
    "Werder Bremen":               "Werder",
    "TSG 1899 Hoffenheim":         "Hoffenheim",
    "1. FC Union Berlin":          "UnionBerlin",
    "1. FSV Mainz 05":             "Mainz",
    "FC St. Pauli 1910":           "StPauli",
    "Holstein Kiel":               "Kiel",
    # Serie A
    "AC Milan":                    "Milan",
    "FC Internazionale Milano":    "Inter",
    "Juventus FC":                 "Juventus",
    "AS Roma":                     "Roma",
    "SS Lazio":                    "Lazio",
    "SSC Napoli":                  "Napoli",
    "ACF Fiorentina":              "Fiorentina",
    "Atalanta BC":                 "Atalanta",
    "Torino FC":                   "Torino",
    "Bologna FC 1909":             "Bologna",
    "Udinese Calcio":              "Udinese",
    "Genoa CFC":                   "Genoa",
    "Cagliari Calcio":             "Cagliari",
    "US Lecce":                    "Lecce",
    "Hellas Verona FC":            "Verona",
    "Empoli FC":                   "Empoli",
    # Ligue 1
    "Paris Saint-Germain FC":      "PSG",
    "Olympique de Marseille":      "Marseille",
    "Olympique Lyonnais":          "Lyon",
    "AS Monaco FC":                "Monaco",
    "Stade Rennais FC 1901":       "Rennes",
    "LOSC Lille":                  "Lille",
    "RC Lens":                     "Lens",
    "OGC Nice":                    "Nice",
    "Stade Brestois 29":           "Brest",
    "RC Strasbourg Alsace":        "Strasbourg",
    "Toulouse FC":                 "Toulouse",
    "FC Nantes":                   "Nantes",
    "Stade de Reims":              "Reims",
    "AS Saint-Étienne":            "StEtienne",
    "AJ Auxerre":                  "Auxerre",
}

@st.cache_data(ttl=86400)
def get_clubelo(team_name):
    """
    Obtiene el ELO actual desde api.clubelo.com.
    Intenta múltiples variantes del nombre si la primera falla.
    """
    # Intentar primero con el mapa exacto
    slugs_to_try = []
    if team_name in CLUBELO_NAME_MAP:
        slugs_to_try.append(CLUBELO_NAME_MAP[team_name])
    # Fallbacks: quitar espacios, quitar sufijos comunes
    clean = team_name.replace(" FC","").replace(" CF","").replace(" AC","").strip()
    slugs_to_try.append(clean.replace(" ",""))
    slugs_to_try.append(team_name.replace(" ",""))

    for slug in slugs_to_try:
        try:
            r = requests.get(f"http://api.clubelo.com/{slug}", timeout=8)
            if r.status_code != 200 or not r.text.strip():
                continue
            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                continue
            last = lines[-1].split(",")
            if len(last) > 4:
                return float(last[4])
        except:
            continue
    return None

def elo_win_probability(elo_home, elo_away, home_advantage=65):
    """
    Probabilidad de victoria basada en diferencia de ELO.
    home_advantage: puntos extra al local (estándar FIFA/clubelo = ~65 pts).
    Fórmula estándar de ELO: P = 1 / (1 + 10^(-diff/400))
    """
    if elo_home is None or elo_away is None:
        return None, None, None
    diff = (elo_home + home_advantage) - elo_away
    p_home_nodraw = 1 / (1 + 10 ** (-diff / 400))
    p_away_nodraw = 1 - p_home_nodraw
    # Estimación de empate: ~28% promedio calibrado con backtest (real: 26.8%)
    closeness = 1 - abs(p_home_nodraw - 0.5) * 2  # 1 = 50/50, 0 = dominante
    draw_prob  = 0.28 * (0.65 + closeness * 0.35)
    home_prob  = p_home_nodraw * (1 - draw_prob)
    away_prob  = p_away_nodraw * (1 - draw_prob)
    total = home_prob + draw_prob + away_prob
    return (round(home_prob/total*100, 1),
            round(draw_prob/total*100, 1),
            round(away_prob/total*100, 1))

# ─────────────────────────────────────────────
#  FATIGA POR CALENDARIO
# ─────────────────────────────────────────────

def calc_fatigue(matches, match_date_str):
    """
    Calcula un factor de fatiga basado en cuántos partidos jugó el equipo
    en los últimos 7, 14 y 21 días antes del partido analizado.
    Retorna multiplicador: 1.0 = sin fatiga, <1.0 = fatigado.
    Basado en estudios: cada partido extra en 7 días reduce rendimiento ~3-5%.
    """
    try:
        match_date = datetime.strptime(match_date_str[:10], "%Y-%m-%d")
    except:
        return 1.0, 0, 0

    finished = [m for m in matches if m.get("status") == "FINISHED"]
    games_7d = games_14d = 0

    for m in finished:
        try:
            d = datetime.strptime(m["utcDate"][:10], "%Y-%m-%d")
            delta = (match_date - d).days
            if 0 < delta <= 7:  games_7d  += 1
            if 0 < delta <= 14: games_14d += 1
        except:
            continue

    # Penalización: +1 partido en 7 días → -4% rendimiento (máx -15%)
    penalty = min(0.15, games_7d * 0.04 + max(0, games_14d - 2) * 0.02)
    return round(1.0 - penalty, 3), games_7d, games_14d

# ─────────────────────────────────────────────
#  LINE MOVEMENT — momios como señal
# ─────────────────────────────────────────────

def market_implied_probs(casas):
    """
    Calcula probabilidades implícitas promedio del mercado (sin margen).
    Retorna (p_home, p_draw, p_away) o None si no hay datos.
    """
    if not casas:
        return None, None, None

    home_probs = draw_probs = away_probs = 0.0
    n = 0
    for c in casas:
        try:
            d_h = (c["local"]/100+1)  if c["local"]  > 0 else (100/abs(c["local"])+1)
            d_d = (c["empate"]/100+1) if c["empate"] > 0 else (100/abs(c["empate"])+1)
            d_a = (c["visita"]/100+1) if c["visita"] > 0 else (100/abs(c["visita"])+1)
            raw_h, raw_d, raw_a = 1/d_h, 1/d_d, 1/d_a
            total_margin = raw_h + raw_d + raw_a
            home_probs  += raw_h / total_margin
            draw_probs  += raw_d / total_margin
            away_probs  += raw_a / total_margin
            n += 1
        except:
            continue

    if n == 0:
        return None, None, None
    return round(home_probs/n*100, 1), round(draw_probs/n*100, 1), round(away_probs/n*100, 1)

def blend_with_market(model_h, model_d, model_a, market_h, market_d, market_a,
                       model_weight=0.65, market_weight=0.35):
    """
    Combina probabilidades del modelo con las del mercado.
    El mercado agrega información implícita de analistas profesionales.
    Peso por defecto: 65% modelo propio, 35% mercado.
    """
    if market_h is None:
        return model_h, model_d, model_a
    blended_h = round(model_h * model_weight + market_h * market_weight, 1)
    blended_d = round(model_d * model_weight + market_d * market_weight, 1)
    blended_a = round(100 - blended_h - blended_d, 1)
    return blended_h, blended_d, blended_a



# Pesos de decaimiento temporal: el partido más reciente vale más
# Ventana de 10 partidos: [0.55, 0.52, 0.49, 0.46, 0.43, 0.40, 0.37, 0.34, 0.31, 0.28]
DECAY_WEIGHTS = [max(0.25, 0.58 - i * 0.03) for i in range(10)]

def _finished(m):
    return m.get("status") == "FINISHED"

def _score(m):
    s = m.get("score", {}).get("fullTime", {})
    return s.get("home", 0) or 0, s.get("away", 0) or 0

def _ht_score(m):
    s = m.get("score", {}).get("halfTime", {})
    return s.get("home", 0) or 0, s.get("away", 0) or 0

def calc_form_weighted(matches, team_id, n=7):
    """
    Forma ponderada por tiempo: partidos recientes pesan más.
    Usa los últimos n partidos terminados.
    Retorna valor 0-1 donde 1 = perfecto.
    """
    finished = [m for m in matches if _finished(m)][-n:]
    if not finished: return 0.5
    total_w = pts_w = 0.0
    for i, m in enumerate(reversed(finished)):
        hg, ag = _score(m)
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        pts = 3 if mg > rg else (1 if mg == rg else 0)
        w = DECAY_WEIGHTS[i]
        pts_w   += pts * w
        total_w += 3   * w
    return round(pts_w / total_w, 4) if total_w else 0.5

def get_recent_results_str(matches, team_id, n=5):
    res = []
    for m in [m for m in matches if _finished(m)][-n:]:
        hg, ag = _score(m)
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        res.append("W" if mg > rg else ("D" if mg == rg else "L"))
    return " ".join(res)

def calc_venue_split(matches, team_id):
    """
    Calcula GF/GA separado para partidos de LOCAL y de VISITANTE.
    Retorna: (home_gf, home_ga, away_gf, away_ga, home_n, away_n)
    Ponderados temporalmente.
    """
    h_gf = h_ga = h_w = 0.0
    a_gf = a_ga = a_w = 0.0
    finished = [m for m in matches if _finished(m)]

    for i, m in enumerate(reversed(finished)):
        hg, ag = _score(m)
        is_home = m.get("homeTeam", {}).get("id") == team_id
        w = DECAY_WEIGHTS[min(i, len(DECAY_WEIGHTS)-1)]
        if is_home:
            h_gf += hg * w; h_ga += ag * w; h_w += w
        else:
            a_gf += ag * w; a_ga += hg * w; a_w += w

    # Fallback: si no hay datos de un contexto usar el global
    global_gf = (h_gf + a_gf) / max(h_w + a_w, 0.01)
    global_ga = (h_ga + a_ga) / max(h_w + a_w, 0.01)

    home_gf = (h_gf / h_w) if h_w > 0 else global_gf
    home_ga = (h_ga / h_w) if h_w > 0 else global_ga
    away_gf = (a_gf / a_w) if a_w > 0 else global_gf
    away_ga = (a_ga / a_w) if a_w > 0 else global_ga

    return (round(home_gf,3), round(home_ga,3),
            round(away_gf,3), round(away_ga,3),
            round(h_w,1),     round(a_w,1))

def calc_avg_goals_fd(matches, team_id):
    """Promedio global ponderado (retrocompat)."""
    _, _, _, _, hw, aw = calc_venue_split(matches, team_id)
    finished = [m for m in matches if _finished(m)]
    gf = ga = w = 0.0
    for i, m in enumerate(reversed(finished)):
        hg, ag = _score(m)
        ih = m.get("homeTeam", {}).get("id") == team_id
        wt = DECAY_WEIGHTS[min(i, len(DECAY_WEIGHTS)-1)]
        gf += (hg if ih else ag) * wt
        ga += (ag if ih else hg) * wt
        w  += wt
    if not w: return 1.2, 1.2
    return round(gf/w, 3), round(ga/w, 3)

def calc_btts_rate(matches):
    """BTTS ponderado temporalmente."""
    btts = total = 0.0
    finished = [m for m in matches if _finished(m)]
    for i, m in enumerate(reversed(finished)):
        hg, ag = _score(m)
        w = DECAY_WEIGHTS[min(i, len(DECAY_WEIGHTS)-1)]
        total += w
        if hg > 0 and ag > 0: btts += w
    return round(btts / total, 4) if total else 0.5

def calc_over_rate(matches, threshold=2.5):
    """Over rate ponderado."""
    over = total = 0.0
    finished = [m for m in matches if _finished(m)]
    for i, m in enumerate(reversed(finished)):
        hg, ag = _score(m)
        w = DECAY_WEIGHTS[min(i, len(DECAY_WEIGHTS)-1)]
        total += w
        if hg + ag > threshold: over += w
    return round(over / total, 4) if total else 0.5

def calc_halftime_rate(matches, team_id):
    hw = hd = hl = 0.0
    total = 0.0
    finished = [m for m in matches if _finished(m)]
    for i, m in enumerate(reversed(finished)):
        hg, ag = _ht_score(m)
        ih = m.get("homeTeam", {}).get("id") == team_id
        mg, rg = (hg, ag) if ih else (ag, hg)
        w = DECAY_WEIGHTS[min(i, len(DECAY_WEIGHTS)-1)]
        total += w
        if mg > rg: hw += w
        elif mg == rg: hd += w
        else: hl += w
    if not total: return 0.33, 0.33, 0.34
    return round(hw/total,4), round(hd/total,4), round(hl/total,4)

def calc_h2h_stats_fd(h2h_matches, home_id, away_id):
    hw = aw = dr = 0
    for m in h2h_matches:
        if not _finished(m): continue
        hg, ag   = _score(m)
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

def calc_goal_timing(matches, team_id):
    """
    Estima qué fracción de goles se marcan en cada mitad.
    Retorna (frac_1st_half_scored, frac_1st_half_conceded).
    Útil para afinar el modelo HT.
    """
    g1_for = g2_for = g1_ag = g2_ag = 0.0
    for m in matches:
        if not _finished(m): continue
        ft_h, ft_a = _score(m)
        ht_h, ht_a = _ht_score(m)
        ih = m.get("homeTeam", {}).get("id") == team_id
        # goles del equipo en cada mitad
        ft_team  = ft_h if ih else ft_a
        ht_team  = ht_h if ih else ht_a
        ft_rival = ft_a if ih else ft_h
        ht_rival = ht_a if ih else ht_h
        g1_for += ht_team;  g2_for += max(0, ft_team  - ht_team)
        g1_ag  += ht_rival; g2_ag  += max(0, ft_rival - ht_rival)
    total_for = g1_for + g2_for
    total_ag  = g1_ag  + g2_ag
    frac_for = round(g1_for / total_for, 3) if total_for else 0.45
    frac_ag  = round(g1_ag  / total_ag,  3) if total_ag  else 0.45
    return frac_for, frac_ag

# ─────────────────────────────────────────────
#  MODELO v2 — POISSON + DIXON-COLES + VENUE SPLIT
# ─────────────────────────────────────────────
#
#  Mejoras sobre v1:
#  1. VENUE SPLIT: índices calculados en casa y fuera por separado.
#  2. PONDERACIÓN TEMPORAL: partidos recientes tienen más peso.
#  3. DIXON-COLES: corrección para scores bajos (0-0, 1-0, 0-1, 1-1)
#     que Poisson independiente sobreestima/subestima.
#  4. REGRESIÓN A LA MEDIA: equipos con pocos partidos se acercan al
#     promedio de liga para no exagerar índices con muestras pequeñas.
#  5. GOAL TIMING: fracción de goles por mitad para afinar HT.
#  6. H2H CONTEXTUAL: solo ajusta si hay ≥5 partidos en el mismo contexto.

LEAGUE_AVG_HOME = 1.35
LEAGUE_AVG_AWAY = 1.10
# Parámetro Dixon-Coles (típico en literatura: 0.13)
DC_RHO = 0.18  # aumentado para corregir subestimación de empates (backtest: 22.3% pred vs 26.8% real)

def temperature_scale(p, T, cap=None, floor=None):
    """
    Temperature Scaling — calibración post-entrenamiento estándar en ML.
    Comprime probabilidades extremas hacia el centro para evitar sobreconfianza.
    T > 1  →  aplana (más incertidumbre). T < 1  →  agudiza (más confianza).
    Calibrado con backtest de 723 partidos de La Liga 2023-2024:
      1X2:    T=1.7  (el modelo sobreestimaba favoritos fuertes ~10%)
      Over25: T=2.0 + cap 65%  (nunca más de 65% Over — techo empírico real)
      BTTS:   T=1.5 + cap 70%  (subestimación moderada corregida)
      Resto:  T=1.5  (conservador)
    """
    if p <= 0.001: return 0.1
    if p >= 0.999: return 99.0
    import math
    logit = math.log(p / (1 - p))
    scaled = 1 / (1 + math.exp(-logit / T))
    if cap   is not None: scaled = min(scaled, cap)
    if floor is not None: scaled = max(scaled, floor)
    return scaled

def ts_pct(p_pct, T, cap_pct=None, floor_pct=None):
    """Wrapper que trabaja en porcentajes (0-100) en lugar de (0-1)."""
    result = temperature_scale(p_pct / 100, T,
                               cap   = cap_pct   / 100 if cap_pct   else None,
                               floor = floor_pct / 100 if floor_pct else None)
    return round(result * 100, 1)

def poisson_prob(lam, k):
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * lam**k) / math.factorial(min(k, 20))

def dixon_coles_tau(i, j, xg_h, xg_a, rho=DC_RHO):
    """
    Factor de corrección Dixon-Coles para scores bajos.
    Ajusta la probabilidad de 0-0, 1-0, 0-1, 1-1.
    Fuera de esos 4 casos tau = 1 (sin cambio).
    """
    if   i == 0 and j == 0: return 1 - xg_h * xg_a * rho
    elif i == 1 and j == 0: return 1 + xg_a * rho
    elif i == 0 and j == 1: return 1 + xg_h * rho
    elif i == 1 and j == 1: return 1 - rho
    else:                   return 1.0

def build_matrix_dc(xg_h, xg_a, max_goals=9):
    """
    Matriz de Poisson bivariada con corrección Dixon-Coles.
    Normalizada para que sume 1.
    """
    M = [[poisson_prob(xg_h, i) * poisson_prob(xg_a, j) *
          dixon_coles_tau(i, j, xg_h, xg_a)
          for j in range(max_goals)] for i in range(max_goals)]
    total = sum(M[i][j] for i in range(max_goals) for j in range(max_goals))
    if total > 0:
        M = [[M[i][j]/total for j in range(max_goals)] for i in range(max_goals)]
    return M

def matrix_sum(m, condition):
    mg = len(m)
    return sum(m[i][j] for i in range(mg) for j in range(mg) if condition(i, j))

def bayesian_index(observed, n_matches, prior=1.0, confidence_n=6):
    """
    Regresión a la media bayesiana.
    Con pocos partidos (n<6), el índice se acerca al prior (=1.0 = media liga).
    Con muchos partidos, el índice observado domina.
    confidence_n: partidos necesarios para confiar plenamente en los datos.
    """
    w_obs   = min(1.0, n_matches / confidence_n)
    w_prior = 1.0 - w_obs
    return observed * w_obs + prior * w_prior


# ─────────────────────────────────────────────
#  CLIMA — Open-Meteo (gratis, sin API key)
# ─────────────────────────────────────────────

# Coordenadas de estadios principales por equipo
STADIUM_COORDS = {
    # ── Premier League — nombres exactos football-data.org ──
    "Arsenal FC":                  (51.5549,  -0.1084),
    "Arsenal":                     (51.5549,  -0.1084),
    "Chelsea FC":                  (51.4816,  -0.1910),
    "Chelsea":                     (51.4816,  -0.1910),
    "Manchester City FC":          (53.4831,  -2.2004),
    "Manchester City":             (53.4831,  -2.2004),
    "Manchester United FC":        (53.4631,  -2.2913),
    "Manchester United":           (53.4631,  -2.2913),
    "Liverpool FC":                (53.4308,  -2.9608),
    "Liverpool":                   (53.4308,  -2.9608),
    "Tottenham Hotspur FC":        (51.6044,  -0.0665),
    "Tottenham Hotspur":           (51.6044,  -0.0665),
    "Newcastle United FC":         (54.9756,  -1.6218),
    "Newcastle United":            (54.9756,  -1.6218),
    "Aston Villa FC":              (52.5090,  -1.8847),
    "Aston Villa":                 (52.5090,  -1.8847),
    "West Ham United FC":          (51.5386,   0.0164),
    "West Ham United":             (51.5386,   0.0164),
    "Brighton & Hove Albion FC":   (50.8618,  -0.0837),
    "Brighton & Hove Albion":      (50.8618,  -0.0837),
    "Wolverhampton Wanderers FC":  (52.5900,  -2.1302),
    "Wolverhampton Wanderers":     (52.5900,  -2.1302),
    "Nottingham Forest FC":        (52.9399,  -1.1328),
    "Nottingham Forest":           (52.9399,  -1.1328),
    "Fulham FC":                   (51.4749,  -0.2217),
    "Fulham":                      (51.4749,  -0.2217),
    "Brentford FC":                (51.4882,  -0.2886),
    "Brentford":                   (51.4882,  -0.2886),
    "Crystal Palace FC":           (51.3983,  -0.0855),
    "Crystal Palace":              (51.3983,  -0.0855),
    "Everton FC":                  (53.4388,  -2.9661),
    "Everton":                     (53.4388,  -2.9661),
    "Leicester City FC":           (52.6204,  -1.1422),
    "Leicester City":              (52.6204,  -1.1422),
    "AFC Bournemouth":             (50.7352,  -1.8383),
    "Bournemouth":                 (50.7352,  -1.8383),
    "Southampton FC":              (50.9058,  -1.3914),
    "Southampton":                 (50.9058,  -1.3914),
    "Ipswich Town FC":             (52.0544,   1.1446),
    "Ipswich Town":                (52.0544,   1.1446),
    "Sunderland AFC":              (54.9148,  -1.3879),
    "Leeds United FC":             (53.7775,  -1.5724),
    "Burnley FC":                  (53.7892,  -2.2300),
    "Sheffield United FC":         (53.3703,  -1.4705),
    "Luton Town FC":               (51.8836,  -0.4316),
    # ── La Liga — nombres EXACTOS football-data.org ──
    "FC Barcelona":                (41.3809,   2.1228),
    "Real Madrid CF":              (40.4531,  -3.6883),
    "Club Atlético de Madrid":     (40.4361,  -3.5995),
    "Athletic Club":               (43.2641,  -2.9494),
    "Real Sociedad de Fútbol":     (43.3015,  -1.9732),
    "Villarreal CF":               (39.9444,  -0.1031),
    "Real Betis Balompié":         (37.3561,  -5.9820),
    "Sevilla FC":                  (37.3841,  -5.9705),
    "Valencia CF":                 (39.4748,  -0.3583),
    "Girona FC":                   (41.9807,   2.8218),
    "Deportivo Alavés":            (42.8467,  -2.6831),
    "Rayo Vallecano de Madrid":    (40.3916,  -3.6567),
    "CA Osasuna":                  (42.7964,  -1.6366),
    "RC Celta de Vigo":            (42.2119,  -8.7399),
    "Getafe CF":                   (40.3255,  -3.7199),
    "RCD Espanyol de Barcelona":   (41.3480,   2.0751),
    "RCD Mallorca":                (39.5900,   2.6608),
    "UD Las Palmas":               (28.1003, -15.4369),
    "CD Leganés":                  (40.3200,  -3.7642),
    "Real Valladolid CF":          (41.6528,  -4.7288),
    # ── Bundesliga ──
    "Borussia Dortmund":           (51.4926,   7.4517),
    "FC Bayern München":           (48.2188,  11.6248),
    "Bayern Munich":               (48.2188,  11.6248),
    "Bayer 04 Leverkusen":         (51.0383,   7.0022),
    "RB Leipzig":                  (51.3457,  12.3484),
    "VfB Stuttgart":               (48.7924,   9.2325),
    "Eintracht Frankfurt":         (50.0686,   8.6456),
    "SC Freiburg":                 (47.9872,   7.8934),
    "Borussia Mönchengladbach":    (51.1742,   6.3853),
    "FC Augsburg":                 (48.3237,  10.8861),
    "Werder Bremen":               (53.0664,   8.8378),
    "TSG 1899 Hoffenheim":         (49.2380,   8.8892),
    "1. FC Union Berlin":          (52.4574,  13.5678),
    "1. FC Heidenheim 1846":       (48.6829,  10.1549),
    "SV Darmstadt 98":             (49.8537,   8.6527),
    "1. FSV Mainz 05":             (49.9839,   8.2244),
    "FC St. Pauli 1910":           (53.5543,   9.9682),
    "Holstein Kiel":               (54.3773,  10.1346),
    # ── Serie A ──
    "AC Milan":                    (45.4781,   9.1240),
    "Inter Milan":                 (45.4781,   9.1240),
    "FC Internazionale Milano":    (45.4781,   9.1240),
    "Juventus FC":                 (45.1096,   7.6413),
    "AS Roma":                     (41.9341,  12.4547),
    "SS Lazio":                    (41.9341,  12.4547),
    "SSC Napoli":                  (40.8279,  14.1931),
    "ACF Fiorentina":              (43.7805,  11.2820),
    "Atalanta BC":                 (45.7085,   9.6801),
    "Torino FC":                   (45.0408,   7.6508),
    "Bologna FC 1909":             (44.4929,  11.3097),
    "Udinese Calcio":              (46.0806,  13.2025),
    "Genoa CFC":                   (44.4169,   8.9513),
    "Cagliari Calcio":             (39.1960,   9.1359),
    "US Lecce":                    (40.3614,  18.1747),
    "Hellas Verona FC":            (45.4312,  10.9770),
    "Empoli FC":                   (43.7196,  10.9516),
    "Venezia FC":                  (45.4733,  12.3151),
    "Como 1907":                   (45.8126,   9.0762),
    "Parma Calcio 1913":           (44.7993,  10.3343),
    "Monza":                       (45.5844,   9.2713),
    # ── Ligue 1 ──
    "Paris Saint-Germain FC":      (48.8414,   2.2530),
    "Paris Saint-Germain":         (48.8414,   2.2530),
    "Olympique de Marseille":      (43.2697,   5.3957),
    "Olympique Lyonnais":          (45.7653,   4.9824),
    "AS Monaco FC":                (43.7272,   7.4153),
    "AS Monaco":                   (43.7272,   7.4153),
    "Stade Rennais FC 1901":       (48.1073,  -1.7139),
    "Stade Rennais FC":            (48.1073,  -1.7139),
    "LOSC Lille":                  (50.6120,   3.1302),
    "RC Lens":                     (50.4328,   2.8228),
    "OGC Nice":                    (43.7052,   7.1921),
    "Stade Brestois 29":           (48.3897,  -4.4892),
    "Montpellier HSC":             (43.6215,   3.8132),
    "RC Strasbourg Alsace":        (48.5600,   7.7558),
    "Toulouse FC":                 (43.5832,   1.4344),
    "FC Nantes":                   (47.2553,  -1.5258),
    "Stade de Reims":              (49.2469,   4.0264),
    "Le Havre AC":                 (49.4935,   0.1073),
    "Angers SCO":                  (47.4651,  -0.5483),
    "Saint-Étienne":               (45.4603,   4.3906),
    "AS Saint-Étienne":            (45.4603,   4.3906),
    "AJ Auxerre":                  (47.7979,   3.5695),
}

@st.cache_data(ttl=1800)
def get_match_weather(team_name, match_date_str):
    """
    Obtiene el clima pronosticado. Open-Meteo: gratis, sin API key.
    Retorna dict con: temp_c, precipitation_mm, wind_kmh, condition
    """
    coords = STADIUM_COORDS.get(team_name)
    if not coords:
        return {"error": f"estadio_no_mapeado:{team_name}"}
    lat, lon = coords
    try:
        date_only = match_date_str[:10]  # "2026-03-15"
        match_dt  = datetime.strptime(date_only, "%Y-%m-%d")
        today     = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        days_out  = (match_dt - today).days
        if days_out < 0 or days_out > 10:
            return {"error": f"fecha_fuera_rango:{date_only} (days_out={days_out})"}

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":      lat,
            "longitude":     lon,
            "hourly":        "temperature_2m,precipitation,wind_speed_10m,weather_code",
            "forecast_days": min(days_out + 2, 10),
            "timezone":      "UTC",   # UTC fijo para que el prefijo siempre coincida
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return {"error": f"http_{r.status_code}"}
        data = r.json()

        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        precs = data["hourly"]["precipitation"]
        winds = data["hourly"]["wind_speed_10m"]
        codes = data["hourly"]["weather_code"]

        # Buscar ~16:00 UTC (hora típica de partido en Europa)
        # Intentar varias horas del día en orden de preferencia
        idx = None
        for hour in ["T16:00", "T15:00", "T14:00", "T13:00", "T17:00", "T18:00", "T12:00"]:
            target = date_only + hour
            idx = next((i for i, t in enumerate(times) if t == target), None)
            if idx is not None:
                break
        # Último fallback: cualquier slot del día
        if idx is None:
            idx = next((i for i, t in enumerate(times) if t.startswith(date_only)), None)
        if idx is None:
            return {"error": f"no_slot_para:{date_only}"}

        temp     = temps[idx]
        precip   = precs[idx]
        wind_kmh = winds[idx]
        wcode    = codes[idx]

        if   wcode in (0, 1):         condition = "☀️ Despejado"
        elif wcode in (2, 3):         condition = "⛅ Nublado"
        elif wcode in range(51, 68):  condition = "🌧️ Lluvia"
        elif wcode in range(71, 78):  condition = "❄️ Nieve"
        elif wcode in range(80, 83):  condition = "🌦️ Chubascos"
        elif wcode in range(95, 100): condition = "⛈️ Tormenta"
        else:                         condition = "🌥️ Variable"

        return {
            "temp_c":    round(temp, 1),
            "precip_mm": round(precip, 2),
            "wind_kmh":  round(wind_kmh, 1),
            "condition": condition,
            "wcode":     wcode,
        }
    except Exception as e:
        return {"error": str(e)}

def calc_weather_factor(weather):
    """
    Convierte condiciones climáticas en multiplicador de xG.
    Retorna (factor_goals, description) donde factor < 1 reduce goles.
    Basado en estudios de Herold et al. (2019) y análisis de 30k partidos.
    """
    if not weather:
        return 1.0, "Sin datos de clima"

    factor = 1.0
    notes  = []

    # Lluvia / Chubascos
    if weather["precip_mm"] >= 5.0:
        factor *= 0.88
        notes.append(f"Lluvia intensa ({weather['precip_mm']}mm) → -12% goles")
    elif weather["precip_mm"] >= 1.5:
        factor *= 0.94
        notes.append(f"Lluvia moderada ({weather['precip_mm']}mm) → -6% goles")
    elif weather["precip_mm"] >= 0.3:
        factor *= 0.97
        notes.append(f"Lluvia leve ({weather['precip_mm']}mm) → -3% goles")

    # Viento
    if weather["wind_kmh"] >= 50:
        factor *= 0.90
        notes.append(f"Viento muy fuerte ({weather['wind_kmh']} km/h) → -10% goles")
    elif weather["wind_kmh"] >= 35:
        factor *= 0.95
        notes.append(f"Viento fuerte ({weather['wind_kmh']} km/h) → -5% goles")

    # Temperatura extrema
    if weather["temp_c"] >= 32:
        factor *= 0.91
        notes.append(f"Calor extremo ({weather['temp_c']}°C) → -9% goles (fatiga 2ª mitad)")
    elif weather["temp_c"] >= 27:
        factor *= 0.96
        notes.append(f"Calor ({weather['temp_c']}°C) → -4% goles")
    elif weather["temp_c"] <= -2:
        factor *= 0.93
        notes.append(f"Frío extremo ({weather['temp_c']}°C) → -7% goles")
    elif weather["temp_c"] <= 3:
        factor *= 0.97
        notes.append(f"Frío ({weather['temp_c']}°C) → -3% goles")

    desc = " | ".join(notes) if notes else "☀️ Condiciones ideales (sin penalización)"
    return round(factor, 3), desc

# ─────────────────────────────────────────────
#  CALIBRACIÓN POR LIGA
#  Medias reales 2023-24 de goles por liga
# ─────────────────────────────────────────────

LEAGUE_CALIBRATION = {
    # avg_away mantenida en valores originales (cambiarlo cancela matemáticamente)
    # La ventaja local se controla con HOME_ADV_FACTOR / AWAY_DIS_FACTOR abajo
    "PL":  {"avg_home": 1.36, "avg_away": 1.10, "over25_base": 0.560, "btts_base": 0.545},
    "PD":  {"avg_home": 1.34, "avg_away": 1.09, "over25_base": 0.480, "btts_base": 0.500},
    "BL1": {"avg_home": 1.58, "avg_away": 1.30, "over25_base": 0.600, "btts_base": 0.580},
    "SA":  {"avg_home": 1.30, "avg_away": 1.04, "over25_base": 0.490, "btts_base": 0.490},
    "FL1": {"avg_home": 1.28, "avg_away": 1.07, "over25_base": 0.505, "btts_base": 0.500},
    "CL":  {"avg_home": 1.55, "avg_away": 1.08, "over25_base": 0.560, "btts_base": 0.535},
}

# Factores de ventaja local calibrados por liga
# Grid search sobre distribuciones reales 2022-2026 (fbref / football-data.org)
# HOME_ADV: multiplica xG del local. AWAY_DIS: multiplica xG del visitante.
# Calibrado para que la distribución promedio H/D/A del modelo matchee la realidad.
LEAGUE_ADV_FACTORS = {
    #          HOME_ADV  AWAY_DIS   (calibrado con dist. real H/D/A)
    "PL":  (    1.22,     0.99  ),  # H=44.6% D=25.2% A=30.2%  real: 44.8/24.3/30.9
    "PD":  (    1.16,     0.83  ),  # H=44.7% D=26.8% A=28.6%  real: 44.8/26.8/28.4
    "BL1": (    1.02,     0.83  ),  # H=42.9% D=25.9% A=31.1%  real: 43.0/25.9/31.1
    "SA":  (    1.10,     0.75  ),  # H=45.1% D=27.1% A=27.7%  real: 45.3/27.1/27.6
    "FL1": (    1.02,     0.73  ),  # H=43.9% D=27.7% A=28.4%  real: 44.0/27.6/28.4
    "CL":  (    1.08,     0.80  ),  # estimado — Champions tiene ventaja local menor
}

def calc_all_predictions(home_form, away_form, home_gf, away_gf,
                          home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr,
                          home_btts, away_btts, home_over25, away_over25,
                          home_ht_w, home_ht_d, home_ht_l,
                          away_ht_w, away_ht_d, away_ht_l,
                          is_clasico=False,
                          home_venue_gf=None, home_venue_ga=None,
                          away_venue_gf=None, away_venue_ga=None,
                          home_n=5, away_n=5,
                          home_ht_frac=0.45, home_ht_frac_ag=0.45,
                          away_ht_frac=0.45, away_ht_frac_ag=0.45,
                          home_xgf=None, home_xga=None,
                          away_xgf=None, away_xga=None,
                          home_xg_regression=1.0, away_xg_regression=1.0,
                          elo_home=None, elo_away=None,
                          home_fatigue=1.0, away_fatigue=1.0,
                          weather_factor=1.0,
                          league_avg_home=None, league_avg_away=None,
                          league_code="PL"):

    MG = 9

    # ── Calibración por liga ──
    cal = LEAGUE_CALIBRATION.get(league_code, LEAGUE_CALIBRATION["PL"])
    L_AVG_H = league_avg_home if league_avg_home else cal["avg_home"]
    L_AVG_A = league_avg_away if league_avg_away else cal["avg_away"]

    # ── Venue split ──
    hgf = home_venue_gf if home_venue_gf is not None else home_gf
    hga = home_venue_ga if home_venue_ga is not None else home_ga
    agf = away_venue_gf if away_venue_gf is not None else away_gf
    aga = away_venue_ga if away_venue_ga is not None else away_ga

    # ── xG real de Understat: blend dinámico según tamaño de muestra ──
    # Con más partidos, confiamos más en el xG real vs goles históricos
    home_xg_n  = len([1 for _ in range(home_n)])  # proxy
    away_xg_n  = len([1 for _ in range(away_n)])
    def xg_weight(n): return 0.50 if n < 6 else (0.70 if n < 10 else 0.80)
    hw = xg_weight(home_n); aw_w = xg_weight(away_n)
    if home_xgf is not None: hgf = home_xgf * hw    + hgf * (1-hw)
    if home_xga is not None: hga = home_xga * hw    + hga * (1-hw)
    if away_xgf is not None: agf = away_xgf * aw_w  + agf * (1-aw_w)
    if away_xga is not None: aga = away_xga * aw_w  + aga * (1-aw_w)

    # ── Índices ataque/defensa usando medias calibradas por liga ──
    raw_home_att = hgf / max(L_AVG_H, 0.5)
    raw_home_def = hga / max(L_AVG_A, 0.5)
    raw_away_att = agf / max(L_AVG_A, 0.5)
    raw_away_def = aga / max(L_AVG_H, 0.5)

    # ── Regresión bayesiana a la media ──
    home_att = bayesian_index(raw_home_att, home_n)
    home_def = bayesian_index(raw_home_def, home_n)
    away_att = bayesian_index(raw_away_att, away_n)
    away_def = bayesian_index(raw_away_def, away_n)

    home_att = max(0.35, min(2.8, home_att))
    home_def = max(0.35, min(2.8, home_def))
    away_att = max(0.35, min(2.8, away_att))
    away_def = max(0.35, min(2.8, away_def))

    # ── Forma ponderada — impacto reducido para no amplificar xG en exceso ──
    home_form_mult = 1.0 + (home_form - 0.5) * 0.16
    away_form_mult = 1.0 + (away_form - 0.5) * 0.16

    # ── H2H ──
    total_h2h = h2h_hw + h2h_aw + h2h_dr
    if total_h2h >= 5:
        home_h2h_mult = 1.0 + (h2h_hw / total_h2h - 0.45) * 0.14
        away_h2h_mult = 1.0 + (h2h_aw / total_h2h - 0.30) * 0.14
    else:
        home_h2h_mult = away_h2h_mult = 1.0

    # ── xG base del modelo Poisson con medias calibradas por liga ──
    xg_h = home_att * away_def * L_AVG_H * home_form_mult * home_h2h_mult
    xg_a = away_att * home_def * L_AVG_A * away_form_mult * away_h2h_mult

    # ── Regresión xG (sobreperformance) ──
    xg_h *= home_xg_regression
    xg_a *= away_xg_regression

    # ── Fatiga ──
    # Un equipo cansado ANOTA menos (su propio factor reduce su xG)
    xg_h *= home_fatigue
    xg_a *= away_fatigue

    # ── Ventaja local estructural por liga ──
    # Calibrado con distribuciones reales 2022-2026 por liga
    _adv = LEAGUE_ADV_FACTORS.get(league_code, LEAGUE_ADV_FACTORS["PL"])
    xg_h *= _adv[0]  # HOME_ADV
    xg_a *= _adv[1]  # AWAY_DIS

    # ── ELO — ajuste reducido para no sobreestimar xG en partidos muy dispares ──
    elo_home_p, elo_draw_p, elo_away_p = elo_win_probability(elo_home, elo_away)
    if elo_home_p is not None:
        HOME_ADV_ELO = 65
        elo_diff_factor = ((elo_home + HOME_ADV_ELO) - elo_away) / 400.0
        xg_h *= (1.0 + elo_diff_factor * 0.05)
        xg_a *= (1.0 - elo_diff_factor * 0.05)

    # ── Clima: afecta AMBOS xG por igual ──
    xg_h *= weather_factor
    xg_a *= weather_factor

    # ── Clásico ──
    if is_clasico:
        xg_h = xg_h * 0.85 + L_AVG_H * 0.15
        xg_a = xg_a * 0.85 + L_AVG_A * 0.15

    xg_h = round(max(0.25, min(3.5, xg_h)), 3)
    xg_a = round(max(0.25, min(3.5, xg_a)), 3)

    # ── Matriz Dixon-Coles ──
    M = build_matrix_dc(xg_h, xg_a, MG)

    # ── 1X2 ──
    hw_r = matrix_sum(M, lambda i,j: i > j)
    dr_r = matrix_sum(M, lambda i,j: i == j)
    aw_r = matrix_sum(M, lambda i,j: i < j)
    tot  = hw_r + dr_r + aw_r
    home_pct = round(hw_r / tot * 100, 1)
    draw_pct = round(dr_r / tot * 100, 1)
    away_pct = round(100 - home_pct - draw_pct, 1)

    # ── Over/Under ──
    over_15_dc = matrix_sum(M, lambda i,j: i+j >= 2) * 100
    over_25_dc = matrix_sum(M, lambda i,j: i+j >= 3) * 100
    over_35_dc = matrix_sum(M, lambda i,j: i+j >= 4) * 100

    # Blend Over 2.5 con historial real de equipos (40% Poisson, 60% historial)
    # Backtest: partidos que modelo veía como "cerrados" (20-30% Over) en realidad
    # tenían ~44-48% Over — el historial del equipo corrige esa subestimación
    over25_hist = (home_over25 + away_over25) / 2 * 100
    over_25_blended = over_25_dc * 0.40 + over25_hist * 0.60

    over_15  = round(over_15_dc, 1)
    over_25  = round(over_25_blended, 1)
    over_35  = round(over_35_dc, 1)
    under_15 = round(100 - over_15, 1)
    under_25 = round(100 - over_25, 1)
    under_35 = round(100 - over_35, 1)

    # ── BTTS ──
    btts_dc   = round(matrix_sum(M, lambda i,j: i > 0 and j > 0) * 100, 1)
    btts_hist = round((home_btts + away_btts) / 2 * 100, 1)
    # Blend: 25% Poisson, 75% historial real
    # Backtest: bucket 40% BTTS predecía 41% cuando real era 52% → historial domina
    # Nota: ganancia máxima empírica ~3% — límite estructural del modelo Poisson
    btts_yes  = round(btts_dc * 0.25 + btts_hist * 0.75, 1)
    btts_no   = round(100 - btts_yes, 1)

    # ── Hándicap Asiático ──
    ha_home_minus05 = round(matrix_sum(M, lambda i,j: i > j)    * 100, 1)
    ha_away_plus05  = round(100 - ha_home_minus05, 1)
    ha_home_minus15 = round(matrix_sum(M, lambda i,j: i-j >= 2) * 100, 1)
    ha_away_plus15  = round(100 - ha_home_minus15, 1)

    # ── HT: usar goal timing real si disponible ──
    # Fracción media de xG que cae en la 1ª mitad
    ht_frac_h = (home_ht_frac + away_ht_frac_ag) / 2   # local anota en 1ª
    ht_frac_a = (away_ht_frac + home_ht_frac_ag) / 2   # visita anota en 1ª
    # Clamp razonable: entre 35% y 55% de los goles en 1ª mitad
    ht_frac_h = max(0.35, min(0.55, ht_frac_h))
    ht_frac_a = max(0.35, min(0.55, ht_frac_a))

    xg_h_ht = xg_h * ht_frac_h
    xg_a_ht = xg_a * ht_frac_a
    M_ht = build_matrix_dc(xg_h_ht, xg_a_ht, 6)
    ht_hw = matrix_sum(M_ht, lambda i,j: i > j)
    ht_dr = matrix_sum(M_ht, lambda i,j: i == j)
    ht_aw = matrix_sum(M_ht, lambda i,j: i < j)
    ht_t  = ht_hw + ht_dr + ht_aw

    # Blend 60% Poisson-HT, 40% historial real HT
    ht_home_win = round((ht_hw/ht_t * 0.60 + home_ht_w * 0.40) * 100, 1)
    ht_draw_val = round((ht_dr/ht_t * 0.60 + (home_ht_d + away_ht_d)/2 * 0.40) * 100, 1)
    ht_away_win = round(max(0, 100 - ht_home_win - ht_draw_val), 1)

    # ── Temperature Scaling — calibración post-modelo ──
    # Corrige sobreconfianza en extremos detectada en backtest 723 partidos La Liga
    home_pct  = ts_pct(home_pct,  T=1.7)
    draw_pct  = ts_pct(draw_pct,  T=1.7)
    away_pct  = ts_pct(away_pct,  T=1.7)
    # Renormalizar 1X2 para que sumen exactamente 100
    _tot_1x2  = home_pct + draw_pct + away_pct
    home_pct  = round(home_pct  / _tot_1x2 * 100, 1)
    draw_pct  = round(draw_pct  / _tot_1x2 * 100, 1)
    away_pct  = round(100 - home_pct - draw_pct, 1)

    over_15   = ts_pct(over_15,  T=1.5, cap_pct=85.0, floor_pct=15.0)
    over_25   = ts_pct(over_25,  T=2.0, cap_pct=65.0, floor_pct=28.0)  # blend ya levanta los casos extremos
    over_35   = ts_pct(over_35,  T=1.5, cap_pct=55.0, floor_pct=10.0)
    under_15  = round(100 - over_15, 1)
    under_25  = round(100 - over_25, 1)
    under_35  = round(100 - over_35, 1)

    btts_yes  = ts_pct(btts_yes, T=1.5, cap_pct=70.0, floor_pct=33.0)  # floor subido: backtest mostró subestimación en rangos bajos
    btts_no   = round(100 - btts_yes, 1)

    ha_home_minus05 = ts_pct(ha_home_minus05, T=1.7)
    ha_away_plus05  = round(100 - ha_home_minus05, 1)
    ha_home_minus15 = ts_pct(ha_home_minus15, T=1.7)
    ha_away_plus15  = round(100 - ha_home_minus15, 1)

    ht_home_win = ts_pct(ht_home_win, T=1.5)
    ht_draw_val = ts_pct(ht_draw_val, T=1.5)
    ht_away_win = round(max(0, 100 - ht_home_win - ht_draw_val), 1)

    # ── Doble Oportunidad — recalcular con probs ya escaladas ──
    do_1x = round(home_pct + draw_pct, 1)
    do_x2 = round(draw_pct + away_pct, 1)
    do_12 = round(home_pct + away_pct, 1)

    return {
        "home_win_pct": home_pct, "draw_pct": draw_pct, "away_win_pct": away_pct,
        "exp_home_goals": xg_h, "exp_away_goals": xg_a, "exp_total_goals": round(xg_h+xg_a,2),
        "over_15": over_15, "under_15": under_15,
        "over_25": over_25, "under_25": under_25,
        "over_35": over_35, "under_35": under_35,
        "btts_yes": btts_yes, "btts_no": btts_no,
        "ha_home_minus05": ha_home_minus05, "ha_away_plus05": ha_away_plus05,
        "ha_home_minus15": ha_home_minus15, "ha_away_plus15": ha_away_plus15,
        "ht_home_win": ht_home_win, "ht_draw": ht_draw_val, "ht_away_win": ht_away_win,
        "do_1x": do_1x, "do_x2": do_x2, "do_12": do_12,
        "goal_diff_exp": round(xg_h - xg_a, 2),
        # Índices para UI y análisis IA
        "home_att_idx": round(home_att, 2), "home_def_idx": round(home_def, 2),
        "away_att_idx": round(away_att, 2), "away_def_idx": round(away_def, 2),
        "home_form_mult": round(home_form_mult, 3),
        "away_form_mult": round(away_form_mult, 3),
        "home_h2h_mult":  round(home_h2h_mult, 3),
        "away_h2h_mult":  round(away_h2h_mult, 3),
        # ELO
        "elo_home_p": elo_home_p, "elo_draw_p": elo_draw_p, "elo_away_p": elo_away_p,
        "elo_home": elo_home, "elo_away": elo_away,
    }

# ─────────────────────────────────────────────
#  ANÁLISIS IA (Claude API)
# ─────────────────────────────────────────────

def generate_ai_analysis(home_team, away_team, data, pred, anthropic_key):
    """Llama a Claude para generar el análisis explicativo."""
    prompt = f"""Eres un analista deportivo experto en apuestas de fútbol. Analiza el siguiente partido y explica en español, de forma clara y concisa, por qué el modelo arroja esos porcentajes. Sé directo, usa datos concretos, y menciona los factores clave que favorecen o perjudican a cada equipo.

PARTIDO: {home_team} (local) vs {away_team} (visitante)

DATOS ESTADÍSTICOS:
- Forma reciente {home_team} (últ.5): {round(data['home_form']*100)}% ({data.get('home_results','')}) → multiplicador forma: ×{pred.get('home_form_mult',1.0):.3f}
- Forma reciente {away_team} (últ.5): {round(data['away_form']*100)}% ({data.get('away_results','')}) → multiplicador forma: ×{pred.get('away_form_mult',1.0):.3f}
- {home_team}: índice ataque {pred.get('home_att_idx',1.0)} / índice defensa {pred.get('home_def_idx',1.0)} (1.0 = media de liga)
- {away_team}: índice ataque {pred.get('away_att_idx',1.0)} / índice defensa {pred.get('away_def_idx',1.0)} (1.0 = media de liga)
- {home_team} promedio goles: {data['home_gf']} anotados / {data['home_ga']} recibidos por partido
- {away_team} promedio goles: {data['away_gf']} anotados / {data['away_ga']} recibidos por partido
- H2H últimos partidos: {home_team} {data['h2h_hw']} victorias — {data['h2h_dr']} empates — {data['h2h_aw']} victorias {away_team}
- BTTS histórico {home_team}: {round(data.get('home_btts',0.5)*100)}% | {away_team}: {round(data.get('away_btts',0.5)*100)}%
- Over 2.5 histórico {home_team}: {round(data.get('home_over25',0.5)*100)}% | {away_team}: {round(data.get('away_over25',0.5)*100)}%

PREDICCIONES (modelo Poisson bivariado):
- xG esperados: {pred['exp_home_goals']} ({home_team}) — {pred['exp_away_goals']} ({away_team})
- Victoria local: {pred['home_win_pct']}% | Empate: {pred['draw_pct']}% | Victoria visitante: {pred['away_win_pct']}%
- Over 2.5: {pred['over_25']}% | BTTS: {pred['btts_yes']}%
- Hándicap {home_team} -0.5: {pred['ha_home_minus05']}% | -1.5: {pred['ha_home_minus15']}%

Escribe un análisis de 4-5 párrafos cortos que explique:
1. Por qué el modelo favorece a quien favorece — menciona los índices de ataque/defensa y la forma
2. Qué dice el H2H y qué peso tuvo en el resultado final
3. Por qué los xG son esos y qué implica para Over/Under y BTTS
4. Una apuesta que destaque como la más interesante según los datos
5. Un factor de riesgo o advertencia importante

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
    """Convierte momio americano a decimal. Detecta si ya es decimal."""
    a = float(a)
    # Si el valor es pequeño positivo (1.01–10.0), ya es decimal
    if 1.01 <= a <= 15.0 and not a.is_integer():
        return round(a, 4)
    # Americano positivo: +240 → 3.40
    if a >= 100:
        return round((a / 100) + 1, 4)
    # Americano negativo: -150 → 1.667
    if a <= -100:
        return round((100 / abs(a)) + 1, 4)
    # Valores raros intermedios (±10 a ±99): asumir decimal si >1, americano si <0
    if a > 0:
        return round(a, 4)  # ya decimal
    return 1.0  # fallback

def decimal_to_american(dec):
    """Convierte decimal a americano para mostrar en la UI."""
    dec = float(dec)
    if dec >= 2.0:
        return int(round((dec - 1) * 100))   # positivo: +240
    elif dec > 1.0:
        return int(round(-100 / (dec - 1)))   # negativo: -150
    return 0

def implied_prob(dec):
    return round((1 / dec) * 100, 2) if dec > 1 else 0

def calc_ev(my_prob_pct, dec_odds):
    return round((my_prob_pct/100 * dec_odds) - 1, 4)

def kelly_criterion(my_prob_pct, dec_odds):
    """Kelly puro — solo para uso interno. Usa smart_kelly para mostrar al usuario."""
    p = my_prob_pct / 100
    b = dec_odds - 1
    if b <= 0: return 0
    return max(0, ((b*p - (1-p)) / b) * 100)

def smart_kelly(my_prob_pct, dec_odds, market_type="1X2", ev=None, max_pct=10.0):
    """
    Kelly fraccionado ajustado por riesgo real de la apuesta.

    Factores:
    1. Kelly puro x fraccion base (25%) — nunca apostar el Kelly completo
    2. Volatilidad del momio: momios altos = mas varianza = menos %
    3. Tipo de mercado: Over/Under mas estable que 1X2
    4. Ventaja real (EV): EV pequeno puede ser ruido del modelo
    5. Cap absoluto configurado por el usuario

    Retorna: (kelly_pct, fraccion_pct, nivel_riesgo)
    """
    kelly_puro = kelly_criterion(my_prob_pct, dec_odds)
    if kelly_puro <= 0:
        return 0.0, 0.0, "Sin ventaja"

    # 1. Fraccion base — profesionales usan 25% del Kelly puro
    fraccion_base = 0.25

    # 2. Ajuste por volatilidad del momio
    prob_implicita = 1 / dec_odds
    if prob_implicita < 0.20:    # momio > +400 — muy arriesgado
        vol_factor = 0.50
    elif prob_implicita < 0.33:  # momio +200 a +400 — arriesgado
        vol_factor = 0.70
    elif prob_implicita < 0.50:  # momio +100 a +200 — moderado
        vol_factor = 0.85
    elif prob_implicita < 0.70:  # momio -100 a +100 — normal
        vol_factor = 1.00
    else:                        # momio < -230 — favorito claro
        vol_factor = 0.90

    # 3. Ajuste por tipo de mercado (calibracion historica del modelo)
    market_factors = {
        "Over/Under":        1.10,   # mas predecible estadisticamente
        "BTTS":              1.00,   # neutral
        "1X2":               0.85,   # dificil por el empate
        "Handicap":          0.90,   # similar a 1X2 sin empate
        "Doble oportunidad": 1.05,   # cubre 2 resultados
        "HT":                0.70,   # el menos confiable del modelo
    }
    mkt_factor = market_factors.get(market_type, 0.85)

    # 4. Ajuste por magnitud del EV
    ev_val = ev if ev is not None else 0.06
    if ev_val >= 0.20:    ev_factor = 1.15   # EV >= 20% — alta confianza
    elif ev_val >= 0.12:  ev_factor = 1.05   # EV 12-20%
    elif ev_val >= 0.06:  ev_factor = 1.00   # EV 6-12% — zona normal
    else:                 ev_factor = 0.75   # EV < 6% — puede ser ruido

    # Calculo final
    fraccion_final = fraccion_base * vol_factor * mkt_factor * ev_factor
    fraccion_final = round(min(fraccion_final, 0.50), 3)

    kelly_ajustado = kelly_puro * fraccion_final
    kelly_ajustado = round(min(kelly_ajustado, max_pct), 2)
    kelly_ajustado = max(0.0, kelly_ajustado)

    # Nivel de riesgo descriptivo
    if kelly_ajustado >= max_pct * 0.70:   riesgo = "⚠️ Alto"
    elif kelly_ajustado >= max_pct * 0.35: riesgo = "🟡 Medio"
    else:                                   riesgo = "🟢 Bajo"

    return kelly_ajustado, round(fraccion_final * 100, 0), riesgo

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
            st.session_state["match_date_str"] = sel["utcDate"]  # guardar para clima
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
            understat_league = league_cfg.get("understat")

            with st.spinner("Jalando datos de football-data.org..."):
                home_matches = get_team_matches(football_api_key, home_team_id, 12)
                away_matches = get_team_matches(football_api_key, away_team_id, 12)
                h2h_matches  = get_h2h(football_api_key, match_id) if match_id else []

            # ── Stats base ──
            home_form        = calc_form_weighted(home_matches, home_team_id)
            away_form        = calc_form_weighted(away_matches, away_team_id)
            home_gf, home_ga = calc_avg_goals_fd(home_matches, home_team_id)
            away_gf, away_ga = calc_avg_goals_fd(away_matches, away_team_id)
            h_vgf, h_vga, _, _, h_vn, _ = calc_venue_split(home_matches, home_team_id)
            _, _, a_vgf, a_vga, _, a_vn  = calc_venue_split(away_matches, away_team_id)
            h2h_hw, h2h_aw, h2h_dr = calc_h2h_stats_fd(h2h_matches, home_team_id, away_team_id)
            home_btts        = calc_btts_rate(home_matches)
            away_btts        = calc_btts_rate(away_matches)
            home_over25      = calc_over_rate(home_matches, 2.5)
            away_over25      = calc_over_rate(away_matches, 2.5)
            h_htw, h_htd, h_htl = calc_halftime_rate(home_matches, home_team_id)
            a_htw, a_htd, a_htl = calc_halftime_rate(away_matches, away_team_id)
            h_ht_frac, h_ht_frac_ag = calc_goal_timing(home_matches, home_team_id)
            a_ht_frac, a_ht_frac_ag = calc_goal_timing(away_matches, away_team_id)
            home_results = get_recent_results_str(home_matches, home_team_id)
            away_results = get_recent_results_str(away_matches, away_team_id)

            # ── Fecha del partido (para clima y fatiga) ──
            # Primero usar la fecha guardada al seleccionar el partido
            match_date_str = st.session_state.get("match_date_str", "")
            if not match_date_str and match_id:
                upcoming = get_upcoming_matches(football_api_key, COMP_CODE)
                for m in upcoming:
                    if m["id"] == match_id:
                        match_date_str = m["utcDate"]
                        break
            home_fatigue, home_g7, home_g14 = calc_fatigue(home_matches, match_date_str)
            away_fatigue, away_g7, away_g14 = calc_fatigue(away_matches, match_date_str)

            # ── xG real de Understat ──
            home_xgf = home_xga = away_xgf = away_xga = None
            home_xg_reg = away_xg_reg = 1.0
            home_understat = away_understat = []
            xg_debug = {}
            if understat_league and UNDERSTAT_AVAILABLE:
                with st.spinner("Jalando xG reales de Understat..."):
                    home_understat = get_understat_xg(home_team_name, understat_league)
                    away_understat = get_understat_xg(away_team_name, understat_league)
                xg_debug["home_name"]    = home_team_name
                xg_debug["away_name"]    = away_team_name
                xg_debug["home_matches"] = len([m for m in home_understat if "_errors" not in m])
                xg_debug["away_matches"] = len([m for m in away_understat if "_errors" not in m])
                home_errs = next((m["_errors"] for m in home_understat if "_errors" in m), None)
                away_errs = next((m["_errors"] for m in away_understat if "_errors" in m), None)
                if home_errs: xg_debug["home_errors"] = home_errs[:3]
                if away_errs: xg_debug["away_errors"] = away_errs[:3]
                # Limpiar errores antes de procesar
                home_understat = [m for m in home_understat if "_errors" not in m]
                away_understat = [m for m in away_understat if "_errors" not in m]
                if home_understat:
                    home_xgf, home_xga, _, _, _, _ = calc_xg_averages(home_understat)
                    home_xg_reg = calc_xg_overperformance(home_understat)
                    xg_debug["home_xgf"] = home_xgf
                    xg_debug["home_xga"] = home_xga
                if away_understat:
                    _, _, away_xgf, away_xga, _, _ = calc_xg_averages(away_understat)
                    away_xg_reg = calc_xg_overperformance(away_understat)
                    xg_debug["away_xgf"] = away_xgf
                    xg_debug["away_xga"] = away_xga
            elif not UNDERSTAT_AVAILABLE:
                xg_debug["error"] = "understatapi no instalado"

            # ── ELO de ClubElo ──
            elo_home_val = elo_away_val = None
            if league_cfg.get("clubelo"):
                with st.spinner("Jalando ratings ELO de ClubElo..."):
                    elo_home_val = get_clubelo(home_team_name)
                    elo_away_val = get_clubelo(away_team_name)

            # ── Line movement: blend con mercado ──
            # No requiere odds_api_key — funciona con momios importados manualmente también
            market_h = market_d = market_a = None
            casas_actuales = st.session_state.get("casas", [])
            if casas_actuales:  # ← QUITADO el requisito de odds_api_key
                market_h, market_d, market_a = market_implied_probs(casas_actuales)

            # ── Clima ──
            weather        = None
            weather_factor = 1.0
            weather_desc   = "Sin datos"
            weather_error  = None
            if match_date_str:
                with st.spinner("Jalando pronóstico del clima..."):
                    wx_result = get_match_weather(home_team_name, match_date_str)
                if wx_result and "error" not in wx_result:
                    weather       = wx_result
                    weather_factor, weather_desc = calc_weather_factor(weather)
                elif wx_result:
                    weather_error = wx_result.get("error", "desconocido")
            else:
                weather_error = "sin_fecha_partido"

            # ── Calibración por liga ──
            cal = LEAGUE_CALIBRATION.get(COMP_CODE, LEAGUE_CALIBRATION["PL"])

            pred = calc_all_predictions(
                home_form, away_form, home_gf, away_gf,
                home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr,
                home_btts, away_btts, home_over25, away_over25,
                h_htw, h_htd, h_htl, a_htw, a_htd, a_htl,
                is_clasico,
                home_venue_gf=h_vgf, home_venue_ga=h_vga,
                away_venue_gf=a_vgf, away_venue_ga=a_vga,
                home_n=max(3, h_vn), away_n=max(3, a_vn),
                home_ht_frac=h_ht_frac, home_ht_frac_ag=h_ht_frac_ag,
                away_ht_frac=a_ht_frac, away_ht_frac_ag=a_ht_frac_ag,
                home_xgf=home_xgf, home_xga=home_xga,
                away_xgf=away_xgf, away_xga=away_xga,
                home_xg_regression=home_xg_reg, away_xg_regression=away_xg_reg,
                elo_home=elo_home_val, elo_away=elo_away_val,
                home_fatigue=home_fatigue, away_fatigue=away_fatigue,
                weather_factor=weather_factor,
                league_avg_home=cal["avg_home"], league_avg_away=cal["avg_away"],
                league_code=COMP_CODE,
            )

            # ── Line movement: blend final con mercado ──
            if market_h is not None:
                blended_h, blended_d, blended_a = blend_with_market(
                    pred["home_win_pct"], pred["draw_pct"], pred["away_win_pct"],
                    market_h, market_d, market_a
                )
                pred["home_win_pct"] = blended_h
                pred["draw_pct"]     = blended_d
                pred["away_win_pct"] = blended_a
                pred["market_blend"] = True
            else:
                pred["market_blend"] = False

            pred["market_h"] = market_h
            pred["market_d"] = market_d
            pred["market_a"] = market_a

            auto_data = {
                "home_form": home_form, "away_form": away_form,
                "home_gf": home_gf, "home_ga": home_ga,
                "away_gf": away_gf, "away_ga": away_ga,
                "home_venue_gf": h_vgf, "home_venue_ga": h_vga,
                "away_venue_gf": a_vgf, "away_venue_ga": a_vga,
                "h2h_hw": h2h_hw, "h2h_aw": h2h_aw, "h2h_dr": h2h_dr,
                "home_btts": home_btts, "away_btts": away_btts,
                "home_over25": home_over25, "away_over25": away_over25,
                "home_results": home_results, "away_results": away_results,
                "home_matches": home_matches, "away_matches": away_matches,
                "h2h_matches": h2h_matches,
                # Nuevos
                "home_xgf": home_xgf, "home_xga": home_xga,
                "away_xgf": away_xgf, "away_xga": away_xga,
                "home_xg_reg": home_xg_reg, "away_xg_reg": away_xg_reg,
                "elo_home": elo_home_val, "elo_away": elo_away_val,
                "home_fatigue": home_fatigue, "away_fatigue": away_fatigue,
                "home_g7": home_g7, "away_g7": away_g7,
                "home_g14": home_g14, "away_g14": away_g14,
                "market_h": market_h, "market_d": market_d, "market_a": market_a,
                "understat_available": bool(home_understat or away_understat),
                "weather": weather, "weather_factor": weather_factor,
                "weather_desc": weather_desc, "weather_error": weather_error,
                "league_code": COMP_CODE,
            }

            st.session_state.update({
                "pred": pred, "auto_data": auto_data,
                "home_team": home_team_name, "away_team": away_team_name,
                "odds_sport_key": ODDS_SPORT,
            })
            st.success("✅ Listo — xG real, ELO, fatiga y line movement integrados.")

    # ── RESULTADOS ──
    if "pred" in st.session_state and "auto_data" in st.session_state:
        pred = st.session_state["pred"]
        data = st.session_state["auto_data"]
        ht   = st.session_state.get("home_team", "Local")
        at   = st.session_state.get("away_team", "Visitante")

        st.markdown("### 🔬 Fuentes de datos integradas")
        src1, src2, src3, src4, src5 = st.columns(5)

        with src1:
            has_xg = data.get("home_xgf") is not None or data.get("away_xgf") is not None
            xg_color = "#00ff88" if has_xg else "#666"
            xg_label = "✅ Activo" if has_xg else "⚠️ No disponible"
            hxgf = f"{data['home_xgf']:.2f}" if data.get('home_xgf') else "—"
            axgf = f"{data['away_xgf']:.2f}" if data.get('away_xgf') else "—"
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:{xg_color}">⚽ xG Real</div>
                <div style="font-family:'Space Mono';font-size:1em;color:{xg_color}">{xg_label}</div>
                <div style="font-size:.78em;color:#aaa">{ht}: {hxgf} · {at}: {axgf}</div>
                <div style="font-size:.72em;color:#666">Reg: ×{data.get('home_xg_reg',1.0):.3f}/×{data.get('away_xg_reg',1.0):.3f}</div>
            </div>""", unsafe_allow_html=True)

        with src2:
            eh = data.get("elo_home"); ea = data.get("elo_away")
            elo_color = "#00ff88" if eh and ea else "#666"
            elo_label = f"{int(eh)} vs {int(ea)}" if eh and ea else "No disponible"
            elo_diff  = f"{int(eh-ea):+d} pts" if eh and ea else ""
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:{elo_color}">📊 ELO</div>
                <div style="font-family:'Space Mono';font-size:1em;color:{elo_color}">{elo_label}</div>
                <div style="font-size:.78em;color:#aaa">{elo_diff}</div>
                <div style="font-size:.72em;color:#666">{pred.get('elo_home_p','?')}% / {pred.get('elo_draw_p','?')}% / {pred.get('elo_away_p','?')}%</div>
            </div>""", unsafe_allow_html=True)

        with src3:
            hf = data.get("home_fatigue", 1.0); af = data.get("away_fatigue", 1.0)
            hg7 = data.get("home_g7", 0); ag7 = data.get("away_g7", 0)
            fat_color = "#ff4466" if hf < 0.93 or af < 0.93 else ("#ffcc44" if hf < 0.97 or af < 0.97 else "#00ff88")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:{fat_color}">😴 Fatiga</div>
                <div style="font-family:'Space Mono';font-size:1em;color:{fat_color}">×{hf:.3f}/×{af:.3f}</div>
                <div style="font-size:.78em;color:#aaa">{ht}: {hg7}pj/7d · {at}: {ag7}pj/7d</div>
                <div style="font-size:.72em;color:#666">1.0 = sin fatiga</div>
            </div>""", unsafe_allow_html=True)

        with src4:
            wx = data.get("weather")
            wf = data.get("weather_factor", 1.0)
            werr = data.get("weather_error")
            wx_color = "#ff4466" if wf < 0.92 else ("#ffcc44" if wf < 0.97 else "#00ff88")
            if wx:
                wx_label  = wx["condition"]
                wx_detail = f"{wx['temp_c']}°C · {wx['wind_kmh']}km/h · {wx['precip_mm']}mm"
                wx_factor = f"Factor xG: ×{wf}"
            elif werr and werr.startswith("estadio_no_mapeado"):
                nombre_faltante = werr.split(":",1)[1] if ":" in werr else werr
                wx_color  = "#888"
                wx_label  = "⚠️ Sin coordenadas"
                wx_detail = nombre_faltante[:28]
                wx_factor = "Agrega al mapa"
            elif werr and werr.startswith("fecha_fuera_rango"):
                wx_color  = "#888"
                wx_label  = "⏳ Partido lejano"
                wx_detail = "Forecast solo ≤10 días"
                wx_factor = "Sin ajuste"
            else:
                wx_color  = "#666"
                wx_label  = "⚠️ Sin datos"
                wx_detail = (werr or "")[:28]
                wx_factor = "Sin ajuste"
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:{wx_color}">🌤️ Clima</div>
                <div style="font-family:'Space Mono';font-size:1em;color:{wx_color}">{wx_label}</div>
                <div style="font-size:.78em;color:#aaa">{wx_detail}</div>
                <div style="font-size:.72em;color:#666">{wx_factor}</div>
            </div>""", unsafe_allow_html=True)

        with src5:
            mh = data.get("market_h"); md = data.get("market_d"); ma = data.get("market_a")
            mkt_color = "#00ff88" if mh else "#666"
            mkt_label = "✅ Blend activo" if pred.get("market_blend") else "Sin blend"
            mkt_detail = f"{mh}%/{md}%/{ma}%" if mh else "Importa momios primero"
            lc = data.get("league_code","?")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:{mkt_color}">📈 Mercado</div>
                <div style="font-family:'Space Mono';font-size:1em;color:{mkt_color}">{mkt_label}</div>
                <div style="font-size:.78em;color:#aaa">{mkt_detail}</div>
                <div style="font-size:.72em;color:#666">Liga: {lc} (calibrada)</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Datos clave auto-jalados
        d1, d2, d3 = st.columns(3)
        with d1:
            fp = round(data['home_form']*100)
            fc = "#00ff88" if fp>=60 else ("#ffcc44" if fp>=40 else "#ff4466")
            hvgf = data.get('home_venue_gf', data['home_gf'])
            hvga = data.get('home_venue_ga', data['home_ga'])
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">🏠 Forma {ht} (ponderada)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fc}">{fp}%</div>
                <div style="font-size:.82em;color:#aaa">Como local: ⚽{hvgf} anotados · 🛡️{hvga} recibidos/pj</div>
                <div style="font-size:.82em;color:#aaa">Índice ataque: <b style="color:#ffcc44">{pred.get('home_att_idx',1.0)}</b> · defensa: <b style="color:#ffcc44">{pred.get('home_def_idx',1.0)}</b></div>
                <div style="font-size:.8em;color:#666;font-family:'Space Mono'">{data['home_results']}</div>
            </div>""", unsafe_allow_html=True)
        with d2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">⚔️ H2H</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:#ffcc44">{data['h2h_hw']}–{data['h2h_dr']}–{data['h2h_aw']}</div>
                <div style="font-size:.82em;color:#aaa">{ht} · Empates · {at}</div>
                <div style="font-size:.8em;color:#666;margin-top:6px">Ajuste H2H local: ×{pred.get('home_h2h_mult',1.0):.3f}</div>
            </div>""", unsafe_allow_html=True)
        with d3:
            fpa = round(data['away_form']*100)
            fca = "#00ff88" if fpa>=60 else ("#ffcc44" if fpa>=40 else "#ff4466")
            avgf = data.get('away_venue_gf', data['away_gf'])
            avga = data.get('away_venue_ga', data['away_ga'])
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:.75em;color:#888">✈️ Forma {at} (ponderada)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fca}">{fpa}%</div>
                <div style="font-size:.82em;color:#aaa">Como visitante: ⚽{avgf} anotados · 🛡️{avga} recibidos/pj</div>
                <div style="font-size:.82em;color:#aaa">Índice ataque: <b style="color:#ffcc44">{pred.get('away_att_idx',1.0)}</b> · defensa: <b style="color:#ffcc44">{pred.get('away_def_idx',1.0)}</b></div>
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

            # Debug: mostrar qué devolvió la API
            if isinstance(live_data, dict) and live_data.get("error_code"):
                st.error(f"❌ Error de API: {live_data.get('message','Error desconocido')}")
                with st.expander("Ver respuesta completa de la API"):
                    st.json(live_data)
            elif not live_data or not isinstance(live_data, list) or len(live_data) == 0:
                st.warning("⚠️ No hay momios disponibles para esta liga ahora mismo.")
                st.info("Esto es normal si: (1) no hay partidos próximos en las próximas 48h, o (2) la liga está fuera de temporada. Puedes ingresar momios manualmente en la tabla de abajo.")
            else:
                # Mostrar TODOS los partidos disponibles
                st.success(f"✅ {len(live_data)} partidos encontrados en {selected_league_name}")

                # Intentar match automático si hay partido seleccionado
                if "home_team" in st.session_state:
                    matched = extract_odds_for_match(live_data, st.session_state["home_team"], st.session_state["away_team"])
                    if matched:
                        st.session_state["casas"] = matched
                        st.success(f"🎯 Momios de {len(matched)} casas importados para **{ht2} vs {at2}**")
                    else:
                        st.info(f"No se encontró '{ht2} vs {at2}' automáticamente. Selecciona un partido de abajo:")

                # Mostrar todos los partidos disponibles para selección manual
                for game in live_data:
                    hn = game.get("home_team","")
                    an = game.get("away_team","")
                    fecha = game.get("commence_time","")[:10]
                    with st.expander(f"📊 {hn} vs {an} — {fecha}"):
                        rows_live = []
                        for bm in game.get("bookmakers",[])[:10]:
                            for mkt in bm.get("markets",[]):
                                if mkt["key"] == "h2h":
                                    oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                    rows_live.append({
                                        "Casa":    bm["title"],
                                        "Local":   oc.get(hn,"?"),
                                        "Empate":  oc.get("Draw","?"),
                                        "Visita":  oc.get(an,"?")
                                    })
                        if rows_live:
                            st.dataframe(pd.DataFrame(rows_live), use_container_width=True, hide_index=True)
                            if st.button(f"📥 Usar estos momios", key=f"use_{hn[:8]}_{an[:8]}"):
                                casas_nuevas = []
                                for bm in game.get("bookmakers",[]):
                                    for mkt in bm.get("markets",[]):
                                        if mkt["key"] == "h2h":
                                            oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                            casas_nuevas.append({
                                                "nombre": bm["title"],
                                                "local":  float(oc.get(hn, 200)),
                                                "empate": float(oc.get("Draw", 230)),
                                                "visita": float(oc.get(an, -150))
                                            })
                                if casas_nuevas:
                                    st.session_state["casas"] = casas_nuevas
                                    st.success(f"✅ Momios de {hn} vs {an} cargados")
                                    st.rerun()

    st.markdown("---")

    # Tabla de momios — ENTRADA MANUAL CORREGIDA
    st.markdown("#### 🏦 Casas de apuestas (1X2)")
    st.caption("Editables manualmente. Los momios van en formato americano: positivos (+240) o negativos (-140).")

    if "casas" not in st.session_state:
        st.session_state["casas"] = []

    # Cabecera
    h0,h1,h2,h3,h4 = st.columns([2,1,1,1,0.4])
    h0.markdown("**Casa**"); h1.markdown(f"**🏠 Local**")
    h2.markdown("**🤝 Empate**"); h3.markdown(f"**✈️ Visita**"); h4.markdown("**✕**")

    casas_actualizar = []
    for i, casa in enumerate(st.session_state["casas"]):
        cols = st.columns([2,1,1,1,0.4])
        nombre = cols[0].text_input("", value=str(casa["nombre"]), key=f"cn_{i}", label_visibility="collapsed")
        # Mostrar con signo + explícito para positivos
        def fmt_american(v):
            try:
                v = int(float(v))
                return f"+{v}" if v > 0 else str(v)
            except: return str(v)
        local_str  = cols[1].text_input("", value=fmt_american(casa["local"]),  key=f"cl_{i}", label_visibility="collapsed", placeholder="+200")
        empate_str = cols[2].text_input("", value=fmt_american(casa["empate"]), key=f"ce_{i}", label_visibility="collapsed", placeholder="+230")
        visita_str = cols[3].text_input("", value=fmt_american(casa["visita"]), key=f"cv_{i}", label_visibility="collapsed", placeholder="-150")
        eliminar   = cols[4].button("🗑", key=f"cd_{i}")

        if not eliminar:
            def parse_american(s, fallback):
                try: return int(float(str(s).replace("+",""))) if float(str(s).replace("+","")) >= 100 or float(str(s).replace("+","")) <= -100 else int(normalize_to_american(float(str(s).replace("+",""))))
                except: return fallback
            local_v  = parse_american(local_str,  casa["local"])
            empate_v = parse_american(empate_str, casa["empate"])
            visita_v = parse_american(visita_str, casa["visita"])
            casas_actualizar.append({"nombre":nombre,"local":local_v,"empate":empate_v,"visita":visita_v})

    if len(casas_actualizar) != len(st.session_state["casas"]):
        st.session_state["casas"] = casas_actualizar
        st.rerun()
    else:
        st.session_state["casas"] = casas_actualizar

    if st.button("➕ Agregar casa manualmente"):
        st.session_state["casas"].append({"nombre":"Casa","local":200.0,"empate":230.0,"visita":-160.0})
        st.rerun()

    if not st.session_state["casas"]:
        st.info("💡 Importa momios en vivo arriba, o agrega una casa manualmente con el botón.")

    st.caption("💡 Formato americano: equipos favoritos en negativo (-150), underdogs en positivo (+240)")

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
            k, frac, riesgo = smart_kelly(my_prob, dec, market_type="1X2", ev=ev, max_pct=max_kelly_pct)
            all_rows.append({"Categoría":"1X2","Casa":nombre_casa,"Mercado":mercado,
                             "Momio":f"{'+' if american>0 else ''}{int(american)}",
                             "Prob.Casa":f"{implied_prob(dec)}%","MiProb":f"{my_prob}%",
                             "EV":ev,"Kelly%":k,"Riesgo":riesgo,"Frac%":frac,
                             "Apostar($)":round((k/100)*bankroll,2)})

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
            mkt_clean = cat.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u").replace("Hándicap","Handicap")
            k, frac, riesgo = smart_kelly(my_prob, dec, market_type=mkt_clean, ev=ev, max_pct=max_kelly_pct)
            all_rows.append({"Categoría":cat,"Casa":"(Manual)","Mercado":mercado,
                             "Momio":f"{'+' if american>0 else ''}{int(american)}",
                             "Prob.Casa":f"{implied_prob(dec)}%","MiProb":f"{my_prob}%",
                             "EV":ev,"Kelly%":k,"Riesgo":riesgo,"Frac%":frac,
                             "Apostar($)":round((k/100)*bankroll,2)})

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
                    riesgo_txt = row.get('Riesgo','')
                    frac_txt   = row.get('Frac%', '')
                    st.markdown(f"""<div class="{css}">
                        <b>{em} {row['Casa']} — {row['Mercado']}</b>
                        &nbsp;<span class="tag {tc}">EV: {ev_pct:.1f}%</span>
                        &nbsp;<span class="tag {tc}">Kelly: {row['Kelly%']}%</span>
                        &nbsp;<span class="tag tag-yellow">Riesgo: {riesgo_txt}</span><br>
                        Momio: <span style="font-family:'Space Mono'">{row['Momio']}</span>
                        &emsp;Prob.casa: <b>{row['Prob.Casa']}</b>
                        &emsp;Mi prob.: <b>{row['MiProb']}</b>
                        &emsp;💰 Apostar: <b>${row['Apostar($)']:,.0f}</b>
                        <br><span style="font-size:.78em;color:#888">
                        Kelly puro × {frac_txt}% de fracción ajustada por tipo de mercado, momio y ventaja</span>
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

    # Selector de tipo de mercado para la calculadora
    calc_mkt = st.selectbox("Tipo de mercado", ["1X2","Over/Under","BTTS","Handicap","Doble oportunidad","HT"], key="calc_mkt")

    calc_dec     = american_to_decimal(calc_am)
    calc_impl    = implied_prob(calc_dec)
    calc_ev_v    = calc_ev(calc_p, calc_dec)
    calc_k, calc_frac, calc_riesgo = smart_kelly(calc_p, calc_dec, market_type=calc_mkt, ev=calc_ev_v, max_pct=max_kelly_pct)
    calc_apuesta = round((calc_k/100)*calc_bk, 2)

    r1,r2,r3,r4 = st.columns(4)
    ev_color = "#00ff88" if calc_ev_v > 0 else "#ff4466"
    with r1: st.markdown(f'''<div class="metric-card"><div style="font-size:.8em;color:#888">Decimal</div><div style="font-family:Space Mono;font-size:1.3em">{calc_dec}</div></div>''', unsafe_allow_html=True)
    with r2: st.markdown(f'''<div class="metric-card"><div style="font-size:.8em;color:#888">Prob. Implícita</div><div style="font-family:Space Mono;font-size:1.3em">{calc_impl}%</div></div>''', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Expected Value</div><div style="font-family:Space Mono;font-size:1.3em;color:{ev_color}">{calc_ev_v*100:.1f}%</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="metric-card"><div style="font-size:.8em;color:#888">Apostar (Kelly ajustado)</div><div style="font-family:Space Mono;font-size:1.3em;color:#00ff88">${calc_apuesta:,.0f}</div><div style="font-size:.75em;color:#888">{calc_riesgo} · {calc_frac}% del Kelly puro</div></div>', unsafe_allow_html=True)

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
