#!/usr/bin/env python3
"""
bosnien.dk - automatisk nyhedsopdatering
Henter nyheder fra RSS-feeds om Bosnien-Hercegovina, kategoriserer dem,
og bygger en statisk index.html side i /docs, som GitHub Pages viser.

Kør automatisk af .github/workflows/update-site.yml (GitHub Actions).
"""

import feedparser
import html
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import mktime
from urllib.parse import quote
from deep_translator import GoogleTranslator

# Cache så vi ikke oversætter den samme overskrift flere gange i én kørsel
_translation_cache = {}


def translate_to_danish(text):
    """Oversætter en overskrift til dansk. Falder tilbage til originalteksten
    hvis oversættelsen fejler (fx midlertidig netværksfejl)."""
    if not text:
        return text
    if text in _translation_cache:
        return _translation_cache[text]
    try:
        translated = GoogleTranslator(source="auto", target="da").translate(text)
        result = translated or text
    except Exception as e:
        print(f"  Oversættelse fejlede for '{text[:50]}...': {e}")
        result = text
    _translation_cache[text] = result
    # lille pause for at være pæn ved oversættelsestjenesten
    time.sleep(0.3)
    return result

# ---------------------------------------------------------------------------
# 1) KILDER - RSS-feeds grupperet i kategorier.
#    De fleste bruger Google News RSS, som er meget stabilt og altid virker
#    for et givet søgeord/sprog. Der er også et par direkte site-feeds.
#    Du kan sagtens tilføje/fjerne linjer her uden at røre resten af koden.
# ---------------------------------------------------------------------------

def google_news(query, hl, gl):
    q = quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"

CATEGORIES = {
    "sport": {
        "title": "⚽ Sport",
        "feeds": [
            google_news("Bosna i Hercegovina fudbal reprezentacija", "bs", "BA"),
            google_news("Bosnia and Herzegovina football", "en", "US"),
            google_news("Bosnien fodbold", "da", "DK"),
        ],
    },
    "politik": {
        "title": "🏛️ Politik",
        "feeds": [
            google_news("Bosna i Hercegovina politika", "bs", "BA"),
            google_news("Bosnia and Herzegovina politics", "en", "US"),
        ],
    },
    "turisme_rejser": {
        "title": "✈️ Turisme og rejser",
        "feeds": [
            google_news("Bosna i Hercegovina turizam", "bs", "BA"),
            google_news("Bosnia Herzegovina tourism travel", "en", "US"),
        ],
    },
    "folk_kultur": {
        "title": "🎭 Folk og kultur",
        "feeds": [
            google_news("Bosna i Hercegovina poznate licnosti kultura", "bs", "BA"),
            google_news("Bosnian culture people", "en", "US"),
        ],
    },
    "bosnien_i_danmark": {
        "title": "🇩🇰 Bosnien i Danmark",
        "feeds": [
            google_news("Bosnien", "da", "DK"),
            google_news("bosnisk Danmark", "da", "DK"),
        ],
    },
    "generelle_nyheder": {
        "title": "📰 Generelle nyheder",
        "feeds": [
            "https://www.klix.ba/rss",
            google_news("Bosna i Hercegovina", "bs", "BA"),
        ],
    },
}

MAX_ITEMS_PER_CATEGORY = 10
MAX_AGE_DAYS = 14  # ignorer artikler ældre end dette

# Ord der skal optræde i overskriften, for at artiklen regnes som relevant.
# Dette luger ud i "falske positive" fra brede søgninger (fx artikler der kun
# tilfældigt matcher søgeordene uden reelt at handle om Bosnien-Hercegovina).
RELEVANCE_KEYWORDS = [
    "bosni", "hercegovin", "herzegovin", "sarajevo", "mostar",
    "banja luka", "tuzla", "zenica", "brčko", "brcko",
    "republika srpska", "bosanac", "bosanka", "bosanski", "bosnisk",
]


def is_relevant(title):
    if not title:
        return False
    lowered = title.lower()
    return any(keyword in lowered for keyword in RELEVANCE_KEYWORDS)


