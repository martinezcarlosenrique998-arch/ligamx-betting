import streamlit as st
import pandas as pd
import requests
import random

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
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League":   {"id": 39,  "season": 2024, "odds_key": "soccer_epl"},
    "🇪🇸 La Liga":               {"id": 140, "season": 2024, "odds_key": "soccer_spain_la_liga"},
    "🇩🇪 Bundesliga":            {"id": 78,  "season": 2024, "odds_key": "soccer_germany_bundesliga"},
    "🇮🇹 Serie A":               {"id": 135, "season": 2024, "odds_key": "soccer_italy_serie_a"},
    "🇫🇷 Ligue 1":               {"id": 61,  "season": 2024, "odds_key": "soccer_france_ligue_1"},
    "🇲🇽 Liga MX":               {"id": 262, "season": 2025, "odds_key": "soccer_mexico_ligamx"},
    "🇺🇸 MLS":                   {"id": 253, "season": 2025, "odds_key": "soccer_usa_mls"},
    "🏆 Champions League":       {"id": 2,   "season": 2024, "odds_key": "soccer_uefa_champs_league"},
}

# ─────────────────────────────────────────────
#  ESTILOS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&family=DM+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 2px; }
.stApp { background: #0a0a0f; color: #e8e8e8; }
.metric-card {
    background: linear-gradient(135deg, #12121a, #1a1a2e);
    border: 1px solid #2a2a40; border-radius: 12px;
    padding: 20px; margin: 8px 0; transition: all 0.3s ease;
}
.metric-card:hover { border-color: #00ff88; transform: translateY(-2px); }
.value-positive { color: #00ff88; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.value-negative { color: #ff4466; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.value-neutral  { color: #ffcc44; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.bet-row-positive { background: rgba(0,255,136,0.08); border-left: 3px solid #00ff88; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-negative { background: rgba(255,68,102,0.08); border-left: 3px solid #ff4466; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-neutral  { background: rgba(255,204,68,0.08); border-left: 3px solid #ffcc44; padding: 12px; border-radius: 6px; margin: 6px 0; }
.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.75em; font-weight:600; margin:2px; }
.tag-green  { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red    { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow { background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }
.player-card { background: #12121a; border: 1px solid #2a2a40; border-radius: 8px; padding: 10px 14px; margin: 4px 0; font-size: 0.9em; }
.section-header { font-family: 'Bebas Neue'; font-size: 1.8em; letter-spacing:3px; color: #00ff88; border-bottom: 1px solid #2a2a40; padding-bottom: 8px; margin: 24px 0 16px 0; }
.live-badge { background:#ff446622; color:#ff4466; border:1px solid #ff446655; border-radius:20px; padding:2px 10px; font-size:0.75em; font-weight:600; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  API: RAPIDAPI (API-FOOTBALL)
# ─────────────────────────────────────────────

def api_football(endpoint, params, api_key):
    """Llama a API-Football vía RapidAPI."""
    url = f"https://api-football-v1.p.rapidapi.com/v3/{endpoint}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        if data.get("errors") and data["errors"] != []:
            return {"error": str(data["errors"])}
        return data
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=3600)
def get_upcoming_fixtures(api_key, league_id, season):
    data = api_football("fixtures", {
        "league": league_id, "season": season, "next": 20
    }, api_key)
    return data.get("response", [])

@st.cache_data(ttl=3600)
def get_team_last_matches(api_key, team_id, league_id, season, last=10):
    data = api_football("fixtures", {
        "team": team_id, "last": last,
        "league": league_id, "season": season
    }, api_key)
    return data.get("response", [])

@st.cache_data(ttl=3600)
def get_h2h(api_key, team1_id, team2_id, last=10):
    data = api_football("fixtures/headtohead", {
        "h2h": f"{team1_id}-{team2_id}", "last": last
    }, api_key)
    return data.get("response", [])

@st.cache_data(ttl=7200)
def get_fixture_lineups(api_key, fixture_id):
    data = api_football("fixtures/lineups", {"fixture": fixture_id}, api_key)
    return data.get("response", [])

@st.cache_data(ttl=7200)
def get_fixture_predictions(api_key, fixture_id):
    data = api_football("predictions", {"fixture": fixture_id}, api_key)
    resp = data.get("response", [])
    return resp[0] if resp else {}

@st.cache_data(ttl=3600)
def get_all_teams(api_key, league_id, season):
    data = api_football("teams", {"league": league_id, "season": season}, api_key)
    return data.get("response", [])

# ─────────────────────────────────────────────
#  API: THE ODDS API — con auto-fill
# ─────────────────────────────────────────────

def get_live_odds(api_key, sport_key):
    """Jala momios en vivo de The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "us,eu,uk",
        "markets": "h2h",
        "oddsFormat": "american"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return []

def extract_odds_for_match(live_data, home_name, away_name):
    """
    Busca el partido correcto en la respuesta de The Odds API
    y extrae momios por casa de apuestas.
    Retorna lista de dicts: [{nombre, local, empate, visita}, ...]
    """
    home_lower = home_name.lower()
    away_lower = away_name.lower()

    best_game = None
    best_score = 0

    for game in live_data:
        gh = game.get("home_team", "").lower()
        ga = game.get("away_team", "").lower()
        # Score de coincidencia por palabras
        score = 0
        for word in home_lower.split():
            if len(word) > 3 and word in gh: score += 2
        for word in away_lower.split():
            if len(word) > 3 and word in ga: score += 2
        if score > best_score:
            best_score = score
            best_game = game

    if not best_game or best_score == 0:
        return []

    casas = []
    home_n = best_game.get("home_team", "")
    away_n = best_game.get("away_team", "")

    for bm in best_game.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt["key"] == "h2h":
                oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                local   = oc.get(home_n, None)
                visita  = oc.get(away_n, None)
                empate  = oc.get("Draw", None)
                if local and visita and empate:
                    casas.append({
                        "nombre": bm["title"],
                        "local":  float(local),
                        "empate": float(empate),
                        "visita": float(visita)
                    })
    return casas

# ─────────────────────────────────────────────
#  PROCESAMIENTO STATS
# ─────────────────────────────────────────────

def calc_form(matches, team_id):
    results = []
    for m in matches[-5:]:
        if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
        is_home = m["teams"]["home"]["id"] == team_id
        hg = m["goals"]["home"] or 0
        ag = m["goals"]["away"] or 0
        mg = hg if is_home else ag
        rg = ag if is_home else hg
        results.append(3 if mg > rg else (1 if mg == rg else 0))
    if not results: return 0.5
    return round(sum(results) / (len(results) * 3), 3)

def calc_avg_goals(matches, team_id):
    gf, ga = [], []
    for m in matches:
        if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
        is_home = m["teams"]["home"]["id"] == team_id
        hg = m["goals"]["home"] or 0
        ag = m["goals"]["away"] or 0
        gf.append(hg if is_home else ag)
        ga.append(ag if is_home else hg)
    if not gf: return 1.2, 1.2
    return round(sum(gf)/len(gf), 2), round(sum(ga)/len(ga), 2)

def calc_h2h_stats(h2h_matches, home_id, away_id):
    hw = aw = dr = 0
    for m in h2h_matches:
        if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
        mid_home = m["teams"]["home"]["id"]
        hg = m["goals"]["home"] or 0
        ag = m["goals"]["away"] or 0
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
#  MODELO DE PREDICCIÓN
# ─────────────────────────────────────────────

def predict_match(home_form, away_form, home_gf, away_gf,
                  home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr, is_clasico=False):
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
    hp = round((h / total) * 100, 1)
    ap = round((a / total) * 100, 1)
    dp = round(100 - hp - ap, 1)
    exp_h = round(home_gf * (away_ga / max(away_gf, 0.5)), 2)
    exp_a = round(away_gf * (home_ga / max(home_gf, 0.5)), 2)
    exp_t = round(exp_h + exp_a, 2)
    return {
        "home_win_pct": hp, "draw_pct": dp, "away_win_pct": ap,
        "exp_home_goals": exp_h, "exp_away_goals": exp_a,
        "exp_total_goals": exp_t,
        "over_25_prob": min(95, round((exp_t / 2.5) * 55, 1))
    }

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

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("# ⚽ Betting Analytics")
    st.markdown("---")

    st.markdown("### 🏆 Liga")
    selected_league_name = st.selectbox("Selecciona la liga", list(LEAGUES.keys()))
    league_cfg = LEAGUES[selected_league_name]
    LEAGUE_ID      = league_cfg["id"]
    SEASON         = league_cfg["season"]
    ODDS_SPORT_KEY = league_cfg["odds_key"]

    st.markdown("---")
    st.markdown("### 🔑 API Keys")
    football_api_key = st.text_input("RapidAPI Key (API-Football)",
        type="password",
        help="Regístrate gratis en rapidapi.com/api-sports/api/api-football → Plan Basic (Free)")
    odds_api_key = st.text_input("The Odds API Key",
        type="password",
        help="Gratis en the-odds-api.com — momios en tiempo real de 40+ casas")

    st.markdown("---")
    st.markdown("### 💰 Bankroll")
    bankroll = st.number_input("Bankroll ($)", min_value=100, value=1000, step=100)

    st.markdown("---")
    st.markdown("### ⚙️ Filtros EV")
    min_ev       = st.slider("EV mínimo (%)", -20, 30, 5)
    max_kelly_pct = st.slider("Kelly máximo (%)", 1, 30, 10)

    st.markdown("---")
    if football_api_key:
        if st.button("🗑️ Limpiar caché"):
            st.cache_data.clear()
            st.success("Caché limpiado")
    st.caption("v3.0 · Football Betting Analytics\nRapidAPI + The Odds API")

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
#  TAB 1 — ANÁLISIS DE PARTIDO
# ══════════════════════════════════════════════
with tab1:
    st.markdown(f'<div class="section-header">🎯 ANÁLISIS — {selected_league_name}</div>', unsafe_allow_html=True)

    if not football_api_key:
        st.warning("👈 Ingresa tu RapidAPI Key en el sidebar para activar el modo automático.")
        st.markdown("""
        **Cómo obtener tu key gratis:**
        1. Ve a: https://rapidapi.com/api-sports/api/api-football
        2. Haz clic en **"Subscribe to Test"** → Plan **Basic (Free)**
        3. Copia tu `X-RapidAPI-Key` y pégala aquí
        """)
        st.stop()

    # Selección de partido
    st.markdown("### 1️⃣ Selecciona el partido")
    search_mode = st.radio("", [
        "📅 Ver próximos partidos",
        "🔍 Buscar por equipos"
    ], horizontal=True)

    fixture_id     = None
    home_team_id   = None
    away_team_id   = None
    home_team_name = ""
    away_team_name = ""

    if search_mode == "📅 Ver próximos partidos":
        with st.spinner(f"Cargando partidos de {selected_league_name}..."):
            fixtures = get_upcoming_fixtures(football_api_key, LEAGUE_ID, SEASON)

        if not fixtures:
            st.error("No se encontraron partidos próximos. Verifica tu RapidAPI Key.")
        else:
            fixture_options = {}
            for f in fixtures:
                fecha = f["fixture"]["date"][:10]
                hora  = f["fixture"]["date"][11:16]
                home  = f["teams"]["home"]["name"]
                away  = f["teams"]["away"]["name"]
                label = f"{fecha} {hora} — {home} vs {away}"
                fixture_options[label] = f

            selected_label   = st.selectbox("Partido", list(fixture_options.keys()))
            selected_fixture = fixture_options[selected_label]
            fixture_id       = selected_fixture["fixture"]["id"]
            home_team_id     = selected_fixture["teams"]["home"]["id"]
            away_team_id     = selected_fixture["teams"]["away"]["id"]
            home_team_name   = selected_fixture["teams"]["home"]["name"]
            away_team_name   = selected_fixture["teams"]["away"]["name"]

            ci1, ci2, ci3 = st.columns(3)
            ci1.metric("🏟️ Estadio",   selected_fixture["fixture"].get("venue", {}).get("name", "N/D"))
            ci2.metric("📅 Fecha",     selected_fixture["fixture"]["date"][:10])
            ci3.metric("🔖 Fixture ID", fixture_id)

    else:
        with st.spinner("Cargando equipos..."):
            teams_list = get_all_teams(football_api_key, LEAGUE_ID, SEASON)

        if teams_list:
            team_map   = {t["team"]["name"]: t["team"]["id"] for t in teams_list}
            team_names = sorted(team_map.keys())
            c1, c2 = st.columns(2)
            with c1: home_team_name = st.selectbox("🏠 Local",    team_names)
            with c2: away_team_name = st.selectbox("✈️ Visitante", [t for t in team_names if t != home_team_name])
            home_team_id = team_map[home_team_name]
            away_team_id = team_map[away_team_name]

            with st.spinner("Buscando fixture próximo..."):
                all_fix = get_upcoming_fixtures(football_api_key, LEAGUE_ID, SEASON)
                for f in all_fix:
                    if (f["teams"]["home"]["id"] == home_team_id and
                        f["teams"]["away"]["id"] == away_team_id):
                        fixture_id = f["fixture"]["id"]
                        break
            if fixture_id:
                st.success(f"✅ Partido encontrado — ID: {fixture_id}")
            else:
                st.info("No se encontró fixture próximo entre estos equipos; se analizará con datos históricos.")
        else:
            st.error("No se pudieron cargar los equipos. Verifica tu RapidAPI Key.")

    # Botón analizar
    st.markdown("---")
    if home_team_id and away_team_id:
        is_clasico = st.checkbox("⚡ ¿Es Clásico? (ajusta modelo al equilibrio)", value=False)

        if st.button("🔮 ANALIZAR AUTOMÁTICAMENTE", use_container_width=True, type="primary"):
            with st.spinner("Jalando datos..."):
                home_matches = get_team_last_matches(football_api_key, home_team_id, LEAGUE_ID, SEASON)
                away_matches = get_team_last_matches(football_api_key, away_team_id, LEAGUE_ID, SEASON)
                h2h_matches  = get_h2h(football_api_key, home_team_id, away_team_id)
                lineups      = get_fixture_lineups(football_api_key, fixture_id) if fixture_id else []
                api_pred     = get_fixture_predictions(football_api_key, fixture_id) if fixture_id else {}

            home_form        = calc_form(home_matches, home_team_id)
            away_form        = calc_form(away_matches, away_team_id)
            home_gf, home_ga = calc_avg_goals(home_matches, home_team_id)
            away_gf, away_ga = calc_avg_goals(away_matches, away_team_id)
            h2h_hw, h2h_aw, h2h_dr = calc_h2h_stats(h2h_matches, home_team_id, away_team_id)

            pred = predict_match(
                home_form, away_form, home_gf, away_gf,
                home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr, is_clasico
            )

            st.session_state.update({
                "pred": pred,
                "home_team": home_team_name,
                "away_team": away_team_name,
                "odds_sport_key": ODDS_SPORT_KEY,
                "auto_data": {
                    "home_form": home_form, "away_form": away_form,
                    "home_gf": home_gf, "home_ga": home_ga,
                    "away_gf": away_gf, "away_ga": away_ga,
                    "h2h_hw": h2h_hw, "h2h_aw": h2h_aw, "h2h_dr": h2h_dr,
                    "home_matches": home_matches, "away_matches": away_matches,
                    "h2h_matches": h2h_matches, "lineups": lineups, "api_pred": api_pred
                }
            })
            st.success("✅ Análisis completado. Ve al Tab 📡 Momios & EV para continuar.")

    # Resultados
    if "pred" in st.session_state and "auto_data" in st.session_state:
        pred = st.session_state["pred"]
        data = st.session_state["auto_data"]
        ht   = st.session_state.get("home_team", "Local")
        at   = st.session_state.get("away_team", "Visitante")

        st.markdown("---")
        st.markdown(f'<div class="section-header">📊 {ht.upper()} VS {at.upper()}</div>', unsafe_allow_html=True)

        # Datos auto-jalados
        d1, d2, d3 = st.columns(3)
        with d1:
            fp = round(data['home_form']*100)
            fc = "#00ff88" if fp >= 60 else ("#ffcc44" if fp >= 40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888">🏠 Forma {ht} (últ.5)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fc}">{fp}%</div>
                <div style="font-size:0.82em;color:#aaa">⚽ {data['home_gf']} anotados · 🛡️ {data['home_ga']} recibidos/partido</div>
            </div>""", unsafe_allow_html=True)
        with d2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888">⚔️ H2H (últ.10)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:#ffcc44">{data['h2h_hw']}–{data['h2h_dr']}–{data['h2h_aw']}</div>
                <div style="font-size:0.82em;color:#aaa">{ht} · Empates · {at}</div>
            </div>""", unsafe_allow_html=True)
        with d3:
            fpa = round(data['away_form']*100)
            fca = "#00ff88" if fpa >= 60 else ("#ffcc44" if fpa >= 40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888">✈️ Forma {at} (últ.5)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{fca}">{fpa}%</div>
                <div style="font-size:0.82em;color:#aaa">⚽ {data['away_gf']} anotados · 🛡️ {data['away_ga']} recibidos/partido</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("#### 🔮 Predicción del modelo")
        p1, p2, p3 = st.columns(3)
        for col, label, val in [(p1, f"🏠 {ht}", pred['home_win_pct']),
                                 (p2, "🤝 Empate",  pred['draw_pct']),
                                 (p3, f"✈️ {at}",  pred['away_win_pct'])]:
            with col:
                st.markdown(f"""<div class="metric-card">
                    <div style="font-size:0.8em;color:#888">{label}</div>
                    <div class="value-neutral">{val}%</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("#### ⚽ Goles esperados")
        g1, g2, g3, g4 = st.columns(4)
        g1.metric(f"Goles {ht}",  pred['exp_home_goals'])
        g2.metric(f"Goles {at}",  pred['exp_away_goals'])
        g3.metric("Total",         pred['exp_total_goals'])
        g4.metric("Prob. Over 2.5", f"{pred['over_25_prob']}%")

        # Predicción API
        if data.get("api_pred"):
            ap   = data["api_pred"]
            pct  = ap.get("predictions", {}).get("percent", {})
            win  = ap.get("predictions", {}).get("winner", {})
            adv  = ap.get("predictions", {}).get("advice", "")
            if pct:
                st.markdown("#### 🤖 Predicción API-Football")
                ac1, ac2, ac3, ac4 = st.columns(4)
                ac1.metric("API Local",      pct.get("home","?"))
                ac2.metric("API Empate",     pct.get("draw","?"))
                ac3.metric("API Visitante",  pct.get("away","?"))
                ac4.metric("Ganador suger.", win.get("name","N/D") if win else "N/D")
                if adv: st.info(f"💡 {adv}")

        # Últimos partidos
        with st.expander("📋 Últimos partidos"):
            lc1, lc2 = st.columns(2)
            for col, matches, tid, tname in [(lc1, data['home_matches'], home_team_id, ht),
                                              (lc2, data['away_matches'], away_team_id, at)]:
                with col:
                    st.markdown(f"**{tname}**")
                    shown = 0
                    for m in reversed(matches):
                        if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
                        date  = m["fixture"]["date"][:10]
                        hn    = m["teams"]["home"]["name"]
                        an    = m["teams"]["away"]["name"]
                        hg    = m["goals"]["home"] or 0
                        ag    = m["goals"]["away"] or 0
                        ih    = m["teams"]["home"]["id"] == tid
                        mg    = hg if ih else ag
                        rg    = ag if ih else hg
                        em    = "🟢" if mg > rg else ("🟡" if mg == rg else "🔴")
                        st.markdown(f"`{date}` {em} **{hn} {hg}–{ag} {an}**")
                        shown += 1
                        if shown >= 7: break

        # H2H
        with st.expander("⚔️ Historial H2H"):
            if data['h2h_matches']:
                for m in reversed(data['h2h_matches'][-8:]):
                    if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
                    date = m["fixture"]["date"][:10]
                    hn   = m["teams"]["home"]["name"]
                    an   = m["teams"]["away"]["name"]
                    hg   = m["goals"]["home"] or 0
                    ag   = m["goals"]["away"] or 0
                    st.markdown(f"`{date}` — **{hn} {hg}–{ag} {an}**")
            else:
                st.info("No se encontró historial H2H.")

        # Alineaciones
        with st.expander("👥 Alineaciones (disponibles ~1h antes del partido)"):
            lineups = data.get("lineups", [])
            if lineups:
                lc1, lc2 = st.columns(2)
                for i, tl in enumerate(lineups[:2]):
                    tname     = tl.get("team",{}).get("name",f"Equipo {i+1}")
                    formation = tl.get("formation","?")
                    with (lc1 if i==0 else lc2):
                        st.markdown(f"**{tname}** — `{formation}`")
                        for p in tl.get("startXI",[]):
                            pi = p.get("player",{})
                            st.markdown(f'<div class="player-card">#{pi.get("number","?")} <b>{pi.get("name","?")}</b> <span style="color:#888;font-size:0.85em">{pi.get("pos","?")}</span></div>', unsafe_allow_html=True)
                        subs = tl.get("substitutes",[])
                        if subs:
                            st.markdown("*Suplentes:*")
                            for p in subs[:5]:
                                pi = p.get("player",{})
                                st.caption(f"· {pi.get('name','?')} ({pi.get('pos','?')})")
            else:
                st.info("⏳ Las alineaciones aparecen ~1h antes del partido.")

# ══════════════════════════════════════════════
#  TAB 2 — MOMIOS & EV
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 MOMIOS & VALOR ESPERADO</div>', unsafe_allow_html=True)

    # Mis probabilidades (del Tab 1)
    if "pred" in st.session_state:
        pred = st.session_state["pred"]
        ht2  = st.session_state.get("home_team", "Local")
        at2  = st.session_state.get("away_team", "Visitante")
        my_home = pred['home_win_pct']
        my_draw = pred['draw_pct']
        my_away = pred['away_win_pct']

        st.markdown(f"#### 🎯 Predicción activa: **{ht2}** vs **{at2}**")
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric(f"🏠 {ht2}",  f"{my_home}%")
        pc2.metric("🤝 Empate",   f"{my_draw}%")
        pc3.metric(f"✈️ {at2}",  f"{my_away}%")
    else:
        st.warning("Primero analiza un partido en el Tab 🎯 Análisis de Partido.")
        ht2, at2 = "Local", "Visitante"
        st.markdown("O ingresa probabilidades manuales:")
        pc1, pc2, pc3 = st.columns(3)
        my_home = pc1.number_input("Prob. Local (%)",    0.0, 100.0, 33.0)
        my_draw = pc2.number_input("Prob. Empate (%)",   0.0, 100.0, 33.0)
        my_away = pc3.number_input("Prob. Visitante (%)",0.0, 100.0, 34.0)

    st.markdown("---")

    # ── IMPORTAR MOMIOS EN VIVO ──
    st.markdown("#### 📡 Momios en tiempo real")

    col_live1, col_live2 = st.columns([3, 1])
    with col_live1:
        st.caption(f"Liga activa: **{selected_league_name}** · sport key: `{ODDS_SPORT_KEY}`")
    with col_live2:
        import_clicked = st.button("🔄 Importar momios en vivo", use_container_width=True)

    if import_clicked:
        if not odds_api_key:
            st.error("Ingresa tu The Odds API Key en el sidebar.")
        else:
            with st.spinner("Importando momios en tiempo real..."):
                live_data = get_live_odds(odds_api_key, ODDS_SPORT_KEY)

            if not live_data or not isinstance(live_data, list):
                st.warning("No se encontraron momios en vivo para esta liga. Puede que no haya partidos próximos en las próximas 48h o el sport key no esté disponible en tu plan.")
            else:
                # Intentar auto-match con el partido analizado
                if "home_team" in st.session_state and "away_team" in st.session_state:
                    matched = extract_odds_for_match(
                        live_data,
                        st.session_state["home_team"],
                        st.session_state["away_team"]
                    )
                    if matched:
                        st.session_state["casas"] = matched
                        st.success(f"✅ Se importaron momios de **{len(matched)} casas** para {ht2} vs {at2}. ¡Los valores de abajo se actualizaron automáticamente!")
                    else:
                        st.info(f"No se encontró el partido '{ht2} vs {at2}' en los momios en vivo. Mostrando todos los partidos disponibles:")

                # Mostrar todos los partidos disponibles con sus momios
                for game in live_data[:5]:
                    hn = game.get("home_team","")
                    an = game.get("away_team","")
                    commence = game.get("commence_time","")[:10]
                    with st.expander(f"📊 {hn} vs {an} ({commence})"):
                        bookmakers = game.get("bookmakers",[])
                        if bookmakers:
                            rows_live = []
                            for bm in bookmakers[:8]:
                                for mkt in bm.get("markets",[]):
                                    if mkt["key"] == "h2h":
                                        oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                        rows_live.append({
                                            "Casa":   bm["title"],
                                            "Local":  oc.get(hn,"?"),
                                            "Empate": oc.get("Draw","?"),
                                            "Visita": oc.get(an,"?"),
                                        })
                            if rows_live:
                                st.dataframe(pd.DataFrame(rows_live), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── TABLA DE MOMIOS (editable, se auto-rellena con live) ──
    st.markdown("#### 🏦 Casas de apuestas")
    st.caption("Se rellenan automáticamente al importar momios en vivo. También puedes editarlos manualmente.")

    if "casas" not in st.session_state:
        st.session_state["casas"] = [
            {"nombre": "Caliente",  "local": 240.0, "empate": 230.0, "visita": -140.0},
            {"nombre": "Betcris",   "local": 220.0, "empate": 240.0, "visita": -150.0},
            {"nombre": "Codere",    "local": 250.0, "empate": 220.0, "visita": -145.0},
            {"nombre": "Bet365",    "local": 235.0, "empate": 225.0, "visita": -142.0},
        ]

    for i, casa in enumerate(st.session_state["casas"]):
        cols = st.columns([2, 1, 1, 1, 0.4])
        with cols[0]: casa["nombre"] = st.text_input("Casa",   casa["nombre"],       key=f"cn_{i}")
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

    # ── ANÁLISIS EV ──
    if st.button("⚡ CALCULAR VALOR ESPERADO", use_container_width=True, type="primary"):
        rows = []
        for casa in st.session_state["casas"]:
            for mercado, american, my_prob in [
                (f"🏠 {ht2} gana", casa["local"],  my_home),
                ("🤝 Empate",      casa["empate"], my_draw),
                (f"✈️ {at2} gana", casa["visita"], my_away),
            ]:
                dec     = american_to_decimal(american)
                impl    = implied_prob(dec)
                ev      = calc_ev(my_prob, dec)
                k       = min(kelly_criterion(my_prob, dec), max_kelly_pct)
                apuesta = round((k/100) * bankroll, 2)
                rows.append({
                    "Casa": casa["nombre"], "Mercado": mercado,
                    "Momio": f"{'+' if american>0 else ''}{int(american)}",
                    "Dec": dec, "Prob.Casa": f"{impl}%",
                    "MiProb": f"{my_prob}%", "EV": ev,
                    "Kelly%": k, "Apostar($)": apuesta
                })

        df   = pd.DataFrame(rows)
        best = df[df["EV"] >= (min_ev/100)].sort_values("EV", ascending=False)

        st.markdown("### 💡 Apuestas con valor")
        if best.empty:
            st.warning(f"No hay apuestas con EV ≥ {min_ev}% con los momios actuales.")
        else:
            for _, row in best.iterrows():
                ev_pct = row["EV"] * 100
                if ev_pct >= 10:   css, tc, em = "bet-row-positive","tag-green","🟢"
                elif ev_pct >= 5:  css, tc, em = "bet-row-neutral","tag-yellow","🟡"
                else:              css, tc, em = "bet-row-negative","tag-red","🔴"
                st.markdown(f"""<div class="{css}">
                    <b>{em} {row['Casa']} — {row['Mercado']}</b>
                    &nbsp;<span class="tag {tc}">EV: {ev_pct:.1f}%</span>
                    &nbsp;<span class="tag {tc}">Kelly: {row['Kelly%']}%</span><br>
                    Momio: <span style="font-family:'Space Mono'">{row['Momio']}</span>
                    &emsp;Prob.casa: <b>{row['Prob.Casa']}</b>
                    &emsp;Mi prob.: <b>{row['MiProb']}</b>
                    &emsp;💰 Apostar: <b>${row['Apostar($)']:,.0f}</b>
                </div>""", unsafe_allow_html=True)

        # Guardar mejor apuesta para la calculadora
        if not best.empty:
            top = best.iloc[0]
            st.session_state["calc_prefill"] = {
                "american": float(top["Momio"].replace("+","")),
                "my_prob":  float(str(top["MiProb"]).replace("%",""))
            }
            st.info("💡 La mejor apuesta se cargó automáticamente en la **Calculadora EV** (Tab 🧮)")

        st.markdown("---")
        st.markdown("#### 📋 Tabla completa")
        st.dataframe(df.drop(columns=["Dec"]), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA EV
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA DE VALOR ESPERADO</div>', unsafe_allow_html=True)

    # Auto-rellenar desde la mejor apuesta del Tab 2
    prefill = st.session_state.get("calc_prefill", {})
    default_am = prefill.get("american", 240.0)
    default_p  = prefill.get("my_prob",  28.0)

    if prefill:
        st.success("✅ Valores cargados automáticamente desde la mejor apuesta del Tab 📡 Momios & EV")

    c1, c2, c3 = st.columns(3)
    with c1: calc_am = st.number_input("Momio americano", value=float(default_am), step=5.0)
    with c2: calc_p  = st.number_input("Mi probabilidad (%)", 0.0, 100.0, float(default_p))
    with c3: calc_bk = st.number_input("Bankroll ($)", min_value=100, value=bankroll, step=100)

    calc_dec     = american_to_decimal(calc_am)
    calc_impl    = implied_prob(calc_dec)
    calc_ev_v    = calc_ev(calc_p, calc_dec)
    calc_k       = min(kelly_criterion(calc_p, calc_dec), max_kelly_pct)
    calc_apuesta = round((calc_k/100) * calc_bk, 2)

    r1, r2, r3, r4 = st.columns(4)
    ev_color = "#00ff88" if calc_ev_v > 0 else "#ff4466"
    with r1: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888">Decimal</div><div style="font-family:Space Mono;font-size:1.3em">{calc_dec}</div></div>', unsafe_allow_html=True)
    with r2: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888">Prob. Implícita</div><div style="font-family:Space Mono;font-size:1.3em">{calc_impl}%</div></div>', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888">Expected Value</div><div style="font-family:Space Mono;font-size:1.3em;color:{ev_color}">{calc_ev_v*100:.1f}%</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888">Apostar (Kelly)</div><div style="font-family:Space Mono;font-size:1.3em;color:#00ff88">${calc_apuesta:,.0f}</div></div>', unsafe_allow_html=True)

    if calc_ev_v > 0.10:  st.success(f"✅ Buena apuesta — EV +{calc_ev_v*100:.1f}%")
    elif calc_ev_v > 0:   st.warning(f"🟡 Valor marginal (+{calc_ev_v*100:.1f}%)")
    else:                  st.error(f"❌ Sin valor ({calc_ev_v*100:.1f}%)")

    st.markdown("#### 📈 Simulación de rentabilidad")
    n_bets = st.slider("Número de apuestas simuladas", 10, 500, 100)
    bk_sim = [calc_bk]
    current = calc_bk
    p = calc_p / 100
    for _ in range(n_bets):
        stake   = (calc_k/100) * current
        current += stake * (calc_dec-1) if random.random() < p else -stake
        bk_sim.append(round(current, 2))
    sim_df = pd.DataFrame({"#": range(n_bets+1), "Bankroll": bk_sim})
    st.line_chart(sim_df.set_index("#"))
    final = bk_sim[-1]
    chg   = round(((final-calc_bk)/calc_bk)*100,1)
    (st.success if final > calc_bk else st.error)(f"Resultado simulado: ${final:,.0f} ({'+' if chg>0 else ''}{chg}%)")
    st.caption("⚠️ Simulación aleatoria ilustrativa. Cada corrida es diferente.")

# ══════════════════════════════════════════════
#  TAB 4 — GUÍA
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📖 GUÍA DE USO</div>', unsafe_allow_html=True)
    st.markdown("""
### 🔧 Setup inicial (una sola vez)

#### 1. RapidAPI Key (API-Football) — para stats automáticas
1. Ve a: **rapidapi.com/api-sports/api/api-football**
2. Haz clic en **"Subscribe to Test"** → Plan **Basic (Free)** → 100 requests/día gratis
3. Copia tu `X-RapidAPI-Key` del dashboard y pégala en el sidebar

#### 2. The Odds API Key — para momios en tiempo real
1. Ve a: **the-odds-api.com**
2. Clic en **"Get API Key"** → Regístrate gratis (500 requests/mes gratis)
3. Copia tu key y pégala en el sidebar

---

### 📋 Flujo recomendado

| Paso | Tab | Acción |
|------|-----|--------|
| 1 | 🎯 Análisis | Selecciona la liga y el partido → Analizar |
| 2 | 📡 Momios & EV | Importa momios en vivo → se rellenan automáticamente |
| 3 | 📡 Momios & EV | Presiona "Calcular Valor Esperado" |
| 4 | 🧮 Calculadora | La mejor apuesta se carga sola para simular |

### 💡 Cómo funcionan los momios auto-importados

Al presionar **"Importar momios en vivo"**, el sistema:
1. Jala momios de 40+ casas de apuestas de The Odds API
2. Busca automáticamente el partido que analizaste
3. **Rellena la tabla de casas de apuestas con los valores reales en tiempo real**
4. Al calcular EV, la **mejor apuesta se carga sola en la Calculadora**

### 🏆 Ligas disponibles
Selecciona desde el sidebar. Las más confiables: Premier League, La Liga, Bundesliga, Serie A.

---
⚠️ *Herramienta de análisis estadístico. Las apuestas conllevan riesgo real. Juega responsablemente.*
    """)
