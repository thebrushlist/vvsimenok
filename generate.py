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
IG_HANDLE      = "vovasimenok"

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
        ig_handle=e(IG_HANDLE),
        biography="".join(f"<p>{e(p)}</p>" for p in BIOGRAPHY_PARAS),
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
