"""Record the demo walkthrough, one video per narrated scene, against the live site.

    python tools/demo_video/record.py            # needs out/audio/*.wav from tts.py

Each scene's actions are paced to its narration length. Writes out/video/<scene>.webm,
out/timings.json (where each scene's content starts in its video) and out/shots/*.png.
"""
import io
import json
import os
import random
import sys
import time
import wave
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
REPO = HERE.parents[1]
BASE = "https://kindtrail.onrender.com"
VIEW = {"width": 1280, "height": 720}
# The fund scene types one of these, so the AI reads it live on camera instead of from the cache.
DONOR_WORDS = [f"Only for kids in Hualien who lost their homes in the typhoon. Not for staff costs. {end}"
               for end in ("Spend it by the end of the year.", "Use it by the end of the year.",
                           "Spend it before the year is over.", "Please spend it by December 31.")]

# A visible cursor, since headless recordings don't draw one.
CURSOR_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.id = 'kt-cursor';
  Object.assign(c.style, {position: 'fixed', left: '-40px', top: '-40px', width: '22px', height: '22px',
    marginLeft: '-11px', marginTop: '-11px', borderRadius: '50%', background: 'rgba(58,11,37,.88)',
    border: '3px solid #fff', boxShadow: '0 2px 10px rgba(0,0,0,.35)', zIndex: 2147483647,
    pointerEvents: 'none', transition: 'transform .12s ease'});
  document.body.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => { c.style.transform = 'scale(.65)'; }, true);
  document.addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; }, true);
});
"""


def audio_seconds(scene: str) -> float:
    with wave.open(str(OUT / "audio" / f"{scene}.wav")) as w:
        return w.getnframes() / w.getframerate()


class Scene:
    """One page = one video. `mark()` says where the watchable part starts; `finish()` pads to the narration."""

    def __init__(self, ctx, name: str):
        self.name, self.page = name, ctx.new_page()
        self.opened = time.monotonic()
        self.start = 0.0
        self.page.mouse.move(VIEW["width"] * 0.6, VIEW["height"] * 0.55)

    def mark(self) -> None:
        self.start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def until(self, t: float) -> None:
        """Wait until t seconds into the narration."""
        left = t - self.elapsed()
        if left > 0:
            time.sleep(left)

    def shot(self, name: str) -> None:
        """A gallery still, without the recording's cursor dot."""
        self.page.evaluate("document.getElementById('kt-cursor')?.style.setProperty('visibility', 'hidden')")
        self.page.screenshot(path=str(OUT / "shots" / f"{name}.png"))
        self.page.evaluate("document.getElementById('kt-cursor')?.style.removeProperty('visibility')")

    def finish(self, timings: dict) -> None:
        self.until(audio_seconds(self.name) + 3.0)  # slack in case a line is re-voiced slightly longer
        video = self.page.video
        self.page.close()
        timings[self.name] = {"video": str(video.path()), "start": round(self.start - self.opened, 2)}
        (OUT / "timings.json").write_text(json.dumps(timings, indent=1))  # saved as we go


def glide(page: Page, locator, click: bool = True, steps: int = 28) -> None:
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y, steps=steps)
    time.sleep(0.25)
    if click:
        page.mouse.click(x, y)


def scroll_to(page: Page, locator, top: int) -> None:
    """Smooth-scroll so the element sits `top` pixels below the top of the window."""
    locator.first.evaluate(f"e => window.scrollBy({{top: e.getBoundingClientRect().top - {top}, behavior: 'smooth'}})")


def scroll(page: Page, dy: int) -> None:
    page.evaluate(f"window.scrollBy({{top: {dy}, behavior: 'smooth'}})")


def fresh_receipt() -> Path:
    """The home-goods receipt, re-encoded so its hash is new and the AI really reads it on camera."""
    img = Image.open(REPO / "backend/demo/receipts/hualien-home-mart.jpg").convert("RGB")
    path = OUT / "receipt-upload.jpg"
    img.save(path, quality=86, comment=os.urandom(12).hex())  # same picture, new bytes
    return path