IMG_TAG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
IMG_TAG_RE_REVERSED = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.IGNORECASE,
)


def fetch_article_image(url, timeout=8):
    """Henter forsidebilledet (og:image) fra selve artikelsiden.
    Returnerer None hvis der ikke findes et billede, eller siden ikke kan hentes
    (fx pga. netværksfejl, timeout eller blokering) - siden vises da uden billede."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; bosnien-dk-bot/1.0; +https://bosnien.dk)"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return None
        chunk = resp.text[:200000]  # kun starten af siden er nødvendig
        match = IMG_TAG_RE.search(chunk) or IMG_TAG_RE_REVERSED.search(chunk)
        if match:
            img = match.group(1).strip()
            if img.startswith("//"):
                img = "https:" + img
            return img
    except Exception as e:
        print(f"  Kunne ikke hente billede fra {url}: {e}")
    return None


def attach_images(items, max_workers=8):
    """Henter billeder til en liste af artikler parallelt, for at gøre det hurtigere."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(fetch_article_image, it["link"]): it for it in items}
        for future in as_completed(future_map):
            it = future_map[future]
            it["image"] = future.result()
    return items

# ---------------------------------------------------------------------------
# 2) HENT OG PARSE
# ---------------------------------------------------------------------------

def parse_entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return datetime.fromtimestamp(mktime(val), tz=timezone.utc)
    return None


def clean_title(title):
    title = html.unescape(title or "")
    title = re.sub(r"\s+-\s+[^-]+$", "", title)  # fjern " - Kildenavn" i slutningen
    return title.strip()


