#!/usr/bin/env python3
"""
Grokipedia News Fetcher — Playwright version
Bruger headless Chromium til at hente JavaScript-rendered indhold fra Grokipedia.
"""

import re
import sys
import time
import html2text
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from deep_translator import GoogleTranslator

URL = "https://grokipedia.com/page/PortalCurrent_events"

CATEGORIES = [
    ("Armed",       "⚔️",  "#dc2626", "Konflikter"),
    ("Politics",    "🏛️",  "#7c3aed", "Politik"),
    ("Economy",     "📈",  "#059669", "Økonomi"),
    ("Disasters",   "⚠️",  "#d97706", "Katastrofer"),
    ("Science",     "🔬",  "#0284c7", "Videnskab"),
    ("Health",      "🏥",  "#0891b2", "Sundhed"),
    ("Technology",  "💻",  "#6366f1", "Teknologi"),
    ("Sports",      "⚽",  "#16a34a", "Sport"),
    ("Environment", "🌍",  "#15803d", "Miljø"),
    ("Law",         "⚖️",  "#be123c", "Lov & Orden"),
]

STOP_WORDS = [
    "references", "table of contents", "sign in to contribute",
    "suggest an article", "something went wrong", "thank you",
]


def get_cat_info(title):
    for key, icon, color, label in CATEGORIES:
        if key.lower() in title.lower():
            return icon, color, label
    return "📌", "#6b7280", title


def fetch_html():
    """Henter siden med Playwright (kører JavaScript fuldt ud)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        print(f"Åbner {URL} ...")
        page.goto(URL, wait_until="networkidle", timeout=60000)

        # Vent på at overskrifter er indlæst
        try:
            page.wait_for_selector("h2", timeout=15000)
        except Exception:
            print("Advarsel: Timeout ved h2-selektor — fortsætter alligevel")

        html = page.content()
        browser.close()
        print(f"Hentet {len(html)} bytes HTML")
        return html


def html_to_markdown(html):
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    h.unicode_snob = True
    return h.handle(html)


def parse_sections(md_text):
    sections = []
    cur_section = None
    cur_sub = None
    buf = []
    in_stop = False

    def flush():
        nonlocal buf
        text = " ".join(buf).strip()
        text = re.sub(r"\[\d+\]", "", text)
        text = re.sub(r"\s{2,}", " ", text)
        buf = []
        return text if len(text) > 30 else ""

    for raw_line in md_text.split("\n"):
        line = raw_line.strip()

        # Stop KUN ved h2-overskrifter der matcher stopord — ikke TOC-bullet-linjer
        if line.startswith("## ") and any(s in line.lower() for s in STOP_WORDS):
            in_stop = True
        if in_stop:
            continue

        if line.startswith("## "):
            title = line[3:].strip()
            if cur_section:
                text = flush()
                if text and cur_sub:
                    cur_section["subsections"].append({"title": cur_sub, "text": text})
                if cur_section["subsections"]:
                    sections.append(cur_section)
            cur_section = {"title": title, "subsections": []}
            cur_sub = None
            buf = []
            continue

        if line.startswith("### ") and cur_section:
            text = flush()
            if text and cur_sub:
                cur_section["subsections"].append({"title": cur_sub, "text": text})
            cur_sub = line[4:].strip()
            continue

        # Spring navigation, TOC-bullets og tomme linjer over
        if not line or line.startswith("#"):
            continue
        if re.match(r"^\*\*.*\*\*$", line):
            continue
        if line.startswith("* ") or line.startswith("- "):
            continue

        if cur_section and cur_sub and len(line) > 15:
            buf.append(line)

    if cur_section:
        text = flush()
        if text and cur_sub:
            cur_section["subsections"].append({"title": cur_sub, "text": text})
        if cur_section["subsections"]:
            sections.append(cur_section)

    return sections


def truncate(text, max_len=350):
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def build_html(sections, updated_at):
    total_arts = sum(len(s["subsections"]) for s in sections)
    updated_str = updated_at.strftime("%-d. %B %Y kl. %H:%M UTC")

    pills_html = ""
    for s in sections:
        icon, color, label = get_cat_info(s["title"])
        safe_id = re.sub(r"\W+", "-", s["title"])
        pills_html += (
            f'<span class="cat-pill" style="background:{color}" '
            f'onclick="document.getElementById(\'sec-{safe_id}\').scrollIntoView({{behavior:\'smooth\'}})">'
            f'{icon} {label}</span>'
        )

    cards_html = ""
    for s in sections:
        icon, color, label = get_cat_info(s["title"])
        safe_id = re.sub(r"\W+", "-", s["title"])
        arts_html = ""
        for sub in s["subsections"]:
            short = truncate(sub["text"])
            full_esc = sub["text"].replace("'", "&#39;").replace('"', "&quot;")
            show_more = short != sub["text"]
            arts_html += f"""
            <div class="article-item">
              <div class="article-sub">
                <span class="dot" style="background:{color}"></span>
                {sub['title']}
              </div>
              <p class="article-text">{short}</p>
              {'<span class="readmore" onclick="toggleRead(this,\'' + full_esc + '\')">Læs mere</span>' if show_more else ''}
            </div>"""

        cards_html += f"""
        <div class="section-card" id="sec-{safe_id}" style="border-top:3px solid {color}">
          <div class="section-header" onclick="toggleCard(this)">
            <span class="sec-icon">{icon}</span>
            <span class="sec-title">{s['title']}</span>
            <span class="sec-count">{len(s['subsections'])}</span>
            <span class="toggle-arrow">▼</span>
          </div>
          <div class="section-body">{arts_html}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="10800">
