import json

import httpx
import pytest

from app.llm import LLM, AIUnavailable, GeminiProvider, ReplayProvider
from app.review import judge, policy_chips

POLICY = {"region": "Hualien County", "allowed": ["shelter", "food", "water", "children_supplies"],
          "never": ["staff_cost"], "beneficiaries": "kids who lost their homes", "until": "2026-12-31"}


def receipt(*items, region="Hualien County", printed="2026-10-24 14:32", total=None, readable=True):
    lines = [{"receipt_text": t, "label": t, "qty": q, "unit_price": u, "line_total": round(q * u, 2), "category": c,
              "box_2d": [100, 100, 150, 600]} for t, q, u, c in items]
    return {"readable": readable, "shop": {"name": "SHOP", "region": region, "printed_at": printed},
            "currency": "USD", "total": total if total is not None else sum(i["line_total"] for i in lines),
            "items": lines}


def verdicts(review):
    return [(ln.receipt_text, ln.verdict) for ln in review.lines]


def test_allowed_never_and_unlisted_categories():
    r = judge(receipt(("Tarp", 4, 8.0, "shelter"), ("Wages", 1, 50.0, "staff_cost"), ("Bus fare", 2, 1.5, "transport")),
              POLICY)
    assert verdicts(r) == [("Tarp", "fits"), ("Wages", "blocked"), ("Bus fare", "blocked")]
    assert "staff costs" in r.lines[1].reason
    assert "isn't one of the uses donors allowed" in r.lines[2].reason
    assert r.flags == []


def test_cash_equivalents_and_alcohol_are_blocked_even_if_a_donor_allows_them():
    generous = {**POLICY, "allowed": POLICY["allowed"] + ["cash_equivalent", "alcohol_tobacco"]}
    r = judge(receipt(("Gift card", 1, 8.8, "cash_equivalent"), ("Beer", 2, 9.9, "alcohol_tobacco")), generous)
    assert verdicts(r) == [("Gift card", "blocked"), ("Beer", "blocked")]


def test_wrong_region_blocks_every_line_but_keeps_item_specific_reasons():
    r = judge(receipt(("Water", 3, 4.5, "water"), ("Beer", 2, 9.9, "alcohol_tobacco"), region="Taipei City"), POLICY)
    assert verdicts(r) == [("Water", "blocked"), ("Beer", "blocked")]
    assert r.lines[0].reason.startswith("Bought in Taipei City")
    assert r.lines[1].reason.startswith("Alcohol")
    assert [f["kind"] for f in r.flags] == ["region"]


def test_region_matching_ignores_county_and_city_suffixes():
    assert judge(receipt(("Rice", 1, 12.0, "food"), region="Hualien"), POLICY).lines[0].verdict == "fits"


def test_after_the_end_date_is_blocked():
    r = judge(receipt(("Rice", 1, 12.0, "food"), printed="2027-01-02 09:00"), POLICY)
    assert r.lines[0].verdict == "blocked"
    assert r.flags[0]["kind"] == "expired"


def test_resubmitted_receipt_is_blocked():
    r = judge(receipt(("Rice", 1, 12.0, "food")), POLICY, duplicate_of="KT-0142")
    assert r.lines[0].verdict == "blocked" and "KT-0142" in r.lines[0].reason
    assert r.flags[0]["kind"] == "duplicate"


def test_a_line_whose_numbers_disagree_is_never_paid():
    # Read as 500 tarps at 19.40 while the line total says 77.60: paying qty x price would send 9,700.
    data = receipt(("Tarp", 4, 19.40, "shelter"), ("Rice", 2, 9.0, "food"))
    data["items"][0]["qty"] = 500
    r = judge(data, POLICY)
    assert verdicts(r) == [("Tarp", "blocked"), ("Rice", "fits")]
    assert "doesn't make the line total" in r.lines[0].reason
    assert [f["kind"] for f in r.flags] == ["math"]


def test_lines_that_claim_more_than_the_receipt_total_block_everything():
    r = judge(receipt(("Rice", 2, 12.0, "food"), total=20.0), POLICY)
    assert verdicts(r) == [("Rice", "blocked")] and r.flags[0]["kind"] == "total"


def test_lines_that_come_to_less_than_the_total_are_paid_as_listed():
    r = judge(receipt(("Rice", 2, 12.0, "food"), total=25.5), POLICY)  # tax, say
    assert verdicts(r) == [("Rice", "fits")]
    assert [(f["kind"], f["severity"]) for f in r.flags] == [("math", "check")]


def test_a_malformed_answer_from_the_model_pays_nothing_and_never_crashes():
    data = receipt(("Tarp", 4, 8.0, "shelter"), ("Rice", 2, 9.0, "food"))
    del data["items"][1]["unit_price"]
    r = judge(data, POLICY)
    assert verdicts(r) == [("Tarp", "blocked")] and r.flags[0]["kind"] == "incomplete"

    data = receipt(("Tarp", 4, 8.0, "shelter"))
    data["items"][0].update(qty="four", box_2d=[1, 2, 3, 9999])
    assert judge(data, POLICY).flags[0]["kind"] == "incomplete"

    data = receipt(("Tarp", 4, 8.0, "shelter"))
    data["items"][0]["box_2d"] = [1, 2, 3, 9999]
    assert judge(data, POLICY).lines[0].box is None  # off the photo: no box rather than a wrong one

    for answer in ([], "text", {"readable": True, "items": "none", "shop": "?"}, {"readable": True, "items": []}):
        r = judge(answer, POLICY)
        assert r.flags[0]["severity"] == "block" and all(ln.verdict == "blocked" for ln in r.lines)


