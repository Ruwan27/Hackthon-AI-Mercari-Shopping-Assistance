import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
from openai.types.chat import ChatCompletionToolUnionParam

import demo_fixtures

SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"


def demo_mode() -> bool:
    return os.environ.get("RAKUTEN_DEMO_MODE", "").lower() in ("1", "true", "yes")

# Rakuten serves thumbnails at ?_ex=128x128; the card grid wants something sharper.
_EX_RE = re.compile(r"\?_ex=\d+x\d+$")
CARD_IMAGE_SIZE = "400x400"

SORT_VALUES = [
    "standard",
    "+itemPrice",
    "-itemPrice",
    "-reviewCount",
    "-reviewAverage",
    "-updateTimestamp",
]

TOOL_DEFS: list[ChatCompletionToolUnionParam] = [
    cast(
        ChatCompletionToolUnionParam,
        {
            "type": "function",
            "function": {
                "name": "rakuten_search_items",
                "description": (
                    "Search the live Rakuten Ichiba (楽天市場) catalog. Returns up to "
                    "`hits` items with name, price in yen, shop, rating, image and URL. "
                    "Keywords may be Japanese or English; Japanese keywords match far "
                    "more items, so translate the shopper's intent into Japanese when "
                    "you can (e.g. 'chocolate gift' -> 'チョコレート ギフト')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Search words, space separated. Max 128 bytes.",
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
                                "'standard' is Rakuten's relevance order. '+itemPrice' "
                                "cheapest first, '-itemPrice' priciest first, "
                                "'-reviewAverage' best rated first."
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
    cast(
        ChatCompletionToolUnionParam,
        {
            "type": "function",
            "function": {
                "name": "rakuten_get_item",
                "description": (
                    "Look up one Rakuten item by its exact itemCode (from a previous "
                    "search result) to get its full caption, image and URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_code": {
                            "type": "string",
                            "description": "itemCode exactly as returned by rakuten_search_items.",
                        }
                    },
                    "required": ["item_code"],
                },
            },
        },
    ),
]


def _big_image(item: dict[str, Any]) -> str | None:
    """Pick the largest thumbnail Rakuten offers and ask its CDN to upscale it."""
    for key in ("mediumImageUrls", "smallImageUrls"):
        urls = item.get(key) or []
        for entry in urls:
            # The API has shipped both [{"imageUrl": "..."}] and ["..."] shapes.
            url = entry.get("imageUrl") if isinstance(entry, dict) else entry
            if url:
                return _EX_RE.sub(f"?_ex={CARD_IMAGE_SIZE}", url)
    return None


def _unwrap(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Items have historically come back as [{"Item": {...}}] and as [{...}]."""
    items = []
    for entry in raw.get("Items") or []:
        item = entry.get("Item", entry) if isinstance(entry, dict) else None
        if isinstance(item, dict):
            items.append(item)
    return items


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    """Trim Rakuten's ~40 fields per item down to what the agent reasons about."""
    price = item.get("itemPrice")
    shaped = {
        "itemCode": item.get("itemCode"),
        "name": item.get("itemName"),
        "price": f"¥{price:,}" if isinstance(price, int) else None,
        "shop": item.get("shopName"),
        "url": item.get("itemUrl"),
        "image": _big_image(item),
        "rating": item.get("reviewAverage") or None,
        "reviewCount": item.get("reviewCount") or None,
        "caption": (item.get("itemCaption") or "")[:400] or None,
    }
    return {k: v for k, v in shaped.items() if v is not None}


class RakutenSession:
    """The agent-facing tool surface, shaped like the MCP session it replaces."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._auth = {
            "applicationId": os.environ["RAKUTEN_APPLICATION_ID"],
            "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        }

    async def list_tools(self) -> list[ChatCompletionToolUnionParam]:
        return TOOL_DEFS

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.get(
            SEARCH_URL,
            params={**self._auth, "format": "json", "imageFlag": 1, **params},
        )
        if resp.status_code == 429:
            raise RuntimeError("rate limited by Rakuten (429)")
        resp.raise_for_status()
        return resp.json()

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "rakuten_search_items":
            return await self._search(args)
        if name == "rakuten_get_item":
            return await self._get_item(args)
        return f"TOOL ERROR: unknown tool {name}"

    async def _search(self, args: dict[str, Any]) -> str:
        params: dict[str, Any] = {
            "keyword": args["keyword"],
            "hits": min(max(int(args.get("hits") or 10), 1), 30),
            "page": min(max(int(args.get("page") or 1), 1), 100),
        }
        if args.get("min_price") is not None:
            params["minPrice"] = int(args["min_price"])
        if args.get("max_price") is not None:
            params["maxPrice"] = int(args["max_price"])
        if args.get("sort") in SORT_VALUES:
            params["sort"] = args["sort"]

        raw = await self._get(params)
        items = [_shape(i) for i in _unwrap(raw)]
        if not items:
            return json.dumps(
                {
                    "items": [],
                    "note": f"No Rakuten items matched {params['keyword']!r}. "
                    "Try broader or Japanese keywords, or a wider price range.",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "items": items,
                "page": raw.get("page"),
                "pageCount": raw.get("pageCount"),
                "totalMatches": raw.get("count"),
            },
            ensure_ascii=False,
        )

    async def _get_item(self, args: dict[str, Any]) -> str:
        raw = await self._get({"itemCode": args["item_code"], "hits": 1})
        items = _unwrap(raw)
        if not items:
            return json.dumps(
                {"error": f"No item with itemCode {args['item_code']!r}."},
                ensure_ascii=False,
            )
        return json.dumps(_shape(items[0]), ensure_ascii=False)


class DemoSession(RakutenSession):
    """Same agent surface, fed from demo_fixtures instead of the network.

    Only the transport is replaced: _search / _get_item / _shape below are the
    production ones, so what the demo shows is what the live API path renders.
    """

    def __init__(self) -> None:  # deliberately skips super(): no http, no keys
        pass

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        return demo_fixtures.search(params)


@asynccontextmanager
async def rakuten_session():
    """Open a session against the Rakuten Ichiba API (or fixtures) for one request."""
    if demo_mode():
        yield DemoSession()
        return
    async with httpx.AsyncClient(timeout=20.0) as http:
        yield RakutenSession(http)
