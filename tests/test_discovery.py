from lore_extractor.discovery import Crawler, CrawlResult


class FakeClient:
    """Minimal stand-in for WikiClient that serves a small closed wiki."""

    def __init__(self, pages):
        # pages: dict title -> (wikitext, links)
        self.pages = pages
        self.fetched = {}

    def get_page(self, title):
        if title not in self.pages:
            return None
        wt, links = self.pages[title]
        self.fetched[title] = self.fetched.get(title, 0) + 1
        return {
            "title": title,
            "pageid": hash(title),
            "wikitext": wt,
            "sections": [],
            "categories": [],
            "links": links,
            "images": [],
            "templates": [],
        }

    def get_category_members(self, category):
        return [t for t in self.pages if category in self.pages[t][0]]

    def page_absolute_url(self, title):
        return f"https://wiki.local/wiki/{title}"


WIKITEXT = """'''Stuff.'''\n==Overview==\nContent here.\n"""


def _make_graph():
    # A/B/C form a strongly-connected tiny wiki; D is dead-end; X is off-domain.
    pages = {
        "A": (WIKITEXT, ["B", "C", "D"]),
        "B": (WIKITEXT, ["A", "C"]),
        "C": (WIKITEXT, ["A"]),
        "D": (WIKITEXT, []),
        "E": (WIKITEXT, ["Category:Foo", "w:external", "Template:X", "B"]),
    }
    return pages


def test_crawl_visits_each_page_once():
    pages = _make_graph()
    client = FakeClient(pages)
    cr = Crawler(client, entrypoint="A")
    res = cr.crawl()
    assert set(res.visited) == {"A", "B", "C", "D"}
    for t in res.visited:
        assert client.fetched.get(t, 0) == 1, f"{t} fetched multiple times"
    assert len(res.visited) == len(set(res.visited))
    assert len(client.fetched) == len(res.visited)


def test_crawl_terminates_when_no_new_pages():
    pages = _make_graph()
    client = FakeClient(pages)
    # Entrypoint D has no links -> nothing new to discover.
    cr = Crawler(client, entrypoint="D")
    res = cr.crawl()
    assert res.visited == ["D"]
    assert len(client.fetched) == 1


def test_non_local_links_not_queued():
    pages = _make_graph()
    client = FakeClient(pages)
    cr = Crawler(client, entrypoint="E")
    res = cr.crawl()
    # E's only in-domain article link is B; Category:/w:/Template: skipped.
    assert "B" in res.visited
    assert "w:external" not in res.visited
    assert "Category:Foo" not in res.visited
    assert "Template:X" not in res.visited
    # None of the non-local titles were fetched.
    for off_domain in ("w:external", "Category:Foo", "Template:X"):
        assert off_domain not in client.fetched


def test_entity_filter_does_not_stop_discovery():
    pages = {
        "Hub": ("[[A]] [[B]]", ["A", "B"]),
        "A": ("{{Infobox Location}}\n[[Category:Locations]]\n==Overview==\ntext", ["B"]),
        "B": (WIKITEXT, []),
    }
    client = FakeClient(pages)
    # asking for only "item" entities, but Hub/A/B must still all be crawled.
    cr = Crawler(client, entrypoint="Hub", entities_filter=["item"])
    res = cr.crawl()
    assert set(res.visited) == {"Hub", "A", "B"}
    assert all(e.entity_type == "item" for e in res.entities) or res.entities == []
    # discovery still traversed even though none were items.
    assert "A" in res.visited and "B" in res.visited


def test_max_pages_cap():
    pages = _make_graph()
    client = FakeClient(pages)
    cr = Crawler(client, entrypoint="A", max_pages=2)
    res = cr.crawl()
    assert len(res.visited) <= 2