def test_fractional_or_zero_quantities_are_not_paid():
    data = receipt(("Rice", 1, 4.0, "food"), ("Water", 1, 2.0, "water"))
    data["items"][0].update(qty=1.5, line_total=6.0)
    data["items"][1].update(qty=0, line_total=0.0)
    data["total"] = 6.0
    r = judge(data, POLICY)
    assert verdicts(r) == [("Rice", "blocked"), ("Water", "blocked")]
    assert "quantity reads as 1.5" in r.lines[0].reason


def test_a_discount_line_blocks_the_receipt():
    r = judge(receipt(("Tarp", 4, 8.0, "shelter"), ("Member discount", 1, -2.0, "other")), POLICY)
    assert all(ln.verdict == "blocked" for ln in r.lines)
    assert any(f["kind"] == "discount" for f in r.flags)


def test_unreadable_photo_is_flagged():
    r = judge(receipt(readable=False), POLICY)
    assert r.flags[0]["kind"] == "unreadable" and r.lines == []


def test_policy_chips():
    assert policy_chips(POLICY) == [
        {"kind": "Where", "value": "Hualien County"},
        {"kind": "For", "value": "shelter, food, drinking water, kids' supplies"},
        {"kind": "Who", "value": "kids who lost their homes"},
        {"kind": "Never", "value": "cash equivalents, alcohol and tobacco, staff"},
        {"kind": "Until", "value": "Dec 31, 2026"},
    ]


# LLM layer -----------------------------------------------------------------------------------

class CountingProvider:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def generate_json(self, **_):
        self.calls += 1
        return self.answer, "fake-model"


def test_answers_are_cached_and_the_daily_cap_holds(conn):
    provider = CountingProvider({"ok": True})
    llm = LLM(provider, daily_cap=2)
    first = llm.ask(conn, task="t", prompt="p1", schema={})
    again = llm.ask(conn, task="t", prompt="p1", schema={})
    assert (first.cached, again.cached, provider.calls) == (False, True, 1)
    llm.ask(conn, task="t", prompt="p2", schema={})
    with pytest.raises(AIUnavailable, match="budget"):
        llm.ask(conn, task="t", prompt="p3", schema={})
    assert llm.ask(conn, task="t", prompt="p1", schema={}).cached  # cache still works past the cap


def test_replay_mode_only_serves_cached_answers(conn):
    with pytest.raises(AIUnavailable):
        LLM(ReplayProvider()).ask(conn, task="t", prompt="never asked", schema={})


def test_gemini_falls_back_to_the_next_model_when_one_is_overloaded():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = request.url.path.split("/models/")[1].split(":")[0]
        seen.append(model)
        if model == "first-model":
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert request.headers["x-goog-api-key"] == "k"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"answer": 42}'}]}}]})

    provider = GeminiProvider("k", models=["first-model", "second-model"], transport=httpx.MockTransport(handler))
    data, model = provider.generate_json(prompt="p", schema={}, image=b"img", mime="image/jpeg")
    assert (data, model, seen) == ({"answer": 42}, "second-model", ["first-model", "second-model"])


def test_gemini_reports_every_model_failure():
    provider = GeminiProvider("k", models=["a", "b"],
                              transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(AIUnavailable, match="a: HTTP 429; b: HTTP 429"):
        provider.generate_json(prompt="p", schema={}, image=None, mime=None)


def test_warm_up_only_lists_models_and_never_fails():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"models": []})

    GeminiProvider("k", transport=httpx.MockTransport(handler)).warm_up()
    assert seen == [("GET", "/v1beta/models")]

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    GeminiProvider("k", transport=httpx.MockTransport(broken)).warm_up()  # swallowed


def test_an_unreadable_photo_pays_nothing():
    r = judge(receipt(("Tarp", 4, 8.0, "shelter"), readable=False), POLICY)
    assert verdicts(r) == [("Tarp", "blocked")]
    assert [f["kind"] for f in r.flags] == ["unreadable"]


def test_a_receipt_in_another_currency_is_not_paid_as_dollars():
    r = judge({**receipt(("Rice", 2, 400.0, "food")), "currency": "TWD"}, POLICY)
    assert verdicts(r) == [("Rice", "blocked")]
    assert [f["kind"] for f in r.flags] == ["currency"] and "TWD" in r.flags[0]["message"]


def test_when_the_shop_or_the_date_cant_be_read_the_limits_fail_closed():
    for region, printed, kind in (("unknown", "2026-10-24 14:32", "region"), ("", "2026-10-24 14:32", "region"),
                                  ("Hualien County", "", "expired")):
        r = judge(receipt(("Tarp", 4, 8.0, "shelter"), region=region, printed=printed), POLICY)
        assert verdicts(r) == [("Tarp", "blocked")], (region, printed)
        assert [f["kind"] for f in r.flags] == [kind]
        assert "Bought in" not in r.flags[0]["message"]  # never "Bought in unknown"


def test_place_names_match_whole_places_only():
    taipei = {**POLICY, "region": "Taipei City"}
    assert verdicts(judge(receipt(("Water", 1, 2.0, "water"), region="New Taipei City"), taipei)) == [("Water", "blocked")]
    assert verdicts(judge(receipt(("Water", 1, 2.0, "water"), region="Taipei City"), taipei)) == [("Water", "fits")]
    township = {**POLICY, "region": "Guangfu Township, Hualien County"}
    assert verdicts(judge(receipt(("Tarp", 1, 8.0, "shelter"), region="Hualien County"), township)) == [("Tarp", "fits")]
