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
    problem: str = ""  # why this line's own numbers can't be trusted; such a line is never paid


@dataclass
class Review:
    lines: list[Line]
    flags: list[dict[str, str]] = field(default_factory=list)
    shop: dict[str, Any] = field(default_factory=dict)
    receipt_total_cents: int = 0


def _cents(x: float) -> int:
    return int(round(float(x) * 100))


USD_NAMES = {"USD", "US$", "US DOLLAR", "US DOLLARS"}
UNKNOWN = {"", "unknown", "n/a", "none", "null", "-"}


def _places(region: str) -> list[str]:
    """'Guangfu Township, Hualien County' -> ['guangfu township', 'hualien']: comma parts, minus county/city."""
    out = []
    for part in region.lower().split(","):
        words = [w for w in part.split() if w not in ("county", "city")]
        if words:
            out.append(" ".join(words))
    return out


def _region_matches(shop_region: str, fund_region: str) -> bool:
    """A whole place name has to match, so 'New Taipei City' is not 'Taipei City'. Receipts usually name only
    the county, so a county-level receipt passes a fund limited to a township in that county."""
    shop, fund = _places(shop_region), _places(fund_region)
    return any(s == f for s in shop for f in fund)


def _number(x: Any) -> float:
    if isinstance(x, bool) or x is None:
        raise ValueError("not a number")
    return float(x)


def _box(value: Any) -> list[int] | None:
    ok = (isinstance(value, list) and len(value) == 4
          and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1000 for v in value))
    return [int(v) for v in value] if ok else None


def _read_lines(items: Any) -> tuple[list[Line], list[int]]:
    """The model's purchase lines, checked one by one. Returns the lines and the numbers of any that couldn't be
    read at all (a missing or non-numeric field): those make the whole reading untrustworthy."""
    lines: list[Line] = []
    unreadable: list[int] = []
    for n, i in enumerate(items if isinstance(items, list) else [], 1):
        try:
            qty, unit, total = _number(i["qty"]), _cents(_number(i["unit_price"])), _cents(_number(i["line_total"]))
            text = str(i.get("receipt_text") or "").strip()
            label = str(i.get("label") or "").strip() or text
            if not label:
                raise ValueError("no name")
        except (KeyError, TypeError, ValueError, AttributeError):
            unreadable.append(n)
            continue
        whole = qty == int(qty)
        line = Line(receipt_text=text or label, label=label, qty=int(qty) if whole and qty > 0 else 0, unit_cents=unit,
                    line_cents=total, category=i.get("category") if i.get("category") in CATEGORIES else "other",
                    box=_box(i.get("box_2d")))
        if not whole or qty < 1:
            line.problem = f"The quantity reads as {qty:g}, which can't be paid as it is. A person has to check the photo."
        elif abs(line.qty * unit - total) > 1:
            line.problem = (f"{line.qty} x {unit / 100:.2f} doesn't make the line total of {total / 100:.2f}, so the AI "
                            "may have misread this line. A person has to check the photo.")
        lines.append(line)
    return lines, unreadable


