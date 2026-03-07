# ⚽ Liga MX Betting Analytics System

Sistema completo para análisis de apuestas de fútbol: modelo propio de predicción,
comparación de momios entre casas de apuestas y cálculo de Expected Value (EV).

---

## 🚀 Instalación paso a paso (sin experiencia requerida)

### Paso 1 — Crea las cuentas gratuitas de APIs

**The Odds API** (momios en tiempo real):
1. Ve a: https://the-odds-api.com
2. Haz clic en "Get API Key"
3. Regístrate con tu correo
4. Copia tu API Key (algo como: `abc123def456...`)

**API-Football** (estadísticas de Liga MX):
1. Ve a: https://dashboard.api-football.com/register
2. Regístrate gratis
3. Copia tu API Key del dashboard

---

### Paso 2 — Sube el código a GitHub

1. Ve a: https://github.com y crea una cuenta si no tienes
2. Haz clic en el botón verde **"New"** para crear un repositorio
3. Nómbralo `ligamx-betting` y déjalo en **Public**
4. Haz clic en **"creating a new file"**
5. Nombra el archivo `app.py` y pega el contenido del archivo `app.py` de esta carpeta
6. Haz clic en **"Commit new file"**
7. Repite para el archivo `requirements.txt`

---

### Paso 3 — Despliega en Streamlit Cloud (gratis)

1. Ve a: https://streamlit.io/cloud
2. Haz clic en **"Sign in with GitHub"**
3. Autoriza el acceso
4. Haz clic en **"New app"**
5. Selecciona tu repositorio `ligamx-betting`
6. En "Main file path" escribe: `app.py`
7. Haz clic en **"Deploy!"**
8. En ~2 minutos tendrás tu app en una URL pública como:
   `https://tu-usuario-ligamx-betting.streamlit.app`

---

### Paso 4 — Configura tus API Keys de forma segura

Para que nadie más vea tus API Keys:

1. En Streamlit Cloud, abre tu app y ve a **Settings > Secrets**
2. Agrega esto:
```toml
ODDS_API_KEY = "tu-key-aqui"
FOOTBALL_API_KEY = "tu-key-aqui"
```
3. Guarda y la app se reiniciará automáticamente

---

## 📱 ¿Cómo usar el sistema?

### Tab 1 — Analizador de Partido
Ingresa los datos del partido manualmente:
- **Forma reciente**: qué tan bien viene jugando el equipo (0.0 = muy mal, 1.0 = perfecto)
  - Ejemplo: Si ganó 4 de sus últimos 5 partidos → 0.80
- **Promedio goles**: del torneo actual
- **H2H**: cuántas veces ha ganado cada quien en los últimos 5-10 enfrentamientos
- Presiona **"Calcular Predicción"** para ver las probabilidades

### Tab 2 — Momios en Vivo
- Ingresa los momios americanos de las casas que quieras comparar
  - Ejemplo: Caliente da +240 al local, -140 al visitante
- El sistema automáticamente calcula cuál apuesta tiene **valor positivo (EV)**
- Verde = buena apuesta | Amarillo = marginal | Rojo = sin valor
- También te dice **cuánto apostar** según tu bankroll

### Tab 3 — Calculadora EV
Herramienta rápida para evaluar una apuesta puntual con simulación.

---

## 🔢 Glosario rápido

| Término | Significado |
|---------|-------------|
| **EV (Expected Value)** | Ganancia esperada por cada $100 apostados. EV > 0 = valor positivo |
| **Kelly %** | Porcentaje del bankroll que matemáticamente deberías apostar |
| **Prob. Implícita** | La probabilidad que la casa "cree" que tiene ese resultado (extraída del momio) |
| **Momio americano** | +240 significa que ganas $240 por cada $100. -140 significa que debes apostar $140 para ganar $100 |

---

## ⚠️ Aviso importante

Este sistema es una herramienta de análisis estadístico. Las apuestas deportivas siempre
conllevan riesgo real de pérdida económica. Úsalo de forma responsable:
- Solo apuesta lo que puedes permitirte perder
- No persigas pérdidas
- Si el juego se vuelve un problema, busca ayuda en: https://www.jugarbien.es

---

## 🛠️ Soporte / Mejoras futuras

Posibles mejoras a implementar:
- [ ] Bot de Telegram con alertas automáticas
- [ ] Base de datos histórica con Supabase
- [ ] Modelo ML con datos de xG (expected goals)
- [ ] Scraping automático de Caliente.mx
- [ ] Tracking de apuestas realizadas y ROI histórico
