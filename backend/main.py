import asyncio
import json
import os
import re
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from prompts import SYSTEM_PROMPT
from mercari_client import demo_mode as mercari_demo_mode, mercari_session
from rakuten_client import demo_mode as rakuten_demo_mode, rakuten_session
from schemas import ChatRequest

load_dotenv()

# --- Marketplace backend selection -----------------------------------------
# SEARCH_BACKEND=mercari (default) | rakuten. The agent loop is identical for
# both — each session exposes the same list_tools()/call_tool() surface.
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "mercari").lower()
if SEARCH_BACKEND == "rakuten":
    marketplace_session = rakuten_session
    demo_mode = rakuten_demo_mode
    MARKETPLACE = "Rakuten Ichiba"
    _PROMPT_SUBS = {}
else:
    marketplace_session = mercari_session
    demo_mode = mercari_demo_mode
    MARKETPLACE = "Mercari"
    # Re-brand the (Rakuten-authored) prompt for Mercari without a full rewrite.
    _PROMPT_SUBS = {
        "Rakuten Ichiba (楽天市場)": "Mercari (メルカリ)",
        "楽天市場": "メルカリ",
        "Rakuten": "Mercari",
    }

MARKETPLACE_PROMPT = SYSTEM_PROMPT
for _old, _new in _PROMPT_SUBS.items():
    MARKETPLACE_PROMPT = MARKETPLACE_PROMPT.replace(_old, _new)
PRODUCTS_RE = re.compile(r"<products>\s*(.*?)\s*</products>", re.DOTALL)

THOUGHT_RE = re.compile(r"^\s*thought\b.*?(?=\n\n|$)", re.DOTALL | re.IGNORECASE)


def strip_leaked_reasoning(text: str) -> str:
    """Defensive: some gateways merge thinking blocks into content."""
    cleaned = THOUGHT_RE.sub("", text, count=1).lstrip()
    return cleaned if cleaned else text  # never return empty — fail open


def index_tool_result(text: str, catalog: dict[str, dict]) -> str:
    """Remember every item the tools returned, keyed by itemCode, and hand back
    the copy the MODEL should see — the same data minus the image URLs.

    This is what makes the cards trustworthy: the model only ever names an id,
    and the price/image/url it gets shown come straight back out of `catalog`.
    Since it never has to repeat an image URL, it never has to read one either;
    dropping them keeps long base64 thumbnails out of the context window."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text  # a TOOL ERROR string, not a result — pass it through
    items = data.get("items") if isinstance(data, dict) else None
    if items is None:
        items = [data] if isinstance(data, dict) and data.get("itemCode") else []
    for item in items:
        if isinstance(item, dict) and item.get("itemCode"):
            catalog[item["itemCode"]] = dict(item)
            item.pop("image", None)
    return json.dumps(data, ensure_ascii=False)


def build_cards(products: list[dict], catalog: dict[str, dict]) -> list[dict]:
    """Turn the model's [{id, note}] into full cards using real tool data.

    Anything the model names that we never saw in a tool result is dropped —
    a hallucinated id yields no card rather than a fabricated one."""
    cards = []
    for p in products:
        item = catalog.get(str(p.get("id", "")))
        if not item:
            print(f"card dropped — unknown id {p.get('id')!r}")
            continue
        card = {
            "id": item["itemCode"],
            "name": item["name"],
            "price": item["price"],
            "url": item["url"],
        }
        if item.get("image"):
            card["image"] = item["image"]
        note = p.get("note")
        if isinstance(note, str) and note.strip():
            card["note"] = note.strip()[:60]
        cards.append(card)
    return cards


def extract_products(text: str) -> tuple[str, list[dict] | None]:
    """Lift the <products> JSON block out of the model's reply.
    Returns (clean_text, products or None). Fails safe: on any parse
    problem the block is still stripped so raw JSON never reaches the UI."""
    match = PRODUCTS_RE.search(text)
    if not match:
        return text, None
    clean = PRODUCTS_RE.sub("", text).strip()
    try:
        products = json.loads(match.group(1))
        if not isinstance(products, list):
            return clean, None
        return clean, products[:6]
    except json.JSONDecodeError:
        print("products block parse failed — stripped, no cards")
        return clean, None


REQUIRED_VARS = ["AIM_API_KEY", "AIM_BASE_URL"]
if SEARCH_BACKEND == "rakuten" and not demo_mode():
    # Mercari needs no marketplace credentials — it mints its own DPoP token.
    REQUIRED_VARS += ["RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY"]

for var in REQUIRED_VARS:
    if not os.environ.get(var):
        raise RuntimeError(
            f"{var} is not set — check backend/.env "
            "(no Rakuten keys yet? set RAKUTEN_DEMO_MODE=1 to run on fixtures)"
        )

if demo_mode():
    # ASCII only: Windows consoles default to cp1252 and a non-ASCII print here
    # crashes the process at import time.
    print(f"[WARNING] DEMO_MODE on - serving snapshot/fixture products, not "
          f"the live {MARKETPLACE} catalog.")

app = FastAPI(title=f"Suki — {MARKETPLACE} Agent API")

DEFAULT_ORIGINS = [
    "https://kapruka-agent-sigma.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
]


def allowed_origins() -> list[str]:
    extra = os.environ.get("ALLOWED_ORIGINS", "")
    origins = list(DEFAULT_ORIGINS)
    if extra:
        origins.extend(origin.strip() for origin in extra.split(",") if origin.strip())
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

client = AsyncOpenAI(
    api_key=os.environ["AIM_API_KEY"],
    base_url=os.environ["AIM_BASE_URL"],  # ← the one line that redirects the SDK
)

MODEL = os.environ.get("MODEL", "aim/gemini-3-flash")
MAX_TURNS = 8  # safety cap on loop iterations


async def run_tool(session, tc) -> str:
    """Execute one tool call; errors become information for the model."""
    args: dict[str, Any] = json.loads(tc.function.arguments or "{}")
    try:
        text = await session.call_tool(tc.function.name, args)
    except Exception as exc:
        print(f"tool error [{tc.function.name}]: {exc!r}")
        text = (
            f"TOOL ERROR: {tc.function.name} failed (possibly rate-limited). "
            "Do not retry immediately. Work with what you have, or tell the "
            "customer to try again shortly — in their language."
        )
    return text[:50_000]


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/")
async def root():
    return {"service": f"Suki — {MARKETPLACE} shopping agent API", "health": "/health"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config")
async def config():
    """Lets the UI warn the audience when products aren't the real catalog."""
    return {"demo": demo_mode()}


