#!/usr/bin/env python3
"""Build the web version of the IODP3 Exp. 506S literature map for mlfischer.github.io.

Usage (from anywhere):
    python3 geolab/_tools/build_exp506s_literature_map.py "/path/to/Exp506S_literature_map_package"

Reads the package folder (README.md, DATA_DICTIONARY.md, 00_LIESMICH.txt, the interactive map,
figures/ and data/) and (re)writes geolab/exp506s-literature-map/:

  index.html                               report page in the site design, built from README.md
                                           and DATA_DICTIONARY.md (text unchanged), with the
                                           credit "Made with Claude Science and Claude Opus"
  Exp506S_interactive_literature_map.html  the map, unchanged except for page metadata, a link
                                           back to the report, the same credit in the title bar,
                                           the site's visitor counter and a
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
            f"Crossref, OpenCitations and Semantic Scholar (as of {facts['asof']}). {MADE_WITH_EN}"),
        og_description=html.escape(
            f"{facts['total']} works in {facts['clusters']} topic clusters: report, interactive "
            f"map with APA 7 and RIS export, and the full dataset. {MADE_WITH_EN}"),
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
    # Credit line at the end of the title bar
    title_end = s.index("</div>", s.index(anchor))
    s = s[:title_end] + MAP_MADE_WITH + s[title_end:]
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


MADE_WITH_EN = "Made with Claude Science and Claude Opus (Anthropic)."
MAP_BACKLINK = '<a class="webback" href="./" title="Report, method and downloads">← Bericht &amp; Daten</a>'
MAP_MADE_WITH = '<span class="madewith"> · erstellt mit Claude Science und Claude Opus</span>'
MAP_LEGEND_OLD = "legend: { orientation: 'h', x: 0, y: 0, yanchor: 'bottom',"
MAP_LEGEND_NEW = ("legend: { orientation: 'h', x: 0, y: (innerWidth <= 760 ? -0.02 : 0), "
                  "yanchor: (innerWidth <= 760 ? 'top' : 'bottom'),")

MAP_HEAD = """
<!-- web:additions (mlfischer.github.io): metadata, back link, visitor count, narrow-screen layout -->
<meta name="description" content="Interaktive Literaturkarte zu IODP³ Expedition 506S (SIGNALS): $total Arbeiten in $clusters Themenclustern. Suche, Filter, APA-7-Referenzen und RIS-Export für Zotero, Citavi und EndNote. Erstellt mit Claude Science und Claude Opus (Anthropic).">
<link rel="canonical" href="$url$map">
<meta property="og:type" content="website">
<meta property="og:title" content="IODP³ Exp. 506S (SIGNALS) – interaktive Literaturkarte">
<meta property="og:description" content="$total Arbeiten in $clusters Themenclustern: Suche, Filter, APA-7-Referenzen und RIS-Export für Zotero, Citavi und EndNote. Erstellt mit Claude Science und Claude Opus (Anthropic).">
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
.madewith{font-weight:400;color:#555}
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
<meta name="theme-color" content="#e8eef0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111523" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="preload" href="/assets/fonts/inter-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="/assets/favicon.svg?v=3" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png?v=3">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Markus Fischer">
<meta property="og:title" content="$title">
<meta property="og:description" content="$og_description">
<meta property="og:url" content="$url">
<meta property="og:image" content="${url}figures/preview.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Topic map of $total works in $clusters topic clusters">
<meta name="twitter:card" content="summary_large_image">
<style>
  /* Kelani · report page (same tokens, type and grid as mlfischer.github.io) */
  @font-face{font-family:"Inter";font-style:normal;font-weight:400 600;font-display:swap;src:url("/assets/fonts/inter-var.woff2") format("woff2")}
  @font-face{font-family:"Inter";font-style:italic;font-weight:400 600;font-display:swap;src:url("/assets/fonts/inter-italic-var.woff2") format("woff2")}
  :root{
    color-scheme:light dark;
    --fr-cloud:#e4d5b0;--fr-mist:#c2bcb0;--fr-shade:#4b3516;--fr-olive:#715c23;--fr-umber:#2d1a0e;
    --fr-moss:#a18b3a;--fr-khaki:#9a8e75;--fr-sage:#6a675b;--fr-slate:#464549;--fr-rust:#863b1b;
    --bg:#fbf4ef;--surface:#fffbf8;--soft:#f4ece6;--line:#e7ddd5;--line-2:#d6c9bf;
    --ink:#2e241e;--ink-2:#5c534c;--ink-3:#675e57;--accent:#33407a;--accent-2:#24306a;--sun:#c0613b;
    --sky-0:#e8eef0;--sky-1:#f1eef4;--sky-2:#f9e3d7;--water-0:#f1dcd5;--water-1:#f7f0ee;
    --m1:#464549;--m2:#6a675b;--m3:#9a8e75;--m4:#a18b3a;--m5:#c0613b;--m-line:#2e241e;
    --font:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    --fs-micro:.8125rem;--fs-small:.9375rem;--fs-body:clamp(1rem,.97rem + .15vw,1.0625rem);
    --fs-lead:clamp(1.125rem,1.04rem + .45vw,1.3125rem);--fs-head:clamp(1.375rem,1.27rem + .5vw,1.625rem);
    --fs-title:clamp(2.125rem,1.55rem + 2.4vw,2.875rem);
    --page:1240px;--pad:clamp(20px,4.4vw,56px);--gap:clamp(20px,3vw,40px);--head-h:68px;--r:4px;--ease:cubic-bezier(.2,.7,.2,1);
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#171b29;--surface:#1e2233;--soft:#20253a;--line:#2d3245;--line-2:#3c4257;
    --ink:#efe8df;--ink-2:#c4bfcb;--ink-3:#a7a2b0;--accent:#f3bb93;--accent-2:#f8d0b2;--sun:#ec9577;
    --sky-0:#111523;--sky-1:#1c1b2f;--sky-2:#3c2733;--water-0:#2a1b25;--water-1:#1b1c2c;
    --m1:#7d7a86;--m2:#8f8a7c;--m3:#9a8e75;--m4:#c3b063;--m5:#ec9577;--m-line:#efe8df;
  }}
  *,*::before,*::after{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%;text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:calc(var(--head-h) + 20px)}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:var(--fs-body);line-height:1.65;font-optical-sizing:auto;
       letter-spacing:-.011em;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
  img,svg{display:block;max-width:100%;height:auto}
  p{margin:0 0 1em;text-wrap:pretty}
  h1,h2,h3{margin:0;font-weight:500;text-wrap:balance}
  b,strong{font-weight:600}
  sup,sub{line-height:0}
  a{color:var(--accent);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:.24em;
    text-decoration-color:color-mix(in srgb,currentColor 32%,transparent);transition:color .15s,text-decoration-color .15s}
  a:hover{text-decoration-color:currentColor}
  :focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px}
  ::selection{background:color-mix(in srgb,var(--sun) 24%,var(--bg))}
  .wrap{width:100%;max-width:var(--page);margin-inline:auto;padding-inline:var(--pad)}
  .skip{position:absolute;left:12px;top:-60px;z-index:60;background:var(--ink);color:var(--bg);padding:10px 14px;border-radius:var(--r);font-size:var(--fs-small);text-decoration:none}
  .skip:focus{top:12px}

  /* header */
  .site-head{position:sticky;top:0;z-index:40;height:var(--head-h);transition:background-color .3s var(--ease),box-shadow .3s var(--ease)}
  .site-head.is-stuck{background:color-mix(in srgb,var(--bg) 86%,transparent);-webkit-backdrop-filter:saturate(160%) blur(16px);backdrop-filter:saturate(160%) blur(16px);box-shadow:0 1px 0 var(--line)}
  .head{display:flex;align-items:center;gap:clamp(18px,2.4vw,36px);height:100%}
  .brand{display:inline-flex;align-items:center;gap:12px;margin-right:auto;color:var(--ink);text-decoration:none}
  .brand .mark{width:48px;height:33px;flex:none}
  .brand-name{font-size:1.0625rem;font-weight:600;letter-spacing:-.02em;white-space:nowrap}
  .mark .s1{fill:var(--m1)}.mark .s2{fill:var(--m2)}.mark .s3{fill:var(--m3)}.mark .s4{fill:var(--m4)}.mark .s5{fill:var(--m5)}.mark .hz{fill:var(--m-line)}
  .nav{display:flex;align-items:center;gap:clamp(14px,1.75vw,26px)}
  .nav a{position:relative;color:var(--ink-2);text-decoration:none;font-size:var(--fs-small);padding:8px 0;white-space:nowrap}
  .nav a:hover,.nav a[aria-current="page"]{color:var(--ink)}
  .nav a::after{content:"";position:absolute;left:50%;bottom:-3px;width:6px;height:6px;margin-left:-3px;border-radius:50%;background:var(--sun);opacity:0}
  .nav a[aria-current="page"]::after{opacity:1}
  .back{display:none;font-size:var(--fs-small);font-weight:500;color:var(--ink);text-decoration:none;border:1px solid var(--line-2);border-radius:999px;padding:7px 15px}
  @media (max-width:1060px){.nav{display:none}.back{display:inline-flex}}
  @media (max-width:600px){.brand .mark{width:42px;height:29px}}

  /* page head on the horizon */
  .sky{margin-top:calc(-1 * var(--head-h));padding:calc(var(--head-h) + clamp(44px,7vh,88px)) 0 clamp(48px,7vh,84px);
       background:linear-gradient(180deg,var(--sky-0) 0%,var(--sky-1) 56%,var(--sky-2) 100%)}
  .water{padding-bottom:clamp(72px,11vh,136px);
         background:linear-gradient(180deg,var(--water-0) 0,var(--water-1) 170px,color-mix(in oklab,var(--water-1) 38%,var(--bg)) 400px,var(--bg) 620px) no-repeat}
  .crumbs{display:flex;flex-wrap:wrap;gap:8px;font-size:var(--fs-small);color:var(--ink-3);margin:0 0 20px}
  .crumbs a{color:var(--ink-2);text-decoration:none}
  .crumbs a:hover{color:var(--ink)}
  h1.title{font-size:var(--fs-title);line-height:1.08;letter-spacing:-.026em;font-weight:400;max-width:18em}
  .byline{font-size:var(--fs-small);color:var(--ink-2);margin:20px 0 0;max-width:44rem}
  .madewith{font-size:var(--fs-small);color:var(--ink-2);margin:4px 0 0}
  .madewith b{color:var(--ink);font-weight:600}

  /* key figures + actions */
  .lead-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,3fr);column-gap:var(--gap);padding:clamp(36px,5.5vh,60px) 0 0}
  .stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:20px;margin:0;max-width:52rem}
  .stats div{min-width:0}
  .stats b{display:block;font-size:var(--fs-head);line-height:1.1;font-weight:400;letter-spacing:-.024em;font-variant-numeric:tabular-nums}
  .stats span{display:block;font-size:var(--fs-micro);line-height:1.4;color:var(--ink-3);margin-top:6px}
  .actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px 26px;margin:28px 0 0;font-size:var(--fs-small)}
  .btn{display:inline-flex;align-items:center;gap:.5em;padding:10px 18px 10px 19px;border-radius:999px;background:var(--ink);color:var(--bg);
       font-size:var(--fs-small);font-weight:500;text-decoration:none;transition:background-color .2s}
  .btn:hover{background:var(--accent);color:var(--bg)}
  .go{font-weight:500;text-decoration:none}
  .note{font-size:var(--fs-micro);line-height:1.55;color:var(--ink-3);margin:18px 0 0;max-width:44rem}
  .k-label{display:flex;align-items:baseline;gap:10px;font-size:var(--fs-small);font-weight:500;line-height:1.45;margin:0;padding-top:.18em}
  .k-label::before{content:"";width:6px;height:6px;border-radius:1.5px;background:var(--sun);flex:none;transform:translateY(-1px)}

  /* report: sticky contents | text */
  .report-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,3fr);column-gap:var(--gap);margin-top:clamp(40px,6vh,64px);padding-top:clamp(36px,5vh,56px);border-top:1px solid var(--line)}
  .toc{position:sticky;top:calc(var(--head-h) + 24px);align-self:start;display:flex;flex-direction:column;gap:2px;font-size:var(--fs-small)}
  .toc>span{display:flex;align-items:baseline;gap:10px;font-weight:500;color:var(--ink);margin-bottom:10px}
  .toc>span::before{content:"";width:6px;height:6px;border-radius:1.5px;background:var(--sun);flex:none;transform:translateY(-1px)}
  .toc a{color:var(--ink-2);text-decoration:none;padding:4px 0 4px 16px;border-left:1px solid var(--line);margin-left:2px}
  .toc a:hover{color:var(--ink);border-left-color:var(--ink-3)}
  .report{min-width:0;max-width:44rem}
  .report>*:first-child{margin-top:0}
  .report h2{font-size:var(--fs-head);line-height:1.25;letter-spacing:-.022em;margin:56px 0 16px;padding-top:24px;border-top:1px solid var(--line);scroll-margin-top:calc(var(--head-h) + 16px)}
  .report h3{font-size:var(--fs-lead);line-height:1.3;letter-spacing:-.018em;margin:36px 0 10px;scroll-margin-top:calc(var(--head-h) + 16px)}
  .report ul,.report ol{padding-left:1.25em;margin:0 0 1em}
  .report li{margin:0 0 8px}
  .report li::marker{color:var(--ink-3)}
  .anchor{margin-left:.35em;color:var(--ink-3);font-weight:400;opacity:0;text-decoration:none;transition:opacity .15s}
  h2:hover .anchor,h3:hover .anchor,.anchor:focus{opacity:1}
  .summary{background:var(--soft);border-radius:var(--r);padding:22px 24px 6px;margin:0 0 8px;scroll-margin-top:calc(var(--head-h) + 16px)}
  .eyebrow{display:flex;align-items:baseline;gap:10px;font-size:var(--fs-small);font-weight:500;color:var(--ink);margin:0 0 10px}
  .eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--sun);flex:none;transform:translateY(-1px)}
  .fig{margin:28px 0 36px}
  .fig a.img{display:block;border-radius:var(--r);overflow:hidden;background:#fff;box-shadow:0 0 0 1px var(--line)}
  .fig a.img:hover{box-shadow:0 0 0 1px var(--line-2)}
  .fig img{width:100%}
  .fig figcaption{font-size:var(--fs-micro);line-height:1.55;color:var(--ink-3);margin-top:12px}
  .fig figcaption b{color:var(--ink);font-weight:600}
  .scroll-hint{display:none;font-size:var(--fs-micro);color:var(--ink-3);margin-bottom:6px}
  .table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:var(--r);box-shadow:0 0 0 1px var(--line);background:var(--surface);margin:16px 0 28px}
  table{border-collapse:collapse;width:100%;font-size:var(--fs-micro);line-height:1.5}
  table.catalogue{min-width:960px}
  th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
  thead th{background:var(--soft);font-weight:500;color:var(--ink);white-space:nowrap}
  tbody tr:last-child td{border-bottom:0}
  th.num,td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  table.catalogue td:nth-child(2){font-weight:500;min-width:180px}
  table.dict td:first-child{white-space:nowrap;font-weight:500}
  .files li{margin-bottom:12px}
  .size{display:inline-block;font-size:var(--fs-micro);font-variant-numeric:tabular-nums;color:var(--ink-3);border:1px solid var(--line-2);border-radius:999px;padding:0 8px;margin:0 5px;vertical-align:1px;white-space:nowrap}
  .report h2.appendix{margin-top:72px}
  @media (max-width:1000px){.scroll-hint{display:block}}
  @media (max-width:860px){
    .lead-grid,.report-grid{grid-template-columns:minmax(0,1fr);row-gap:18px}
    .toc{position:static;flex-direction:row;flex-wrap:wrap;gap:4px 16px}
    .toc>span{width:100%;margin-bottom:2px}
    .toc a{border-left:0;padding:2px 0;margin:0}
    .stats{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:22px}
  }
  @media (max-width:520px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}table.dict td:first-child{white-space:normal}}

  /* footer */
  .band{display:flex;height:4px}.band span{display:block;height:100%}
  .foot-base{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px 28px;padding:28px 0 44px;font-size:var(--fs-micro);line-height:1.55;color:var(--ink-3)}
  .foot-base p{margin:0}
  .foot-base a{color:var(--ink-2);text-decoration:none}
  .foot-base a:hover{color:var(--ink)}
  @media print{.site-head,.band,.toc{display:none}.sky,.water{background:none;margin:0;padding:16px 0}}
