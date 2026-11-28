#!/usr/bin/env python3
"""watch/headlines.json の内容を、静的なHTMLと更新日の情報に書き出す。

日次ヘッドラインを更新したあとに、リポジトリのルートで
    python3 -I watch/build.py
を実行する。次の5か所をまとめて書き換える。

1. watch/index.html の hl-data（JSONの控え）
2. watch/index.html の #hl-all と #hl-top（JavaScriptなしでも読める見出しのHTML）
3. watch/index.html 上部の「YYYY年M月D日更新」
4. watch/index.html の構造化データ（JSON-LD、id="watch-ld"）
5. sitemap.xml の /watch/ の lastmod

何度実行しても同じ結果になる。
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "watch" / "index.html"
DATA = ROOT / "watch" / "headlines.json"
SITEMAP = ROOT / "sitemap.xml"
URL = "https://synapxis.jp/watch/"
TITLE = "飲食SaaS 市場ウォッチ｜業界動向｜株式会社SynapXis"


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


def jsonld(data, items):
    elems = []
    for i, h in enumerate(items, 1):
        art = {
            "@type": "NewsArticle",
            "headline": h["title"],
            "description": h["summary"],
            "articleSection": h["cat"],
            "isBasedOn": h["url"],
            "inLanguage": "ja",
            "author": {"@type": "Organization", "name": "株式会社SynapXis", "url": "https://synapxis.jp/"},
        }
        if len(h["date"]) == 10:
            art["datePublished"] = h["date"]
        elems.append({"@type": "ListItem", "position": i, "item": art})
    obj = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": TITLE,
        "url": URL,
        "inLanguage": "ja",
        "description": "飲食向けSaaSと飲食業界の動きを、公表情報から出典付きで毎日まとめています。",
        "dateModified": data["updated"],
        "publisher": {"@type": "Organization", "name": "株式会社SynapXis", "url": "https://synapxis.jp/"},
        "mainEntity": {"@type": "ItemList", "name": "日次ヘッドライン", "itemListElement": elems},
    }
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    items = sorted(data["items"], key=lambda h: h["date"], reverse=True)
    y, m, d = (int(x) for x in data["updated"].split("-"))

    page = PAGE.read_text(encoding="utf-8")

    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page, n = re.subn(
        r'(<script type="application/json" id="hl-data">).*?(</script>)',
        lambda mm: mm.group(1) + blob + mm.group(2), page, flags=re.S)
    if n != 1:
        sys.exit("hl-data が見つかりません")

    page = put_block(page, "hl-all", render_all(items))
    page = put_block(page, "hl-top", "".join(item(h) for h in items[:4]))

    page, n = re.subn(r'<span class="upd">[^<]*</span>',
                      f'<span class="upd">{y}年{m}月{d}日更新</span>', page, count=1)
    if n != 1:
        sys.exit("更新日の表示が見つかりません")

    ld = f'<script type="application/ld+json" id="watch-ld">{jsonld(data, items)}</script>'
    if 'id="watch-ld"' in page:
        page = re.sub(r'<script type="application/ld\+json" id="watch-ld">.*?</script>', lambda mm: ld, page, flags=re.S)
    else:
        page = page.replace("</head>", ld + "\n</head>", 1)

    PAGE.write_text(page, encoding="utf-8")

    sm = SITEMAP.read_text(encoding="utf-8")
    sm, n = re.subn(r"(<loc>https://synapxis\.jp/watch/</loc>\s*<lastmod>)[^<]*(</lastmod>)",
                    lambda mm: mm.group(1) + data["updated"] + mm.group(2), sm)
    if n != 1:
        sys.exit("sitemap.xml に /watch/ の lastmod が見つかりません")
    SITEMAP.write_text(sm, encoding="utf-8")

    # 確認
    page = PAGE.read_text(encoding="utf-8")
    json.loads(re.search(r'id="hl-data">(.*?)</script>', page, re.S).group(1))
    json.loads(re.search(r'id="watch-ld">(.*?)</script>', page, re.S).group(1))
    print(f"OK: {len(items)}件、更新日 {data['updated']}")


if __name__ == "__main__":
    main()