<title>Grokipedia Nyheder</title>
<style>
:root{{color-scheme:light;--bg:#f4f6f9;--surface:#fff;--surface2:#f0f2f5;--border:#e2e6ea;--text:#1a1d23;--text2:#4b5563;--text3:#9ca3af;--r:10px;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.6;}}
header{{background:#fff;border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;position:sticky;top:0;z-index:100;}}
.logo{{display:flex;align-items:center;gap:8px;font-weight:700;font-size:16px;}}
.logo-badge{{background:#1e40af;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;}}
.meta{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
.chip{{background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:4px 12px;font-size:12px;color:var(--text2);}}
.source-link{{font-size:12px;color:#1e40af;text-decoration:none;}}
.source-link:hover{{text-decoration:underline;}}
main{{max-width:960px;margin:0 auto;padding:20px 16px 40px;}}
.summary-bar{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:10px 16px;margin-bottom:20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px;color:var(--text2);}}
.cat-pills{{display:flex;gap:6px;flex-wrap:wrap;}}
.cat-pill{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;color:#fff;cursor:pointer;transition:opacity .15s;}}
.cat-pill:hover{{opacity:.8;}}
#news{{display:flex;flex-direction:column;gap:20px;}}
.section-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.07);}}
.section-header{{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;}}
.section-header:hover{{background:var(--surface2);}}
.sec-icon{{font-size:18px;flex-shrink:0;}}
.sec-title{{font-weight:700;font-size:14px;flex:1;}}
.sec-count{{background:var(--surface2);color:var(--text2);font-size:11px;font-weight:600;padding:2px 7px;border-radius:10px;}}
.toggle-arrow{{color:var(--text3);font-size:12px;transition:transform .2s;}}
.section-body{{padding:4px 0;}}
.article-item{{padding:10px 16px;border-bottom:1px solid var(--border);}}
.article-item:last-child{{border-bottom:none;}}
.article-item:hover{{background:var(--surface2);}}
.article-sub{{font-weight:600;font-size:13px;margin-bottom:4px;display:flex;align-items:center;gap:6px;}}
.dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0;}}
.article-text{{font-size:12.5px;color:var(--text2);line-height:1.55;}}
.readmore{{font-size:11px;color:#1e40af;cursor:pointer;margin-top:3px;display:inline-block;}}
.readmore:hover{{text-decoration:underline;}}
footer{{text-align:center;color:var(--text3);font-size:11px;padding:24px;border-top:1px solid var(--border);margin-top:20px;}}
footer a{{color:#1e40af;text-decoration:none;}}
</style>
</head>
<body>
<header>
  <div class="logo">🌐 Grokipedia Nyheder <span class="logo-badge">Auto</span></div>
  <div class="meta">
    <span class="chip">🕒 {updated_str}</span>
    <span class="chip">📰 {total_arts} historier · {len(sections)} kategorier</span>
    <a class="source-link" href="{URL}" target="_blank">↗ Kilde</a>
  </div>
</header>
<main>
  <div class="summary-bar">
    <span>Hop til:</span>
    <div class="cat-pills">{pills_html}</div>
  </div>
  <div id="news">{cards_html}</div>
</main>
<footer>
  Data fra <a href="{URL}" target="_blank">Grokipedia Portal: Current Events</a>
  &nbsp;·&nbsp; Opdateres automatisk via GitHub Actions hver 3. time &nbsp;·&nbsp; {updated_str}
</footer>
<script>
function toggleCard(hdr){{var b=hdr.nextElementSibling,a=hdr.querySelector('.toggle-arrow'),o=b.style.display!=='none';b.style.display=o?'none':'block';a.style.transform=o?'rotate(-90deg)':'';}}
function toggleRead(el,full){{var p=el.previousElementSibling;if(el.dataset.exp){{p.textContent=p.dataset.s;el.textContent='Læs mere';delete el.dataset.exp;}}else{{p.dataset.s=p.textContent;p.textContent=full;el.textContent='Vis mindre';el.dataset.exp=1;}}}}
</script>
</body>
</html>"""


def translate_sections(sections):
    """Oversætter alle artikel-titler og tekster til dansk via Google Translate."""
    print("Oversætter indhold til dansk...")
    translator = GoogleTranslator(source="auto", target="da")
    total = sum(len(s["subsections"]) for s in sections)
    count = 0

    for section in sections:
        for sub in section["subsections"]:
            count += 1
            print(f"  [{count}/{total}] {sub['title'][:50]}")
            try:
                sub["title"] = translator.translate(sub["title"]) or sub["title"]
                time.sleep(0.2)
                # Google Translate maks 5000 tegn pr. kald
                text = sub["text"]
                if len(text) <= 4999:
                    sub["text"] = translator.translate(text) or text
                else:
                    # Opdel i to halvdele ved nærmeste mellemrum
                    mid = text.rfind(" ", 0, 4999)
                    part1 = translator.translate(text[:mid]) or text[:mid]
                    time.sleep(0.2)
                    part2 = translator.translate(text[mid:].strip()) or text[mid:].strip()
                    sub["text"] = part1 + " " + part2
                time.sleep(0.2)
            except Exception as e:
                print(f"    Oversættelsesfejl (beholder original): {e}")

    print(f"Oversættelse færdig.")
    return sections


def main():
    print("Starter Playwright og henter Grokipedia...")
    try:
        html = fetch_html()
    except Exception as e:
        print(f"FEJL ved hentning: {e}", file=sys.stderr)
        sys.exit(1)

    print("Konverterer HTML → markdown...")
    md_text = html_to_markdown(html)

    # Debug: vis første 800 tegn
    print("--- Første 800 tegn ---")
    print(md_text[:800])
    print("---")

    print("Parser sektioner...")
    sections = parse_sections(md_text)

    if not sections:
        print("FEJL: Ingen sektioner fundet. Udskriver 3000 tegn til fejlsøgning:")
        print(md_text[:3000])
        sys.exit(1)

    total = sum(len(s["subsections"]) for s in sections)
    print(f"Fandt {len(sections)} kategorier med {total} historier:")
    for s in sections:
        print(f"  · {s['title']}: {len(s['subsections'])} artikler")

    sections = translate_sections(sections)
    updated_at = datetime.now(timezone.utc)
    output = build_html(sections, updated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)
    print("✓ index.html genereret og gemt.")


if __name__ == "__main__":
    main()
