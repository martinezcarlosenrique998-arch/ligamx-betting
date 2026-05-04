from typing import Dict

import numpy as np


def apply_context_adjustments(base_prob, features, side="home"):
    """
    Ajusta una probabilidad base usando features numéricas.
    Limita impacto total a ±10%.
    """
    p = float(base_prob)
    if side == "home":
        total_adjustment = (
            features.get("injury_impact_home", 0.0)
            + features.get("form_adjustment_home", 0.0)
            + features.get("motivation_factor", 0.0)
            + features.get("lineup_strength_diff", 0.0)
            + 0.35 * features.get("weather_impact", 0.0)
        )
    else:
        total_adjustment = (
            features.get("injury_impact_away", 0.0)
            + features.get("form_adjustment_away", 0.0)
            + features.get("motivation_factor", 0.0)
            - features.get("lineup_strength_diff", 0.0)
            + 0.35 * features.get("weather_impact", 0.0)
        )
    adjustment_total = float(np.clip(total_adjustment, -0.1, 0.1))
    return float(np.clip(p + adjustment_total, 0.01, 0.99))


def apply_context_to_prediction(base_pred: Dict, features: Dict) -> Dict:
    """
    Aplica el contexto sin reemplazar el modelo base.
    Ajusta 1X2 y mercado de goles con cap suave.
    """
    pred = dict(base_pred or {})
    home = float(pred.get("home_win_pct", 0.0)) / 100.0
    draw = float(pred.get("draw_pct", 0.0)) / 100.0
    away = float(pred.get("away_win_pct", 0.0)) / 100.0

    adj_home = apply_context_adjustments(home, features, side="home")
    adj_away = apply_context_adjustments(away, features, side="away")

    draw_shift = -0.25 * (abs(adj_home - home) + abs(adj_away - away))
    adj_draw = float(np.clip(draw + draw_shift, 0.05, 0.60))

    total_1x2 = adj_home + adj_draw + adj_away
    if total_1x2 <= 0:
        total_1x2 = 1.0

    adj_home /= total_1x2
    adj_draw /= total_1x2
    adj_away /= total_1x2

    over_base = float(pred.get("over_25", 50.0)) / 100.0
    over_adj = (
        0.20 * features.get("motivation_factor", 0.0)
        - 0.50 * abs(features.get("weather_impact", 0.0))
        - 0.20 * abs(features.get("injury_impact_home", 0.0))
        - 0.20 * abs(features.get("injury_impact_away", 0.0))
    )
    over_adj = float(np.clip(over_adj, -0.05, 0.05))
    over_new = float(np.clip(over_base + over_adj, 0.05, 0.95))

    pred["home_win_pct"] = round(adj_home * 100.0, 1)
    pred["draw_pct"] = round(adj_draw * 100.0, 1)
    pred["away_win_pct"] = round(adj_away * 100.0, 1)
    pred["over_25"] = round(over_new * 100.0, 1)
    pred["under_25"] = round((1.0 - over_new) * 100.0, 1)
    pred["context_total_adjustment_home"] = round((adj_home - home) * 100.0, 2)
    pred["context_total_adjustment_away"] = round((adj_away - away) * 100.0, 2)
    return pred

