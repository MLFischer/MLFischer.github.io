#!/usr/bin/env python3
"""Build the web version of the IODP3 Exp. 506S literature map for mlfischer.github.io.

Usage (from anywhere):
    python3 geolab/_tools/build_exp506s_literature_map.py "/path/to/Exp506S_literature_map_package"

Reads the package folder (README.md, DATA_DICTIONARY.md, 00_LIESMICH.txt, the interactive map,
figures/ and data/) and (re)writes geolab/exp506s-literature-map/:

  index.html                               report page in the site design, built from README.md
                                           and DATA_DICTIONARY.md (text unchanged)
  Exp506S_interactive_literature_map.html  the map, unchanged except for page metadata, a link
                                           back to the report, the site's visitor counter and a
                                           layout that also works on narrow screens (there the
                                           legend sits below the plot)
  figures/*.png                            figures, copied unchanged
  figures/preview.jpg                      1200x630 link-preview image (made from fig. 1)
  data/*                                   data files, copied unchanged

Re-run it after regenerating the package; numbers and date are read from README.md and
00_LIESMICH.txt. Needs: pip install markdown beautifulsoup4 pillow
GitHub Pages (Jekyll) does not publish folders starting with "_", so this script is kept in the
repository but not served on the website.
"""
import argparse
import html
import re
import shutil
import sys
from pathlib import Path
from string import Template

import markdown
from bs4 import BeautifulSoup
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "geolab" / "exp506s-literature-map"
URL = "https://mlfischer.github.io/geolab/exp506s-literature-map/"
MAP = "Exp506S_interactive_literature_map.html"

# file -> (figure number, caption title as in README, alt text)
FIGS = {
    "fig1_topic_map.png": (1, "Topic map",
        "Topic map: UMAP projection of all works, coloured by six super-themes, with the 30 "
        "numbered topic clusters and the prospectus references marked as open circles; the "
        "legend lists cluster names and sizes."),
    "fig2_publication_trends.png": (2, "Publication trends",
        "Publication trends: (a) works per year since 1960, core versus field, with the DSDP, "
        "ODP and IODP phases shaded; (b) works per year by super-theme, 3-year mean; (c) share "
        "of each cluster's works per five-year period, 1975 to 2024."),
    "fig3_venues_authors.png": (3, "Venues and authors",
        "Venues, authors and institutions: (a) journals with the most works, core versus field; "
        "(b) most prolific authors; (c) works by country of author affiliation; (d) German "
        "institutions."),
    "fig4_emerging_topics.png": (4, "Emerging topics",
        "Emerging topics: (a) relative growth 2019-26 versus 2009-18 against cluster size; "
        "(b) relative growth of method and proxy facets; (c) rising and falling terms in "
        "abstracts."),
    "fig5_sites_topics.png": (5, "Sites by topic",
        "Legacy sites by topic: (a) share of each site group's works per topic cluster, anchor "
        "sites in bold; (b) works per site group by decade."),
}
NUMERIC_COLUMNS = {"#", "Works (core)", "Median year", "Growth"}
MONTHS_DE = {"Januar": "January", "Februar": "February", "März": "March", "April": "April",
             "Mai": "May", "Juni": "June", "Juli": "July", "August": "August",
             "September": "September", "Oktober": "October", "November": "November",
             "Dezember": "December"}


def human(n):
    """Decimal file size, as Finder shows it."""
    if n < 1e6:
        return f"{n / 1e3:.0f} KB"
    return f"{n / 1e6:.1f} MB"


def need(pattern, text, what):
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"Could not find {what} (pattern {pattern!r}) - has the README wording changed?")
    return m.group(1)


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)  # copyfile: no read-only permission bits from the source


def make_preview(src, dst):
    """Whole fig. 1 letterboxed on white, 1200x630 (Open Graph); small enough for messengers."""
    im = Image.open(src).convert("RGB")
    W, H, pad = 1200, 630, 22
    s = min((W - 2 * pad) / im.width, (H - 2 * pad) / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    canvas.save(dst, "JPEG", quality=85, optimize=True, progressive=True)


def md_to_html(text):
    md = markdown.Markdown(
        extensions=["tables", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": "#", "permalink_class": "anchor",
                                   "permalink_title": "Link to this section"}})
    return md.convert(text)


