import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import random

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Liga MX · Betting Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

LIGA_MX_ID = 262
CURRENT_SEASON = 2025  # API-Football: temporada de inicio (Clausura 2026 = 2025)

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
.bet-row-negative { background: rgba(255,68,102,0.08);  border-left: 3px solid #ff4466; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-neutral  { background: rgba(255,204,68,0.08);  border-left: 3px solid #ffcc44; padding: 12px; border-radius: 6px; margin: 6px 0; }
.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.75em; font-weight:600; margin:2px; }
.tag-green  { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red    { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow { background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }
.player-card {
    background: #12121a; border: 1px solid #2a2a40; border-radius: 8px;
    padding: 10px 14px; margin: 4px 0; font-size: 0.9em;
}
.section-header {
    font-family: 'Bebas Neue'; font-size: 1.8em; letter-spacing:3px;
    color: #00ff88; border-bottom: 1px solid #2a2a40;
    padding-bottom: 8px; margin: 24px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  API HELPERS
# ─────────────────────────────────────────────

def api_football(endpoint, params, api_key):
    url = f"https://v3.football.api-sports.io/{endpoint}"
    headers = {"x-apisports-key": api_key}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            return {"error": str(data["errors"])}
        return data
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=3600)
def get_upcoming_fixtures(api_key):
    data = api_football("fixtures", {
        "league": LIGA_MX_ID, "season": CURRENT_SEASON, "next": 20
    }, api_key)
    return data.get("response", [])

@st.cache_data(ttl=3600)
def get_team_last_matches(api_key, team_id, last=10):
    data = api_football("fixtures", {
        "team": team_id, "last": last,
        "league": LIGA_MX_ID, "season": CURRENT_SEASON
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
def get_all_teams(api_key):
    data = api_football("teams", {
        "league": LIGA_MX_ID, "season": CURRENT_SEASON
    }, api_key)
    return data.get("response", [])

def get_live_odds(api_key, sport="soccer_mexico_ligamx"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {"apiKey": api_key, "regions": "us,eu,uk", "markets": "h2h", "oddsFormat": "american"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return []

# ─────────────────────────────────────────────
#  PROCESAMIENTO
# ─────────────────────────────────────────────

def calc_form(matches, team_id):
    results = []
    for m in matches[-5:]:
        if m["fixture"]["status"]["short"] not in ["FT", "AET", "PEN"]:
            continue
        home_id = m["teams"]["home"]["id"]
        hg = m["goals"]["home"] or 0
        ag = m["goals"]["away"] or 0
        if home_id == team_id:
            results.append(3 if hg > ag else (1 if hg == ag else 0))
        else:
            results.append(3 if ag > hg else (1 if ag == hg else 0))
    if not results:
        return 0.5
    return round(sum(results) / (len(results) * 3), 3)

def calc_avg_goals(matches, team_id):
    gf, ga = [], []
    for m in matches:
        if m["fixture"]["status"]["short"] not in ["FT", "AET", "PEN"]:
            continue
        is_home = m["teams"]["home"]["id"] == team_id
        hg = m["goals"]["home"] or 0
        ag = m["goals"]["away"] or 0
        gf.append(hg if is_home else ag)
        ga.append(ag if is_home else hg)
    if not gf:
        return 1.2, 1.2
    return round(sum(gf)/len(gf), 2), round(sum(ga)/len(ga), 2)

def calc_h2h_stats(h2h_matches, home_id, away_id):
    hw = aw = dr = 0
    for m in h2h_matches:
        if m["fixture"]["status"]["short"] not in ["FT", "AET", "PEN"]:
            continue
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
    st.markdown("# ⚽ LIGA MX\n### Betting Analytics")
    st.markdown("---")
    st.markdown("### 🔑 API Keys")
    football_api_key = st.text_input("API-Football Key", type="password",
        help="Gratis en api-sports.io")
    odds_api_key = st.text_input("The Odds API Key", type="password",
        help="Gratis en the-odds-api.com")
    st.markdown("---")
    st.markdown("### 💰 Bankroll")
    bankroll = st.number_input("Bankroll ($MXN)", min_value=100, value=1000, step=100)
    st.markdown("---")
    st.markdown("### ⚙️ Filtros")
    min_ev = st.slider("EV mínimo (%)", -20, 30, 5)
    max_kelly_pct = st.slider("Kelly máximo (%)", 1, 30, 10)
    st.markdown("---")
    if football_api_key:
        if st.button("🗑️ Limpiar caché"):
            st.cache_data.clear()
            st.success("Caché limpiado")
    st.caption("v2.0 · Liga MX Betting Analytics")

# ─────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Análisis Automático",
    "📡 Momios en Vivo",
    "🧮 Calculadora EV",
    "📖 Guía"
])

# ══════════════════════════════════════════════
#  TAB 1 — ANÁLISIS AUTOMÁTICO
# ══════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🎯 ANÁLISIS AUTOMÁTICO DE PARTIDO</div>', unsafe_allow_html=True)

    if not football_api_key:
        # DIAGNÓSTICO TEMPORAL - borrar después
import json
if football_api_key:
    st.markdown("### 🔍 Diagnóstico")
    
    # Test temporadas disponibles
    r1 = api_football("leagues", {"id": 262}, football_api_key)
    seasons = r1.get("response", [{}])[0].get("seasons", [])
    st.write("Temporadas disponibles:", [s["year"] for s in seasons[-5:]])
    
    # Test fixtures con temporada 2025
    r2 = api_football("fixtures", {"league": 262, "season": 2025, "next": 5}, football_api_key)
    st.write("Fixtures 2025:", len(r2.get("response", [])), "encontrados")
    
    # Test fixtures con temporada 2024
    r3 = api_football("fixtures", {"league": 262, "season": 2024, "next": 5}, football_api_key)
    st.write("Fixtures 2024:", len(r3.get("response", [])), "encontrados")
    
    # Errores de la API
    st.write("Errores API:", r2.get("errors", "ninguno"))
    st.write("Requests restantes:", r2.get("parameters", {}))
        st.warning("👈 Ingresa tu API Key de API-Football en el sidebar para activar el modo automático.")
        st.info("Regístrate gratis en: https://dashboard.api-football.com/register")
        st.stop()

    st.markdown("### 1️⃣ Selecciona el partido")
    search_mode = st.radio("", [
        "📅 Ver jornada completa (próximos partidos)",
        "🔍 Buscar escribiendo los equipos"
    ], horizontal=True)

    fixture_id = None
    home_team_id = None
    away_team_id = None
    home_team_name = ""
    away_team_name = ""

    if search_mode == "📅 Ver jornada completa (próximos partidos)":
        with st.spinner("Cargando partidos próximos de Liga MX..."):
            fixtures = get_upcoming_fixtures(football_api_key)

        if not fixtures:
            st.error("No se encontraron partidos. Verifica tu API Key.")
        else:
            fixture_options = {}
            for f in fixtures:
                fecha = f["fixture"]["date"][:10]
                hora  = f["fixture"]["date"][11:16]
                home  = f["teams"]["home"]["name"]
                away  = f["teams"]["away"]["name"]
                fid   = f["fixture"]["id"]
                label = f"{fecha} {hora} — {home} vs {away}"
                fixture_options[label] = f

            selected_label   = st.selectbox("Partido", list(fixture_options.keys()))
            selected_fixture = fixture_options[selected_label]
            fixture_id       = selected_fixture["fixture"]["id"]
            home_team_id     = selected_fixture["teams"]["home"]["id"]
            away_team_id     = selected_fixture["teams"]["away"]["id"]
            home_team_name   = selected_fixture["teams"]["home"]["name"]
            away_team_name   = selected_fixture["teams"]["away"]["name"]

            col_info = st.columns(3)
            col_info[0].metric("🏟️ Estadio", selected_fixture["fixture"].get("venue", {}).get("name", "N/D"))
            col_info[1].metric("📅 Fecha", selected_fixture["fixture"]["date"][:10])
            col_info[2].metric("🔖 Fixture ID", fixture_id)

    else:  # Buscar por equipos
        with st.spinner("Cargando equipos de Liga MX..."):
            teams_list = get_all_teams(football_api_key)

        if teams_list:
            team_map   = {t["team"]["name"]: t["team"]["id"] for t in teams_list}
            team_names = sorted(team_map.keys())

            c1, c2 = st.columns(2)
            with c1:
                home_team_name = st.selectbox("🏠 Equipo Local", team_names, index=0)
            with c2:
                other_teams = [t for t in team_names if t != home_team_name]
                away_team_name = st.selectbox("✈️ Equipo Visitante", other_teams, index=0)

            home_team_id = team_map[home_team_name]
            away_team_id = team_map[away_team_name]

            with st.spinner("Buscando fixture próximo entre estos equipos..."):
                all_fix = get_upcoming_fixtures(football_api_key)
                for f in all_fix:
                    if (f["teams"]["home"]["id"] == home_team_id and
                        f["teams"]["away"]["id"] == away_team_id):
                        fixture_id = f["fixture"]["id"]
                        break

            if fixture_id:
                st.success(f"✅ Partido encontrado — ID: {fixture_id}")
            else:
                st.info("ℹ️ No se encontró partido próximo programado entre estos equipos, pero se analizarán con datos históricos.")
        else:
            st.error("No se pudieron cargar los equipos. Verifica tu API Key.")

    # ── ANALIZAR ──
    st.markdown("---")
    if home_team_id and away_team_id:
        is_clasico = st.checkbox("⚡ ¿Es Clásico? (el modelo ajusta al equilibrio)", value=False)

        if st.button("🔮 ANALIZAR AUTOMÁTICAMENTE", use_container_width=True, type="primary"):
            with st.spinner(f"Jalando datos de {home_team_name} y {away_team_name}..."):
                home_matches = get_team_last_matches(football_api_key, home_team_id, 10)
                away_matches = get_team_last_matches(football_api_key, away_team_id, 10)
                h2h_matches  = get_h2h(football_api_key, home_team_id, away_team_id, 10)
                lineups      = get_fixture_lineups(football_api_key, fixture_id) if fixture_id else []
                api_pred     = get_fixture_predictions(football_api_key, fixture_id) if fixture_id else {}

            home_form         = calc_form(home_matches, home_team_id)
            away_form         = calc_form(away_matches, away_team_id)
            home_gf, home_ga  = calc_avg_goals(home_matches, home_team_id)
            away_gf, away_ga  = calc_avg_goals(away_matches, away_team_id)
            h2h_hw, h2h_aw, h2h_dr = calc_h2h_stats(h2h_matches, home_team_id, away_team_id)

            pred = predict_match(
                home_form, away_form, home_gf, away_gf,
                home_ga, away_ga, h2h_hw, h2h_aw, h2h_dr, is_clasico
            )

            st.session_state.update({
                "pred": pred,
                "home_team": home_team_name,
                "away_team": away_team_name,
                "auto_data": {
                    "home_form": home_form, "away_form": away_form,
                    "home_gf": home_gf, "home_ga": home_ga,
                    "away_gf": away_gf, "away_ga": away_ga,
                    "h2h_hw": h2h_hw, "h2h_aw": h2h_aw, "h2h_dr": h2h_dr,
                    "home_matches": home_matches, "away_matches": away_matches,
                    "h2h_matches": h2h_matches, "lineups": lineups, "api_pred": api_pred
                }
            })

    # ── RESULTADOS ──
    if "pred" in st.session_state and "auto_data" in st.session_state:
        pred = st.session_state["pred"]
        data = st.session_state["auto_data"]
        ht   = st.session_state.get("home_team", "Local")
        at   = st.session_state.get("away_team", "Visitante")

        st.markdown("---")
        st.markdown(f'<div class="section-header">📊 {ht.upper()} VS {at.upper()}</div>', unsafe_allow_html=True)

        # Datos auto-jalados
        st.markdown("#### 📥 Datos jalados automáticamente <span class='tag tag-green'>AUTO</span>", unsafe_allow_html=True)
        d1, d2, d3 = st.columns(3)
        with d1:
            form_pct = round(data['home_form'] * 100)
            form_color = "#00ff88" if form_pct >= 60 else ("#ffcc44" if form_pct >= 40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888;">🏠 Forma {ht} (últ. 5 partidos)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{form_color}">{form_pct}%</div>
                <div style="font-size:0.82em;color:#aaa;">⚽ {data['home_gf']} goles/partido &nbsp;🛡️ {data['home_ga']} recibidos</div>
            </div>""", unsafe_allow_html=True)
        with d2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888;">⚔️ Historial H2H (últ. 10)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:#ffcc44">{data['h2h_hw']} – {data['h2h_dr']} – {data['h2h_aw']}</div>
                <div style="font-size:0.82em;color:#aaa;">{ht} · Empates · {at}</div>
            </div>""", unsafe_allow_html=True)
        with d3:
            form_pct_a = round(data['away_form'] * 100)
            form_color_a = "#00ff88" if form_pct_a >= 60 else ("#ffcc44" if form_pct_a >= 40 else "#ff4466")
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.75em;color:#888;">✈️ Forma {at} (últ. 5 partidos)</div>
                <div style="font-family:'Space Mono';font-size:1.5em;color:{form_color_a}">{form_pct_a}%</div>
                <div style="font-size:0.82em;color:#aaa;">⚽ {data['away_gf']} goles/partido &nbsp;🛡️ {data['away_ga']} recibidos</div>
            </div>""", unsafe_allow_html=True)

        # Predicción del modelo
        st.markdown("#### 🔮 Predicción del modelo")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">🏠 Victoria {ht}</div>
                <div class="value-neutral">{pred['home_win_pct']}%</div>
            </div>""", unsafe_allow_html=True)
        with p2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">🤝 Empate</div>
                <div class="value-neutral">{pred['draw_pct']}%</div>
            </div>""", unsafe_allow_html=True)
        with p3:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">✈️ Victoria {at}</div>
                <div class="value-neutral">{pred['away_win_pct']}%</div>
            </div>""", unsafe_allow_html=True)

        # Goles esperados
        st.markdown("#### ⚽ Goles esperados por el modelo")
        g1, g2, g3, g4 = st.columns(4)
        g1.metric(f"Goles {ht}", pred['exp_home_goals'])
        g2.metric(f"Goles {at}", pred['exp_away_goals'])
        g3.metric("Total esperado", pred['exp_total_goals'])
        g4.metric("Prob. Over 2.5", f"{pred['over_25_prob']}%")

        # Predicción de la API
        if data.get("api_pred"):
            ap = data["api_pred"]
            comp = ap.get("predictions", {})
            winner = comp.get("winner", {})
            pct = comp.get("percent", {})
            advice = comp.get("advice", "")
            if pct:
                st.markdown("#### 🤖 Predicción de API-Football (comparación)")
                ac1, ac2, ac3, ac4 = st.columns(4)
                ac1.metric("API: Local", pct.get("home", "?"))
                ac2.metric("API: Empate", pct.get("draw", "?"))
                ac3.metric("API: Visitante", pct.get("away", "?"))
                ac4.metric("Ganador sugerido", winner.get("name", "N/D") if winner else "N/D")
                if advice:
                    st.info(f"💡 {advice}")

        # Últimos partidos
        with st.expander("📋 Últimos partidos de cada equipo"):
            col_home, col_away = st.columns(2)
            with col_home:
                st.markdown(f"**{ht}**")
                shown = 0
                for m in reversed(data['home_matches']):
                    if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
                    date  = m["fixture"]["date"][:10]
                    hname = m["teams"]["home"]["name"]
                    aname = m["teams"]["away"]["name"]
                    hg    = m["goals"]["home"] or 0
                    ag    = m["goals"]["away"] or 0
                    is_home = m["teams"]["home"]["id"] == home_team_id
                    mg = hg if is_home else ag
                    rg = ag if is_home else hg
                    emoji = "🟢" if mg > rg else ("🟡" if mg == rg else "🔴")
                    st.markdown(f"`{date}` {emoji} **{hname} {hg}–{ag} {aname}**")
                    shown += 1
                    if shown >= 7: break

            with col_away:
                st.markdown(f"**{at}**")
                shown = 0
                for m in reversed(data['away_matches']):
                    if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
                    date  = m["fixture"]["date"][:10]
                    hname = m["teams"]["home"]["name"]
                    aname = m["teams"]["away"]["name"]
                    hg    = m["goals"]["home"] or 0
                    ag    = m["goals"]["away"] or 0
                    is_home = m["teams"]["home"]["id"] == away_team_id
                    mg = hg if is_home else ag
                    rg = ag if is_home else hg
                    emoji = "🟢" if mg > rg else ("🟡" if mg == rg else "🔴")
                    st.markdown(f"`{date}` {emoji} **{hname} {hg}–{ag} {aname}**")
                    shown += 1
                    if shown >= 7: break

        # H2H
        with st.expander("⚔️ Historial H2H detallado"):
            if data['h2h_matches']:
                for m in reversed(data['h2h_matches'][-8:]):
                    if m["fixture"]["status"]["short"] not in ["FT","AET","PEN"]: continue
                    date  = m["fixture"]["date"][:10]
                    hname = m["teams"]["home"]["name"]
                    aname = m["teams"]["away"]["name"]
                    hg    = m["goals"]["home"] or 0
                    ag    = m["goals"]["away"] or 0
                    st.markdown(f"`{date}` — **{hname} {hg}–{ag} {aname}**")
            else:
                st.info("No se encontró historial H2H disponible.")

        # Alineaciones
        with st.expander("👥 Alineaciones (disponibles ~1h antes del partido)"):
            lineups = data.get("lineups", [])
            if lineups:
                lc1, lc2 = st.columns(2)
                for i, team_lineup in enumerate(lineups[:2]):
                    tname     = team_lineup.get("team", {}).get("name", f"Equipo {i+1}")
                    formation = team_lineup.get("formation", "?")
                    players   = team_lineup.get("startXI", [])
                    with (lc1 if i == 0 else lc2):
                        st.markdown(f"**{tname}** — `{formation}`")
                        for p in players:
                            pi = p.get("player", {})
                            st.markdown(f'<div class="player-card">#{pi.get("number","?")} <b>{pi.get("name","?")}</b> <span style="color:#888;font-size:0.85em;">{pi.get("pos","?")}</span></div>', unsafe_allow_html=True)
                        subs = team_lineup.get("substitutes", [])
                        if subs:
                            st.markdown("*Suplentes:*")
                            for p in subs[:5]:
                                pi = p.get("player", {})
                                st.caption(f"· {pi.get('name','?')} ({pi.get('pos','?')})")
            else:
                st.info("⏳ Las alineaciones aparecen ~1 hora antes del partido cuando el técnico las confirma oficialmente.")

# ══════════════════════════════════════════════
#  TAB 2 — MOMIOS + EV
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 MOMIOS & VALOR ESPERADO</div>', unsafe_allow_html=True)

    col_probs, col_odds = st.columns([1, 2])

    with col_probs:
        st.markdown("#### 🎯 Mis probabilidades")
        if "pred" in st.session_state:
            pred = st.session_state["pred"]
            ht2  = st.session_state.get("home_team", "Local")
            at2  = st.session_state.get("away_team", "Visitante")
            st.success("Usando predicción automática del Tab 1")
            st.metric(f"🏠 {ht2}", f"{pred['home_win_pct']}%")
            st.metric("🤝 Empate", f"{pred['draw_pct']}%")
            st.metric(f"✈️ {at2}", f"{pred['away_win_pct']}%")
            my_home = pred['home_win_pct']
            my_draw = pred['draw_pct']
            my_away = pred['away_win_pct']
        else:
            st.warning("Primero analiza un partido en Tab 1, o ingresa manualmente:")
            ht2, at2 = "Local", "Visitante"
            my_home = st.number_input("Prob. Local (%)",    0.0, 100.0, 30.0)
            my_draw = st.number_input("Prob. Empate (%)",   0.0, 100.0, 30.0)
            my_away = st.number_input("Prob. Visitante (%)",0.0, 100.0, 40.0)

    with col_odds:
        st.markdown("#### 🏦 Momios de casas de apuestas")
        st.caption("Ingresa momios americanos. Ej: +240 (ganarías $240 por cada $100) | -140 (apuestas $140 para ganar $100)")

        if "casas" not in st.session_state:
            st.session_state["casas"] = [
                {"nombre": "Caliente",  "local": 240,  "empate": 230, "visita": -140},
                {"nombre": "Betcris",   "local": 220,  "empate": 240, "visita": -150},
                {"nombre": "Codere",    "local": 250,  "empate": 220, "visita": -145},
                {"nombre": "Bet365",    "local": 235,  "empate": 225, "visita": -142},
            ]

        for i, casa in enumerate(st.session_state["casas"]):
            cols = st.columns([2, 1, 1, 1, 0.4])
            with cols[0]: casa["nombre"] = st.text_input("Casa",   casa["nombre"],        key=f"cn_{i}")
            with cols[1]: casa["local"]  = st.number_input("Local",  float(casa["local"]),  key=f"cl_{i}", step=5.0)
            with cols[2]: casa["empate"] = st.number_input("Empate", float(casa["empate"]), key=f"ce_{i}", step=5.0)
            with cols[3]: casa["visita"] = st.number_input("Visita", float(casa["visita"]), key=f"cv_{i}", step=5.0)
            with cols[4]:
                if st.button("🗑", key=f"cd_{i}"):
                    st.session_state["casas"].pop(i); st.rerun()

        if st.button("➕ Agregar casa de apuestas"):
            st.session_state["casas"].append({"nombre":"Nueva","local":200,"empate":230,"visita":-160})
            st.rerun()

    # Momios live via API
    if odds_api_key:
        st.markdown("---")
        if st.button("🔄 Importar momios en tiempo real (The Odds API)"):
            with st.spinner("Importando..."):
                live = get_live_odds(odds_api_key)
            if live and isinstance(live, list):
                st.success(f"{len(live)} partidos con momios encontrados")
                for game in live[:3]:
                    hn = game.get("home_team","")
                    an = game.get("away_team","")
                    with st.expander(f"📊 {hn} vs {an}"):
                        for bm in game.get("bookmakers",[])[:5]:
                            bname = bm["title"]
                            for mkt in bm.get("markets",[]):
                                if mkt["key"] == "h2h":
                                    oc = {o["name"]: o["price"] for o in mkt["outcomes"]}
                                    st.markdown(f"**{bname}**: {hn} `{oc.get(hn,'?')}` | Draw `{oc.get('Draw','?')}` | {an} `{oc.get(an,'?')}`")
            else:
                st.warning("No se encontraron momios o verifica tu API Key / sport key.")

    # Análisis EV
    st.markdown("---")
    if st.button("⚡ ANALIZAR VALOR ESPERADO", use_container_width=True, type="primary"):
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
                    "Dec": dec, "Prob. Casa": f"{impl}%",
                    "Mi Prob.": f"{my_prob}%", "EV": ev,
                    "Kelly%": k, "Apostar ($MXN)": apuesta
                })

        df   = pd.DataFrame(rows)
        best = df[df["EV"] >= (min_ev/100)].sort_values("EV", ascending=False)

        st.markdown("### 💡 Apuestas con valor")
        if best.empty:
            st.warning(f"No hay apuestas con EV ≥ {min_ev}%.")
        else:
            for _, row in best.iterrows():
                ev_pct = row["EV"] * 100
                if ev_pct >= 10:   css, tc, em = "bet-row-positive", "tag-green",  "🟢"
                elif ev_pct >= 5:  css, tc, em = "bet-row-neutral",  "tag-yellow", "🟡"
                else:              css, tc, em = "bet-row-negative", "tag-red",    "🔴"
                st.markdown(f"""<div class="{css}">
                    <b>{em} {row['Casa']} — {row['Mercado']}</b>
                    &nbsp;<span class="tag {tc}">EV: {ev_pct:.1f}%</span>
                    &nbsp;<span class="tag {tc}">Kelly: {row['Kelly%']}%</span>
                    <br>
                    Momio: <span style="font-family:'Space Mono'">{row['Momio']}</span>
                    &emsp;Prob. casa: <b>{row['Prob. Casa']}</b>
                    &emsp;Mi prob.: <b>{row['Mi Prob.']}</b>
                    &emsp;💰 Apostar: <b>${row['Apostar ($MXN)']:,.0f} MXN</b>
                </div>""", unsafe_allow_html=True)

        st.markdown("---")
        st.dataframe(df.drop(columns=["Dec"]), use_container_width=True)

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA EV
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA DE VALOR ESPERADO</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1: calc_am = st.number_input("Momio americano", value=240, step=5)
    with c2: calc_p  = st.number_input("Mi probabilidad (%)", 0.0, 100.0, 28.0)
    with c3: calc_bk = st.number_input("Bankroll ($MXN)", min_value=100, value=bankroll, step=100)

    calc_dec    = american_to_decimal(calc_am)
    calc_impl   = implied_prob(calc_dec)
    calc_ev_v   = calc_ev(calc_p, calc_dec)
    calc_k      = min(kelly_criterion(calc_p, calc_dec), max_kelly_pct)
    calc_apuesta = round((calc_k/100) * calc_bk, 2)

    r1, r2, r3, r4 = st.columns(4)
    ev_color = "#00ff88" if calc_ev_v > 0 else "#ff4466"
    with r1: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888;">Decimal</div><div style="font-family:Space Mono;font-size:1.3em">{calc_dec}</div></div>', unsafe_allow_html=True)
    with r2: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888;">Prob. Implícita</div><div style="font-family:Space Mono;font-size:1.3em">{calc_impl}%</div></div>', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888;">Expected Value</div><div style="font-family:Space Mono;font-size:1.3em;color:{ev_color}">{calc_ev_v*100:.1f}%</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="metric-card"><div style="font-size:0.8em;color:#888;">Apostar (Kelly)</div><div style="font-family:Space Mono;font-size:1.3em;color:#00ff88">${calc_apuesta:,.0f}</div></div>', unsafe_allow_html=True)

    if calc_ev_v > 0.10:   st.success(f"✅ Buena apuesta — EV +{calc_ev_v*100:.1f}%")
    elif calc_ev_v > 0:    st.warning(f"🟡 Valor marginal (+{calc_ev_v*100:.1f}%)")
    else:                   st.error(f"❌ Sin valor ({calc_ev_v*100:.1f}%)")

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
    chg   = round(((final-calc_bk)/calc_bk)*100, 1)
    (st.success if final > calc_bk else st.error)(f"Resultado simulado: ${final:,.0f} MXN ({'+' if chg>0 else ''}{chg}%)")
    st.caption("⚠️ Simulación aleatoria ilustrativa. Cada corrida es diferente.")

