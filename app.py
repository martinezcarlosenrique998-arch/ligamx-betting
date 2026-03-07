import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import os

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Liga MX · Betting Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    border: 1px solid #2a2a40;
    border-radius: 12px;
    padding: 20px;
    margin: 8px 0;
    transition: all 0.3s ease;
}
.metric-card:hover { border-color: #00ff88; transform: translateY(-2px); }

.value-positive { color: #00ff88; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.value-negative { color: #ff4466; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }
.value-neutral   { color: #ffcc44; font-family: 'Space Mono'; font-size: 1.4em; font-weight: 700; }

.bet-row-positive { background: rgba(0,255,136,0.08); border-left: 3px solid #00ff88; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-negative  { background: rgba(255,68,102,0.08);  border-left: 3px solid #ff4466; padding: 12px; border-radius: 6px; margin: 6px 0; }
.bet-row-neutral   { background: rgba(255,204,68,0.08);  border-left: 3px solid #ffcc44; padding: 12px; border-radius: 6px; margin: 6px 0; }

.tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.75em; font-weight:600; margin:2px; }
.tag-green { background:#00ff8822; color:#00ff88; border:1px solid #00ff8855; }
.tag-red   { background:#ff446622; color:#ff4466; border:1px solid #ff446655; }
.tag-yellow{ background:#ffcc4422; color:#ffcc44; border:1px solid #ffcc4455; }

.section-header {
    font-family: 'Bebas Neue'; font-size: 1.8em; letter-spacing:3px;
    color: #00ff88; border-bottom: 1px solid #2a2a40;
    padding-bottom: 8px; margin: 24px 0 16px 0;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  FUNCIONES CORE
# ─────────────────────────────────────────────

def american_to_decimal(american: float) -> float:
    if american > 0:
        return round((american / 100) + 1, 4)
    else:
        return round((100 / abs(american)) + 1, 4)

def decimal_to_implied_prob(decimal: float) -> float:
    if decimal <= 0:
        return 0
    return round((1 / decimal) * 100, 2)

def american_to_implied_prob(american: float) -> float:
    dec = american_to_decimal(american)
    return decimal_to_implied_prob(dec)

def calc_ev(my_prob_pct: float, decimal_odds: float) -> float:
    """Expected Value. Positivo = apuesta con valor."""
    p = my_prob_pct / 100
    return round((p * decimal_odds) - 1, 4)

def kelly_criterion(my_prob_pct: float, decimal_odds: float) -> float:
    """Fracción Kelly óptima del bankroll a apostar."""
    p = my_prob_pct / 100
    q = 1 - p
    b = decimal_odds - 1
    if b <= 0:
        return 0
    kelly = (b * p - q) / b
    return max(0, round(kelly * 100, 2))  # como porcentaje del bankroll

def get_live_odds(api_key: str, sport: str = "soccer_mexico_ligamx") -> dict:
    """Jala momios reales de The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
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
        return {"error": str(e)}

def get_fixtures(api_key: str) -> list:
    """Partidos de Liga MX vía API-Football."""
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}
    # Liga MX = league_id 262
    params = {"league": 262, "season": 2026, "next": 10}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        return []

# ─────────────────────────────────────────────
#  MODELO DE PREDICCIÓN PROPIO
# ─────────────────────────────────────────────

def predict_match(home_form: float, away_form: float,
                  home_avg_gf: float, away_avg_gf: float,
                  home_avg_ga: float, away_avg_ga: float,
                  h2h_home_wins: int, h2h_away_wins: int, h2h_draws: int,
                  is_clasico: bool = False) -> dict:
    """
    Modelo heurístico de predicción.
    Factores: forma reciente (0-1), promedios goles, H2H, ventaja local.
    """
    # Base: ventaja de local ~55% sin info
    home_score = 0.0
    away_score = 0.0
    draw_score = 0.0

    # Forma reciente (peso 35%)
    home_score += home_form * 0.35
    away_score += away_form * 0.35

    # Ataque vs defensa rival (peso 30%)
    home_attack = home_avg_gf / max(away_avg_ga, 0.5)
    away_attack = away_avg_gf / max(home_avg_ga, 0.5)
    home_score += min(home_attack / 3, 0.3)
    away_score += min(away_attack / 3, 0.3)

    # H2H (peso 20%)
    total_h2h = h2h_home_wins + h2h_away_wins + h2h_draws
    if total_h2h > 0:
        home_score += (h2h_home_wins / total_h2h) * 0.20
        away_score += (h2h_away_wins / total_h2h) * 0.20
        draw_score += (h2h_draws / total_h2h) * 0.20

    # Ventaja local (peso 15%)
    home_score += 0.15

    # Clásicos tienden al equilibrio (ajuste)
    if is_clasico:
        avg = (home_score + away_score) / 2
        home_score = home_score * 0.85 + avg * 0.15
        away_score = away_score * 0.85 + avg * 0.15
        draw_score += 0.05

    # Normalizar a 100%
    total = home_score + away_score + draw_score
    home_pct = round((home_score / total) * 100, 1)
    away_pct = round((away_score / total) * 100, 1)
    draw_pct = round(100 - home_pct - away_pct, 1)

    # Estimado de goles
    expected_home_goals = round(home_avg_gf * (away_avg_ga / max(away_avg_gf, 0.5)), 2)
    expected_away_goals = round(away_avg_gf * (home_avg_ga / max(home_avg_gf, 0.5)), 2)
    total_expected = round(expected_home_goals + expected_away_goals, 2)

    return {
        "home_win_pct": home_pct,
        "draw_pct": draw_pct,
        "away_win_pct": away_pct,
        "exp_home_goals": expected_home_goals,
        "exp_away_goals": expected_away_goals,
        "exp_total_goals": total_expected,
        "over_25_prob": min(95, round((total_expected / 2.5) * 55, 1))
    }

# ─────────────────────────────────────────────
#  UI — SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("# ⚽ LIGA MX\n### Betting Analytics System")
    st.markdown("---")

    st.markdown("### 🔑 API Keys")
    odds_api_key = st.text_input("The Odds API Key", type="password",
                                  help="Regístrate gratis en the-odds-api.com")
    football_api_key = st.text_input("API-Football Key", type="password",
                                      help="Regístrate gratis en api-sports.io")

    st.markdown("---")
    st.markdown("### 💰 Bankroll")
    bankroll = st.number_input("Mi bankroll ($MXN)", min_value=100, value=1000, step=100)

    st.markdown("---")
    st.markdown("### ⚙️ Filtros")
    min_ev = st.slider("EV mínimo para mostrar (%)", -20, 30, 5)
    max_kelly = st.slider("Kelly máximo por apuesta (%)", 1, 30, 10)

    st.markdown("---")
    st.caption("v1.0 · Liga MX Betting Analytics\nDatos: The Odds API + API-Football")

# ─────────────────────────────────────────────
#  UI — MAIN TABS
# ─────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Analizador de Partido",
    "📡 Momios en Vivo",
    "🧮 Calculadora EV",
    "📖 Guía de Uso"
])

# ══════════════════════════════════════════════
#  TAB 1 — ANALIZADOR DE PARTIDO
# ══════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🎯 ANALIZADOR DE PARTIDO</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🏠 Equipo Local")
        home_team = st.text_input("Nombre", "Atlas", key="home_name")
        home_form = st.slider("Forma reciente (0=horrible, 1=perfecto)", 0.0, 1.0, 0.55, key="home_form")
        home_avg_gf = st.number_input("Promedio goles anotados", 0.0, 5.0, 1.1, step=0.1, key="home_gf")
        home_avg_ga = st.number_input("Promedio goles recibidos", 0.0, 5.0, 1.2, step=0.1, key="home_ga")

    with col2:
        st.markdown("#### ✈️ Equipo Visitante")
        away_team = st.text_input("Nombre", "Chivas", key="away_name")
        away_form = st.slider("Forma reciente (0=horrible, 1=perfecto)", 0.0, 1.0, 0.65, key="away_form")
        away_avg_gf = st.number_input("Promedio goles anotados", 0.0, 5.0, 1.4, step=0.1, key="away_gf")
        away_avg_ga = st.number_input("Promedio goles recibidos", 0.0, 5.0, 1.0, step=0.1, key="away_ga")

    st.markdown("#### ⚔️ Historial H2H")
    col3, col4, col5 = st.columns(3)
    with col3: h2h_home = st.number_input(f"Victorias {home_team}", 0, 20, 3, key="h2h_home")
    with col4: h2h_draw = st.number_input("Empates", 0, 20, 3, key="h2h_draw")
    with col5: h2h_away = st.number_input(f"Victorias {away_team}", 0, 20, 4, key="h2h_away")

    is_clasico = st.checkbox("¿Es Clásico? (ajusta probabilidades al equilibrio)", value=True)

    if st.button("🔮 CALCULAR PREDICCIÓN", use_container_width=True):
        pred = predict_match(
            home_form, away_form,
            home_avg_gf, away_avg_gf,
            home_avg_ga, away_avg_ga,
            h2h_home, h2h_away, h2h_draw,
            is_clasico
        )
        st.session_state["pred"] = pred
        st.session_state["home_team"] = home_team
        st.session_state["away_team"] = away_team

    if "pred" in st.session_state:
        pred = st.session_state["pred"]
        ht = st.session_state.get("home_team", "Local")
        at = st.session_state.get("away_team", "Visitante")

        st.markdown("---")
        st.markdown(f'<div class="section-header">📊 RESULTADOS: {ht} vs {at}</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">🏠 Victoria {ht}</div>
                <div class="value-neutral">{pred['home_win_pct']}%</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">🤝 Empate</div>
                <div class="value-neutral">{pred['draw_pct']}%</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="metric-card">
                <div style="font-size:0.8em;color:#888;">✈️ Victoria {at}</div>
                <div class="value-neutral">{pred['away_win_pct']}%</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("#### ⚽ Estimado de Goles")
        g1, g2, g3, g4 = st.columns(4)
        with g1:
            st.metric(f"Goles {ht}", pred['exp_home_goals'])
        with g2:
            st.metric(f"Goles {at}", pred['exp_away_goals'])
        with g3:
            st.metric("Total esperado", pred['exp_total_goals'])
        with g4:
            st.metric("Prob. Over 2.5", f"{pred['over_25_prob']}%")

        # Guardar predicción para Tab 2
        st.session_state["last_pred"] = pred

# ══════════════════════════════════════════════
#  TAB 2 — MOMIOS EN VIVO + COMPARACIÓN
# ══════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-header">📡 MOMIOS EN VIVO & VALOR ESPERADO</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns([2, 1])

    with col_b:
        st.markdown("#### ℹ️ Mis probabilidades")
        if "pred" in st.session_state:
            pred = st.session_state["pred"]
            ht = st.session_state.get("home_team", "Local")
            at = st.session_state.get("away_team", "Visitante")
            st.info(f"Usando predicción de Tab 1:\n\n🏠 {ht}: **{pred['home_win_pct']}%**\n\n🤝 Empate: **{pred['draw_pct']}%**\n\n✈️ {at}: **{pred['away_win_pct']}%**")
            my_home = pred['home_win_pct']
            my_draw = pred['draw_pct']
            my_away = pred['away_win_pct']
        else:
            st.warning("Primero calcula una predicción en Tab 1, o ingresa manualmente:")
            my_home = st.number_input("Mi prob. Local (%)", 0.0, 100.0, 28.0)
            my_draw = st.number_input("Mi prob. Empate (%)", 0.0, 100.0, 30.0)
            my_away = st.number_input("Mi prob. Visitante (%)", 0.0, 100.0, 42.0)
            ht, at = "Local", "Visitante"

    with col_a:
        st.markdown("#### 🏦 Ingresar Momios de Casas de Apuestas")
        st.caption("Ingresa los momios americanos (ej: +240, -140). Puedes agregar varias casas.")

        if "casas" not in st.session_state:
            st.session_state["casas"] = [
                {"nombre": "Caliente", "local": 240, "empate": 230, "visita": -140},
                {"nombre": "Betcris",  "local": 220, "empate": 240, "visita": -150},
                {"nombre": "Codere",   "local": 250, "empate": 220, "visita": -145},
            ]

        casas_df = []
        for i, casa in enumerate(st.session_state["casas"]):
            cols = st.columns([2, 1, 1, 1, 0.4])
            with cols[0]: casa["nombre"] = st.text_input("Casa", casa["nombre"], key=f"casa_{i}")
            with cols[1]: casa["local"]  = st.number_input("Local", value=float(casa["local"]),  key=f"loc_{i}", step=5.0)
            with cols[2]: casa["empate"] = st.number_input("Empate", value=float(casa["empate"]), key=f"emp_{i}", step=5.0)
            with cols[3]: casa["visita"] = st.number_input("Visita", value=float(casa["visita"]), key=f"vis_{i}", step=5.0)
            with cols[4]:
                if st.button("🗑", key=f"del_{i}"):
                    st.session_state["casas"].pop(i)
                    st.rerun()
            casas_df.append(casa)

        if st.button("➕ Agregar casa de apuestas"):
            st.session_state["casas"].append({"nombre": "Nueva", "local": 200, "empate": 230, "visita": -160})
            st.rerun()

    # ── TABLA DE ANÁLISIS ──
    if st.button("⚡ ANALIZAR VALOR ESPERADO", use_container_width=True):
        st.markdown("---")
        st.markdown('<div class="section-header">💡 APUESTAS CON VALOR</div>', unsafe_allow_html=True)

        rows = []
        for casa in st.session_state["casas"]:
            for mercado, american, my_prob in [
                (f"🏠 {ht} gana", casa["local"],  my_home),
                ("🤝 Empate",     casa["empate"], my_draw),
                (f"✈️ {at} gana", casa["visita"], my_away),
            ]:
                dec = american_to_decimal(american)
                impl = decimal_to_implied_prob(dec)
                ev = calc_ev(my_prob, dec)
                kelly = kelly_criterion(my_prob, dec)
                kelly_clipped = min(kelly, max_kelly)
                apuesta_mxn = round((kelly_clipped / 100) * bankroll, 2)
                rows.append({
                    "Casa": casa["nombre"],
                    "Mercado": mercado,
                    "Momio": f"{'+' if american > 0 else ''}{int(american)}",
                    "Decimal": dec,
                    "Prob. Implícita": f"{impl}%",
                    "Mi Prob.": f"{my_prob}%",
                    "EV": ev,
                    "Kelly%": kelly_clipped,
                    "Apostar ($MXN)": apuesta_mxn
                })

        df = pd.DataFrame(rows)
        ev_val = df["EV"].astype(float)
        best = df[ev_val >= (min_ev / 100)].sort_values("EV", ascending=False)

        if best.empty:
            st.warning(f"No hay apuestas con EV ≥ {min_ev}% con los datos actuales.")
        else:
            for _, row in best.iterrows():
                ev_pct = row['EV'] * 100
                if ev_pct >= 10:
                    css, tag_css = "bet-row-positive", "tag-green"
                    emoji = "🟢"
                elif ev_pct >= 5:
                    css, tag_css = "bet-row-neutral", "tag-yellow"
                    emoji = "🟡"
                else:
                    css, tag_css = "bet-row-negative", "tag-red"
                    emoji = "🔴"

                st.markdown(f"""
                <div class="{css}">
                    <b>{emoji} {row['Casa']} — {row['Mercado']}</b>
                    &nbsp;<span class="tag {tag_css}">EV: {ev_pct:.1f}%</span>
                    &nbsp;<span class="tag {tag_css}">Kelly: {row['Kelly%']}%</span>
                    <br>
                    <span style="font-family:'Space Mono';font-size:1.1em;">{row['Momio']}</span>
                    &emsp;Prob. implícita: <b>{row['Prob. Implícita']}</b>
                    &emsp;Mi prob.: <b>{row['Mi Prob.']}</b>
                    &emsp;💰 Apostar: <b>${row['Apostar ($MXN)']:,.0f} MXN</b>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 📋 Tabla completa")
        st.dataframe(df.style.applymap(
            lambda v: "color: #00ff88" if isinstance(v, float) and v > 0.05
            else ("color: #ff4466" if isinstance(v, float) and v < 0 else ""),
            subset=["EV"]
        ), use_container_width=True)

    # ── MOMIOS EN VIVO (API) ──
    st.markdown("---")
    st.markdown("#### 📡 Momios en Tiempo Real (The Odds API)")
    if odds_api_key:
        if st.button("🔄 Actualizar momios en vivo"):
            with st.spinner("Jalando momios..."):
                data = get_live_odds(odds_api_key)
                if "error" in data:
                    st.error(f"Error: {data['error']}")
                elif not data:
                    st.warning("No hay partidos disponibles ahora.")
                else:
                    for game in data[:5]:
                        home = game.get("home_team", "")
                        away = game.get("away_team", "")
                        commence = game.get("commence_time", "")
                        st.markdown(f"**{home} vs {away}** — {commence[:10]}")
                        for bookmaker in game.get("bookmakers", [])[:3]:
                            bname = bookmaker["title"]
                            for market in bookmaker.get("markets", []):
                                if market["key"] == "h2h":
                                    outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
                                    st.caption(f"  {bname}: {home} {outcomes.get(home,'?')} | Draw {outcomes.get('Draw','?')} | {away} {outcomes.get(away,'?')}")
    else:
        st.info("👉 Ingresa tu API Key de The Odds API en el sidebar para ver momios en tiempo real.")

# ══════════════════════════════════════════════
#  TAB 3 — CALCULADORA EV STANDALONE
# ══════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">🧮 CALCULADORA DE VALOR ESPERADO</div>', unsafe_allow_html=True)
    st.caption("Herramienta rápida: ingresa cualquier momio y tu probabilidad estimada.")

    col1, col2, col3 = st.columns(3)
    with col1:
        calc_american = st.number_input("Momio americano", value=240, step=5)
    with col2:
        calc_my_prob = st.number_input("Mi probabilidad (%)", 0.0, 100.0, 28.0)
    with col3:
        calc_bankroll = st.number_input("Bankroll ($MXN)", min_value=100, value=bankroll, step=100)

    calc_dec = american_to_decimal(calc_american)
    calc_impl = decimal_to_implied_prob(calc_dec)
    calc_ev_val = calc_ev(calc_my_prob, calc_dec)
    calc_kelly = min(kelly_criterion(calc_my_prob, calc_dec), max_kelly)
    calc_apuesta = round((calc_kelly / 100) * calc_bankroll, 2)

    st.markdown("---")
    r1, r2, r3, r4 = st.columns(4)

    def color_metric(val, threshold=0):
        color = "#00ff88" if val > threshold else "#ff4466"
        return color

    ev_color = color_metric(calc_ev_val)

    with r1:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:0.8em;color:#888;">Decimal</div>
            <div style="font-family:'Space Mono';font-size:1.3em;">{calc_dec}</div>
        </div>""", unsafe_allow_html=True)
    with r2:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:0.8em;color:#888;">Prob. Implícita</div>
            <div style="font-family:'Space Mono';font-size:1.3em;">{calc_impl}%</div>
        </div>""", unsafe_allow_html=True)
    with r3:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:0.8em;color:#888;">Expected Value</div>
            <div style="font-family:'Space Mono';font-size:1.3em;color:{ev_color};">{calc_ev_val*100:.1f}%</div>
        </div>""", unsafe_allow_html=True)
    with r4:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:0.8em;color:#888;">Apostar (Kelly)</div>
            <div style="font-family:'Space Mono';font-size:1.3em;color:#00ff88;">${calc_apuesta:,.0f}</div>
        </div>""", unsafe_allow_html=True)

    if calc_ev_val > 0.10:
        st.success(f"✅ Esta apuesta tiene **BUEN VALOR** (EV +{calc_ev_val*100:.1f}%). El mercado subestima tus probabilidades.")
    elif calc_ev_val > 0:
        st.warning(f"🟡 Valor positivo marginal (+{calc_ev_val*100:.1f}%). Procede con cautela.")
    else:
        st.error(f"❌ Sin valor ({calc_ev_val*100:.1f}%). La casa tiene ventaja en esta apuesta.")

    st.markdown("---")
    st.markdown("#### 📈 Simulación de rentabilidad a largo plazo")
    n_bets = st.slider("Número de apuestas simuladas", 10, 500, 100)

    import random
    bankroll_sim = [calc_bankroll]
    current = calc_bankroll
    p = calc_my_prob / 100
    for _ in range(n_bets):
        stake = (calc_kelly / 100) * current
        if random.random() < p:
            current += stake * (calc_dec - 1)
        else:
            current -= stake
        bankroll_sim.append(round(current, 2))

    sim_df = pd.DataFrame({"Apuesta #": range(n_bets + 1), "Bankroll ($MXN)": bankroll_sim})
    final = bankroll_sim[-1]
    change = round(((final - calc_bankroll) / calc_bankroll) * 100, 1)
    st.line_chart(sim_df.set_index("Apuesta #"))
    if final > calc_bankroll:
        st.success(f"📈 Resultado simulado: ${final:,.0f} MXN (+{change}%)")
    else:
        st.error(f"📉 Resultado simulado: ${final:,.0f} MXN ({change}%)")
    st.caption("⚠️ Simulación aleatoria, solo ilustrativa. Cada corrida es diferente.")

# ══════════════════════════════════════════════
#  TAB 4 — GUÍA DE USO
# ══════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📖 GUÍA DE USO</div>', unsafe_allow_html=True)
    st.markdown("""
### ¿Cómo usar este sistema?

**1. Tab "Analizador de Partido"**
- Ingresa los datos del partido: forma reciente de cada equipo (qué tan bien vienen jugando, de 0 a 1), promedio de goles anotados y recibidos en el torneo, y el historial de enfrentamientos directos.
- Activa "Es Clásico" si es un derby para que el modelo ajuste hacia mayor equilibrio.
- Presiona "Calcular Predicción" para obtener las probabilidades del modelo.

**2. Tab "Momios en Vivo"**
- Ingresa los momios americanos de cada casa de apuestas que quieras comparar.
- El sistema calcula automáticamente el **Expected Value (EV)** de cada apuesta.
- EV positivo = la apuesta tiene valor. EV negativo = la casa tiene ventaja.
- También calcula cuánto apostar usando el **Criterio de Kelly** para proteger tu bankroll.

**3. Tab "Calculadora EV"**
- Herramienta rápida para evaluar cualquier apuesta individual.
- Incluye simulación de rentabilidad a largo plazo.

---
### ¿Qué es el Expected Value (EV)?
Si una apuesta tiene **EV = +15%**, significa que por cada $100 que apuestas, en promedio ganarías $15 a largo plazo (si tus probabilidades son correctas).

### ¿Qué es el Criterio de Kelly?
Es una fórmula matemática que calcula **qué porcentaje de tu bankroll apostar** para maximizar el crecimiento a largo plazo sin arriesgar la quiebra.

---
### APIs necesarias (ambas gratuitas)
- **The Odds API**: [the-odds-api.com](https://the-odds-api.com) — momios de 40+ casas
- **API-Football**: [api-sports.io](https://api-sports.io) — estadísticas Liga MX

---
⚠️ **Aviso**: Este sistema es una herramienta de análisis. Las apuestas siempre conllevan riesgo real. Juega responsablemente, solo si eres mayor de edad, y nunca apuestes más de lo que puedes perder.
    """)