def fetch_category(feeds):
    seen_links = set()
    items = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"  Fejl ved hentning af {url}: {e}")
            continue
        for entry in parsed.entries:
            link = entry.get("link")
            if not link or link in seen_links:
                continue
            original_title = clean_title(entry.get("title", ""))
            if not is_relevant(original_title):
                continue
            seen_links.add(link)
            dt = parse_entry_date(entry)
            if dt and (datetime.now(timezone.utc) - dt).days > MAX_AGE_DAYS:
                continue
            source = ""
            if "source" in entry and hasattr(entry.source, "title"):
                source = entry.source.title
            items.append({
                "title": translate_to_danish(original_title),
                "original_title": original_title,
                "link": link,
                "date": dt,
                "source": source,
            })
    items.sort(key=lambda x: x["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    items = items[:MAX_ITEMS_PER_CATEGORY]
    attach_images(items)
    return items


# ---------------------------------------------------------------------------
# 3) BYG HTML
# ---------------------------------------------------------------------------

def format_date(dt):
    if not dt:
        return ""
    return dt.strftime("%d.%m.%Y")


def render_category(key, cat, items):
    if not items:
        cards = '<p class="empty">Ingen nye artikler lige nu.</p>'
    else:
        cards = "\n".join(
            f'''<li class="item">
  {'<img class="thumb" src="' + html.escape(it["image"]) + '" alt="" loading="lazy">' if it.get("image") else '<div class="thumb thumb-empty" aria-hidden="true">🇧🇦</div>'}
  <div class="item-content">
    <a href="{html.escape(it["link"])}" target="_blank" rel="noopener noreferrer" title="{html.escape(it.get("original_title") or "")}">{html.escape(it["title"])}</a>
    <div class="meta">{html.escape(it["source"]) if it["source"] else ""}{" · " if it["source"] else ""}{format_date(it["date"])}</div>
  </div>
</li>'''
            for it in items
        )
        cards = f'<ul class="item-list">\n{cards}\n</ul>'
    return f'''<section class="category" id="{key}">
  <h2>{cat["title"]}</h2>
  {cards}
</section>'''


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>bosnien.dk - Alt om Bosnien-Hercegovina</title>
<meta name="description" content="Aktuel information om Bosnien-Hercegovina: sport, politik, turisme, rejser, folk og kultur, samt bosnisk-danske nyheder. Opdateres automatisk.">
<style>
  :root {{
    --bg: #0a1e5c;
    --card: #0f2a7a;
    --accent: #fecb00;
    --accent2: #002395;
    --text: #ffffff;
    --muted: #a8bce8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }}
  header {{
    background: linear-gradient(135deg, var(--accent2), #0a1e5c);
    padding: 2.5rem 1.5rem 2rem;
    text-align: center;
    border-bottom: 5px solid var(--accent);
    position: relative;
    overflow: hidden;
  }}
  header::after {{
    content: "";
    position: absolute;
    top: -40%;
    right: -10%;
    width: 260px;
    height: 260px;
    background: var(--accent);
    clip-path: polygon(0 0, 100% 0, 0 100%);
    opacity: 0.9;
  }}
  header h1 {{
    margin: 0 0 .4rem;
    font-size: 2.2rem;
    letter-spacing: -0.02em;
    position: relative;
  }}
  header p {{
    margin: 0;
    color: #dce6fa;
    font-size: 1rem;
    position: relative;
  }}
  nav {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: .5rem;
    padding: 1rem;
    background: #081a4d;
    position: sticky;
    top: 0;
    z-index: 10;
  }}
  nav a {{
    color: var(--text);
    text-decoration: none;
    background: var(--card);
    padding: .4rem .9rem;
    border-radius: 999px;
    font-size: .85rem;
    border: 1px solid #1b3a8f;
  }}
  nav a:hover {{ border-color: var(--accent); }}
  main {{
    max-width: 900px;
    margin: 0 auto;
    padding: 1.5rem 1rem 3rem;
    display: grid;
    gap: 1.5rem;
  }}
  .category {{
    background: var(--card);
    border: 1px solid #1b3a8f;
    border-top: 3px solid var(--accent);
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
  }}
  .category h2 {{
    margin-top: 0;
    font-size: 1.25rem;
    color: #ffffff;
  }}
  .item-list {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: .85rem;
  }}
  .item {{
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }}
  .thumb {{
    width: 84px;
    height: 84px;
    flex-shrink: 0;
    border-radius: 8px;
    object-fit: cover;
    background: var(--bg);
  }}
  .thumb-empty {{
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    border: 1px solid #1b3a8f;
  }}
  .item-content {{
    min-width: 0;
  }}
  .item a {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }}
  .item a:hover {{ text-decoration: underline; }}
  .meta {{
    color: var(--muted);
    font-size: .8rem;
    margin-top: .15rem;
  }}
  .empty {{ color: var(--muted); font-style: italic; }}
  footer {{
    text-align: center;
    color: var(--muted);
    font-size: .8rem;
    padding: 2rem 1rem 3rem;
  }}
</style>
</head>
<body>
<header>
  <h1>🇧🇦 bosnien.dk</h1>
  <p>Alt vigtigt om Bosnien-Hercegovina – sport, politik, turisme, rejser, folk og bosnisk-danske nyheder</p>
</header>
<nav>
  {nav_links}
</nav>
<main>
  {sections}
</main>
<footer>
  Siden opdateres automatisk flere gange dagligt fra offentlige nyhedskilder.<br>
  Overskrifter oversættes automatisk til dansk (hold musen over en overskrift for at se originalsproget).<br>
  Sidst opdateret: {updated}
</footer>
</body>
</html>
"""


def build_site():
    sections_html = []
    nav_links = []
    for key, cat in CATEGORIES.items():
        print(f"Henter kategori: {cat['title']}")
        items = fetch_category(cat["feeds"])
        sections_html.append(render_category(key, cat, items))
        nav_links.append(f'<a href="#{key}">{cat["title"]}</a>')

    updated = datetime.now(timezone.utc).strftime("%d.%m.%Y kl. %H:%M UTC")
    page = PAGE_TEMPLATE.format(
        nav_links="\n  ".join(nav_links),
        sections="\n  ".join(sections_html),
        updated=updated,
    )
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("docs/index.html er opdateret.")


if __name__ == "__main__":
    build_site()
