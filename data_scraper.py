import re
from typing import Dict, List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

DEFAULT_TIMEOUT = 8
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _clean_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_get(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


def _search_duckduckgo(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html = _safe_get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for node in soup.select(".result")[:max_results]:
        title_el = node.select_one(".result__title")
        snippet_el = node.select_one(".result__snippet")
        link_el = node.select_one(".result__a")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        href = link_el.get("href", "") if link_el else ""
        rows.append({"title": title, "snippet": snippet, "url": href})
    return rows


def _fetch_article_preview(url: str, max_chars: int = 1200) -> str:
    html = _safe_get(url)
    if not html:
        return ""
    text = _clean_text(html)
    return text[:max_chars]


def get_match_news(team_home, team_away) -> List[str]:
    """
    Obtiene snippets y previews de noticias previas al partido.
    Fallback: devuelve lista vacía si falla la búsqueda.
    """
    query = f"{team_home} vs {team_away} football preview injuries lineups news"
    results = _search_duckduckgo(query, max_results=4)
    news = []
    for item in results:
        parts = [p for p in [item.get("title", ""), item.get("snippet", "")] if p]
        article_preview = _fetch_article_preview(item.get("url", ""))
        if article_preview:
            parts.append(article_preview)
        txt = " | ".join(parts).strip()
        if txt:
            news.append(txt)
    return news


def get_lineups(team_home, team_away) -> Dict:
    """
    Extrae contexto de alineaciones probables como texto estructurado.
    """
    query = f"{team_home} {team_away} predicted lineup injuries suspension"
    results = _search_duckduckgo(query, max_results=3)
    source_text = " ".join(
        " | ".join([r.get("title", ""), r.get("snippet", "")]).strip()
        for r in results
    ).strip()
    return {
        "team_home": team_home,
        "team_away": team_away,
        "raw_text": source_text,
        "sources_found": len(results),
    }


def get_match_context(team_home, team_away) -> str:
    """
    Recupera texto general de contexto: preview, motivación, lesiones, clima, etc.
    """
    query = f"{team_home} {team_away} match preview injuries motivation weather"
    results = _search_duckduckgo(query, max_results=4)
    chunks = []
    for item in results:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        if title or snippet:
            chunks.append(f"{title} | {snippet}".strip(" |"))
    return " ".join(chunks).strip()