</style>
<!-- GoatCounter: privacy-friendly visitor stats (dashboard: mlfischer.goatcounter.com) -->
<script data-goatcounter="https://mlfischer.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
</head>
<body>
<a class="skip" href="#report">Skip to content</a>

<header class="site-head">
  <div class="wrap head">
    <a class="brand" href="/" aria-label="Markus Fischer — home"><svg class="mark" viewBox="0 18.35 120 82.05" aria-hidden="true" focusable="false"><clipPath id="hz-r"><rect width="120" height="96"/></clipPath><g clip-path="url(#hz-r)"><rect class="s s1" x="10" y="86" width="12" height="12"/><rect class="s s2" x="26.5" y="68.5" width="15" height="15" rx="1.88"/><rect class="s s3" x="45.62" y="51.62" width="18.75" height="18.75" rx="4.69"/><rect class="s s4" x="66.28" y="35.28" width="23.44" height="23.44" rx="8.79"/><rect class="s s5" x="87.35" y="19.35" width="29.3" height="29.3" rx="14.65"/></g><rect class="hz" y="96" width="120" height="3.4" rx="1.7"/></svg><span class="brand-name" aria-hidden="true">Markus Fischer</span></a>
    <nav class="nav" aria-label="Main">
      <a href="/#ueber">About</a><a href="/#publikationen">Research</a><a href="/#expertise">Expertise</a><a href="/#geonews">GeoNews</a><a href="/#geolab" aria-current="page">GeoLab</a><a href="/#klettergeologie">GeoCrimps</a><a href="/#klimamusik">ClimateMusic</a>
    </nav>
    <a class="back" href="/#geolab">← GeoLab</a>
  </div>
