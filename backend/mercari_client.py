"""Mercari (メルカリ) search backend — a drop-in replacement for rakuten_client.

Same agent-facing surface as RakutenSession (list_tools / call_tool returning a
JSON {"items": [...]} payload with itemCode/name/price/url/image), so main.py can
swap marketplaces without touching the agent loop.

Mercari has no public API key: its web frontend calls api.mercari.jp with a
self-signed DPoP proof-of-possession JWT (ES256). We mint the same token here —
a fresh keypair per request — so no credentials are needed.
"""

import base64
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from openai.types.chat import ChatCompletionToolUnionParam

SEARCH_URL = "https://api.mercari.jp/v2/entities:search"
_SNAPSHOT_PATH = Path(__file__).with_name("mercari_snapshot.json")


def demo_mode() -> bool:
    return os.environ.get("MERCARI_DEMO_MODE", "").lower() in ("1", "true", "yes")


# Same public sort vocabulary as the Rakuten client so the prompt's guidance
# (sort="-reviewAverage" for "best", "+itemPrice" for "cheap") keeps working.
# Mercari has no star ratings, so "best/most reviewed" maps to most-liked.
SORT_VALUES = [
    "standard",
    "+itemPrice",
    "-itemPrice",
    "-reviewCount",
    "-reviewAverage",
    "-updateTimestamp",
]
_SORT_MAP = {
    "standard": ("SORT_SCORE", "ORDER_DESC"),
    "+itemPrice": ("SORT_PRICE", "ORDER_ASC"),
    "-itemPrice": ("SORT_PRICE", "ORDER_DESC"),
    "-reviewCount": ("SORT_NUM_LIKES", "ORDER_DESC"),
    "-reviewAverage": ("SORT_NUM_LIKES", "ORDER_DESC"),
    "-updateTimestamp": ("SORT_CREATED_TIME", "ORDER_DESC"),
}

