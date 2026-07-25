#Suki · スキ — AI Shopping Agent for Mercari  🛍️



## What Suki · スキ can do

- **Speak how Engilsh speak** — mirrors the customer's language _and register_,
  including mid-conversation switches and code-switched Singlish/Tanglish
- **Bridge the language gap** — translates the shopper's intent into Japanese
  keywords for Mercari, then explains the Japanese results back in their language
  (product names and ¥ prices stay verbatim; a short gloss is added alongside)
- **Search the live catalog** and present products as rich image cards (never a wall of text)
- **Stay truthful** — every product, price, image and link is grounded in live
  Mercari API results; structured card data bypasses the model entirely

### What it deliberately does not do

Mercari's public API is **read-only** — there is no order or payment endpoint.
Suki searches and recommends; each card deep-links to the real Mercari item page
where the customer checks out themselves. The prompt forbids promising orders,
delivery dates or shipping costs.

## Architecture

Browser ── Next.js (Vercel, static shell + streaming chat UI)
│ POST /chat → SSE stream (tool / products / text events)
FastAPI (Render, persistent process)
│ hand-built agent loop (OpenAI SDK · manual tool orchestration)
│ • per-request session → Mercari  Item Search API
│ • hand-written tool layer (search + item lookup) in OpenAI function-call shape
│ • parallel tool execution (asyncio.gather)
│ • response shaping: ~40 API fields per item trimmed to what the model reasons about
│ • structured <products> extraction; thumbnails upscaled via Mercari's CDN
│ • graceful degradation: tool errors (429s included) are fed back to the model
Claude Sonnet (via OpenAI-compatible gateway; model is env-configurable)

## Engineering notes

- **Manual agent loop** — tools declared as OpenAI function-calling schemas;
  the transcript is the agent's only state
- **Cross-script bridging** — Japanese only ever appears inside tool arguments
  and verbatim tool output; Kiri's own prose stays in Sinhala/Tamil/English
- **Anti-hallucination, in layers** — grounding rules in the system prompt,
  card data extracted server-side from real API responses
  (guarantees in code, preferences in prompts), temperature tuned for
  low-resource-language script stability
- **Multilingual by prompting** — mirroring rules + native-authored few-shot
  examples per language/register; no translation layer (it would destroy
  code-switching)
- **Evaluated** — a 20-row golden test matrix (languages × behaviors ×
  checkout) re-run on every change
- **Resilient** — Pydantic validation at the boundary, bounded loop (MAX_TURNS),
  tool-result truncation, keep-alive against cold starts, CORS allow-list

## Stack

FastAPI · httpx · Mercari  Item Search API · OpenAI SDK (custom base_url) ·
Next.js 16 · Tailwind v4 · react-markdown · Docker Compose · Render + Vercel



## Run with Docker

```bash
cp backend/.env.example backend/.env   # then fill in the four values
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000

Stop with `Ctrl+C`, or run detached: `docker compose up -d --build`.

## Run locally

```bash
# backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the four values
uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev
```


#Suki · スキ — AI Shopping Agent for Mercari  🛍️



## What Suki · スキ can do

- **Speak how Engilsh speak** — mirrors the customer's language _and register_,
  including mid-conversation switches and code-switched Singlish/Tanglish
- **Bridge the language gap** — translates the shopper's intent into Japanese
  keywords for Mercari, then explains the Japanese results back in their language
  (product names and ¥ prices stay verbatim; a short gloss is added alongside)
- **Search the live catalog** and present products as rich image cards (never a wall of text)
- **Stay truthful** — every product, price, image and link is grounded in live
  Mercari API results; structured card data bypasses the model entirely

### What it deliberately does not do

Mercari's public API is **read-only** — there is no order or payment endpoint.
Suki searches and recommends; each card deep-links to the real Mercari item page
where the customer checks out themselves. The prompt forbids promising orders,
delivery dates or shipping costs.

## Architecture

Browser ── Next.js (Vercel, static shell + streaming chat UI)
│ POST /chat → SSE stream (tool / products / text events)
FastAPI (Render, persistent process)
│ hand-built agent loop (OpenAI SDK · manual tool orchestration)
│ • per-request session → Mercari Ichiba Item Search API
│ • hand-written tool layer (search + item lookup) in OpenAI function-call shape
│ • parallel tool execution (asyncio.gather)
│ • response shaping: ~40 API fields per item trimmed to what the model reasons about
│ • structured <products> extraction; thumbnails upscaled via Mercari's CDN
│ • graceful degradation: tool errors (429s included) are fed back to the model
Claude Sonnet (via OpenAI-compatible gateway; model is env-configurable)

## Engineering notes

- **Manual agent loop** — tools declared as OpenAI function-calling schemas;
  the transcript is the agent's only state
- **Cross-script bridging** — Japanese only ever appears inside tool arguments
  and verbatim tool output; Kiri's own prose stays in Sinhala/Tamil/English
- **Anti-hallucination, in layers** — grounding rules in the system prompt,
  card data extracted server-side from real API responses
  (guarantees in code, preferences in prompts), temperature tuned for
  low-resource-language script stability
- **Multilingual by prompting** — mirroring rules + native-authored few-shot
  examples per language/register; no translation layer (it would destroy
  code-switching)
- **Evaluated** — a 20-row golden test matrix (languages × behaviors ×
  checkout) re-run on every change
- **Resilient** — Pydantic validation at the boundary, bounded loop (MAX_TURNS),
  tool-result truncation, keep-alive against cold starts, CORS allow-list

## Stack

FastAPI · httpx · Mercari  Item Search API · OpenAI SDK (custom base_url) ·
Next.js 16 · Tailwind v4 · react-markdown · Docker Compose · Render + Vercel



## Run with Docker

```bash
cp backend/.env.example backend/.env   # then fill in the four values
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000

Stop with `Ctrl+C`, or run detached: `docker compose up -d --build`.

## Run locally

```bash
# backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the four values
uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev
```


