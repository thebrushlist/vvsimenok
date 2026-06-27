"""
Portfolio site generator.

Reads three image folders and produces a static index.html.

Folder layout
─────────────
  paintings/   night-tide_50x70cm_available.jpg
               harbour-dawn_80x100cm_sold.jpg

  drawings/    portrait-of-lena_A3_sold.jpg
               street-scene_30x40cm_available.jpg

  prints/      night-tide_A3_25_available.jpg
               katoomba-river_A4_18_sold.jpg

Filenames:
  • paintings → name_size_status
  • drawings → name_size_status
  • prints   → name_size_price_status

Status: "available" or "sold".

Environment variables
─────────────────────
  STRIPE_API_KEY   — Stripe secret key (sk_live_… or sk_test_…) used to
                     create payment links for available prints.

Run:
    STRIPE_API_KEY="sk_test_…" python3 generate.py
"""

import os
import re
import json
import html
import datetime as dt
from pathlib import Path
from string import Template
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ── config ───────────────────────────────────────────────────────────
PAINTINGS_DIR = Path("paintings")
DRAWINGS_DIR  = Path("drawings")
PRINTS_DIR    = Path("prints")
OUTPUT_PATH   = Path("index.html")

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_API     = "https://api.stripe.com"

INQUIRY_EMAIL  = "vvsimenok@hotmail.com"

SITE_TITLE     = "Vladimir Vladislav Simenok"
IG_HANDLE      = "vvsimenok"        # primary (art) account \u2014 shown in nav, masthead, footer
SECONDARY_IG   = "vovasimenok"      # shown in the biography

FAVICON_DATA_URI = "data:image/png;base64,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"

BIOGRAPHY_PARAS = (
    "I am a self-taught artist who started painting in 2024. Since 2024 I have "
    "been travelling extensively, covering 32 countries \u2014 Albania, Armenia, "
    "Australia, Austria, Azerbaijan, Bahrain, Cambodia, Czechia, Egypt, Estonia, "
    "France, Georgia, Germany, Greece, Hungary, India, Indonesia, Italy, Laos, "
    "Malaysia, Nepal, New Zealand, Philippines, Singapore, Slovakia, South Korea, "
    "Sri Lanka, Thailand, United Arab Emirates, Vanuatu, Vatican and Vietnam \u2014 "
    "of a current tally of 54.",

    "Induced by the grief of losing a child. Pursuing travel and art were the "
    "alternative to serving in the Ukrainian foreign legion. With the focus of "
    "my art to invite people to pause, converse and reflect.",
)

STATEMENT_TEXT = (
    "The intention of my art is to create a point in space which can exist in "
    "the form of counsel and entertainment, bringing people together to converse "
    "and speculate on its impression. Whilst simultaneously being a place for the "
    "viewer\u2019s expression of thought and emotion. At that exact point in time. "
    "An invitation to draw you into a complete standstill, pausing oneself from "
    "the ever-turning idiosyncratic journey that is life."
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ── helpers ──────────────────────────────────────────────────────────
def title_from_name(raw):
    """night-tide -> Night Tide"""
    return " ".join(w.capitalize() for w in re.split(r"[-_ ]+", raw))


def format_size(raw):
    """50x70cm -> 50 x 70 cm, A3 -> A3"""
    # Add spaces around 'x' in dimensions like 50x70cm
    s = re.sub(r"(\d+)x(\d+)", r"\1 x \2", raw)
    # Add space before unit if missing: 70cm -> 70 cm
    s = re.sub(r"(\d)(cm|mm|in|inch)", r"\1 \2", s)
    return s


def parse_artwork(filename, folder):
    """Parse paintings/drawings: name_size_status.ext"""
    stem = Path(filename).stem
    parts = stem.rsplit("_", 2)
    if len(parts) != 3:
        print(f"  \u26a0  skipping {folder}/{filename} (expected name_size_status)")
        return None
    name, size, status = parts
    status = status.lower()
    if status not in ("available", "sold"):
        print(f"  \u26a0  skipping {folder}/{filename} (unknown status '{status}')")
        return None
    return {
        "file": filename,
        "path": f"{folder}/{filename}",
        "title": title_from_name(name),
        "size": format_size(size),
        "status": status,
    }


def parse_print(filename):
    """Parse prints: name_size_price_status.ext"""
    stem = Path(filename).stem
    parts = stem.rsplit("_", 3)
    if len(parts) != 4:
        print(f"  \u26a0  skipping prints/{filename} (expected name_size_price_status)")
        return None
    name, size, price_str, status = parts
    status = status.lower()
    try:
        price = int(price_str)
    except ValueError:
        print(f"  \u26a0  skipping prints/{filename} (bad price '{price_str}')")
        return None
    if status not in ("available", "sold"):
        print(f"  \u26a0  skipping prints/{filename} (unknown status '{status}')")
        return None
    return {
        "file": filename,
        "path": f"prints/{filename}",
        "title": title_from_name(name),
        "size": format_size(size),
        "price": price,
        "status": status,
        "payment_link": None,
    }


# ── Stripe ───────────────────────────────────────────────────────────
def stripe_request(method, endpoint, **params):
    url = f"{STRIPE_API}/v1/{endpoint.lstrip('/')}"
    data = urlencode(params).encode("utf-8") if params else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {STRIPE_API_KEY}")
    req.add_header("User-Agent", "portfolio-generator/1.0")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()), None
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body
        return None, f"HTTP {e.code}: {msg}"


