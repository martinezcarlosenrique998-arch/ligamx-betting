import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from data_scraper import get_lineups, get_match_context, get_match_news
from feature_extractor import extract_features_from_text
from feature_integration import apply_context_to_prediction

USE_CONTEXT = True
DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "context_pipeline_log.jsonl"


def _safe_log(payload: Dict, log_path=None) -> None:
    try:
        out_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _compose_text(team_home: str, team_away: str) -> Dict:
    news_items = get_match_news(team_home, team_away)
    lineups = get_lineups(team_home, team_away)
    context = get_match_context(team_home, team_away)
    combined = "\n\n".join(
        [txt for txt in news_items + [lineups.get("raw_text", ""), context] if txt]
    ).strip()
    return {
        "news_items": news_items,
        "lineups": lineups,
        "context_text": context,
        "combined_text": combined,
    }


def run_context_pipeline(
    team_home: str,
    team_away: str,
    base_prediction: Dict,
    anthropic_key=None,
    use_context: bool = True,
    log_path=None,
):
    """
    1) scraping
    2) interpretación a features
    3) ajuste acotado sobre el modelo existente
    4) logging para auditoría
    """
    payload = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "team_home": team_home,
        "team_away": team_away,
        "used_context": bool(USE_CONTEXT and use_context),
        "base_prediction": dict(base_prediction or {}),
        "text_bundle": {},
        "features": {},
        "adjusted_prediction": dict(base_prediction or {}),
        "error": None,
    }

    if not (USE_CONTEXT and use_context):
        _safe_log(payload, log_path=log_path)
        return payload

    try:
        text_bundle = _compose_text(team_home, team_away)
        payload["text_bundle"] = text_bundle
        features = extract_features_from_text(
            text_bundle.get("combined_text", ""),
            anthropic_key=anthropic_key,
        )
        payload["features"] = features
        payload["adjusted_prediction"] = apply_context_to_prediction(base_prediction, features)
    except Exception as e:
        payload["error"] = str(e)
        payload["adjusted_prediction"] = dict(base_prediction or {})

    _safe_log(payload, log_path=log_path)
    return payload