@app.post("/chat")
async def chat(req: ChatRequest):
    async def event_stream():
        try:
            async with marketplace_session() as session:
                tool_defs = await session.list_tools()
                catalog: dict[str, dict] = {}  # itemCode -> real item, for cards

                # Explicit annotation — fixes the too-narrow inference (Error 1)
                # and satisfies create()'s signature (Error 2)
                today = datetime.now(ZoneInfo("Asia/Colombo")).strftime("%A, %Y-%m-%d")
                messages: list[ChatCompletionMessageParam] = [
                    {
                        "role": "system",
                        "content": MARKETPLACE_PROMPT
                        + f"\n\n# TODAY\nToday is {today} (Sri Lanka time).",
                    }
                ]
                for m in req.messages:
                    if m.role == "user":
                        messages.append({"role": "user", "content": m.content})
                    else:
                        messages.append({"role": "assistant", "content": m.content})

                for _ in range(MAX_TURNS):
                    resp = await client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        tools=tool_defs,
                        max_tokens=4096,
                        temperature=0.4,
                    )
                    msg = resp.choices[0].message

                    if msg.tool_calls:
                        # The one honest cast: model_dump() is dynamic data,
                        # provably-correct typing is impossible here by nature
                        messages.append(
                            cast(
                                ChatCompletionMessageParam,
                                {
                                    "role": "assistant",
                                    "content": msg.content,
                                    "tool_calls": [
                                        tc.model_dump() for tc in msg.tool_calls
                                    ],
                                },
                            )
                        )

                        function_calls = [
                            tc for tc in msg.tool_calls if tc.type == "function"
                        ]

                        # announce all tools at once — the UI shows the plan
                        for tc in function_calls:
                            yield sse({"type": "tool", "name": tc.function.name})

                        # execute them CONCURRENTLY
                        results = await asyncio.gather(
                            *(run_tool(session, tc) for tc in function_calls)
                        )

                        for tc, result_text in zip(function_calls, results):
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": index_tool_result(result_text, catalog),
                                }
                            )
                        continue
                    # 4. No tool calls → final answer
                    clean_text, products = extract_products(
                        strip_leaked_reasoning(msg.content or "")
                    )
                    cards = build_cards(products, catalog) if products else []
                    if cards:
                        yield sse({"type": "products", "items": cards})
                    yield sse({"type": "text", "text": clean_text})
                    break

        except Exception as exc:
            print(f"stream error: {exc!r}")
            yield sse({"type": "error", "message": "Something went wrong"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
