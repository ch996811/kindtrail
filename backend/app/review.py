"""The AI review: the model reads, plain Python decides.

1. read_receipt: the model turns a receipt photo into line items, each with a spending category
   and its position on the photo.
2. parse_limits: the model turns a donor's plain words into a structured policy.
3. judge: a deterministic rule engine checks every line against the policy. No model output is
   trusted to make the call; it only supplies facts the rules work on.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any

CATEGORIES = ["shelter", "food", "water", "children_supplies", "clothing", "hygiene", "medical", "education",
              "transport", "cash_equivalent", "alcohol_tobacco", "staff_cost", "fees", "other"]

LABELS = {
    "shelter": "shelter", "food": "food", "water": "drinking water", "children_supplies": "kids' supplies",
    "clothing": "clothing", "hygiene": "hygiene", "medical": "medical care", "education": "school supplies",
    "transport": "transport", "cash_equivalent": "cash equivalents", "alcohol_tobacco": "alcohol and tobacco",
    "staff_cost": "staff", "fees": "fees", "other": "other",
}

# Never paid from restricted gifts, whatever a donor wrote.
ALWAYS_NEVER = {"cash_equivalent", "alcohol_tobacco"}

ALLOWED_REASON = {
    "shelter": "Shelter, an allowed use",
    "food": "Food, an allowed use",
    "water": "Drinking water, an allowed use",
    "children_supplies": "For children, exactly who the fund serves",
}
NEVER_REASON = {
    "cash_equivalent": "Cash equivalents break the donors' limits. The partner can pay this from general funds.",
    "alcohol_tobacco": "Alcohol and tobacco can't be paid for with donors' gifts.",
    "staff_cost": "Donors asked that their gifts never pay staff costs.",
}

# --- What the model is asked for ----------------------------------------------------------

RECEIPT_PROMPT = (
    "You are reading a photo of a shop receipt submitted by a charity's field partner.\n"
    "Extract every purchased line exactly as printed. For each line give: receipt_text (the item name as printed), "
    "label (plain English with the quantity, e.g. '4 waterproof tarps'), qty, unit_price, line_total, "
    "category, and box_2d: the bounding box [ymin, xmin, ymax, xmax] of that item's lines on the image, scaled 0-1000.\n"
    "Categories: anything made for children (kids' clothing, diapers, baby formula, toys, school bags) is "
    "children_supplies; prepaid, gift, phone top-up and stored-value cards and vouchers are cash_equivalent; "
    "beer, wine, spirits and cigarettes are alcohol_tobacco; wages and allowances are staff_cost.\n"
    "shop.region is the county or city in English (e.g. 'Hualien County'). printed_at is 'YYYY-MM-DD HH:MM'. "
    "Set readable=false if the image is not a legible receipt."
)

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "shop": {"type": "object", "properties": {
            "name": {"type": "string"}, "branch": {"type": "string"}, "address": {"type": "string"},
            "region": {"type": "string"}, "printed_at": {"type": "string"}},
            "required": ["name", "region", "printed_at"]},
        "currency": {"type": "string"},
        "total": {"type": "number"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "receipt_text": {"type": "string"}, "label": {"type": "string"},
            "qty": {"type": "integer"}, "unit_price": {"type": "number"}, "line_total": {"type": "number"},
            "category": {"type": "string", "enum": CATEGORIES},
            "box_2d": {"type": "array", "items": {"type": "integer"}}},
            "required": ["receipt_text", "label", "qty", "unit_price", "line_total", "category", "box_2d"]}},
    },
    "required": ["readable", "shop", "currency", "total", "items"],
}

LIMITS_PROMPT = (
    "Today is {today}. A donor wrote how their gift to a disaster-relief fund may be used. Turn it into a policy.\n"
    "region: the county or city the money must be spent in, in English (e.g. 'Hualien County'), or null.\n"
    "allowed: the spending categories the donor allows. If they name a group of people (e.g. kids) but no "
    "goods, allow the basics that group needs: shelter, food, water and that group's supplies.\n"
    "never: only categories the donor explicitly names as ruled out (e.g. 'not for staff costs' -> staff_cost). "
    "'Nothing else' just means leaving other categories out of allowed; do not list them in never.\n"
    "beneficiaries: who the money is for, in a few plain words, or null.\n"
    "until: the last day money may be spent as YYYY-MM-DD if the donor gives one (resolve phrases like "
    "'by the end of the year' from today's date), else null.\n"
    "Donor's words: {words}"
)

LIMITS_SCHEMA = {
    "type": "object",
    "properties": {
        "region": {"type": ["string", "null"]},
        "allowed": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
        "never": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
        "beneficiaries": {"type": ["string", "null"]},
        "until": {"type": ["string", "null"]},
    },
    "required": ["region", "allowed", "never", "beneficiaries", "until"],
}


# --- The rule engine ----------------------------------------------------------------------

@dataclass
class Line:
    receipt_text: str
    label: str
    qty: int
    unit_cents: int
    line_cents: int
    category: str
    box: list[int] | None
    verdict: str = "fits"
    reason: str = ""


@dataclass
class Review:
    lines: list[Line]
    flags: list[dict[str, str]] = field(default_factory=list)
    shop: dict[str, Any] = field(default_factory=dict)
    receipt_total_cents: int = 0


def _cents(x: float) -> int:
    return int(round(float(x) * 100))


def _region_matches(shop_region: str, fund_region: str) -> bool:
    a = shop_region.lower().replace("county", "").replace("city", "").strip()
    b = fund_region.lower().replace("county", "").replace("city", "").strip()
    return bool(a) and bool(b) and (a in b or b in a)


def judge(receipt: dict[str, Any], policy: dict[str, Any], *, duplicate_of: str | None = None) -> Review:
    shop = receipt.get("shop") or {}
    lines = [
        Line(receipt_text=i["receipt_text"], label=i["label"], qty=int(i["qty"]), unit_cents=_cents(i["unit_price"]),
             line_cents=_cents(i["line_total"]), category=i["category"] if i["category"] in CATEGORIES else "other",
             box=i.get("box_2d") if isinstance(i.get("box_2d"), list) and len(i["box_2d"]) == 4 else None)
        for i in receipt.get("items", [])
    ]
    review = Review(lines=lines, shop=shop, receipt_total_cents=_cents(receipt.get("total") or 0))

    if not receipt.get("readable", True):
        review.flags.append({"kind": "unreadable", "severity": "block",
                             "message": "The photo isn't a readable receipt. Ask the partner for a clearer one."})

    # Receipt-wide problems block every line.
    block_all = None
    if duplicate_of:
        block_all = f"This receipt was already submitted with request {duplicate_of}."
        review.flags.append({"kind": "duplicate", "severity": "block", "message": block_all})
    region = policy.get("region")
    if region and shop.get("region") and not _region_matches(shop["region"], region):
        msg = f"Bought in {shop['region']}, but donors limited this fund to {region}."
        review.flags.append({"kind": "region", "severity": "block", "message": msg})
        block_all = block_all or msg
    until, printed = policy.get("until"), (shop.get("printed_at") or "")[:10]
    if until and printed:
        try:
            if date.fromisoformat(printed) > date.fromisoformat(until):
                msg = f"Bought on {printed}, after the fund's end date ({until})."
                review.flags.append({"kind": "expired", "severity": "block", "message": msg})
                block_all = block_all or msg
        except ValueError:
            pass

    # Arithmetic checks catch misreads; they don't decide anything but the reviewer should look.
    for ln in lines:
        if abs(ln.qty * ln.unit_cents - ln.line_cents) > 1:
            review.flags.append({"kind": "math", "severity": "check",
                                 "message": f"{ln.receipt_text}: {ln.qty} x {ln.unit_cents / 100:.2f} "
                                            f"doesn't equal {ln.line_cents / 100:.2f}. Check the photo."})
    lines_sum = sum(ln.line_cents for ln in lines)
    if lines and review.receipt_total_cents and abs(lines_sum - review.receipt_total_cents) > 1:
        review.flags.append({"kind": "math", "severity": "check",
                             "message": f"The lines add up to {lines_sum / 100:.2f} but the receipt total "
                                        f"is {review.receipt_total_cents / 100:.2f}. Check the photo."})

    allowed = set(policy.get("allowed") or [])
    never = set(policy.get("never") or []) | ALWAYS_NEVER
    allowed_text = ", ".join(LABELS[c] for c in CATEGORIES if c in allowed) or "nothing yet"
    for ln in lines:
        if ln.category in never:  # the item's own problem says more than a receipt-wide one
            ln.verdict = "blocked"
            ln.reason = NEVER_REASON.get(ln.category, f"Donors ruled out {LABELS[ln.category]}.")
        elif block_all:
            ln.verdict, ln.reason = "blocked", block_all
        elif ln.category in allowed:
            ln.verdict = "fits"
            ln.reason = ALLOWED_REASON.get(ln.category, f"{LABELS[ln.category].capitalize()}, an allowed use")
        else:
            ln.verdict = "blocked"
            ln.reason = f"{LABELS[ln.category].capitalize()} isn't one of the uses donors allowed ({allowed_text})."
    return review


def policy_chips(policy: dict[str, Any]) -> list[dict[str, str]]:
    """The fund's limits as short display chips (Where / For / Who / Never / Until)."""
    chips = []
    if policy.get("region"):
        chips.append({"kind": "Where", "value": policy["region"]})
    if policy.get("allowed"):
        chips.append({"kind": "For", "value": ", ".join(LABELS[c] for c in CATEGORIES if c in policy["allowed"])})
    if policy.get("beneficiaries"):
        chips.append({"kind": "Who", "value": policy["beneficiaries"]})
    never = [c for c in CATEGORIES if c in set(policy.get("never") or []) | ALWAYS_NEVER]
    if never:
        chips.append({"kind": "Never", "value": ", ".join(LABELS[c] for c in never)})
    if policy.get("until"):
        d = date.fromisoformat(policy["until"])
        chips.append({"kind": "Until", "value": f"{d:%b} {d.day}, {d.year}"})
    return chips