TOOL_DEFS: list[ChatCompletionToolUnionParam] = [
    cast(
        ChatCompletionToolUnionParam,
        {
            "type": "function",
            "function": {
                "name": "mercari_search_items",
                "description": (
                    "Search the live Mercari (メルカリ) marketplace. Returns up to "
                    "`hits` items with name, price in yen, image and URL. Keywords "
                    "may be Japanese or English; Japanese keywords match far more "
                    "items, so translate the shopper's intent into Japanese when "
                    "you can (e.g. 'chocolate gift' -> 'チョコレート ギフト')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Search words, space separated.",
                        },
                        "min_price": {
                            "type": "integer",
                            "description": "Minimum price in JPY (yen, not rupees).",
                        },
                        "max_price": {
                            "type": "integer",
                            "description": "Maximum price in JPY (yen, not rupees).",
                        },
                        "sort": {
                            "type": "string",
                            "enum": SORT_VALUES,
                            "description": (
                                "'standard' is Mercari's relevance order. "
                                "'+itemPrice' cheapest first, '-itemPrice' priciest "
                                "first, '-reviewAverage' most popular first."
                            ),
                        },
                        "page": {
                            "type": "integer",
                            "description": "Result page, 1-100. Use 2 for 'show me more'.",
                        },
                        "hits": {
                            "type": "integer",
                            "description": "Items per page, 1-30. Default 10.",
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
    ),
]


def _item_url(item: dict[str, Any]) -> str:
    """Mercari C2C items live at /item/{id}; Mercari Shops items at /shops/product/{id}."""
    iid = str(item.get("id") or "")
    itype = item.get("itemType") or ""
    if itype == "ITEM_TYPE_BEYOND" or not iid.startswith("m"):
        return f"https://jp.mercari.com/shops/product/{iid}"
    return f"https://jp.mercari.com/item/{iid}"


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    """Trim a Mercari item to the fields the agent and cards need."""
    raw_price = item.get("price")
    try:
        price = int(raw_price)
    except (TypeError, ValueError):
        price = None
    thumbs = item.get("thumbnails") or []
    shaped = {
        "itemCode": item.get("id"),
        "name": item.get("name"),
        "price": f"¥{price:,}" if price is not None else None,
        "shop": item.get("shopName") or None,
        "url": _item_url(item),
        "image": thumbs[0] if thumbs else None,
    }
    return {k: v for k, v in shaped.items() if v is not None}


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_dpop(key: ec.EllipticCurvePrivateKey) -> str:
    """A DPoP proof JWT (ES256) Mercari's API accepts in place of an API key."""
    nums = key.public_key().public_numbers()
    header = {
        "typ": "dpop+jwt",
        "alg": "ES256",
        "jwk": {
            "crv": "P-256",
            "kty": "EC",
            "x": _b64url(nums.x.to_bytes(32, "big")),
            "y": _b64url(nums.y.to_bytes(32, "big")),
        },
    }
    payload = {
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        "htu": SEARCH_URL,
        "htm": "POST",
        "uuid": str(uuid.uuid4()),
    }
    signing_input = (
        _b64url(json.dumps(header).encode())
        + "."
        + _b64url(json.dumps(payload).encode())
    )
    der = key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"{signing_input}.{sig}"


def _search_body(keyword: str, sort: str, order: str, page: int, hits: int,
                 min_price: int, max_price: int) -> dict[str, Any]:
    return {
        "userId": "",
        "pageSize": hits,
        "pageToken": f"v1:{page - 1}" if page > 1 else "",
        "searchSessionId": uuid.uuid4().hex,
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": keyword,
            "excludeKeyword": "",
            "sort": sort,
            "order": order,
            "status": ["STATUS_ON_SALE"],
            "sizeId": [], "categoryId": [], "brandId": [], "sellerId": [],
            "priceMin": min_price, "priceMax": max_price,
            "itemConditionId": [], "shippingPayerId": [], "shippingFromArea": [],
            "shippingMethod": [], "colorId": [], "hasCoupon": False,
            "attributes": [], "itemTypes": [], "skuIds": [], "shopIds": [],
        },
        "defaultDatabaseId": "DATABASE_ID_DEFAULT",
        "serviceFrom": "suruga",
        "withItemBrand": True,
        "withItemPromotions": True,
        "withItemSizes": True,
        "useDynamicAttribute": True,
        "withSuggestedItems": True,
        "withProductSuggest": True,
    }


class MercariSession:
    """The agent-facing tool surface for the live Mercari marketplace."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def list_tools(self) -> list[ChatCompletionToolUnionParam]:
        return TOOL_DEFS

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "mercari_search_items":
            return await self._search(args)
        return f"TOOL ERROR: unknown tool {name}"

    async def _search(self, args: dict[str, Any]) -> str:
        hits = min(max(int(args.get("hits") or 10), 1), 30)
        page = min(max(int(args.get("page") or 1), 1), 100)
        sort, order = _SORT_MAP.get(args.get("sort") or "standard",
                                    _SORT_MAP["standard"])
        min_price = int(args["min_price"]) if args.get("min_price") is not None else 0
        max_price = int(args["max_price"]) if args.get("max_price") is not None else 0
        body = _search_body(args["keyword"], sort, order, page, hits,
                            min_price, max_price)

        key = ec.generate_private_key(ec.SECP256R1())
        headers = {
            "DPoP": _make_dpop(key),
            "X-Platform": "web",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://jp.mercari.com",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
        }
        resp = await self._http.post(SEARCH_URL, json=body, headers=headers)
        if resp.status_code == 429:
            raise RuntimeError("rate limited by Mercari (429)")
        resp.raise_for_status()
        raw = resp.json()
        items = [_shape(i) for i in (raw.get("items") or [])]
        return _pack(items, args["keyword"])


def _pack(items: list[dict[str, Any]], keyword: str) -> str:
    if not items:
        return json.dumps(
            {
                "items": [],
                "note": f"No Mercari items matched {keyword!r}. "
                "Try broader or Japanese keywords, or a wider price range.",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"items": items, "totalMatches": len(items)}, ensure_ascii=False
    )


class DemoSession(MercariSession):
    """Same agent surface, fed from a captured snapshot of real Mercari results.

    Insurance for a live presentation: if the venue blocks api.mercari.jp, flip
    MERCARI_DEMO_MODE=1 and the exact same code path renders real Japanese
    products (names, prices, thumbnails) from mercari_snapshot.json instead."""

    def __init__(self) -> None:  # deliberately skips super(): no http
        with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
            data: dict[str, list[dict[str, Any]]] = json.load(f)
        self._pool = [i for items in data.values() for i in items]

    async def _search(self, args: dict[str, Any]) -> str:
        keyword = str(args.get("keyword") or "")
        tokens = [t for t in keyword.replace("　", " ").split() if t]
        hits = min(max(int(args.get("hits") or 10), 1), 30)

        def matches(item: dict[str, Any]) -> bool:
            name = item.get("name") or ""
            return any(t in name for t in tokens)

        pool = [i for i in self._pool if matches(i)] or self._pool
        shaped = [_shape(i) for i in pool]

        lo = args.get("min_price")
        hi = args.get("max_price")

        def price_ok(it: dict[str, Any]) -> bool:
            digits = "".join(c for c in it.get("price", "") if c.isdigit())
            if not digits:
                return True
            p = int(digits)
            if lo is not None and p < int(lo):
                return False
            if hi is not None and p > int(hi):
                return False
            return True

        shaped = [i for i in shaped if price_ok(i)]
        if args.get("sort") == "+itemPrice":
            shaped.sort(key=lambda it: int("".join(c for c in it.get("price", "0") if c.isdigit()) or 0))
        elif args.get("sort") == "-itemPrice":
            shaped.sort(key=lambda it: int("".join(c for c in it.get("price", "0") if c.isdigit()) or 0), reverse=True)

        return _pack(shaped[:hits], keyword)


@asynccontextmanager
async def mercari_session():
    """Open a session against the live Mercari API (or the snapshot) for one request."""
    if demo_mode():
        yield DemoSession()
        return
    async with httpx.AsyncClient(timeout=20.0) as http:
        yield MercariSession(http)