CALLOUT_JS = """([title, sub, rows, foot, where]) => {
  document.getElementById('kt-callout')?.remove();
  const box = document.createElement('div');
  box.id = 'kt-callout';
  const pos = where === 'top' ? {top: '92px', right: '84px'} : {bottom: '28px', right: '28px'};
  Object.assign(box.style, {position: 'fixed', ...pos, width: '460px', zIndex: 2147483646,
    background: '#3A0B25', color: '#FFF0F4', borderRadius: '20px', padding: '18px 22px 16px',
    boxShadow: '0 18px 40px rgba(58,11,37,.35)', fontFamily: '"Bricolage Grotesque", system-ui, sans-serif',
    opacity: '0', transform: 'translateY(10px)', transition: 'opacity .45s ease, transform .45s ease'});
  const esc = v => String(v).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
  const cells = rows.map(([k, v, hi]) => `<div style="color:#D9A5BC">${esc(k)}</div><div style="${hi
    ? 'color:#3A0B25;background:#FFD84D;border-radius:6px;padding:0 6px;justify-self:start;font-weight:700' : ''}">${esc(v)}</div>`).join('');
  box.innerHTML = `<div style="font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#F0A3BC">${esc(title)}</div>
    <div style="margin-top:4px;font-size:17px;font-weight:700">${esc(sub)}</div>
    <div style="margin-top:12px;display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font:14px/1.35 Consolas, ui-monospace, monospace">${cells}</div>
    ${foot ? `<div style="margin-top:12px;font-size:13px;line-height:1.35;color:#F0A3BC">${esc(foot)}</div>` : ''}`;
  document.body.appendChild(box);
  requestAnimationFrame(() => requestAnimationFrame(() => { box.style.opacity = '1'; box.style.transform = 'none'; }));
}"""


def callout(page: Page, title: str, sub: str, rows: list, foot: str = "", where: str = "bottom") -> None:
    page.evaluate(CALLOUT_JS, [title, sub, rows, foot, where])


def point_at(page: Page, locator) -> None:
    """Hover something optional; skip quietly rather than stall the take."""
    try:
        if locator.count() and locator.first.is_visible():
            glide(page, locator.first, click=False)
    except Exception as e:  # noqa: BLE001 - a missed hover must not ruin a recording
        print("skip hover:", type(e).__name__, flush=True)


def paypal_client():
    sys.path.insert(0, str(REPO / "backend"))
    from app.config import load_settings
    from app.paypal import PayPalClient
    st = load_settings()
    assert st.paypal_env == "sandbox"
    return PayPalClient("https://api-m.sandbox.paypal.com", st.paypal_client_id, st.paypal_client_secret)


def sandbox_order() -> list:
    """Off camera: a real sandbox order created by the live server (as the Give button does), read back from PayPal."""
    gift = httpx.post(BASE + "/api/gifts", timeout=60,
                      json={"fund_code": "FUND-HUALIEN-KIDS", "donor_name": "Ana K.", "amount_cents": 2500}).json()
    order = paypal_client().get_order(gift["order_id"])
    unit = order["purchase_units"][0]
    amount = unit["amount"]
    print("sandbox order", order["id"], order["status"], unit["custom_id"], flush=True)
    return [["order", order["id"], False], ["status", order["status"], False],
            ["amount", f"{amount['currency_code']} {amount['value']}", False], ["custom_id", unit["custom_id"], True]]


def webhook_event(request_id: str) -> list:
    """Off camera: PayPal's own record of the webhook it sent for this payout."""
    pp = paypal_client()
    for _ in range(30):
        events = pp._call("GET", "/v1/notifications/webhooks-events?page_size=10"
                                 "&event_type=PAYMENT.PAYOUTS-ITEM.SUCCEEDED").get("events", [])
        for e in events:
            r = e["resource"]
            if r.get("payout_item", {}).get("sender_item_id") == request_id:
                amount = r["payout_item"]["amount"]
                print("webhook event", e["id"], r["transaction_id"], flush=True)
                return [["event", e["event_type"], False], ["id", e["id"][:22] + "...", False],
                        ["sender_item_id", request_id, True], ["transaction", r["transaction_id"], False],
                        ["amount", f"{amount['currency']} {amount['value']}  {r['transaction_status']}", False]]
        time.sleep(4)
    raise RuntimeError(f"PayPal has no PAYOUTS-ITEM.SUCCEEDED event for {request_id} yet")


def capture_event() -> list | None:
    """Off camera: PayPal's record of the newest sandbox gift captured for the demo fund (a test buyer's checkout)."""
    pp = paypal_client()
    events = pp._call("GET", "/v1/notifications/webhooks-events?page_size=20&event_type=PAYMENT.CAPTURE.COMPLETED").get("events", [])
    for e in events:
        r = e["resource"]
        if r.get("custom_id") == "FUND-HUALIEN-KIDS":
            print("capture event", e["id"], r["id"], flush=True)
            return [["event", e["event_type"], False], ["capture", r["id"], False],
                    ["amount", f"{r['amount']['currency_code']} {r['amount']['value']}  {r['status']}", False],
                    ["custom_id", r["custom_id"], True]]
    print("no captured sandbox gift yet", flush=True)
    return None