def escape_extra_pipes(text):
    """DATA_DICTIONARY tables have two columns; a '|' inside a cell (e.g. 'core | field') is content."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and not re.fullmatch(r"[|\-: ]+", s):
            cells = [c.strip() for c in s[1:-1].split("|")]
            if len(cells) > 2:
                cells = [cells[0], " &#124; ".join(cells[1:])]
            line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out)


def heading_text(h):
    h = BeautifulSoup(str(h), "html.parser").find(h.name)
    for a in h.find_all("a", class_="anchor"):
        a.decompose()
    return h.get_text(" ", strip=True)


def build_report(src, readme, dd, facts):
    lines = readme.splitlines()
    if not lines[0].startswith("# "):
        sys.exit("README.md should start with a '# ' title line")
    title = lines[0][2:].strip()
    body = md_to_html("\n".join(lines[1:]))

    dd_lines = dd.splitlines()
    if not dd_lines[0].startswith("# "):
        sys.exit("DATA_DICTIONARY.md should start with a '# ' title line")
    dd_md = "## Data dictionary\n" + "\n".join(
        ("#" + l) if l.startswith("## ") else l for l in dd_lines[1:])
    body += md_to_html(escape_extra_pipes(dd_md))

    soup = BeautifulSoup(body, "html.parser")

    # Opening paragraph -> "In brief" box
    first = soup.find("p")
    box = soup.new_tag("div", attrs={"class": "summary", "id": "in-brief"})
    first.wrap(box)
    eyebrow = soup.new_tag("p", attrs={"class": "eyebrow"})
    eyebrow.string = "In brief"
    box.insert(0, eyebrow)

    # Images -> numbered figures linking to the full-resolution PNG
    for img in soup.find_all("img"):
        rel = img["src"]
        name = Path(rel).name
        if name not in FIGS:
            sys.exit(f"Unknown figure {rel}: add it to FIGS")
        num, cap, alt = FIGS[name]
        path = OUT / "figures" / name
        w, h = Image.open(path).size
        fig = BeautifulSoup(
            f'<figure class="fig" id="fig{num}"><a class="img" href="{rel}" '
            f'title="Open full resolution"><img src="{rel}" alt="{html.escape(alt)}" '
            f'width="{w}" height="{h}" loading="lazy" decoding="async"></a>'
            f"<figcaption><b>Figure {num}</b> · {html.escape(cap)}. "
            f'<a href="{rel}">Full resolution</a> (PNG, 300 dpi, {human(path.stat().st_size)})'
            f"</figcaption></figure>", "html.parser").figure
        p = img.parent
        (p if p.name == "p" and len(p.find_all(True)) == 1 else img).replace_with(fig)

    # Tables -> scroll container; numeric columns right-aligned
    for t in soup.find_all("table"):
        heads = [th.get_text(strip=True) for th in t.find_all("th")]
        catalogue = bool(heads) and heads[0] == "#"
        t["class"] = ["catalogue" if catalogue else "dict"]
        if catalogue:
            cols = {i for i, hd in enumerate(heads) if hd in NUMERIC_COLUMNS}
            for tr in t.find_all("tr"):
                for i, cell in enumerate(tr.find_all(["th", "td"])):
                    if i in cols:
                        cell["class"] = ["num"]
        wrap = soup.new_tag("div", attrs={"class": "table-wrap"})
        t.wrap(wrap)
        if catalogue:
            hint = soup.new_tag("p", attrs={"class": "scroll-hint"})
            hint.string = "Swipe sideways to see all columns."
            wrap.insert_before(hint)

    # Files list -> file sizes, direct downloads, data dictionary on this page
    files = soup.find("h2", id="files")
    if files is None:
        sys.exit("README.md has no '## Files' section")
    ul = files.find_next_sibling("ul")
    ul["class"] = ["files"]
    for a in ul.find_all("a", href=True):
        href = a["href"]
        if href == "DATA_DICTIONARY.md":
            a["href"] = "#data-dictionary"
            a.string = "Data dictionary"
            a.insert_after(" (below)")
            continue
        if href.startswith(("http", "#")):
            continue
        path = OUT / href
        if not path.exists():
            sys.exit(f"README links to {href}, which is not in the package")
        if href.startswith("figures/"):
            continue  # sizes are given in the figure captions
        badge = soup.new_tag("span", attrs={"class": "size"})
        badge.string = f"{path.suffix[1:].upper()} · {human(path.stat().st_size)}"
        a.insert_after(badge)
        if href.startswith("data/"):
            a["download"] = ""

    soup.find("h2", id="data-dictionary")["class"] = ["appendix"]

    # δ18O -> δ<sup>18</sup>O (text only, never inside attributes)
    for s in list(soup.find_all(string=re.compile(r"δ\d"))):
        new = re.sub(r"δ(\d+)([A-Z])", r"δ<sup>\1</sup>\2", html.escape(str(s), quote=False))
        s.replace_with(*BeautifulSoup(new, "html.parser").contents)

    toc = [("in-brief", "In brief")] + [(h["id"], heading_text(h)) for h in soup.find_all("h2")]
    toc_html = "".join(f'<a href="#{i}">{html.escape(t)}</a>' for i, t in toc)

    page = Template(PAGE).substitute(
        title=html.escape(title),
        url=URL,
        map=MAP,
        description=html.escape(
            f"{facts['total']} works in {facts['clusters']} topic clusters around IODP³ "
            f"Expedition 506S (SIGNALS): report, interactive map and data, drawing on OpenAlex, "
            f"Crossref, OpenCitations and Semantic Scholar (as of {facts['asof']})."),
        og_description=html.escape(
            f"{facts['total']} works in {facts['clusters']} topic clusters: report, interactive "
            f"map with APA 7 and RIS export, and the full dataset."),
        asof=facts["asof"], year=facts["asof"].split()[-1],
        total=facts["total"], core=facts["core"], field=facts["field"],
        clusters=facts["clusters"], sites=facts["sites"], seeds=facts["seeds"],
        map_size=human((OUT / MAP).stat().st_size).replace(" ", "&nbsp;"),
        toc=toc_html, body=str(soup))
    (OUT / "index.html").write_text(page, encoding="utf-8")


def patch_map(src, dst, total, clusters):
    s = src.read_bytes().decode("utf-8")  # bytes in/out: keeps the 20 MB file byte-identical otherwise
    if "web:additions" in s:
        sys.exit(f"{src.name} already contains web additions - point the script at the original package")
    first_script = s.index("<script")
    style_end = s.rfind("</style>", 0, first_script)
    if style_end < 0:
        sys.exit("Map layout changed: no <style> block before the first <script>")
    style_end += len("</style>")
    total_de = total.replace(",", ".")
    add = Template(MAP_HEAD).substitute(url=URL, map=MAP, total=total_de, clusters=clusters)
    s = s[:style_end] + add + s[style_end:]
    anchor = '<div id="top"><div class="title">'
    if s.count(anchor) != 1:
        sys.exit("Map layout changed: title bar not found exactly once")
    s = s.replace(anchor, anchor + MAP_BACKLINK, 1)
    # Narrow screens: legend below the plot instead of on top of the points (desktop unchanged)
    if s.count(MAP_LEGEND_OLD) != 1:
        sys.exit("Map layout changed: legend definition not found exactly once")
    s = s.replace(MAP_LEGEND_OLD, MAP_LEGEND_NEW, 1)
    dst.write_bytes(s.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", type=Path, help="Exp506S_literature_map_package folder")
    pkg = ap.parse_args().package
    for f in ("README.md", "DATA_DICTIONARY.md", "00_LIESMICH.txt", MAP):
        if not (pkg / f).exists():
            sys.exit(f"{pkg / f} not found")

    readme = (pkg / "README.md").read_text(encoding="utf-8")
    dd = (pkg / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    liesmich = (pkg / "00_LIESMICH.txt").read_text(encoding="utf-8")
    m = re.search(r"Stand:\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})", liesmich)
    if not m or m.group(2) not in MONTHS_DE:
        sys.exit("Could not read the date ('Stand: ...') from 00_LIESMICH.txt")
    facts = {
        "asof": f"{int(m.group(1))} {MONTHS_DE[m.group(2)]} {m.group(3)}",
        "total": need(r"\*\*([\d,]+) works\*\*", readme, "the number of works"),
        "clusters": need(r"in (\d+) topic clusters", readme, "the number of clusters"),
        "core": need(r"([\d,]+) core works", readme, "the number of core works"),
        "field": need(r"([\d,]+) field works", readme, "the number of field works"),
        "seeds": need(r"the (\d+) prospectus references", readme, "the number of prospectus references"),
        "sites": need(r"its (\d+) Table 1 sites", readme, "the number of target sites"),
    }

    for sub in ("figures", "data"):
        for f in sorted((pkg / sub).iterdir()):
            if f.is_file() and not f.name.startswith("."):
                copy(f, OUT / sub / f.name)
    make_preview(pkg / "figures" / "fig1_topic_map.png", OUT / "figures" / "preview.jpg")
    patch_map(pkg / MAP, OUT / MAP, facts["total"], facts["clusters"])
    build_report(pkg, readme, dd, facts)
    print(f"Built {OUT.relative_to(REPO)}/ ({facts['total']} works, as of {facts['asof']})")


MAP_BACKLINK = '<a class="webback" href="./" title="Report, method and downloads">← Bericht &amp; Daten</a>'
MAP_LEGEND_OLD = "legend: { orientation: 'h', x: 0, y: 0, yanchor: 'bottom',"
MAP_LEGEND_NEW = ("legend: { orientation: 'h', x: 0, y: (innerWidth <= 760 ? -0.02 : 0), "
                  "yanchor: (innerWidth <= 760 ? 'top' : 'bottom'),")

MAP_HEAD = """
<!-- web:additions (mlfischer.github.io): metadata, back link, visitor count, narrow-screen layout -->
<meta name="description" content="Interaktive Literaturkarte zu IODP³ Expedition 506S (SIGNALS): $total Arbeiten in $clusters Themenclustern. Suche, Filter, APA-7-Referenzen und RIS-Export für Zotero, Citavi und EndNote.">
<link rel="canonical" href="$url$map">
<meta property="og:type" content="website">
<meta property="og:title" content="IODP³ Exp. 506S (SIGNALS) – interaktive Literaturkarte">
<meta property="og:description" content="$total Arbeiten in $clusters Themenclustern: Suche, Filter, APA-7-Referenzen und RIS-Export für Zotero, Citavi und EndNote.">
<meta property="og:url" content="$url$map">
<meta property="og:image" content="${url}figures/preview.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>
body{display:flex;flex-direction:column;height:100vh;height:100dvh}
#top{flex:none}
#main{flex:1 1 auto;height:auto;min-height:0}
.webback{float:right;margin-left:14px;font-weight:400;font-size:13px;color:#1f3b5c;text-decoration:none}
.webback:hover{text-decoration:underline}
@media (max-width:760px){
  body{display:block;height:auto}
  #main{flex-direction:column;height:auto}
  #plot{flex:none;height:76vh;min-height:420px}
  #side{flex:none;max-width:none;border-left:0;border-top:1px solid #ddd;overflow:visible}
  .controls input[type=search],.controls select{width:100%;max-width:none}
  .webback{float:none;display:block;margin:0 0 4px}
}
</style>
<script data-goatcounter="https://mlfischer.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<!-- /web:additions -->
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>$title · Markus Fischer</title>
<meta name="description" content="$description">
<link rel="canonical" href="$url">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Markus Fischer · Spatial Perspective">
<meta property="og:title" content="$title">
<meta property="og:description" content="$og_description">
<meta property="og:url" content="$url">
<meta property="og:image" content="${url}figures/preview.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Topic map of $total works in $clusters topic clusters">
<meta name="twitter:card" content="summary_large_image">
<style>
  :root{
    --bg:#fbfbfa;--fg:#22232a;--muted:#6b6c74;--faint:#8b8c94;--line:#e7e7e4;
    --accent:#3a5a48;--soft:#f0f2ee;--card:#ffffff;--col:760px;--wide:1040px;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  @media (prefers-color-scheme:dark){
    :root{--bg:#14151a;--fg:#e6e6e8;--muted:#9c9da6;--faint:#7d7e88;--line:#272831;
          --accent:#8bbfa0;--soft:#1b1e22;--card:#191a1f;}
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--fg);font-size:17px;line-height:1.7;
       font-family:Georgia,"Iowan Old Style",Charter,"Times New Roman",serif;-webkit-font-smoothing:antialiased}
  a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
  a:hover{border-bottom-color:currentColor}
  .wrap{max-width:var(--wide);margin:0 auto;padding:0 clamp(16px,4vw,26px)}
  .col{max-width:var(--col);margin:0 auto}
  p{margin:0 0 16px}

  .topbar{display:flex;justify-content:space-between;align-items:baseline;gap:14px;flex-wrap:wrap;
          padding-top:18px;padding-bottom:4px;font-family:var(--sans)}
  .wordmark{font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:var(--faint)}
  .crumb{font-size:.82rem;color:var(--muted)}
  .hero{border-bottom:1px solid var(--line)}
  .hero .col{padding:30px 0 30px}
  .kicker{font-family:var(--sans);font-size:.76rem;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:0 0 10px}
  h1{font-size:2.2rem;font-weight:600;letter-spacing:-.02em;line-height:1.12;margin:0 0 12px}
  .byline{font-family:var(--sans);font-size:.86rem;color:var(--muted);margin:0}
  .facts{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}
  .fact{font-family:var(--sans);font-size:.85rem;color:var(--muted);background:var(--soft);
        border:1px solid var(--line);border-radius:8px;padding:5px 11px}
  .fact b{color:var(--fg);font-weight:600;font-variant-numeric:tabular-nums}
  .cta{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0 12px}
  .btn{display:inline-flex;align-items:center;justify-content:center;font-family:var(--sans);font-size:.92rem;
       font-weight:600;line-height:1.2;padding:12px 17px;border-radius:10px;border:1px solid var(--line);
       background:var(--card);color:var(--fg)}
  .btn:hover{border-color:var(--accent)}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:var(--bg)}
  .btn.primary:hover{filter:brightness(1.1)}
  .note{font-family:var(--sans);font-size:.84rem;color:var(--muted);line-height:1.55;margin:0}

  .toc{font-family:var(--sans);font-size:.84rem;display:flex;flex-wrap:wrap;gap:4px 16px;
       margin-top:26px;padding-bottom:4px}
  .toc span{color:var(--faint);text-transform:uppercase;letter-spacing:.14em;font-size:.68rem;align-self:center}

  .report{padding:4px 0 8px}
  .report>*{max-width:var(--col);margin-left:auto;margin-right:auto}
  .report>.fig,.report>.table-wrap{max-width:none}
  .report h2{font-family:var(--sans);font-size:1.12rem;font-weight:600;letter-spacing:.01em;
             margin-top:48px;margin-bottom:14px;scroll-margin-top:16px}
  .report h3{font-size:1.18rem;font-weight:600;margin-top:32px;margin-bottom:8px;scroll-margin-top:16px}
  .report ul,.report ol{padding-left:1.3em}
  .report li{margin:0 0 8px}
  .anchor{margin-left:.35em;color:var(--faint);font-weight:400;opacity:0;transition:opacity .15s}
  h2:hover .anchor,h3:hover .anchor,.anchor:focus{opacity:1}
  sup{font-size:.68em;line-height:0}

  .summary{background:var(--soft);border:1px solid var(--line);border-left:3px solid var(--accent);
           border-radius:0 10px 10px 0;padding:18px 22px 4px;margin-top:28px;scroll-margin-top:16px}
  .eyebrow{font-family:var(--sans);font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;
           color:var(--faint);margin:0 0 6px}

  .fig{margin-top:26px;margin-bottom:34px}
  .fig a.img{display:block;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
  .fig a.img:hover{border-color:var(--accent)}
  .fig img{display:block;width:100%;height:auto}
  .fig figcaption{font-family:var(--sans);font-size:.82rem;color:var(--muted);line-height:1.5;margin-top:9px}
  .fig figcaption b{color:var(--fg);font-weight:600}

  .scroll-hint{display:none;font-family:var(--sans);font-size:.78rem;color:var(--faint);margin-bottom:6px}
  .table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;
              background:var(--card);margin-top:16px;margin-bottom:24px}
  table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:.8rem;line-height:1.45}
  table.catalogue{min-width:960px}
  th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
  thead th{background:var(--soft);font-weight:600;white-space:nowrap}
  tbody tr:last-child td{border-bottom:0}
  th.num,td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  table.catalogue td:nth-child(2){font-weight:600;min-width:180px}
  table.dict td:first-child{white-space:nowrap;font-weight:600}
  @media (max-width:1000px){.scroll-hint{display:block}}

  .files li{margin-bottom:12px}
  .size{display:inline-block;font-family:var(--sans);font-size:.68rem;letter-spacing:.06em;color:var(--faint);
        border:1px solid var(--line);border-radius:5px;padding:0 6px;margin:0 5px;vertical-align:1px;white-space:nowrap}
  .report h2.appendix{border-top:1px solid var(--line);padding-top:30px;margin-top:56px}

  footer{border-top:1px solid var(--line);margin-top:48px;padding:30px 0 56px;
         font-family:var(--sans);font-size:.85rem;color:var(--faint)}
  @media (max-width:600px){
    body{font-size:16px}
    h1{font-size:1.62rem}
    .btn{flex:1 1 100%}
    table.dict td:first-child{white-space:normal}
  }
