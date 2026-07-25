"""Offline stand-in for the Rakuten Ichiba API.

Enabled with RAKUTEN_DEMO_MODE=1, for showing the agent off without API keys.
`search()` returns payloads in the SAME shape the live API returns, so the
production parsing path in rakuten_client.py runs unchanged — demo mode
exercises real code, it only swaps where the bytes come from.

Honesty rules for this file:
- Items are INVENTED. Names, prices and ratings are plausible, not real.
- Images are obviously-placeholder SVGs, never a real product photo.
- `itemUrl` points at a real Rakuten SEARCH for that product name, so a click
  lands somewhere real instead of a 404 on a fabricated item page.
"""

import base64
from urllib.parse import quote

# Palette per category — keeps the card grid looking deliberate, not random.
_COLORS = {
    "sweets": ("#7c3f2e", "#f7e6dc", "🍫"),
    "kitchen": ("#2f5d50", "#dff0e8", "☕"),
    "beauty": ("#8a2f5d", "#fbe0ee", "🧴"),
    "stationery": ("#2b4a7c", "#dfe8fa", "🖊️"),
    "tech": ("#333a45", "#e4e7ec", "🎧"),
    "flowers": ("#a3325a", "#fde2ec", "💐"),
    "tea": ("#3f6b2b", "#e6f3dc", "🍵"),
    "towel": ("#2f5f7c", "#ddeef8", "🧺"),
    "toys": ("#a35a1f", "#fdeada", "🧸"),
}


def _placeholder(category: str, label: str) -> str:
    """A self-contained SVG data URI. Marked DEMO so no one mistakes it for a photo."""
    fg, bg, emoji = _COLORS.get(category, ("#444", "#eee", "🎁"))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">'
        f'<rect width="400" height="400" fill="{bg}"/>'
        f'<text x="200" y="215" font-size="130" text-anchor="middle">{emoji}</text>'
        f'<text x="200" y="285" font-size="22" text-anchor="middle" '
        f'font-family="sans-serif" fill="{fg}">{label}</text>'
        f'<text x="200" y="330" font-size="15" text-anchor="middle" '
        f'font-family="sans-serif" fill="{fg}" opacity="0.65">DEMO IMAGE</text>'
        "</svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _url(name: str) -> str:
    return f"https://search.rakuten.co.jp/search/mall/{quote(name)}/"


def _item(code, name, price, shop, cat, label, rating, reviews, caption, tags):
    return {
        "itemCode": code,
        "itemName": name,
        "itemPrice": price,
        "shopName": shop,
        "itemUrl": _url(name),
        "itemCaption": caption,
        "reviewAverage": rating,
        "reviewCount": reviews,
        "mediumImageUrls": [{"imageUrl": _placeholder(cat, label)}],
        "_tags": tags,  # demo-only matching aid; stripped before returning
    }


