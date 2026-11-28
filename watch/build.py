#!/usr/bin/env python3
"""業界動向（/watch/ 配下の各ページ）を、headlines.json と各ページの中身に合わせて更新する。

日次ヘッドラインの更新や年表の移動をしたあとに、リポジトリのルートで
    python3 -I watch/build.py
を実行する。

ページの一覧は watch/pages.json にある（名前、タイトル、説明文、最終更新日、中身の指紋）。
各ページ（watch/index.html、watch/<名前>/index.html）について、次をまとめて書き換える。

1. ヘッドラインを載せるページ（トップと daily）の hl-data（JSONの控え）と、
   #hl-all・#hl-top（<!--hl-all-->…<!--/hl-all--> の目印の中。JavaScriptなしでも読める見出し）
2. 中身が前回から変わったページだけ、最終更新日を今日（日本時間）にする
3. 各ページ上部の「YYYY年M月D日更新」を、そのページの最終更新日にする
4. 各ページの構造化データ（JSON-LD、id="watch-ld"。パンくずリストを含む）
5. sitemap.xml の各ページの lastmod（中身が変わったページだけ動く。無い行は足す）

中身が変わっていなければ何も書き換えないので、何度実行しても同じ結果になる。
日付を指定したいときは --date YYYY-MM-DD を付ける。
"""
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
WATCH = ROOT / "watch"
MANIFEST = WATCH / "pages.json"
DATA = WATCH / "headlines.json"
SITEMAP = ROOT / "sitemap.xml"
BASE = "https://synapxis.jp"
ORG = {"@type": "Organization", "name": "株式会社SynapXis", "url": BASE + "/"}


def page_url(slug):
    return f"{BASE}/watch/" + (f"{slug}/" if slug else "")


def page_file(slug):
    return WATCH / (f"{slug}/index.html" if slug else "index.html")


def esc(s):
    return html.escape(str(s), quote=True)


def dlabel(d):
    p = d.split("-")
    if len(p) == 3:
        return f"{int(p[1])}月{int(p[2])}日"
    return f"{int(p[1])}月（日付未確認）"


def item(h):
    why = f'<div class="hw"><b>見立て</b>　{esc(h["why"])}</div>' if h.get("why") else ""
    return (
        f'<div class="hi"><span class="hc">{esc(h["cat"])}</span>'
        f'<span class="ht">{esc(h["title"])}</span>'
        f'<div class="hs">{esc(h["summary"])}（<a href="{esc(h["url"])}">{esc(h["src"])}</a>）</div>'
        f"{why}</div>"
    )


def render_all(items):
    out, cur = [], None
    for h in items:
        d = h["date"][:10]
        if d != cur:
            cur = d
            out.append(f'<div class="hd">{dlabel(d)}</div>')
        out.append(item(h))
    return "".join(out) or "<p>まだ項目がありません。</p>"


def put_block(page, div_id, inner):
    """<div id="X"> の中身を、目印コメントで囲んで差し替える。"""
    start, end = f"<!--{div_id}-->", f"<!--/{div_id}-->"
    block = f"{start}{inner}{end}"
    if start in page:
        new, n = re.subn(re.escape(start) + r".*?" + re.escape(end), lambda m: block, page, flags=re.S)
    else:
        new, n = re.subn(rf'(<div id="{div_id}"[^>]*>)', lambda m: m.group(1) + block, page, count=1)
    if n != 1:
        sys.exit(f"#{div_id} が見つかりません")
    return new


def news(items):
    elems = []
    for i, h in enumerate(items, 1):
        art = {"@type": "NewsArticle", "headline": h["title"], "description": h["summary"],
               "articleSection": h["cat"], "isBasedOn": h["url"], "inLanguage": "ja", "author": ORG}
        if len(h["date"]) == 10:
            art["datePublished"] = h["date"]
        elems.append({"@type": "ListItem", "position": i, "item": art})
    return elems