</style>
<!-- GoatCounter: privacy-friendly visitor stats (dashboard: mlfischer.goatcounter.com) -->
<script data-goatcounter="https://mlfischer.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
</head>
<body>

<div class="wrap"><div class="col topbar">
  <a class="wordmark" href="../../">Spatial Perspective</a>
  <a class="crumb" href="../../#literatursuche">GeoLab · Literature search</a>
</div></div>

<header class="hero">
  <div class="wrap"><div class="col">
    <p class="kicker">GeoLab · Literature search</p>
    <h1>$title</h1>
    <p class="byline">Markus Fischer · As of $asof · Sources: OpenAlex, Crossref, OpenCitations, Semantic Scholar</p>
    <div class="facts">
      <span class="fact"><b>$total</b> works</span>
      <span class="fact"><b>$core</b> core · <b>$field</b> field</span>
      <span class="fact"><b>$clusters</b> topic clusters</span>
      <span class="fact"><b>$sites</b> target sites</span>
      <span class="fact"><b>$seeds</b> prospectus references</span>
    </div>
    <div class="cta">
      <a class="btn primary" href="$map">Open the interactive map</a>
      <a class="btn" href="#files">Data &amp; downloads</a>
    </div>
    <p class="note">The interactive map is a single page of $map_size with a German interface and works best
      in a desktop browser: click a point for its APA&nbsp;7 reference, search and filter, or lasso a region
      to copy a reference list or export it as RIS for Zotero, Citavi or EndNote.</p>
  </div></div>
</header>

<main class="wrap">
  <nav class="col toc" aria-label="Contents"><span>Contents</span>$toc</nav>
  <article class="report">
$body
  </article>
</main>

<footer>
  <div class="wrap"><div class="col">© $year Markus Fischer · University of Potsdam ·
    <a href="../../#geolab">GeoLab</a> · <a href="../../">mlfischer.github.io</a></div></div>
</footer>

</body>
</html>
"""

if __name__ == "__main__":
    main()