CATALOG = [
    _item("royce-demo:10000101", "ロイズ 生チョコレート ギフトボックス", 2980,
          "ロイズ 楽天市場店", "sweets", "Chocolate", 4.71, 1203,
          "北海道の定番、口どけのよい生チョコレート。化粧箱入りで贈り物に最適です。",
          ["チョコレート", "チョコ", "ギフト", "プレゼント", "スイーツ", "お菓子",
           "chocolate", "sweets", "gift"]),
    _item("godiva-demo:10000102", "ゴディバ アソートメント 20粒", 5400,
          "GODIVA 楽天市場店", "sweets", "Chocolate", 4.62, 842,
          "定番のアソートメント。特別な日の贈り物に。",
          ["チョコレート", "チョコ", "ギフト", "プレゼント", "高級", "スイーツ",
           "chocolate", "luxury", "gift"]),
    _item("shiroi-demo:10000103", "白い恋人 24枚入", 1620,
          "石屋製菓 楽天市場店", "sweets", "Cookies", 4.55, 2310,
          "北海道土産の定番、ホワイトチョコをラング・ド・シャで挟んだお菓子。",
          ["お菓子", "クッキー", "ギフト", "お土産", "北海道", "スイーツ",
           "cookies", "sweets", "gift"]),
    _item("kitkat-demo:10000104", "キットカット 抹茶 12枚", 980,
          "ネスレ 楽天市場店", "sweets", "Matcha KitKat", 4.31, 517,
          "宇治抹茶を使ったキットカット。手軽なプチギフトに。",
          ["チョコレート", "抹茶", "お菓子", "安い", "プチギフト",
           "chocolate", "matcha", "cheap", "sweets"]),
    _item("mug-demo:10000201", "有田焼 マグカップ 化粧箱入り", 3300,
          "有田焼やきもの市場", "kitchen", "Mug", 4.48, 233,
          "職人が仕上げた有田焼のマグカップ。母の日や誕生日の贈り物に。",
          ["マグカップ", "カップ", "食器", "ギフト", "プレゼント", "母",
           "mug", "kitchen", "gift"]),
    _item("nanbu-demo:10000202", "南部鉄器 急須 0.6L", 8800,
          "岩鋳 楽天市場店", "kitchen", "Teapot", 4.66, 156,
          "伝統工芸、南部鉄器の急須。長く使える上質な贈り物。",
          ["急須", "鉄瓶", "食器", "高級", "ギフト", "伝統",
           "teapot", "luxury", "kitchen", "gift"]),
    _item("towel-demo:10000301", "今治タオル ギフトセット 3枚", 4200,
          "今治タオル本舗", "towel", "Towel Set", 4.59, 689,
          "今治産の柔らかいタオル3枚セット。のし対応。",
          ["タオル", "ギフト", "プレゼント", "母", "父", "実用",
           "towel", "gift"]),
    _item("shiseido-demo:10000401", "資生堂 スキンケア トライアルセット", 3850,
          "資生堂 楽天市場店", "beauty", "Skincare", 4.44, 921,
          "人気のスキンケアをそろえたセット。女性への贈り物に。",
          ["スキンケア", "化粧品", "コスメ", "ギフト", "プレゼント", "女性", "彼女",
           "skincare", "beauty", "gift"]),
    _item("bath-demo:10000402", "入浴剤 ギフトセット 10種", 2200,
          "バスクリン 楽天市場店", "beauty", "Bath Set", 4.38, 445,
          "香りの異なる入浴剤の詰め合わせ。ちょっとした贈り物に。",
          ["入浴剤", "バス", "ギフト", "プレゼント", "リラックス",
           "bath", "beauty", "gift"]),
    _item("pilot-demo:10000501", "パイロット 万年筆 カスタム74", 11000,
          "パイロット 楽天市場店", "stationery", "Fountain Pen", 4.73, 312,
          "定番の万年筆。名入れ対応、就職祝いや記念日に。",
          ["万年筆", "ペン", "文房具", "高級", "ギフト", "記念",
           "pen", "stationery", "luxury", "gift"]),
    _item("hobo-demo:10000502", "ほぼ日手帳 2026 オリジナル", 2640,
          "ほぼ日 楽天市場店", "stationery", "Planner", 4.51, 588,
          "1日1ページの人気手帳。カバーと合わせて贈り物に。",
          ["手帳", "文房具", "ノート", "ギフト",
           "planner", "notebook", "stationery", "gift"]),
    _item("sony-demo:10000601", "ソニー ワイヤレスイヤホン WF-C700N", 14300,
          "ソニーストア 楽天市場店", "tech", "Earbuds", 4.57, 1876,
          "ノイズキャンセリング搭載のワイヤレスイヤホン。",
          ["イヤホン", "ワイヤレス", "音楽", "ガジェット", "ギフト", "誕生日",
           "earbuds", "headphones", "tech", "gift"]),
    _item("anker-demo:10000602", "Anker モバイルバッテリー 10000mAh", 3990,
          "Anker Japan 公式", "tech", "Power Bank", 4.64, 3401,
          "軽量で持ち運びやすいモバイルバッテリー。",
          ["モバイルバッテリー", "充電器", "ガジェット", "実用", "安い",
           "battery", "charger", "tech", "cheap"]),
    _item("flower-demo:10000701", "プリザーブドフラワー ボックスアレンジ", 6600,
          "花由 楽天市場店", "flowers", "Flowers", 4.69, 734,
          "枯れないプリザーブドフラワー。母の日や記念日に。",
          ["花", "フラワー", "ギフト", "プレゼント", "母", "記念日", "誕生日",
           "flowers", "anniversary", "gift"]),
    _item("uji-demo:10000801", "宇治抹茶 ギフト 詰め合わせ", 3780,
          "伊藤久右衛門", "tea", "Matcha Set", 4.61, 402,
          "宇治抹茶のスイーツとお茶の詰め合わせ。",
          ["抹茶", "お茶", "日本茶", "ギフト", "お土産", "スイーツ",
           "matcha", "tea", "gift"]),
    _item("shizuoka-demo:10000802", "静岡茶 煎茶 詰め合わせ", 2160,
          "静岡茶問屋", "tea", "Green Tea", 4.42, 198,
          "静岡産の煎茶セット。日常使いにも贈り物にも。",
          ["お茶", "日本茶", "煎茶", "ギフト", "安い",
           "tea", "gift", "cheap"]),
    _item("plush-demo:10000901", "ぬいぐるみ くま 特大 60cm", 4980,
          "ぬいぐるみ専門店", "toys", "Teddy Bear", 4.35, 267,
          "ふわふわの特大ぬいぐるみ。誕生日や記念日の贈り物に。",
          ["ぬいぐるみ", "くま", "おもちゃ", "ギフト", "誕生日", "彼女", "子供",
           "teddy", "plush", "toys", "gift"]),
    _item("baum-demo:10000105", "バウムクーヘン ギフト 2個入", 1980,
          "ユーハイム 楽天市場店", "sweets", "Baumkuchen", 4.47, 356,
          "しっとり焼き上げたバウムクーヘン。のし対応。",
          ["お菓子", "スイーツ", "バウムクーヘン", "ギフト", "プレゼント",
           "sweets", "cake", "gift"]),
]

