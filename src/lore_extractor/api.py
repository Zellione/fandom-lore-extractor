"""MediaWiki API client for Fandom wikis.

Handles rate limiting, retries, redirect resolution and page fetching.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_API_PARAMS = {
    "format": "json",
    "formatversion": "2",
}


class WikiApiError(Exception):
    """Raised for non-retriable API errors."""


class PageNotFound(WikiApiError):
    """Raised when a requested page does not exist."""


class WikiClient:
    """Thin wrapper around the MediaWiki action API."""

    def __init__(
        self,
        wiki_domain: str,
        rate_per_sec: float = 1.0,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.wiki_domain = wiki_domain.rstrip("/")
        if not self.wiki_domain.startswith(("http://", "https://")):
            self.wiki_domain = f"https://{self.wiki_domain}"
        self.api_url = f"{self.wiki_domain}/api.php"
        self._min_interval = 1.0 / max(rate_per_sec, 0.01)
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "lore-extractor/0.1.0 "
                    "(https://github.com/example/lore-extractor; learning tool)"
                )
            }
        )
        self._last_request = 0.0

    # -- rate limiting -------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    # -- low level request ---------------------------------------------
    @retry(
        retry=retry_if_exception_type(requests.ConnectionError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        reraise=True,
    )
    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._throttle()
        resp = self._session.get(self.api_url, params=params, timeout=self.timeout)
        if resp.status_code == 429:  # rate limited
            raise requests.ConnectionError("Rate limited (429)")
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            info = data["error"].get("info", str(data["error"]))
            code = data["error"].get("code", "")
            if code in ("missingtitle", "missingtitle-rev", "invalidtitle"):
                raise PageNotFound(info)
            raise WikiApiError(f"API error ({code}): {info}")
        return data

    # -- convenience ---------------------------------------------------
    def get_page(
        self, title: str, redirects: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Fetch parse data for a single page. Returns None if not a valid article.

        Returns normalized dict with keys: title, pageid, wikitext, sections,
        categories, links, images, templates, redirects.
        """
        params = {
            "action": "parse",
            "page": title,
            "prop": "wikitext|sections|categories|links|images|templates",
            "redirects": "1" if redirects else "0",
        }
        try:
            data = self._request({**DEFAULT_API_PARAMS, **params})
        except PageNotFound:
            return None

        parse = data.get("parse", {})
        # With formatversion=2, wikitext is a plain string.
        wikitext = parse.get("wikitext", "")
        if isinstance(wikitext, dict):
            wikitext = wikitext.get("*", "")
        # Normalize links/categories/images into flat lists of titles.
        return {
            "title": parse.get("title", title),
            "pageid": parse.get("pageid"),
            "wikitext": wikitext,
            "sections": parse.get("sections") or [],
            "categories": [
                c.get("category", c.get("title", "")).replace("Category:", "")
                for c in parse.get("categories") or []
            ],
            "links": [
                l.get("title", "")
                for l in parse.get("links") or []
                if l.get("ns", 0) == 0
            ],
            "images": [
                i if isinstance(i, str) else i.get("title", "") for i in parse.get("images") or []
            ],
            "templates": parse.get("templates") or [],
        }

    def get_category_members(
        self, category: str, limit: int = 500
    ) -> List[str]:
        """Return page titles under a category (paginated)."""
        titles: List[str] = []
        cmcontinue: Optional[str] = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmtype": "page",
                "cmnamespace": "0",
                "cmlimit": str(min(limit, 500)),
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue
            data = self._request({**DEFAULT_API_PARAMS, **params})
            members = data.get("query", {}).get("categorymembers", [])
            titles.extend(m.get("title", "") for m in members)
            cont = data.get("continue", {})
            if cont.get("cmcontinue"):
                cmcontinue = cont["cmcontinue"]
            else:
                break
        return titles

    def get_page_redirects(self, titles: Iterable[str]) -> Dict[str, str]:
        """Map page titles to their final (redirect-resolved) titles."""
        titles = list(titles)
        mapping: Dict[str, str] = {}
        for i in range(0, len(titles), 50):
            batch = titles[i : i + 50]
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "redirects": "1",
            }
            data = self._request({**DEFAULT_API_PARAMS, **params})
            pages = data.get("query", {}).get("pages", [])
            normalized = data.get("query", {}).get("normalized", [])
            # build normalized map: from -> to
            norm_map = {n.get("from"): n.get("to") for n in normalized}
            resolved = {}
            for p in pages:
                title_in = p.get("title", "")
                resolved[title_in] = title_in
            # Map redirected via 'redirects' entries where 'to' is a page title
            redirect_map = {}
            for r in data.get("query", {}).get("redirects", []):
                redirect_map[r.get("from")] = r.get("to")
            for from_title in batch:
                final = from_title
                seen = set()
                while final in redirect_map and final not in seen:
                    seen.add(final)
                    final = redirect_map[final]
                # follow normalization too
                final = norm_map.get(final, final)
                mapping[from_title] = final
        return mapping

    @property
    def page_url(self) -> str:
        return f"{self.wiki_domain}/wiki/"

    def page_absolute_url(self, title: str) -> str:
        return f"{self.wiki_domain}/wiki/{quote(title.replace(' ', '_'))}"
