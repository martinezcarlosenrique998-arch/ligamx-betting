import streamlit as st
import pandas as pd
import requests
import random
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

# football-data.org v4 — códigos de competición
LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League":   {"code": "PL",  "odds_key": "soccer_epl"},
    "🇪🇸 La Liga":               {"code": "PD",  "odds_key": "soccer_spain_la_liga"},
    "🇩🇪 Bundesliga":            {"code": "BL1", "odds_key": "soccer_germany_bundesliga"},
    "🇮🇹 Serie A":               {"code": "SA",  "odds_key": "soccer_italy_serie_a"},
    "🇫🇷 Ligue 1":               {"code": "FL1", "odds_key": "soccer_france_ligue_1"},
    "🏆 Champions League":       {"code": "CL",  "odds_key": "soccer_uefa_champs_league"},
}

BASE_URL = "https://api.football-data.org/v4"

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
.value-neutral { color: #ffcc44; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.bet-row-positive { background: rgba(0,255,136,0.08); border-left: 3px solid #00ff88; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-negative { background: rgba(255,68,102,0.08); border-left: 3px solid #ff4466; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-neutral  { background: rgba(255,204,68,0.08); border-left: 3px solid #ffcc44; padding: 12px; border-radius: 6px; margin: 6px 0; }
.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.75em; font-weight:600; margin:2px; }
.tag-green  { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red    { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow { background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }
.section-header { font-family: 'Bebas Neue'; font-size: 1.8em; letter-spacing:3px; color: #00ff88; border-bottom: 1px solid #2a2a40; padding-bottom: 8px; margin: 24px 0 16px 0; }
.player-card { background: #12121a; border: 1px solid #2a2a40; border-radius: 8px; padding: 10px 14px; margin: 4px 0; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  API: FOOTBALL-DATA.ORG
# ─────────────────────────────────────────────

def fd_get(endpoint, api_key, params=None):
    """Llamada a football-data.org v4."""
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
    """Próximos partidos de una competición."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
    data = fd_get(f"competitions/{comp_code}/matches",
                  api_key,
                  {"status": "SCHEDULED", "dateFrom": today, "dateTo": future})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_team_matches(api_key, team_id, last=10):
    """Últimos N partidos de un equipo."""
    data = fd_get(f"teams/{team_id}/matches", api_key, {"status": "FINISHED", "limit": last})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_h2h(api_key, match_id):
    """H2H de un partido específico (football-data lo da por partido)."""
    data = fd_get(f"matches/{match_id}/head2head", api_key, {"limit": 10})
    return data.get("matches", [])

@st.cache_data(ttl=3600)
def get_standings(api_key, comp_code):
    """Tabla de posiciones actual."""
    data = fd_get(f"competitions/{comp_code}/standings", api_key)
    tables = data.get("standings", [])
    for t in tables:
        if t.get("type") == "TOTAL":
            return t.get("table", [])
    return []

@st.cache_data(ttl=3600)
def get_competition_teams(api_key, comp_code):
    """Equipos de una competición."""
    data = fd_get(f"competitions/{comp_code}/teams", api_key)
    return data.get("teams", [])

def get_live_odds(api_key, sport_key):
    """Momios en tiempo real de The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": api_key, "regions": "us,eu,uk", "markets": "h2h", "oddsFormat": "american"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return []

def extract_odds_for_match(live_data, home_name, away_name):
    """Busca el partido en los momios y extrae las casas."""
    home_lower = home_name.lower()
    away_lower = away_name.lower()
    best_game, best_score = None, 0
    for game in live_data:
        gh = game.get("home_team", "").lower()
        ga = game.get("away_team", "").lower()
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
        for mkt in bm.get("markets", []):
            if mkt["key"] == "h2h":
                oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                local, visita, empate = oc.get(hn), oc.get(an), oc.get("Draw")
                if local and visita and empate:
                    casas.append({"nombre": bm["title"],
                                  "local": float(local), "empate": float(empate), "visita": float(visita)})
    return casas

# ─────────────────────────────────────────────
#  PROCESAMIENTO STATS
# ─────────────────────────────────────────────

def calc_form_fd(matches, team_id):
    """Forma reciente con estructura de football-data.org."""
    results = []
    for m in matches[-5:]:
        s = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        is_home = m.get("homeTeam", {}).get("id") == team_id
        mg = hg if is_home else ag
        rg = ag if is_home else hg
        results.append(3 if mg > rg else (1 if mg == rg else 0))
    if not results: return 0.5
    return round(sum(results) / (len(results) * 3), 3)

def calc_avg_goals_fd(matches, team_id):
    gf, ga = [], []
    for m in matches:
        s = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
        if hg == 0 and ag == 0 and m.get("status") != "FINISHED":
            continue
        is_home = m.get("homeTeam", {}).get("id") == team_id
        gf.append(hg if is_home else ag)
        ga.append(ag if is_home else hg)
    if not gf: return 1.2, 1.2
    return round(sum(gf)/len(gf), 2), round(sum(ga)/len(ga), 2)

def calc_h2h_stats_fd(h2h_matches, home_id, away_id):
    hw = aw = dr = 0
    for m in h2h_matches:
        if m.get("status") != "FINISHED": continue
        s = m.get("score", {}).get("fullTime", {})
        hg = s.get("home", 0) or 0
        ag = s.get("away", 0) or 0
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
#  MODELO
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
    return {"home_win_pct": hp, "draw_pct": dp, "away_win_pct": ap,
            "exp_home_goals": exp_h, "exp_away_goals": exp_a,
            "exp_total_goals": exp_t,
            "over_25_prob": min(95, round((exp_t / 2.5) * 55, 1))}

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
    league_cfg   = LEAGUES[selected_league_name]
    COMP_CODE    = league_cfg["code"]
    ODDS_SPORT   = league_cfg["odds_key"]

    st.markdown("---")
    st.markdown("### 🔑 API Keys")

    football_api_key = st.text_input(
        "football-data.org Token",
        type="password",
        help="Gratis en football-data.org — regístrate y te envían el token por email"
    )
    odds_api_key = st.text_input(
        "The Odds API Key",
        type="password",
        help="Gratis en the-odds-api.com — 500 requests/mes"
    )

    st.markdown("---")
    st.markdown("### 💰 Bankroll")
    bankroll = st.number_input("Bankroll ($)", min_value=100, value=1000, step=100)

    st.markdown("---")
    st.markdown("### ⚙️ Filtros EV")
    min_ev        = st.slider("EV mínimo (%)", -20, 30, 5)
    max_kelly_pct = st.slider("Kelly máximo (%)", 1, 30, 10)

    st.markdown("---")
    if football_api_key:
        if st.button("🗑️ Limpiar caché"):
            st.cache_data.clear()
            st.success("Caché limpiado")

    st.markdown("---")
    st.markdown("""
    **Cómo obtener tu token gratis:**
    1. Ve a **football-data.org**
    2. Clic en **"Register for free"**
    3. Revisa tu email — te mandan el token
    4. Pégalo arriba ☝️
    """)
    st.caption("v4.0 · football-data.org + The Odds API")

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
        **Obtén tu token gratis (2 minutos):**
        1. Ve a: **https://www.football-data.org/client/register**
        2. Llena el formulario — no requiere tarjeta de crédito
        3. Recibirás el token en tu correo
        4. Pégalo en el sidebar izquierdo
        
        ✅ Cubre: Premier League, La Liga, Bundesliga, Serie A, Ligue 1 y Champions League
        """)
        st.stop()

    st.markdown("### 1️⃣ Selecciona el partido")
    search_mode = st.radio("", [
        "📅 Ver próximos partidos",
        "🔍 Buscar por equipos"
    ], horizontal=True)

    match_id       = None
    home_team_id   = None
    away_team_id   = None
    home_team_name = ""
    away_team_name = ""

    if search_mode == "📅 Ver próximos partidos":
        with st.spinner(f"Cargando partidos de {selected_league_name}..."):
            matches = get_upcoming_matches(football_api_key, COMP_CODE)

        if not matches:
            st.error("No se encontraron partidos próximos. Verifica tu token o la liga seleccionada.")
        else:
            match_options = {}
            for m in matches[:30]:
                date   = m["utcDate"][:10]
                home   = m["homeTeam"]["name"]
                away   = m["awayTeam"]["name"]
                mid    = m["id"]
                jornada = m.get("matchday", "?")
                label  = f"J{jornada} · {date} — {home} vs {away}"
                match_options[label] = m

            selected_label = st.selectbox("Partido", list(match_options.keys()))
            sel = match_options[selected_label]
            match_id       = sel["id"]
            home_team_id   = sel["homeTeam"]["id"]
            away_team_id   = sel["awayTeam"]["id"]
            home_team_name = sel["homeTeam"]["name"]
            away_team_name = sel["awayTeam"]["name"]

            ci1, ci2, ci3 = st.columns(3)
            ci1.metric("📅 Fecha",    sel["utcDate"][:10])
            ci2.metric("🗓️ Jornada",  sel.get("matchday","?"))
            ci3.metric("🔖 Match ID", match_id)

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

            # Buscar match ID
            with st.spinner("Buscando fixture..."):
                upcoming = get_upcoming_matches(football_api_key, COMP_CODE)
                for m in upcoming:
                    if (m["homeTeam"]["id"] == home_team_id and
                        m["awayTeam"]["id"] == away_team_id):
                        match_id = m["id"]
                        break
            if match_id:
                st.success(f"✅ Partido encontrado — ID: {match_id}")
            else:
                st.info("No se encontró fixture próximo; se analizará con datos históricos.")
        else:
            st.error("No se pudieron cargar los equipos.")

    st.markdown("---")
    if home_team_id and away_team_id:
        is_clasico = st.checkbox("⚡ ¿Es Clásico?", value=False)

        if st.button("🔮 ANALIZAR AUTOMÁTICAMENTE", use_container_width=True, type="primary"):
            with st.spinner("Jalando datos..."):
                home_matches = get_team_matches(football_api_key, home_team_id, 10)
                away_matches = get_team_matches(football_api_key, away_team_id, 10)
                h2h_matches  = get_h2h(football_api_key, match_id) if match_id else []

            home_form        = calc_form_fd(home_matches, home_team_id)
            away_form        = calc_form_fd(away_matches, away_team_id)
            home_gf, home_ga = calc_avg_goals_fd(home_matches, home_team_id)
            away_gf, away_ga = calc_avg_goals_fd(away_matches, away_team_id)
            h2h_hw, h2h_aw, h2h_dr = calc_h2h_stats_fd(h2h_matches, home_team_id, away_team_id)

            pred = predict_match(
                home_form, away_form, home_gf, away_gf,
                home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr, is_clasico
            )

            st.session_state.update({
                "pred": pred,
                "home_team": home_team_name,
                "away_team": away_team_name,
                "odds_sport_key": ODDS_SPORT,
                "auto_data": {
                    "home_form": home_form, "away_form": away_form,
                    "home_gf": home_gf, "home_ga": home_ga,
                    "away_gf": away_gf, "away_ga": away_ga,
                    "h2h_hw": h2h_hw, "h2h_aw": h2h_aw, "h2h_dr": h2h_dr,
                    "home_matches": home_matches,
                    "away_matches": away_matches,
                    "h2h_matches": h2h_matches,
                }
            })
            st.success("✅ Análisis listo. Ve al Tab 📡 Momios & EV para continuar.")

    # ── RESULTADOS ──
    if "pred" in st.session_state and "auto_data" in st.session_state:
        pred = st.session_state["pred"]
        data = st.session_state["auto_data"]
        ht   = st.session_state.get("home_team", "Local")
        at   = st.session_state.get("away_team", "Visitante")

        st.markdown("---")
        st.markdown(f'<div class="section-header">📊 {ht.upper()} VS {at.upper()}</div>', unsafe_allow_html=True)

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
        g1.metric(f"Goles {ht}",   pred['exp_home_goals'])
        g2.metric(f"Goles {at}",   pred['exp_away_goals'])
        g3.metric("Total",          pred['exp_total_goals'])
        g4.metric("Prob. Over 2.5", f"{pred['over_25_prob']}%")

        # Últimos partidos
        with st.expander("📋 Últimos partidos de cada equipo"):
            lc1, lc2 = st.columns(2)
            for col, matches, tid, tname in [
                (lc1, data['home_matches'], home_team_id, ht),
                (lc2, data['away_matches'], away_team_id, at)
            ]:
                with col:
                    st.markdown(f"**{tname}**")
                    shown = 0
                    for m in reversed(matches):
                        if m.get("status") != "FINISHED": continue
                        date = m["utcDate"][:10]
                        hn   = m["homeTeam"]["name"]
                        an   = m["awayTeam"]["name"]
                        s    = m.get("score", {}).get("fullTime", {})
                        hg   = s.get("home", 0) or 0
                        ag   = s.get("away", 0) or 0
                        ih   = m["homeTeam"]["id"] == tid
                        mg   = hg if ih else ag
                        rg   = ag if ih else hg
                        em   = "🟢" if mg > rg else ("🟡" if mg == rg else "🔴")
                        st.markdown(f"`{date}` {em} **{hn} {hg}–{ag} {an}**")
                        shown += 1
                        if shown >= 7: break

        # H2H
        with st.expander("⚔️ Historial H2H"):
            if data['h2h_matches']:
                for m in reversed(data['h2h_matches'][-8:]):
                    if m.get("status") != "FINISHED": continue
                    date = m["utcDate"][:10]
                    hn   = m["homeTeam"]["name"]
                    an   = m["awayTeam"]["name"]
                    s    = m.get("score", {}).get("fullTime", {})
                    hg   = s.get("home", 0) or 0
                    ag   = s.get("away", 0) or 0
                    st.markdown(f"`{date}` — **{hn} {hg}–{ag} {an}**")
            else:
                st.info("H2H no disponible para este partido.")

        # Tabla de posiciones
        with st.expander("📊 Tabla de posiciones actual"):
            with st.spinner("Cargando tabla..."):
                table = get_standings(football_api_key, COMP_CODE)
            if table:
                rows = []
                for row in table:
                    rows.append({
                        "Pos": row["position"],
                        "Equipo": row["team"]["name"],
                        "PJ": row["playedGames"],
                        "G": row["won"],
                        "E": row["draw"],
                        "P": row["lost"],
                        "GF": row["goalsFor"],
                        "GC": row["goalsAgainst"],
                        "Pts": row["points"],
                        "Forma": row.get("form", "")
                    })
                df_table = pd.DataFrame(rows)
                st.dataframe(df_table, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
#  TAB 2 — MOMIOS & EV
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 MOMIOS & VALOR ESPERADO</div>', unsafe_allow_html=True)

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
        pc2.metric("🤝 Empate",  f"{my_draw}%")
        pc3.metric(f"✈️ {at2}", f"{my_away}%")
    else:
        st.warning("Primero analiza un partido en el Tab 🎯.")
        ht2, at2 = "Local", "Visitante"
        pc1, pc2, pc3 = st.columns(3)
        my_home = pc1.number_input("Prob. Local (%)",    0.0, 100.0, 33.0)
        my_draw = pc2.number_input("Prob. Empate (%)",   0.0, 100.0, 33.0)
        my_away = pc3.number_input("Prob. Visitante (%)",0.0, 100.0, 34.0)

    st.markdown("---")

    # Importar momios en vivo
    st.markdown("#### 📡 Importar momios en tiempo real")
    st.caption(f"Liga: **{selected_league_name}** · sport key: `{ODDS_SPORT}`")

    if st.button("🔄 Importar momios en vivo", use_container_width=True):
        if not odds_api_key:
            st.error("Ingresa tu The Odds API Key en el sidebar.")
        else:
            with st.spinner("Importando momios..."):
                live_data = get_live_odds(odds_api_key, ODDS_SPORT)

            if not live_data or not isinstance(live_data, list):
                st.warning("No hay momios en vivo para esta liga en este momento.")
            else:
                matched = []
                if "home_team" in st.session_state:
                    matched = extract_odds_for_match(
                        live_data,
                        st.session_state["home_team"],
                        st.session_state["away_team"]
                    )

                if matched:
                    st.session_state["casas"] = matched
                    st.success(f"✅ ¡Momios importados de {len(matched)} casas para **{ht2} vs {at2}**! La tabla de abajo se actualizó.")
                else:
                    st.info("No se encontró el partido exacto. Mostrando todos los disponibles:")

                # Mostrar todos los partidos disponibles
                for game in live_data[:6]:
                    hn = game.get("home_team","")
                    an = game.get("away_team","")
                    date = game.get("commence_time","")[:10]
                    with st.expander(f"📊 {hn} vs {an} — {date}"):
                        rows_live = []
                        for bm in game.get("bookmakers",[])[:8]:
                            for mkt in bm.get("markets",[]):
                                if mkt["key"] == "h2h":
                                    oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                    rows_live.append({
                                        "Casa": bm["title"],
                                        "Local": oc.get(hn,"?"),
                                        "Empate": oc.get("Draw","?"),
                                        "Visita": oc.get(an,"?"),
                                    })
                        if rows_live:
                            st.dataframe(pd.DataFrame(rows_live), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Tabla de momios editable (se auto-rellena con live)
    st.markdown("#### 🏦 Casas de apuestas")
    st.caption("Se rellenan automáticamente al importar momios. También puedes editarlos manualmente.")

    if "casas" not in st.session_state:
        st.session_state["casas"] = [
            {"nombre": "Caliente",  "local": 240.0, "empate": 230.0, "visita": -140.0},
            {"nombre": "Betcris",   "local": 220.0, "empate": 240.0, "visita": -150.0},
            {"nombre": "Codere",    "local": 250.0, "empate": 220.0, "visita": -145.0},
            {"nombre": "Bet365",    "local": 235.0, "empate": 225.0, "visita": -142.0},
        ]

    for i, casa in enumerate(st.session_state["casas"]):
        cols = st.columns([2, 1, 1, 1, 0.4])
        with cols[0]: casa["nombre"] = st.text_input("Casa",   casa["nombre"],         key=f"cn_{i}")
        with cols[1]: casa["local"]  = st.number_input("Local",  float(casa["local"]),   key=f"cl_{i}", step=5.0)
        with cols[2]: casa["empate"] = st.number_input("Empate", float(casa["empate"]),  key=f"ce_{i}", step=5.0)
        with cols[3]: casa["visita"] = st.number_input("Visita", float(casa["visita"]),  key=f"cv_{i}", step=5.0)
        with cols[4]:
            if st.button("🗑", key=f"cd_{i}"):
                st.session_state["casas"].pop(i); st.rerun()

    if st.button("➕ Agregar casa"):
        st.session_state["casas"].append({"nombre":"Nueva","local":200.0,"empate":230.0,"visita":-160.0})
        st.rerun()

    st.markdown("---")

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
            st.warning(f"No hay apuestas con EV ≥ {min_ev}%.")
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

        if not best.empty:
            top = best.iloc[0]
            st.session_state["calc_prefill"] = {
                "american": float(str(top["Momio"]).replace("+","")),
                "my_prob":  float(str(top["MiProb"]).replace("%",""))
            }
            st.info("💡 La mejor apuesta se cargó en la **Calculadora EV** (Tab 🧮)")

        st.markdown("---")
        st.dataframe(df.drop(columns=["Dec"]), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA EV
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA DE VALOR ESPERADO</div>', unsafe_allow_html=True)

    prefill    = st.session_state.get("calc_prefill", {})
    default_am = prefill.get("american", 240.0)
    default_p  = prefill.get("my_prob",  28.0)

    if prefill:
        st.success("✅ Valores cargados automáticamente desde la mejor apuesta del Tab 📡")

    c1, c2, c3 = st.columns(3)
    with c1: calc_am = st.number_input("Momio americano",    value=float(default_am), step=5.0)
    with c2: calc_p  = st.number_input("Mi probabilidad (%)", 0.0, 100.0, float(default_p))
    with c3: calc_bk = st.number_input("Bankroll ($)",        min_value=100, value=bankroll, step=100)

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
    bk_sim  = [calc_bk]
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
    st.caption("⚠️ Simulación aleatoria ilustrativa.")

# ══════════════════════════════════════════════
#  TAB 4 — GUÍA
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📖 GUÍA DE USO</div>', unsafe_allow_html=True)
    st.markdown("""
### 🔧 Setup (una sola vez)

#### 1. football-data.org Token (estadísticas, fixtures, H2H)
1. Ve a: **https://www.football-data.org/client/register**
2. Llena el formulario — **gratis, sin tarjeta**
3. Recibirás el token en tu correo (llega en minutos)
4. Pégalo en el sidebar

#### 2. The Odds API Key (momios en tiempo real)
1. Ve a: **https://the-odds-api.com**
2. Regístrate gratis — **500 requests/mes gratis**
3. Pégala en el sidebar

---

### 📋 Flujo de uso

| Paso | Tab | Acción |
|------|-----|--------|
| 1 | 🎯 Análisis | Elige la liga en el sidebar → selecciona el partido → Analizar |
| 2 | 📡 Momios & EV | Presiona "Importar momios en vivo" → se rellenan automáticamente |
| 3 | 📡 Momios & EV | Presiona "Calcular Valor Esperado" → ves qué apuestas tienen valor |
| 4 | 🧮 Calculadora | La mejor apuesta se carga sola para simular rentabilidad |

### 🏆 Ligas disponibles (gratis)
Premier League · La Liga · Bundesliga · Serie A · Ligue 1 · Champions League

### 💡 Cómo funcionan los momios auto-importados
Al picar **"Importar momios en vivo"**, el sistema jala los momios de 40+ casas de apuestas,
busca automáticamente el partido que analizaste, y rellena la tabla completa con los valores reales.
La mejor apuesta identificada se carga sola en la Calculadora EV.

---
⚠️ *Herramienta de análisis estadístico. Las apuestas conllevan riesgo real. Juega responsablemente.*
    """)