# Every fixture carries 'ギフト' or 'gift', so a broad retry always finds stock.
_SORTERS = {
    "+itemPrice": lambda i: i["itemPrice"],
    "-itemPrice": lambda i: -i["itemPrice"],
    "-reviewAverage": lambda i: -i["reviewAverage"],
    "-reviewCount": lambda i: -i["reviewCount"],
}


def _score(item: dict, tokens: list[str]) -> int:
    """Loose relevance: substring hits against the name and the tag list."""
    haystack = (item["itemName"] + " " + " ".join(item["_tags"])).lower()
    return sum(1 for t in tokens if t and t in haystack)


def search(params: dict) -> dict:
    """Mimic IchibaItem/Search: filter, sort, paginate, and wrap like the API."""
    if params.get("itemCode"):
        hits = [i for i in CATALOG if i["itemCode"] == params["itemCode"]]
        return _wrap(hits, page=1, hits_per_page=1)

    tokens = [t for t in str(params.get("keyword", "")).lower().split() if t]
    scored = [(i, _score(i, tokens)) for i in CATALOG]
    matched = [i for i, s in sorted(scored, key=lambda x: -x[1]) if s > 0]

    lo, hi = params.get("minPrice"), params.get("maxPrice")
    if lo is not None:
        matched = [i for i in matched if i["itemPrice"] >= lo]
    if hi is not None:
        matched = [i for i in matched if i["itemPrice"] <= hi]

    sorter = _SORTERS.get(str(params.get("sort", "")))
    if sorter:
        matched.sort(key=sorter)

    per_page = int(params.get("hits", 10))
    page = int(params.get("page", 1))
    start = (page - 1) * per_page
    return _wrap(matched[start : start + per_page], page, per_page, total=len(matched))


def _wrap(items: list[dict], page: int, hits_per_page: int, total: int | None = None) -> dict:
    total = len(items) if total is None else total
    clean = [{k: v for k, v in i.items() if k != "_tags"} for i in items]
    return {
        "count": total,
        "page": page,
        "pageCount": max(1, -(-total // hits_per_page)),
        "hits": len(clean),
        "Items": [{"Item": i} for i in clean],
    }