def warm_ai() -> None:
    """Off camera: one image read first, so the on-camera read is warm (a cold first read took 10.8 s once)."""
    data = fresh_receipt().read_bytes()
    r = httpx.post(BASE + "/api/requests", timeout=120,
                   data={"fund_code": "FUND-HUALIEN-KIDS", "partner_id": "hualien-mountain-kitchen", "purpose": "warm-up"},
                   files={"receipt": ("warm.jpg", data, "image/jpeg")})
    print("warm-up read", r.json().get("ai"), flush=True)


def prepare() -> dict:
    """Wake the free instance, reset the demo, pre-read the example limits so the fund scene is snappy."""
    api = httpx.Client(base_url=BASE, timeout=60)
    for _ in range(40):
        try:
            if api.get("/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(3)
    api.post("/api/demo/reset")
    fund = api.get("/api/funds/FUND-HUALIEN-KIDS").json()
    print("available", fund["available_cents"], "gifts", [(g["gift_id"], g["donor"]) for g in fund["gifts"]], flush=True)
    return fund


def main() -> None:
    for d in ("video", "shots"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    prepare()
    if not capture_event():  # the give scene's narration shows a gift that really went through PayPal
        sys.exit("No captured sandbox gift for FUND-HUALIEN-KIDS yet: complete one checkout on /give first.")
    timings: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=1, locale="en-US",
                                  record_video_dir=str(OUT / "video"), record_video_size=VIEW)
        ctx.add_init_script(CURSOR_JS)

        # 1. Home: Mei's condition, and what Kindtrail does with it.
        s = Scene(ctx, "1-home")
        s.page.goto(BASE + "/", wait_until="networkidle")
        s.mark()
        s.until(1.6)
        s.shot("1-home")
        s.until(4.0)
        glide(s.page, s.page.get_by_role("link", name="Try it in four steps"), click=False)
        s.until(9.6)  # "Kindtrail checks that condition against every receipt"
        scroll(s.page, 560)
        s.finish(timings)

        # 2. The condition becomes rules; a rule is added; the fund is saved.
        s = Scene(ctx, "2-fund")
        s.page.goto(BASE + "/funds/new", wait_until="networkidle")
        s.mark()
        s.until(0.3)
        words = s.page.locator("textarea").first
        glide(s.page, words)
        words.type(random.choice(DONOR_WORDS), delay=16)
        s.until(3.0)  # "Gemini turns it into rules"
        glide(s.page, s.page.get_by_role("button", name="Turn my words into rules"))
        s.page.get_by_text("The rules Kindtrail will enforce").wait_for(timeout=60_000)
        s.until(5.7)  # "where the money can be spent, on what, for whom, and until when"
        scroll(s.page, 330)
        s.until(9.8)  # "Any rule can be changed."
        scroll(s.page, 150)
        medical = s.page.get_by_role("button", name="Remove medical care")
        if medical.count():  # the model already allowed it: take it out so it can be added on camera
            medical.click()
        s.until(11.4)  # "Adding medical care re-scores the sample pharmacy receipt right away."
        add = s.page.get_by_label("Add a use")
        glide(s.page, add, click=False)
        add.select_option(label="medical care")
        s.until(13.0)
        point_at(s.page, s.page.get_by_text("Pharmacy, Hualien"))
        s.until(13.8)
        s.shot("2-fund")
        s.until(15.0)  # "Once the fund is saved, every gift to it follows these rules."
        name = s.page.get_by_placeholder("e.g. Taitung Flood Families")
        glide(s.page, name)
        name.type("Kids in Hualien", delay=30)
        glide(s.page, s.page.get_by_role("button", name="Create the fund"))
        s.page.get_by_role("link", name="Give to this fund").wait_for(timeout=20_000)
        s.finish(timings)

        order_rows = sandbox_order()
        capture_rows = capture_event()

        # 3. Giving through PayPal (sandbox): the order PayPal stores, then a test buyer's gift that went through.
        s = Scene(ctx, "3-give")
        s.page.goto(BASE + "/give", wait_until="load")
        s.page.get_by_role("radio", name="$25").wait_for()
        s.mark()
        s.until(0.5)
        glide(s.page, s.page.get_by_role("radio", name="$25"))
        s.until(1.3)
        donor = s.page.get_by_placeholder("Anonymous")
        glide(s.page, donor)
        donor.type("Ana K.", delay=80)
        s.until(2.8)
        glide(s.page, s.page.locator("paypal-button"), click=False)
        s.until(4.3)  # "The server creates the order with the fund's code in custom ID"
        callout(s.page, "Behind the scenes · PayPal sandbox", "The order Kindtrail created, as PayPal stores it", order_rows)
        s.until(9.0)
        s.shot("3-give-order")
        if capture_rows:
            s.until(11.8)  # "Here's a test buyer's gift that went all the way through"
            callout(s.page, "Behind the scenes · PayPal webhook", "A sandbox test buyer's gift, captured", capture_rows,
                    "Kindtrail checked this webhook's signature before adding the gift to the fund.")
            s.until(15.6)
            s.shot("3-give")
        s.finish(timings)

        warm_ai()

        # 4. A field partner sends a receipt; the AI reads it live.
        s = Scene(ctx, "4-receipt")
        s.page.goto(BASE + "/submit", wait_until="networkidle")
        s.mark()
        purpose = s.page.locator("#purpose")
        glide(s.page, purpose)
        purpose.fill("")
        purpose.type("tarps, rice and raincoats for typhoon families", delay=24)
        s.until(3.6)
        glide(s.page, s.page.get_by_role("button", name="Choose a photo"), click=False)
        s.page.set_input_files("input[type=file]", str(fresh_receipt()))
        s.until(5.2)
        glide(s.page, s.page.get_by_role("button", name="Check this receipt"))
        s.page.get_by_text("Sent to the charity as").wait_for(timeout=90_000)
        request_id = s.page.get_by_role("heading", name="Sent to the charity as").inner_text().split()[-1]
        s.until(12.6)
        s.shot("4-receipt")
        s.until(15.9)  # "The prepaid gift card counts as cash"
        glide(s.page, s.page.get_by_text("Prepaid gift card", exact=False).last, click=False)
        s.finish(timings)
        print("new request", request_id, flush=True)

        # 5a. The charity reviews: verdicts, then which gifts pay; then Approve.
        s = Scene(ctx, "5a-review")
        s.page.goto(f"{BASE}/requests/{request_id}", wait_until="networkidle")
        s.page.get_by_text("What the AI found").wait_for()
        s.mark()
        s.until(0.4)
        scroll_to(s.page, s.page.get_by_text("What the AI found"), 96)
        s.until(2.6)
        s.shot("5-review")
        s.until(3.9)  # "and which gifts will pay for it, oldest first"
        scroll_to(s.page, s.page.get_by_text("Whose dollars"), 96)
        s.until(5.6)
        s.shot("5-review-gifts")
        s.until(7.4)  # "Approve sends the money to the kitchen with PayPal Payouts."
        glide(s.page, s.page.get_by_role("button", name="Approve"))
        s.finish(timings)

        # Off camera: wait for PayPal to finish the payout.
        api = httpx.Client(base_url=BASE, timeout=60)
        for _ in range(30):
            if api.post(f"/api/requests/{request_id}/refresh").json()["status"] == "paid":
                break
            time.sleep(5)
        print("paid", flush=True)

        webhook_rows = webhook_event(request_id)

        # 5b. Paid, confirmed by PayPal's webhook.
        s = Scene(ctx, "5b-paid")
        s.page.goto(f"{BASE}/requests/{request_id}", wait_until="networkidle")
        s.page.get_by_role("link", name="Send donor thank-yous").wait_for()
        s.mark()
        s.until(0.3)  # "PayPal's webhook confirms the payout."
        callout(s.page, "Behind the scenes · PayPal webhook", "PayPal's notification for this payout", webhook_rows,
                "Kindtrail checks every delivery with verify-webhook-signature before the ledger changes.", where="top")
        s.until(3.0)
        s.shot("5-paid")
        point_at(s.page, s.page.get_by_text("Paid", exact=True))
        s.finish(timings)

        # 6. Mei's receipt.
        s = Scene(ctx, "6-impact")
        s.page.goto(f"{BASE}/requests/{request_id}/thanks", wait_until="networkidle")
        s.page.get_by_role("link", name="Open receipt").first.wait_for()
        s.mark()
        s.until(0.3)
        glide(s.page, s.page.get_by_role("link", name="Open receipt").first)
        s.page.get_by_text("paid for").first.wait_for()
        s.until(3.2)
        s.shot("6-impact")
        s.until(7.6)  # "who shared the rest, the gift card it didn't touch"
        scroll(s.page, 430)
        s.until(10.4)  # "who approved it, and the PayPal transaction for the payout"
        scroll(s.page, 430)
        s.until(12.4)
        s.shot("6-impact-proof")
        s.finish(timings)

        # 7. End card.
        s = Scene(ctx, "7-close")
        s.page.goto((HERE / "endcard.html").as_uri(), wait_until="networkidle")
        s.mark()
        s.shot("7-close")
        s.finish(timings)

        ctx.close()
        browser.close()

    (OUT / "timings.json").write_text(json.dumps(timings, indent=1))
    print(json.dumps(timings, indent=1))


if __name__ == "__main__":
    sys.exit(main())