def judge(receipt: dict[str, Any], policy: dict[str, Any], *, duplicate_of: str | None = None) -> Review:
    """Decide every line. The model's answer is only trusted as far as it checks out: anything missing, negative or
    inconsistent blocks payment instead of slipping through."""
    receipt = receipt if isinstance(receipt, dict) else {"readable": False}
    shop = receipt.get("shop") if isinstance(receipt.get("shop"), dict) else {}
    lines, unreadable = _read_lines(receipt.get("items"))
    try:
        total_cents = _cents(_number(receipt.get("total")))
    except (TypeError, ValueError):
        total_cents = 0
    review = Review(lines=lines, shop=shop, receipt_total_cents=total_cents)

    # Receipt-wide problems block every line. When the model can't tell us something a limit depends on,
    # nothing is paid: a person has to look.
    block_all = None

    def block(kind: str, msg: str) -> None:
        nonlocal block_all
        review.flags.append({"kind": kind, "severity": "block", "message": msg})
        block_all = block_all or msg

    if not receipt.get("readable", True):
        block("unreadable", "The photo isn't a readable receipt. Ask the partner for a clearer one.")
        return _verdicts(review, policy, block_all)
    if unreadable:
        which = ", ".join(str(n) for n in unreadable)
        block("incomplete", f"The AI's reading of {'line' if len(unreadable) == 1 else 'lines'} {which} came back "
                            "incomplete, so nothing is paid. Ask the partner for a clearer photo.")
    elif not lines:
        block("incomplete", "The AI found no purchases on this receipt, so there is nothing it can pay.")
    if any(ln.unit_cents < 0 or ln.line_cents < 0 for ln in lines):
        block("discount", "This receipt has a discount or refund line. Kindtrail can't spread a discount across "
                          "the other lines yet, so nothing is paid until a person handles it.")

    if duplicate_of:
        block("duplicate", f"This receipt was already submitted with request {duplicate_of}.")
    currency = str(receipt.get("currency") or "").strip().upper()
    if currency not in USD_NAMES:
        shown = currency if currency.lower() not in UNKNOWN else "an unknown currency"
        block("currency", f"This receipt is in {shown}. The fund pays in US dollars and Kindtrail doesn't convert "
                          "currencies yet, so a person has to handle it.")
    region, shop_region = policy.get("region"), str(shop.get("region") or "").strip()
    if region and shop_region.lower() in UNKNOWN:
        block("region", f"The AI couldn't tell where the shop is, so the {region} limit can't be checked.")
    elif region and not _region_matches(shop_region, region):
        block("region", f"Bought in {shop_region}, but donors limited this fund to {region}.")
    until, printed = policy.get("until"), (shop.get("printed_at") or "")[:10]
    if until:
        try:
            if date.fromisoformat(printed) > date.fromisoformat(until):
                block("expired", f"Bought on {printed}, after the fund's end date ({until}).")
        except ValueError:
            block("expired", f"The AI couldn't read the purchase date, so the end date ({until}) can't be checked.")

    # Arithmetic catches misreads. A line whose own numbers disagree is never paid; lines that claim more than the
    # receipt's total block everything. Lines that come to less (tax, say) are only paid as listed.
    for ln in lines:
        if ln.problem:
            review.flags.append({"kind": "math", "severity": "check",
                                 "message": f"{ln.receipt_text}: the quantity and prices don't agree, so this line "
                                            "isn't paid. Check the photo."})
    lines_sum, total = sum(ln.line_cents for ln in lines), review.receipt_total_cents
    if lines and total > 0 and lines_sum > total + 1:
        block("total", f"The lines add up to {lines_sum / 100:.2f}, more than the receipt's total of {total / 100:.2f}, "
                       "so the AI may have misread a line. Nothing is paid until a person checks the photo.")
    elif lines and total > 0 and lines_sum < total - 1:
        review.flags.append({"kind": "math", "severity": "check",
                             "message": f"The lines add up to {lines_sum / 100:.2f} but the receipt's total is "
                                        f"{total / 100:.2f} (tax, or a line the AI missed). Only the lines listed "
                                        "can be paid."})
    elif lines and total <= 0:
        review.flags.append({"kind": "math", "severity": "check",
                             "message": "The AI couldn't read the receipt's total, so the lines weren't checked "
                                        "against it. Check the photo."})
    return _verdicts(review, policy, block_all)


def _verdicts(review: Review, policy: dict[str, Any], block_all: str | None) -> Review:
    lines = review.lines
    allowed = set(policy.get("allowed") or [])
    never = set(policy.get("never") or []) | ALWAYS_NEVER
    allowed_text = ", ".join(LABELS[c] for c in CATEGORIES if c in allowed) or "nothing yet"
    for ln in lines:
        if ln.category in never:  # the item's own problem says more than a receipt-wide one
            ln.verdict = "blocked"
            ln.reason = NEVER_REASON.get(ln.category, f"Donors ruled out {LABELS[ln.category]}.")
        elif ln.problem:
            ln.verdict, ln.reason = "blocked", ln.problem
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