def create_shipping_rates():
    rates = []
    for name, amount, min_days, max_days in [
        ("Standard Worldwide", 1200, 7, 21),
        ("Express Worldwide", 3500, 3, 7),
    ]:
        rate, err = stripe_request(
            "POST", "shipping_rates",
            display_name=name,
            type="fixed_amount",
            **{
                "fixed_amount[amount]": str(amount),
                "fixed_amount[currency]": "usd",
                "delivery_estimate[minimum][unit]": "business_day",
                "delivery_estimate[minimum][value]": str(min_days),
                "delivery_estimate[maximum][unit]": "business_day",
                "delivery_estimate[maximum][value]": str(max_days),
            },
        )
        if err:
            print(f"  \u26a0  Stripe shipping rate error for '{name}': {err}")
        else:
            rates.append(rate["id"])
            print(f"  \u2713 shipping rate: {name} (${amount/100:.0f})")
    return rates


def create_stripe_product(title, price_cents, shipping_rate_ids=None, image_url=None):
    prod_params = {"name": f"Signed printed digital scan \u2014 {title}"}
    if image_url:
        prod_params["images[0]"] = image_url
    product, err = stripe_request("POST", "products", **prod_params)
    if err:
        print(f"  \u26a0  Stripe product error for '{title}': {err}")
        return None
    product_id = product["id"]

    price, err = stripe_request(
        "POST", "prices",
        product=product_id, currency="usd", unit_amount=str(price_cents),
    )
    if err:
        print(f"  \u26a0  Stripe price error for '{title}': {err}")
        return None
    price_id = price["id"]

    link_params = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "shipping_address_collection[allowed_countries][0]": "US",
        "shipping_address_collection[allowed_countries][1]": "GB",
        "shipping_address_collection[allowed_countries][2]": "AU",
        "shipping_address_collection[allowed_countries][3]": "CA",
        "shipping_address_collection[allowed_countries][4]": "DE",
        "shipping_address_collection[allowed_countries][5]": "FR",
        "shipping_address_collection[allowed_countries][6]": "ES",
        "shipping_address_collection[allowed_countries][7]": "IT",
        "shipping_address_collection[allowed_countries][8]": "NL",
        "shipping_address_collection[allowed_countries][9]": "JP",
        "shipping_address_collection[allowed_countries][10]": "NZ",
        "shipping_address_collection[allowed_countries][11]": "SE",
        "shipping_address_collection[allowed_countries][12]": "NO",
        "shipping_address_collection[allowed_countries][13]": "DK",
        "shipping_address_collection[allowed_countries][14]": "PT",
        "shipping_address_collection[allowed_countries][15]": "IE",
        "shipping_address_collection[allowed_countries][16]": "AT",
        "shipping_address_collection[allowed_countries][17]": "CH",
        "shipping_address_collection[allowed_countries][18]": "BE",
        "shipping_address_collection[allowed_countries][19]": "SG",
    }
    for i, rate_id in enumerate(shipping_rate_ids or []):
        link_params[f"shipping_options[{i}][shipping_rate]"] = rate_id

    link, err = stripe_request("POST", "payment_links", **link_params)
    if err:
        print(f"  \u26a0  Stripe payment-link error for '{title}': {err}")
        return None
    return link.get("url")


