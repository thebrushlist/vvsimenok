"""
Portfolio site generator.

Reads two image folders and produces a static index.html.

Folder layout
─────────────
  originals/   night-tide_painting_available.jpg
               portrait-of-lena_drawing_sold.jpg

  prints/      night-tide_25_available.jpg
               katoomba-river_18_sold.jpg

Filenames are: name_meta_status.ext
  • originals → name_type_status   (type = painting | drawing)
  • prints    → name_price_status  (price in whole dollars)

Status: "available" or "sold".

Environment variables
─────────────────────
  STRIPE_API_KEY   — Stripe secret key (sk_live_… or sk_test_…) used to
                     create payment links for available prints.

Run:
    STRIPE_API_KEY="sk_test_…" python3 generate.py

Or via GitHub Actions (see .github/workflows/build.yml).
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
ORIGINALS_DIR = Path("originals")
PRINTS_DIR    = Path("prints")
OUTPUT_PATH   = Path("index.html")

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_API     = "https://api.stripe.com"

INQUIRY_EMAIL  = "vvsimenok@hotmail.com"

SITE_TITLE     = "Vladimir Vladislav Simenok"
SITE_SUBTITLE  = ""
IG_HANDLE      = "vovasimenok"

ABOUT_TEXT = (
    "I've been travelling the world the last 2 years, accumulating works "
    "of landscapes, places and people. Using predominantly ink and paint "
    "as my mediums. I aim for work that stretches my creative potential as "
    "much as possible from large murals to smaller more precise works. "
    "I've been selling prints, tattoos and originals on the road and mostly "
    "found opportunities through serendipity, making genuine lasting "
    "connections. I would like to work with artists that are bold and eager "
    "to challenge myself to breaking new boundaries."
)

STATEMENT_TEXT = (
    "The intention of my art is so a point in space can exist in the form "
    "of counsel and entertainment, accessible to the masses, bringing "
    "people together to converse and speculate on its impression. Whilst "
    "simultaneously being a place of the viewer's expression of thoughts "
    "and emotions. At that exact particular point in time. With the goal "
    "to invite you to a complete standstill, pausing oneself from the ever "
    "turning idiosyncratic journey that is life."
)

AMBITION_TEXT = (
    "My ambitions this year are to return home with successfully producing "
    "a collection of paintings from the studies and works I have accrued "
    "from my journey. Which will hopefully fund my ability to rent a studio "
    "to create even more works. During my journey I realised I cannot "
    "sustain travelling and creating art full time, although I have been "
    "successful in recent sales of original works in this year as well as "
    "last, I realise I need to be fixed in a place and be apart of a "
    "community to become much more successful."
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ── helpers ──────────────────────────────────────────────────────────
def title_from_name(raw):
    """night-tide -> Night Tide"""
    return " ".join(w.capitalize() for w in re.split(r"[-_ ]+", raw))


def parse_original(filename):
    stem = Path(filename).stem
    parts = stem.rsplit("_", 2)
    if len(parts) != 3:
        print(f"  ⚠  skipping original (bad name): {filename}")
        return None
    name, kind, status = parts
    kind = kind.lower()
    status = status.lower()
    if kind not in ("painting", "drawing"):
        print(f"  ⚠  skipping original (unknown type '{kind}'): {filename}")
        return None
    if status not in ("available", "sold"):
        print(f"  ⚠  skipping original (unknown status '{status}'): {filename}")
        return None
    return {
        "file": filename,
        "path": f"originals/{filename}",
        "title": title_from_name(name),
        "type": kind.capitalize(),
        "status": status,
    }


def parse_print(filename):
    stem = Path(filename).stem
    parts = stem.rsplit("_", 2)
    if len(parts) != 3:
        print(f"  ⚠  skipping print (bad name): {filename}")
        return None
    name, price_str, status = parts
    status = status.lower()
    try:
        price = int(price_str)
    except ValueError:
        print(f"  ⚠  skipping print (bad price '{price_str}'): {filename}")
        return None
    if status not in ("available", "sold"):
        print(f"  ⚠  skipping print (unknown status '{status}'): {filename}")
        return None
    return {
        "file": filename,
        "path": f"prints/{filename}",
        "title": title_from_name(name),
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


def create_stripe_product(title, price_cents, image_url=None):
    prod_params = {"name": f"Print — {title}"}
    if image_url:
        prod_params["images[0]"] = image_url
    product, err = stripe_request("POST", "products", **prod_params)
    if err:
        print(f"  ⚠  Stripe product error for '{title}': {err}")
        return None
    product_id = product["id"]

    price, err = stripe_request(
        "POST", "prices",
        product=product_id, currency="usd", unit_amount=str(price_cents),
    )
    if err:
        print(f"  ⚠  Stripe price error for '{title}': {err}")
        return None
    price_id = price["id"]

    link, err = stripe_request(
        "POST", "payment_links",
        **{"line_items[0][price]": price_id, "line_items[0][quantity]": "1"},
    )
    if err:
        print(f"  ⚠  Stripe payment-link error for '{title}': {err}")
        return None
    return link.get("url")


# ── main ─────────────────────────────────────────────────────────────
def main():
    originals = []
    if ORIGINALS_DIR.exists():
        for p in sorted(ORIGINALS_DIR.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                parsed = parse_original(p.name)
                if parsed:
                    originals.append(parsed)
    print(f"Originals: {len(originals)}")

    prints = []
    if PRINTS_DIR.exists():
        for p in sorted(PRINTS_DIR.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                parsed = parse_print(p.name)
                if parsed:
                    prints.append(parsed)
    print(f"Prints: {len(prints)}")

    if STRIPE_API_KEY:
        for pr in prints:
            if pr["status"] == "available":
                print(f"  → creating Stripe link for '{pr['title']}' (${pr['price']})…")
                url = create_stripe_product(pr["title"], pr["price"] * 100)
                if url:
                    pr["payment_link"] = url
                    print(f"    ✓ {url}")
    else:
        print("No STRIPE_API_KEY — skipping payment link creation.")

    html_out = render(originals, prints)
    OUTPUT_PATH.write_text(html_out, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html_out):,} bytes)")


# ── HTML rendering ───────────────────────────────────────────────────
def render(originals, prints):
    e = html.escape
    now = dt.datetime.now(dt.timezone.utc)
    year = now.strftime("%Y")

    # ── originals cards ──
    originals_html = ""
    if not originals:
        originals_html = '<p class="empty">No originals yet.</p>'
    else:
        for o in originals:
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
            originals_html += f"""
              <div class="card{sold_cls}">
                <div class="card-img"><img src="{e(o['path'])}" alt="{e(o['title'])}" loading="lazy"></div>
                <div class="card-info">
                  <h3>{e(o['title'])}</h3>
                  <span class="card-type">{e(o['type'])}</span>
                  {badge}
                  {cta}
                </div>
              </div>"""

    # ── prints cards ──
    prints_html = ""
    if not prints:
        prints_html = '<p class="empty">No prints yet.</p>'
    else:
        for pr in prints:
            sold_cls = " sold" if pr["status"] == "sold" else ""
            badge = '<span class="badge sold-badge">Sold</span>' if pr["status"] == "sold" else ""
            if pr["status"] == "available" and pr["payment_link"]:
                cta = f'<a class="cta" href="{e(pr["payment_link"])}" target="_blank" rel="noopener">Buy — ${pr["price"]}</a>'
            elif pr["status"] == "available":
                cta = f'<span class="cta-price">${pr["price"]}</span>'
            else:
                cta = ""
            prints_html += f"""
              <div class="card{sold_cls}">
                <div class="card-img"><img src="{e(pr['path'])}" alt="{e(pr['title'])}" loading="lazy"></div>
                <div class="card-info">
                  <h3>{e(pr['title'])}</h3>
                  {badge}
                  {cta}
                </div>
              </div>"""

    return Template(TEMPLATE).safe_substitute(
        site_title=e(SITE_TITLE),
        site_subtitle=e(SITE_SUBTITLE),
        ig_handle=e(IG_HANDLE),
        about=e(ABOUT_TEXT),
        statement=e(STATEMENT_TEXT),
        ambition=e(AMBITION_TEXT),
        originals=originals_html,
        prints=prints_html,
        year=year,
        email=e(INQUIRY_EMAIL),
        originals_count=len(originals),
        prints_count=len(prints),
    )


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>$site_title</title>
<meta property="og:title" content="$site_title">
<meta property="og:description" content="$site_subtitle">
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

  /* ─── ornamental border frame ─── */
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

  /* ─── nav ─── */
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

  /* ─── masthead ─── */
  .masthead {
    text-align: center; padding: 0 0 48px;
    border-bottom: 1px solid var(--ink);
  }
  .masthead h1 {
    font-family: "Instrument Serif", serif;
    font-weight: 400; font-style: italic;
    font-size: clamp(42px, 8vw, 72px);
    letter-spacing: -0.02em; line-height: 1;
    margin-bottom: 8px;
  }
  .masthead .subtitle {
    font-family: "Cormorant Garamond", serif;
    font-size: 13px; font-weight: 400;
    letter-spacing: 0.35em; text-transform: uppercase;
    color: var(--ink-soft);
  }

  /* ─── ornamental divider ─── */
  .ornament {
    display: flex; align-items: center; justify-content: center;
    gap: 16px; padding: 32px 0;
    color: var(--ink-faint);
  }
  .ornament-line {
    height: 1px; width: 60px;
    background: linear-gradient(90deg, transparent, var(--ink-faint), transparent);
  }

  /* ─── about ─── */
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

  /* ─── section headings ─── */
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

  /* ─── card grid ─── */
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
  .card.sold { opacity: 0.55; }
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
  }
  .card-type {
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

  /* ─── footer ─── */
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

  /* ─── touch devices: disable hover lift ─── */
  @media (hover: none) {
    .card:hover { transform: none; }
    .card:hover .card-img img { transform: none; }
    nav a::after { display: none; }
  }

  @media (max-width: 768px) {
    .page-frame { margin: 6px; }
    .page-frame::before { inset: 3px; }
    .wrap { padding: 48px 28px 48px; }

    nav {
      flex-wrap: wrap; justify-content: center;
      gap: 8px 24px; font-size: 12px;
      padding: 16px 0 28px;
    }
    nav a { padding: 8px 4px; }

    .masthead { padding: 0 0 32px; }
    .masthead h1 {
      font-size: clamp(28px, 7vw, 48px);
      line-height: 1.05;
    }

    .ornament { padding: 24px 0; }

    .section-title { padding: 28px 0 20px; }
    .section-title h2 { font-size: clamp(24px, 6vw, 36px); }

    .grid {
      grid-template-columns: 1fr 1fr;
      gap: 24px 16px; padding-bottom: 32px;
    }
    .card-img { aspect-ratio: 3 / 4; }
    .card-info { padding: 10px 0 0; gap: 5px; }
    .card-info h3 { font-size: 17px; }
    .card-type { font-size: 11px; }

    .cta {
      font-size: 11px; padding: 10px 18px;
      min-height: 44px;
      display: inline-flex; align-items: center;
    }

    .about { padding: 0 0 28px; }
    .about p { font-size: 15px; line-height: 1.7; margin-bottom: 16px; }

    footer {
      padding-top: 24px; margin-top: 28px;
      gap: 6px; font-size: 11px;
    }
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
    <a href="#originals">Originals</a>
    <a href="#prints">Prints</a>
    <a href="#about">About</a>
    <a href="mailto:$email">Contact</a>
  </nav>

  <header class="masthead">
    <h1>$site_title</h1>
  </header>

  <div class="section-title" id="originals">
    <h2>Originals</h2>
    <div class="count">$originals_count works</div>
  </div>
  <div class="grid">$originals</div>

  <div class="section-title" id="prints">
    <h2>Prints</h2>
    <div class="count">$prints_count editions</div>
  </div>
  <div class="grid">$prints</div>

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

  <section class="about" id="about">
    <p>$about</p>
    <p>$statement</p>
    <p>$ambition</p>
  </section>

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
