import responses

from lore_extractor.api import WikiClient


@responses.activate
def test_get_page_handles_wikitext_string_format():
    resp = {
        "parse": {
            "title": "Akame",
            "pageid": 2067,
            "wikitext": "Hello [[World]]",
            "sections": [],
            "categories": [{"category": "Characters"}],
            "links": [{"ns": 0, "title": "World"}],
            "images": [],
            "templates": [],
        }
    }
    responses.add(
        responses.GET,
        "https://akamegakill.fandom.com/api.php",
        json=resp,
        status=200,
    )
    client = WikiClient("akamegakill.fandom.com")
    page = client.get_page("Akame")
    assert page["title"] == "Akame"
    assert page["wikitext"] == "Hello [[World]]"
    assert page["categories"] == ["Characters"]
    assert page["links"] == ["World"]


@responses.activate
def test_get_page_returns_none_on_missing():
    responses.add(
        responses.GET,
        "https://akamegakill.fandom.com/api.php",
        json={
            "error": {
                "code": "missingtitle",
                "info": "The page you specified doesn't exist.",
            }
        },
        status=200,
    )
    client = WikiClient("akamegakill.fandom.com")
    assert client.get_page("Does Not Exist") is None


@responses.activate
def test_get_category_members_pagination():
    def request_callback(request):
        if "cmcontinue=nextpage" in request.url:
            return (200, {}, '{"query":{"categorymembers":[{"title":"C"}]}}')
        return (
            200,
            {},
            '{"query":{"categorymembers":[{"title":"A"},{"title":"B"}]},'
            '"continue":{"cmcontinue":"nextpage"}}',
        )

    responses.add_callback(
        responses.GET,
        "https://akamegakill.fandom.com/api.php",
        callback=request_callback,
        content_type="application/json",
    )
    client = WikiClient("akamegakill.fandom.com", rate_per_sec=100)
    members = client.get_category_members("Characters")
    assert members == ["A", "B", "C"]


@responses.activate
def test_api_error_raises():
    responses.add(
        responses.GET,
        "https://akamegakill.fandom.com/api.php",
        json={
            "error": {
                "code": "badvalue",
                "info": "Bad value for parameter.",
            }
        },
        status=200,
    )
    client = WikiClient("akamegakill.fandom.com")
    try:
        client.get_page("Akame")
        assert False, "should have raised"
    except Exception as exc:
        assert "badvalue" in str(exc).lower() or "API error" in str(exc)