# ══════════════════════════════════════════════
#  TAB 4 — GUÍA
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📖 GUÍA DE USO</div>', unsafe_allow_html=True)
    st.markdown("""
### ¿Qué jala automáticamente el sistema?

Con solo ingresar tu API Key de API-Football, el sistema extrae automáticamente:

| Dato | Descripción |
|------|-------------|
| ✅ **Forma reciente** | Resultados de los últimos 5 partidos en Liga MX |
| ✅ **Promedio de goles** | Anotados y recibidos en la temporada actual |
| ✅ **Historial H2H** | Últimos 10 enfrentamientos directos |
| ✅ **Goles esperados** | Calculados con el modelo interno |
| ✅ **Alineaciones** | Disponibles ~1 hora antes del partido |
| ✅ **Predicción API** | Comparación con el modelo propio de API-Football |

### Flujo recomendado

1. **Tab 1** → selecciona el partido → presiona "Analizar Automáticamente"
2. **Tab 2** → ingresa los momios de Caliente, Betcris, Codere, etc. → presiona "Analizar EV"
3. Las apuestas en **verde** tienen valor matemático positivo
4. La columna **Kelly%** te dice qué fracción de tu bankroll apostar de forma óptima

### Glosario

| Término | Explicación |
|---------|-------------|
| **EV +15%** | Por cada $100 apostados, ganarías $15 en promedio a largo plazo (si tus probabilidades son correctas) |
| **Kelly 5%** | Apuesta el 5% de tu bankroll en esta jugada |
| **Prob. Implícita** | Lo que la casa "cree" que va a pasar, expresado como % |
| **H2H** | Historial de enfrentamientos directos entre ambos equipos |

### APIs necesarias (ambas gratuitas)
- **API-Football**: [dashboard.api-football.com](https://dashboard.api-football.com/register)
- **The Odds API**: [the-odds-api.com](https://the-odds-api.com)

---
⚠️ *Herramienta de análisis estadístico. Las apuestas conllevan riesgo real. Juega responsablemente y solo si eres mayor de edad.*
    """)