</header>

<div class="sky"><div class="wrap">
  <p class="crumbs"><a href="/#geolab">GeoLab</a><span aria-hidden="true">/</span><a href="/#literatursuche">Literature search</a></p>
  <h1 class="title">$title</h1>
  <p class="byline">Markus Fischer · As of $asof · Sources: OpenAlex, Crossref, OpenCitations, Semantic Scholar</p>
  <p class="madewith">Made with <b>Claude Science</b> and <b>Claude Opus</b> (Anthropic)</p>
</div></div>

<main class="water"><div class="wrap">
  <div class="lead-grid">
    <p class="k-label">Key figures</p>
    <div>
      <div class="stats">
        <div><b>$total</b><span>works</span></div>
        <div><b>$core</b><span>core</span></div>
        <div><b>$field</b><span>field</span></div>
        <div><b>$clusters</b><span>topic clusters</span></div>
        <div><b>$sites</b><span>target sites</span></div>
        <div><b>$seeds</b><span>prospectus references</span></div>
      </div>
      <div class="actions">
        <a class="btn" href="$map">Open the interactive map<span aria-hidden="true">↗</span></a>
        <a class="go" href="#files">Data &amp; downloads →</a>
      </div>
      <p class="note">The interactive map is a single page of $map_size with a German interface and works best
        in a desktop browser: click a point for its APA&nbsp;7 reference, search and filter, or lasso a region
        to copy a reference list or export it as RIS for Zotero, Citavi or EndNote.</p>
    </div>
  </div>

  <div class="report-grid">
    <nav class="toc" aria-label="Contents"><span>Contents</span>$toc</nav>
    <article class="report" id="report">