def jsonld(slug, meta, modified, items):
    crumbs = [{"@type": "ListItem", "position": 1, "name": "ホーム", "item": BASE + "/"},
              {"@type": "ListItem", "position": 2, "name": "業界動向", "item": page_url("")}]
    if slug:
        crumbs.append({"@type": "ListItem", "position": 3, "name": meta["name"], "item": page_url(slug)})
    pg = {"@type": "CollectionPage" if meta.get("hl") else "WebPage", "@id": page_url(slug) + "#page",
          "url": page_url(slug), "name": meta["title"], "headline": meta["h1"], "description": meta["description"],
          "inLanguage": "ja", "dateModified": modified, "publisher": ORG, "breadcrumb": {"@id": page_url(slug) + "#breadcrumb"}}
    if slug:
        pg["isPartOf"] = {"@type": "CollectionPage", "@id": page_url("") + "#page", "url": page_url("")}
    if meta.get("hl"):
        shown = items if slug else items[:4]
        pg["mainEntity"] = {"@type": "ItemList", "name": "日次ヘッドライン", "itemListElement": news(shown)}
    obj = {"@context": "https://schema.org",
           "@graph": [pg, {"@type": "BreadcrumbList", "@id": page_url(slug) + "#breadcrumb", "itemListElement": crumbs}]}
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def fingerprint(page):
    """更新日と構造化データ（更新日を含む）を除いた中身の指紋。"""
    p = re.sub(r'<span class="upd">[^<]*</span>', "", page)
    p = re.sub(r'<script type="application/ld\+json" id="watch-ld">.*?</script>', "", p, flags=re.S)
    return hashlib.sha256(p.encode("utf-8")).hexdigest()[:16]


def set_sitemap(sm, loc, lastmod):
    pat = re.compile(r"(<url>\s*<loc>" + re.escape(loc) + r"</loc>\s*<lastmod>)[^<]*(</lastmod>)")
    if pat.search(sm):
        return pat.sub(lambda m: m.group(1) + lastmod + m.group(2), sm, count=1)
    entry = f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>\n"
    return sm.replace("</urlset>", entry + "</urlset>", 1)


def main():
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    if "--date" in sys.argv:
        today = sys.argv[sys.argv.index("--date") + 1]
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data = json.loads(DATA.read_text(encoding="utf-8"))
    items = sorted(data["items"], key=lambda h: h["date"], reverse=True)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    sm = SITEMAP.read_text(encoding="utf-8")
    changed = []

    for slug in man["order"]:
        meta = man["pages"][slug]
        f = page_file(slug)
        page = old = f.read_text(encoding="utf-8")

        if meta.get("hl"):
            page, n = re.subn(r'(<script type="application/json" id="hl-data">).*?(</script>)',
                              lambda mm: mm.group(1) + blob + mm.group(2), page, flags=re.S)
            if n != 1:
                sys.exit(f"{f}: hl-data が見つかりません")
            if 'id="hl-all"' in page:
                page = put_block(page, "hl-all", render_all(items))
            if 'id="hl-top"' in page:
                page = put_block(page, "hl-top", "".join(item(h) for h in items[:4]))

        fp = fingerprint(page)
        if fp != meta.get("hash") or not meta.get("modified"):
            meta["hash"], meta["modified"] = fp, today
            changed.append(slug or "(トップ)")
        y, m, d = (int(x) for x in meta["modified"].split("-"))

        page, n = re.subn(r'<span class="upd">[^<]*</span>', f'<span class="upd">{y}年{m}月{d}日更新</span>', page, count=1)
        if n != 1:
            sys.exit(f"{f}: 更新日の表示が見つかりません")
        ld = f'<script type="application/ld+json" id="watch-ld">{jsonld(slug, meta, meta["modified"], items)}</script>'
        page, n = re.subn(r'<script type="application/ld\+json" id="watch-ld">.*?</script>', lambda mm: ld, page, count=1, flags=re.S)
        if n != 1:
            sys.exit(f"{f}: 構造化データ（watch-ld）が見つかりません")

        if page != old:
            f.write_text(page, encoding="utf-8")
        sm = set_sitemap(sm, page_url(slug), meta["modified"])

    if sm != SITEMAP.read_text(encoding="utf-8"):
        SITEMAP.write_text(sm, encoding="utf-8")
    new_man = json.dumps(man, ensure_ascii=False, indent=1) + "\n"
    if new_man != MANIFEST.read_text(encoding="utf-8"):
        MANIFEST.write_text(new_man, encoding="utf-8")

    # 確認：JSONとして読めること
    for slug in man["order"]:
        page = page_file(slug).read_text(encoding="utf-8")
        json.loads(re.search(r'id="watch-ld">(.*?)</script>', page, re.S).group(1))
        if man["pages"][slug].get("hl"):
            json.loads(re.search(r'id="hl-data">(.*?)</script>', page, re.S).group(1))
    print(f"OK: ヘッドライン{len(items)}件、{len(man['order'])}ページ、更新したページ：{'、'.join(changed) or 'なし'}")


if __name__ == "__main__":
    main()
