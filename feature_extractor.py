import json
import re
from typing import Dict

import numpy as np
import requests

FEATURE_LIMITS = {
    "injury_impact_home": (-0.2, 0.0),
    "injury_impact_away": (-0.2, 0.0),
    "form_adjustment_home": (-0.1, 0.1),
    "form_adjustment_away": (-0.1, 0.1),
    "motivation_factor": (0.0, 0.1),
    "lineup_strength_diff": (-0.15, 0.15),
    "weather_impact": (-0.1, 0.0),
}


def _neutral_features() -> Dict[str, float]:
    return {k: 0.0 for k in FEATURE_LIMITS}


def _clip_features(data: Dict) -> Dict[str, float]:
    out = _neutral_features()
    for key, (lo, hi) in FEATURE_LIMITS.items():
        try:
            out[key] = float(np.clip(float(data.get(key, 0.0)), lo, hi))
        except Exception:
            out[key] = 0.0
    return out


def _extract_json_blob(text: str) -> Dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def interpret_with_llm(text, anthropic_key=None):
    prompt = f"""
Analiza el siguiente texto sobre un partido de fútbol.

Extrae SOLO valores numéricos en JSON válido con estas llaves exactas:
- injury_impact_home (-0.2 a 0)
- injury_impact_away (-0.2 a 0)
- form_adjustment_home (-0.1 a 0.1)
- form_adjustment_away (-0.1 a 0.1)
- motivation_factor (0 a 0.1)
- lineup_strength_diff (-0.15 a 0.15)
- weather_impact (-0.1 a 0)

No expliques nada. Devuelve solo JSON.

Texto:
{text[:12000]}
"""
    if not anthropic_key or not text.strip():
        return _neutral_features()
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        data = r.json()
        txt = data.get("content", [{}])[0].get("text", "")
        parsed = _extract_json_blob(txt)
        return _clip_features(parsed)
    except Exception:
        return _neutral_features()


def _count_hits(text: str, keywords) -> int:
    text_l = (text or "").lower()
    return sum(1 for kw in keywords if kw in text_l)


def _heuristic_features(text: str) -> Dict[str, float]:
    text_l = (text or "").lower()
    out = _neutral_features()

    home_bad = _count_hits(text_l, ["home injury", "home injuries", "home doubtful", "home suspended", "local lesion", "local suspend"])
    away_bad = _count_hits(text_l, ["away injury", "away injuries", "away doubtful", "away suspended", "visita lesion", "visitante suspend"])
    out["injury_impact_home"] = -0.03 * min(home_bad, 6)
    out["injury_impact_away"] = -0.03 * min(away_bad, 6)

    home_form = _count_hits(text_l, ["home unbeaten", "home good form", "home won", "local en forma", "local llega bien"])
    away_form = _count_hits(text_l, ["away unbeaten", "away good form", "away won", "visitante en forma", "visitante llega bien"])
    home_form_neg = _count_hits(text_l, ["home poor form", "home lost", "local mala racha", "local llega mal"])
    away_form_neg = _count_hits(text_l, ["away poor form", "away lost", "visitante mala racha", "visitante llega mal"])
    out["form_adjustment_home"] = 0.02 * min(home_form, 5) - 0.02 * min(home_form_neg, 5)
    out["form_adjustment_away"] = 0.02 * min(away_form, 5) - 0.02 * min(away_form_neg, 5)

    motivation = _count_hits(text_l, ["must win", "title race", "relegation", "clasico", "derby", "playoff", "final", "decisive", "obligado a ganar"])
    out["motivation_factor"] = 0.015 * min(motivation, 6)

    lineup_home_pos = _count_hits(text_l, ["home full squad", "home strongest lineup", "local cuadro completo", "local titulares"])
    lineup_away_pos = _count_hits(text_l, ["away full squad", "away strongest lineup", "visitante cuadro completo", "visitante titulares"])
    lineup_home_neg = _count_hits(text_l, ["home rotated", "home weakened", "local rotacion", "local suplentes"])
    lineup_away_neg = _count_hits(text_l, ["away rotated", "away weakened", "visitante rotacion", "visitante suplentes"])
    out["lineup_strength_diff"] = 0.03 * (lineup_home_pos - lineup_home_neg) - 0.03 * (lineup_away_pos - lineup_away_neg)

    weather_hits = _count_hits(text_l, ["heavy rain", "storm", "snow", "strong wind", "lluvia", "tormenta", "nieve", "viento fuerte"])
    out["weather_impact"] = -0.02 * min(weather_hits, 5)

    return _clip_features(out)


def extract_features_from_text(text: str, anthropic_key=None) -> Dict[str, float]:
    """
    1) intenta LLM si hay key
    2) fallback heurístico
    3) clip de seguridad
    """
    llm_out = interpret_with_llm(text, anthropic_key=anthropic_key)
    if any(abs(v) > 1e-9 for v in llm_out.values()):
        return _clip_features(llm_out)
    return _heuristic_features(text)