$body
    </article>
  </div>
</div></main>

<footer>
  <div class="band" aria-hidden="true"><span style="flex:9;background:var(--fr-umber)"></span><span style="flex:12;background:var(--fr-shade)"></span><span style="flex:9;background:var(--fr-slate)"></span><span style="flex:3;background:var(--fr-rust)"></span><span style="flex:9;background:var(--fr-olive)"></span><span style="flex:13;background:var(--fr-sage)"></span><span style="flex:10;background:var(--fr-khaki)"></span><span style="flex:6;background:var(--fr-moss)"></span><span style="flex:14;background:var(--fr-mist)"></span><span style="flex:15;background:var(--fr-cloud)"></span></div>
  <div class="wrap foot-base">
    <p>© $year Markus Fischer · University of Potsdam · <a href="/#geolab">GeoLab</a> · <a href="/">mlfischer.github.io</a></p>
    <p>Set in Inter. Colours measured from Ernst Haeckel's watercolour “Urwald am Blauen Fluß (Kelany-Ganga)”, Ceylon 1882.</p>
  </div>
</footer>
<script>
  (function(){var h=document.querySelector('.site-head'),t=false;function f(){if(t)return;t=true;requestAnimationFrame(function(){h.classList.toggle('is-stuck',window.scrollY>6);t=false})}
  window.addEventListener('scroll',f,{passive:true});f();})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
