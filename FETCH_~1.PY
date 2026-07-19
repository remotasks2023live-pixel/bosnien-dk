#!/usr/bin/env python3
"""
Grokipedia News Fetcher
Henter Portal:Current Events fra Grokipedia og genererer index.html
"""

import re
import sys
import json
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

URL = "https://grokipedia.com/page/PortalCurrent_events"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da,en-US;q=0.9,en;q=0.8",
}

STOP_SECTIONS = {
    "References", "Table of Contents", "Sign in to contribute",
    "Suggest an article", "Something went wrong", "Thank you"
}

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

def get_cat_info(title):
    for key, icon, color, label in CATEGORIES:
        if key.lower() in title.lower():
            return icon, color, label
    return "📌", "#6b7280", title


def fetch_page():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_sections(html):
    soup = BeautifulSoup(html, "lxml")

    # Remove nav, footer, script, style noise
    for tag in soup(["script", "style", "nav", "footer", "button", "form"]):
        tag.decompose()

    # Find article body — try common containers first
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", id=re.compile(r"content|article|body", re.I))
        or soup.body
    )

    sections = []
    cur_section = None
    cur_sub = None
    cur_texts = []

    def flush_sub():
        nonlocal cur_texts
        if cur_sub and cur_texts:
            combined = " ".join(cur_texts).strip()
            combined = re.sub(r"\[\d+\]", "", combined)   # strip [1],[2]...
            combined = re.sub(r"\s{2,}", " ", combined)
            if len(combined) > 30:
                cur_section["subsections"].append({"title": cur_sub, "text": combined})
        cur_texts = []

    for tag in body.find_all(["h2", "h3", "p"]):
        text = tag.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue

        if tag.name == "h2":
            if any(s.lower() in text.lower() for s in STOP_SECTIONS):
                break
            if cur_section:
                flush_sub()
                if cur_section["subsections"]:
                    sections.append(cur_section)
            cur_section = {"title": text, "subsections": []}
            cur_sub = None
            cur_texts = []

        elif tag.name == "h3" and cur_section:
            flush_sub()
            cur_sub = text

        elif tag.name == "p" and cur_section and cur_sub:
            clean = re.sub(r"\[\d+\]", "", text)
            clean = clean.strip()
            if len(clean) > 20:
                cur_texts.append(clean)

    if cur_section:
        flush_sub()
        if cur_section["subsections"]:
            sections.append(cur_section)

    return sections


def truncate(text, max_len=350):
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def build_html(sections, updated_at):
    total_arts = sum(len(s["subsections"]) for s in sections)

    # Category pills
    pills_html = ""
    for s in sections:
        icon, color, label = get_cat_info(s["title"])
        safe_id = re.sub(r"\W+", "-", s["title"])
        pills_html += (
            f'<span class="cat-pill" style="background:{color}" '
            f'onclick="document.getElementById(\'sec-{safe_id}\').scrollIntoView({{behavior:\'smooth\'}})">'
            f'{icon} {label}</span>'
        )

    # Section cards
    cards_html = ""
    for s in sections:
        icon, color, label = get_cat_info(s["title"])
        safe_id = re.sub(r"\W+", "-", s["title"])
        arts_html = ""
        for sub in s["subsections"]:
            short = truncate(sub["text"])
            full_escaped = sub["text"].replace("'", "&#39;").replace('"', "&quot;")
            is_truncated = short != sub["text"]
            arts_html += f"""
            <div class="article-item">
              <div class="article-sub">
                <span class="dot" style="background:{color}"></span>
                {sub['title']}
              </div>
              <p class="article-text" id="txt-{id(sub)}">{short}</p>
              {'<span class="readmore" onclick="toggleRead(this,\'' + full_escaped + '\')">Læs mere</span>' if is_truncated else ''}
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

    updated_str = updated_at.strftime("%-d. %B %Y kl. %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="10800">
<title>Grokipedia Nyheder</title>
<style>
:root {{color-scheme:light;--bg:#f4f6f9;--surface:#fff;--surface2:#f0f2f5;--border:#e2e6ea;--text:#1a1d23;--text2:#4b5563;--text3:#9ca3af;--accent:#1e40af;--r:10px;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.6;}}
header{{background:#fff;border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;position:sticky;top:0;z-index:100;}}
.logo{{display:flex;align-items:center;gap:8px;font-weight:700;font-size:16px;}}
.logo-badge{{background:#1e40af;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:.5px;}}
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
.article-item{{padding:10px 16px;border-bottom:1px solid var(--border);transition:background .1s;}}
.article-item:last-child{{border-bottom:none;}}
.article-item:hover{{background:var(--surface2);}}
.article-sub{{font-weight:600;font-size:13px;margin-bottom:4px;display:flex;align-items:center;gap:6px;}}
.dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0;}}
.article-text{{font-size:12.5px;color:var(--text2);line-height:1.55;}}
.readmore{{font-size:11px;color:#1e40af;cursor:pointer;margin-top:3px;display:inline-block;}}
.readmore:hover{{text-decoration:underline;}}
footer{{text-align:center;color:var(--text3);font-size:11px;padding:24px;border-top:1px solid var(--border);}}
footer a{{color:#1e40af;text-decoration:none;}}
footer a:hover{{text-decoration:underline;}}
</style>
</head>
<body>
<header>
  <div class="logo">
    🌐 Grokipedia Nyheder
    <span class="logo-badge">Auto</span>
  </div>
  <div class="meta">
    <span class="chip">🕒 Opdateret: {updated_str}</span>
    <span class="chip">📰 {total_arts} historier i {len(sections)} kategorier</span>
    <a class="source-link" href="{URL}" target="_blank">↗ Kilde</a>
  </div>
</header>

<main>
  <div class="summary-bar">
    <span>Hop til kategori:</span>
    <div class="cat-pills">{pills_html}</div>
  </div>
  <div id="news">{cards_html}</div>
</main>

<footer>
  Data fra <a href="{URL}" target="_blank">Grokipedia Portal: Current Events</a>
  &nbsp;·&nbsp; Siden opdateres automatisk via GitHub Actions hver 3. time
  &nbsp;·&nbsp; Sidst hentet: {updated_str}
</footer>

<script>
function toggleCard(hdr) {{
  const body = hdr.nextElementSibling;
  const arr = hdr.querySelector('.toggle-arrow');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  arr.style.transform = open ? 'rotate(-90deg)' : '';
}}
function toggleRead(el, full) {{
  const p = el.previousElementSibling;
  if (el.dataset.expanded) {{
    p.textContent = p.dataset.short;
    el.textContent = 'Læs mere';
    delete el.dataset.expanded;
  }} else {{
    p.dataset.short = p.textContent;
    p.textContent = full;
    el.textContent = 'Vis mindre';
    el.dataset.expanded = '1';
  }}
}}
</script>
</body>
</html>"""


def main():
    print("Henter data fra Grokipedia...")
    try:
        html = fetch_page()
    except Exception as e:
        print(f"FEJL ved hentning: {e}", file=sys.stderr)
        sys.exit(1)

    print("Parser indhold...")
    sections = parse_sections(html)

    if not sections:
        print("ADVARSEL: Ingen sektioner fundet — tjek HTML-strukturen på Grokipedia", file=sys.stderr)
        sys.exit(1)

    print(f"Fandt {len(sections)} kategorier med {sum(len(s['subsections']) for s in sections)} historier.")

    updated_at = datetime.now(timezone.utc)
    output = build_html(sections, updated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)

    print("index.html genereret.")


if __name__ == "__main__":
    main()
