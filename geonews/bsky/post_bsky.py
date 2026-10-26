#!/usr/bin/env python3
"""GeoNews -> Bluesky. Laeuft per GitHub Actions im Website-Repo.

Liest geonews/issues/*/bsky.json (vom woechentlichen GeoNews-Lauf erzeugt) und
postet jeden faelligen Eintrag genau einmal auf Bluesky:
  * faellig  = Termin erreicht und hoechstens MAX_LATE Stunden her
  * nicht    = schon gepostet, "hold": true im Eintrag, oder ID in state.json "hold"
Zustand (geposted/uebersprungen/hold) steht in geonews/bsky/state.json.

Zugangsdaten nur aus Umgebungsvariablen (GitHub-Secrets BSKY_HANDLE,
BSKY_APP_PASSWORD) -- nie aus Dateien.

    python geonews/bsky/post_bsky.py --dry-run     # zeigt nur, was gepostet wuerde
"""
import argparse, datetime as dt, glob, json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "geonews", "bsky", "state.json")
PDS = "https://bsky.social"
NEWSLETTER = "https://mlfischer.github.io/#geonews"
MAX_LATE = 24      # Stunden
LIMIT = 300        # Bluesky-Grenze (Grapheme; ohne Emoji ~ Zeichen)


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    for k, v in (("posted", {}), ("skipped", {}), ("hold", [])):
        s.setdefault(k, v)
    return s


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_text(p, week_label):
    """Text + Link-Facets. Links stehen kurz im Text, verlinkt wird die volle URL."""
    doi_url = "https://doi.org/" + p["doi"]
    lines = [p["text"].strip(), "", "Paper: doi.org/" + p["doi"],
             f"GeoNews {week_label}: mlfischer.github.io/#geonews"]
    text = "\n".join(lines)
    facets = []
    for shown, url in (("doi.org/" + p["doi"], doi_url),
                       ("mlfischer.github.io/#geonews", NEWSLETTER)):
        start = text.encode("utf-8").find(shown.encode("utf-8"))
        facets.append({"index": {"byteStart": start, "byteEnd": start + len(shown.encode("utf-8"))},
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]})
    return text, facets


def xrpc(method, token=None, body=None, raw=None, ctype="application/json"):
    url = f"{PDS}/xrpc/{method}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", ctype)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Bluesky-Fehler {method}: {e.code} {e.read().decode()[:300]}")


def due_posts(state, t):
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "geonews", "issues", "*", "bsky.json"))):
        with open(path, encoding="utf-8") as f:
            q = json.load(f)
        for p in q.get("posts", []):
            pid = p["id"]
            if pid in state["posted"] or pid in state["skipped"]:
                continue
            when = dt.datetime.fromisoformat(p["scheduled"])
            if t < when:
                continue
            if p.get("hold") or pid in state["hold"]:
                print(f"  {pid}: hold — wird nicht gepostet")
                continue
            if (t - when).total_seconds() > MAX_LATE * 3600:
                state["skipped"][pid] = {"reason": f"mehr als {MAX_LATE} h zu spaet", "at": t.isoformat()}
                print(f"  {pid}: zu spaet ({when.isoformat()}) — uebersprungen")
                continue
            out.append((os.path.dirname(path), q, p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", help="Zeit simulieren (ISO), nur mit --dry-run")
    a = ap.parse_args()
    t = dt.datetime.fromisoformat(a.now) if (a.now and a.dry_run) else now_utc()
    state = load_state()
    todo = due_posts(state, t)
    if not todo:
        print("Nichts faellig.")
        if not a.dry_run:
            save_state(state)
        return
    todo = todo[:1]   # hoechstens ein Post pro Lauf -> kein Schwall nach Ausfaellen
    token = did = None
    for d, q, p in todo:
        text, facets = build_text(p, q.get("week_en", "this week"))
        n = len(text)
        print(f"== {p['id']} ({p['scheduled']}) · {n} Zeichen\n{text}\n")
        if n > LIMIT:
            raise SystemExit(f"{p['id']}: {n} > {LIMIT} Zeichen — nicht gepostet")
        img = os.path.join(d, p["image"])
        with open(img, "rb") as f:
            blob_bytes = f.read()
        if len(blob_bytes) > 950_000:
            raise SystemExit(f"{p['id']}: Bild zu gross ({len(blob_bytes)} B)")
        if a.dry_run:
            print("  (dry-run: nicht gepostet)")
            continue
        if token is None:
            h, pw = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
            if not h or not pw:
                raise SystemExit("BSKY_HANDLE / BSKY_APP_PASSWORD fehlen (GitHub-Secrets)")
            s = xrpc("com.atproto.server.createSession", body={"identifier": h, "password": pw})
            token, did = s["accessJwt"], s["did"]
        blob = xrpc("com.atproto.repo.uploadBlob", token, raw=blob_bytes, ctype="image/png")["blob"]
        record = {"$type": "app.bsky.feed.post", "text": text, "facets": facets,
                  "langs": ["en"], "createdAt": now_utc().isoformat().replace("+00:00", "Z"),
                  "embed": {"$type": "app.bsky.embed.images", "images": [{
                      "image": blob, "alt": p["alt"],
                      "aspectRatio": {"width": 1080, "height": 1350}}]}}
        r = xrpc("com.atproto.repo.createRecord", token,
                 body={"repo": did, "collection": "app.bsky.feed.post", "record": record})
        rkey = r["uri"].rsplit("/", 1)[-1]
        link = f"https://bsky.app/profile/{os.environ['BSKY_HANDLE']}/post/{rkey}"
        state["posted"][p["id"]] = {"uri": r["uri"], "url": link, "at": now_utc().isoformat()}
        print("  gepostet:", link)
    if not a.dry_run:
        save_state(state)


if __name__ == "__main__":
    main()