# ── main ─────────────────────────────────────────────────────────────
def main():
    # ── read paintings ──
    paintings = []
    if PAINTINGS_DIR.exists():
        for p in sorted(PAINTINGS_DIR.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                parsed = parse_artwork(p.name, "paintings")
                if parsed:
                    paintings.append(parsed)
    print(f"Paintings: {len(paintings)}")

    # ── read drawings ──
    drawings = []
    if DRAWINGS_DIR.exists():
        for p in sorted(DRAWINGS_DIR.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                parsed = parse_artwork(p.name, "drawings")
                if parsed:
                    drawings.append(parsed)
    print(f"Drawings: {len(drawings)}")

    # ── read prints ──
    prints = []
    if PRINTS_DIR.exists():
        for p in sorted(PRINTS_DIR.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                parsed = parse_print(p.name)
                if parsed:
                    prints.append(parsed)
    print(f"Prints: {len(prints)}")

    # ── Stripe ──
    if STRIPE_API_KEY:
        print("Creating shipping rates\u2026")
        shipping_ids = create_shipping_rates()
        for pr in prints:
            if pr["status"] == "available":
                print(f"  \u2192 creating Stripe link for '{pr['title']}' (${pr['price']})\u2026")
                url = create_stripe_product(pr["title"], pr["price"] * 100, shipping_ids)
                if url:
                    pr["payment_link"] = url
                    print(f"    \u2713 {url}")
    else:
        print("No STRIPE_API_KEY \u2014 skipping payment link creation.")

    html_out = render(paintings, drawings, prints)
    OUTPUT_PATH.write_text(html_out, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html_out):,} bytes)")


# ── HTML rendering ───────────────────────────────────────────────────
def render(paintings, drawings, prints):
    e = html.escape
    now = dt.datetime.now(dt.timezone.utc)
    year = now.strftime("%Y")

    def render_artwork_cards(items, section_type):
        """Render cards for paintings or drawings (inquiry CTA)."""
        if not items:
            return f'<p class="empty">No {section_type} yet.</p>'
        cards = ""
        for o in items:
            sold_cls = " sold" if o["status"] == "sold" else ""
            badge = '<span class="badge sold-badge">Sold</span>' if o["status"] == "sold" else ""
            if o["status"] == "available":
                subj = f"Inquiry: {o['title']}".replace(" ", "%20")
                body = f"Hello, I am interested in the original work \"{o['title']}\".".replace(" ", "%20").replace('"', "%22")
                cta = (
                    f'<a class="cta" href="mailto:{e(INQUIRY_EMAIL)}'
                    f'?subject={subj}&body={body}">Inquire</a>'
                )
            else:
                cta = ""
            cards += f"""
              <div class="card{sold_cls}">
                <div class="card-img"><img src="{e(o['path'])}" alt="{e(o['title'])}" loading="lazy"></div>
                <div class="card-info">
                  <h3>{e(o['title'])}</h3>
                  <span class="card-size">{e(o['size'])}</span>
                  {badge}
                  {cta}
                </div>
              </div>"""
        return cards

    def render_print_cards(items):
        if not items:
            return '<p class="empty">No prints yet.</p>'
        cards = ""
        for pr in items:
            sold_cls = " sold" if pr["status"] == "sold" else ""
            badge = '<span class="badge sold-badge">Sold</span>' if pr["status"] == "sold" else ""
            if pr["status"] == "available" and pr["payment_link"]:
                cta = f'<a class="cta" href="{e(pr["payment_link"])}" target="_blank" rel="noopener">Buy \u2014 ${pr["price"]}</a>'
            elif pr["status"] == "available":
                cta = f'<span class="cta-price">${pr["price"]}</span>'
            else:
                cta = ""
            cards += f"""
              <div class="card{sold_cls}">
                <div class="card-img"><img src="{e(pr['path'])}" alt="{e(pr['title'])}" loading="lazy"></div>
                <div class="card-info">
                  <h3>{e(pr['title'])}</h3>
                  <span class="card-size">{e(pr['size'])}</span>
                  {badge}
                  {cta}
                </div>
              </div>"""
        return cards

    return Template(TEMPLATE).safe_substitute(
        site_title=e(SITE_TITLE),
        favicon=FAVICON_DATA_URI,
        ig_handle=e(IG_HANDLE),
        biography=(
            "".join(f"<p>{e(p)}</p>" for p in BIOGRAPHY_PARAS)
            + f'<p class="bio-links">Also on Instagram '
              f'<a href="https://instagram.com/{e(SECONDARY_IG)}" target="_blank" rel="noopener">@{e(SECONDARY_IG)}</a></p>'
        ),
        statement=f"<p>{e(STATEMENT_TEXT)}</p>",
        paintings=render_artwork_cards(paintings, "paintings"),
        drawings=render_artwork_cards(drawings, "drawings"),
        prints=render_print_cards(prints),
        year=year,
        email=e(INQUIRY_EMAIL),
        paintings_count=len(paintings),
        drawings_count=len(drawings),
        prints_count=len(prints),
    )


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>$site_title</title>
<link rel="icon" type="image/png" href="$favicon">
<link rel="apple-touch-icon" href="$favicon">
<meta property="og:title" content="$site_title">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400;1,500&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
  :root {
    --cream: #f7f6f3;
    --cream-dark: #eeedea;
    --ink: #1a1815;
    --ink-soft: #5c564c;
    --ink-faint: #a09a90;
    --accent: #1a1815;
    --border: #1a1815;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
  body {
    background: var(--cream);
    color: var(--ink);
    font-family: "EB Garamond", "Times New Roman", serif;
    font-size: 18px;
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }

  .page-frame {
    position: fixed; inset: 0; pointer-events: none; z-index: 100;
    border: 2px solid var(--ink);
    margin: 12px;
  }
  .page-frame::before {
    content: "";
    position: absolute; inset: 4px;
    border: 1px solid rgba(26,24,21,0.25);
  }

  .wrap { max-width: 920px; margin: 0 auto; padding: 80px 48px 64px; }

  nav {
    display: flex; justify-content: center;
    gap: 32px; padding: 24px 0 48px;
    font-family: "Cormorant Garamond", serif;
    font-size: 14px; font-weight: 500;
    letter-spacing: 0.2em; text-transform: uppercase;
  }
  nav a {
    color: var(--ink); text-decoration: none;
    position: relative; padding-bottom: 2px;
  }
  nav a::after {
    content: ""; position: absolute; bottom: 0; left: 0;
    width: 0; height: 1px; background: var(--ink);
    transition: width 0.3s ease;
  }
  nav a:hover::after { width: 100%; }

  .masthead {
    text-align: center; padding: 0 0 48px;
    border-bottom: 1px solid var(--ink);
  }
  .masthead h1 {
    font-family: "Instrument Serif", serif;
    font-weight: 400; font-style: italic;
    font-size: clamp(42px, 8vw, 72px);
    letter-spacing: -0.02em; line-height: 1;
  }
  .masthead-handle {
    display: inline-block; margin-top: 14px;
    font-family: "Cormorant Garamond", serif;
    font-size: 13px; letter-spacing: 0.3em; text-transform: uppercase;
    color: var(--ink-soft); text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: color 0.25s ease, border-color 0.25s ease;
  }
  .masthead-handle:hover { color: var(--ink); border-bottom-color: var(--ink); }
  .shop-note {
    text-align: center; margin: -20px 0 28px;
    font-family: "Cormorant Garamond", serif;
    font-size: 13px; letter-spacing: 0.12em;
    color: var(--ink-soft); font-style: italic;
  }

  .ornament {
    display: flex; align-items: center; justify-content: center;
    gap: 16px; padding: 32px 0;
    color: var(--ink-faint);
  }
  .ornament-line {
    height: 1px; width: 60px;
    background: linear-gradient(90deg, transparent, var(--ink-faint), transparent);
  }

  .about {
    max-width: 620px; margin: 0 auto;
    padding: 0 0 48px; text-align: center;
  }
  .about p {
    font-size: 17px; line-height: 1.75;
    color: var(--ink-soft); margin-bottom: 20px;
    font-style: italic;
  }
  .about p:last-child { margin-bottom: 0; }
  .bio-links {
    font-style: normal !important;
    font-family: "Cormorant Garamond", serif;
    font-size: 13px !important; letter-spacing: 0.15em; text-transform: uppercase;
    margin-top: 28px !important;
  }
  .bio-links a {
    color: var(--ink-soft); text-decoration: none;
    border-bottom: 1px solid rgba(26,24,21,0.3);
  }
  .bio-links a:hover { color: var(--ink); border-bottom-color: var(--ink); }

  .section-title {
    text-align: center; padding: 48px 0 36px;
    border-top: 1px solid var(--ink);
  }
  .section-title h2 {
    font-family: "Instrument Serif", serif;
    font-weight: 400; font-style: italic;
    font-size: clamp(28px, 5vw, 44px);
    letter-spacing: -0.015em;
  }
  .section-title .count {
    font-family: "Cormorant Garamond", serif;
    font-size: 12px; letter-spacing: 0.3em;
    text-transform: uppercase; color: var(--ink-faint);
    margin-top: 4px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 36px 28px;
    padding-bottom: 48px;
  }
  .card {
    display: flex; flex-direction: column;
    transition: transform 0.2s ease;
  }
  .card:hover { transform: translateY(-3px); }
  .card.sold { }
  .card.sold .card-img img {
    filter: blur(3px) saturate(0.3) brightness(1.1);
    transform: scale(1.15);
  }
  .card.sold .card-info { opacity: 0.5; }
  .card-img {
    aspect-ratio: 4 / 5; overflow: hidden;
    border: 1px solid var(--ink);
    background: var(--cream-dark);
  }
  .card-img img {
    width: 100%; height: 100%;
    object-fit: cover; display: block;
    transition: transform 0.4s ease;
  }
  .card:hover .card-img img { transform: scale(1.03); }
  .card-info {
    padding: 14px 0 0;
    display: flex; flex-direction: column; gap: 6px;
  }
  .card-info h3 {
    font-family: "Instrument Serif", serif;
    font-weight: 400; font-style: italic;
    font-size: 22px; letter-spacing: -0.01em;
    line-height: 1.15;
    text-transform: uppercase;
  }
  .card-size {
    font-family: "Cormorant Garamond", serif;
    font-size: 12px; letter-spacing: 0.25em;
    text-transform: uppercase; color: var(--ink-faint);
  }
  .badge {
    font-family: "Cormorant Garamond", serif;
    font-size: 11px; letter-spacing: 0.2em;
    text-transform: uppercase; display: inline-block;
    padding: 2px 10px;
  }
  .sold-badge {
    background: var(--ink); color: var(--cream);
    width: fit-content;
  }
  .cta {
    display: inline-block; width: fit-content;
    font-family: "Cormorant Garamond", serif;
    font-size: 13px; font-weight: 600;
    letter-spacing: 0.2em; text-transform: uppercase;
    color: var(--cream); background: var(--ink);
    text-decoration: none;
    padding: 10px 24px; margin-top: 4px;
    border: 1px solid var(--ink);
    transition: background 0.25s ease, color 0.25s ease;
  }
  .cta:hover { background: transparent; color: var(--ink); }
  .cta-price {
    font-family: "Cormorant Garamond", serif;
    font-size: 15px; font-weight: 500;
    letter-spacing: 0.1em; color: var(--ink-soft);
  }
  .empty {
    grid-column: 1 / -1; text-align: center;
    font-style: italic; color: var(--ink-faint);
    padding: 48px 0;
  }

  footer {
    border-top: 1px solid var(--ink);
    padding: 32px 0 0;
    text-align: center;
    font-family: "Cormorant Garamond", serif;
    font-size: 12px; letter-spacing: 0.25em;
    text-transform: uppercase; color: var(--ink-faint);
    display: flex; flex-direction: column; gap: 8px;
  }
  footer a { color: var(--ink-soft); text-decoration: none; }
  footer a:hover { color: var(--ink); }

  @media (hover: none) {
    .card:hover { transform: none; }
    .card:hover .card-img img { transform: none; }
    nav a::after { display: none; }
  }

  @media (max-width: 768px) {
    .page-frame { margin: 6px; }
    .page-frame::before { inset: 3px; }
    .wrap { padding: 48px 28px 48px; }
    nav { flex-wrap: wrap; gap: 8px 24px; font-size: 12px; padding: 16px 0 28px; }
    nav a { padding: 8px 4px; }
    .masthead { padding: 0 0 32px; }
    .masthead h1 { font-size: clamp(28px, 7vw, 48px); line-height: 1.05; }
    .ornament { padding: 24px 0; }
    .section-title { padding: 28px 0 20px; }
    .section-title h2 { font-size: clamp(24px, 6vw, 36px); }
    .grid { grid-template-columns: 1fr 1fr; gap: 24px 16px; padding-bottom: 32px; }
    .card-img { aspect-ratio: 3 / 4; }
    .card-info { padding: 10px 0 0; gap: 5px; }
    .card-info h3 { font-size: 17px; }
    .card-size { font-size: 11px; }
    .cta { font-size: 11px; padding: 10px 18px; min-height: 44px; display: inline-flex; align-items: center; }
    .about { padding: 0 0 28px; }
    .about p { font-size: 15px; line-height: 1.7; margin-bottom: 16px; }
    footer { padding-top: 24px; margin-top: 28px; gap: 6px; font-size: 11px; }
  }

  @media (max-width: 420px) {
    .page-frame { display: none; }
    .wrap { padding: 24px 20px 40px; }
    nav { gap: 6px 18px; font-size: 11px; padding: 12px 0 24px; }
    .masthead h1 { font-size: clamp(24px, 8vw, 36px); }
    .grid { grid-template-columns: 1fr; gap: 28px; }
    .card-img { aspect-ratio: 4 / 5; }
    .card-info h3 { font-size: 20px; }
    .cta { padding: 12px 20px; font-size: 12px; }
    .about p { font-size: 14px; }
    footer { font-size: 10px; letter-spacing: 0.18em; }
  }
</style>
</head>
<body>

<div class="page-frame"></div>

<div class="wrap">

  <nav>
    <a href="#paintings">Paintings</a>
    <a href="#drawings">Drawings</a>
    <a href="#shop">Shop</a>
    <a href="#biography">Biography</a>
    <a href="#statement">Statement</a>
    <a href="https://instagram.com/$ig_handle" target="_blank" rel="noopener">Instagram</a>
    <a href="mailto:$email">Contact</a>
  </nav>

  <header class="masthead">
    <h1>$site_title</h1>
    <a class="masthead-handle" href="https://instagram.com/$ig_handle" target="_blank" rel="noopener">@$ig_handle</a>
  </header>

  <div class="ornament">
    <div class="ornament-line"></div>
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="0.8">
      <circle cx="9" cy="9" r="7"/>
      <circle cx="9" cy="9" r="3"/>
      <line x1="9" y1="2" x2="9" y2="6"/>
      <line x1="9" y1="12" x2="9" y2="16"/>
      <line x1="2" y1="9" x2="6" y2="9"/>
      <line x1="12" y1="9" x2="16" y2="9"/>
    </svg>
    <div class="ornament-line"></div>
  </div>

  <div class="section-title" id="paintings">
    <h2>Paintings</h2>
    <div class="count">$paintings_count works</div>
  </div>
  <div class="grid">$paintings</div>

  <div class="section-title" id="drawings">
    <h2>Drawings</h2>
    <div class="count">$drawings_count works</div>
  </div>
  <div class="grid">$drawings</div>

  <div class="section-title" id="shop">
    <h2>Shop</h2>
    <div class="count">$prints_count prints</div>
  </div>
  <p class="shop-note">Signed and printed digital scans &middot; shipped worldwide</p>
  <div class="grid">$prints</div>

  <div class="section-title" id="biography">
    <h2>Biography</h2>
  </div>
  <section class="about">$biography</section>

  <div class="section-title" id="statement">
    <h2>Artist Statement</h2>
  </div>
  <section class="about">$statement</section>

  <footer>
    <span><a href="https://instagram.com/$ig_handle">@$ig_handle</a></span>
    <span><a href="mailto:$email">$email</a></span>
    <span>&copy; $year $site_title</span>
  </footer>

</div>

</body>
</html>
"""


if __name__ == "__main__":
    main()
