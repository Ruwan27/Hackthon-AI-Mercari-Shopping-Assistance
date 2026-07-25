"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Product = {
  id: string;
  name: string;
  price: string;
  image?: string;
  url: string;
  /** Short gloss in the customer's language — the Japanese name alone means nothing to them. */
  note?: string;
};
type Msg = {
  role: "user" | "assistant";
  content: string;
  products?: Product[];
  retryText?: string;
};

const SUGGESTIONS = [
  "🎂 Birthday gift under ¥5000",
  "🍫 Chocolates for my sister",
  "අම්මාට තෑග්ගක් ඕනේ 🎁",
  "Anniversary gift ekak hoyala denna",
];

const WELCOME: Msg = {
  role: "assistant",
  content:
    "いらっしゃいませ！🇯🇵 Ayubowan! 👋 I'm **Suki (スキ)** — your Mercari (メルカリ) shopping buddy. " +
    "ඔයාට ඕන තෑග්ග මම හොයලා දෙන්නම් — English, සිංහල, 日本語, Singlish… ඕන භාෂාවකින් කතා කරන්න! " +
    "Who are we shopping for today? 🎁",
};

export default function Home() {
  const [messages, setMessages] = useState<Msg[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<"idle" | "thinking" | string>("idle");
  const [demo, setDemo] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  // The backend decides; the banner must never be a guess.
  useEffect(() => {
    fetch(`${API_URL}/config`)
      .then((r) => r.json())
      .then((c) => setDemo(Boolean(c.demo)))
      .catch(() => setDemo(false));
  }, []);

  async function send(text: string) {
    const content = text.trim();
    if (!content || status !== "idle") return;

    const history: Msg[] = [...messages, { role: "user", content }];
    setMessages(history);
    setInput("");
    setStatus("thinking");

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";
      let assistantProducts: Product[] | undefined;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          if (!frame.startsWith("data: ")) continue;
          const payload = frame.slice(6);
          if (payload === "[DONE]") continue;

          const event = JSON.parse(payload);
          if (event.type === "tool") {
            setStatus(friendlyToolName(event.name));
          } else if (event.type === "products") {
            assistantProducts = event.items;
            setMessages([
              ...history,
              {
                role: "assistant",
                content: assistantText,
                products: assistantProducts,
              },
            ]);
          } else if (event.type === "text") {
            assistantText += event.text;
            setMessages([
              ...history,
              {
                role: "assistant",
                content: assistantText,
                products: assistantProducts,
              },
            ]);
          } else if (event.type === "error") {
            setMessages([
              ...history,
              {
                role: "assistant",
                content:
                  "අපොයි! Something went wrong on my side 🙈 Please try again.",
              },
            ]);
          }
        }
      }
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content:
            "I couldn't reach the server 🙏 Check that the backend is running and try again.",
          retryText: content,
        },
      ]);
    } finally {
      setStatus("idle");
    }
  }

  return (
    <main className="flex h-dvh flex-col bg-gradient-to-b from-emerald-50 via-white to-amber-50">
      {/* Header */}
      <header className="border-b border-emerald-100 bg-white/70 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-600 text-xl shadow-sm">
            🛍️
          </div>
          <div>
            <h1 className="text-lg font-bold text-emerald-900">
              Suki <span className="font-normal text-emerald-600">· スキ</span>
            </h1>
            <p className="text-xs text-emerald-700">
              Your Mercari メルカリ shopping buddy — English · සිංහල · 日本語
            </p>
          </div>
        </div>
        {demo && (
          <div className="mx-auto mt-2 max-w-3xl rounded-lg bg-amber-100 px-3 py-2 text-xs text-amber-900">
            ⚠️ <strong>Demo mode</strong> — snapshot products, not the live Mercari
            catalog. Prices are illustrative.
          </div>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {!messages.some((m) => m.role === "user") && (
            <div className="mt-16 text-center duration-500 animate-in fade-in slide-in-from-bottom-4">
              <p className="text-3xl">🎁</p>
              <h2 className="mt-3 text-xl font-semibold text-emerald-900">
                Ayubowan! What are we shopping for today?
              </h2>
              <p className="mt-1 text-sm text-emerald-700">
                Gifts, chocolates, flowers, cakes — I&apos;ll find it and get it
                delivered anywhere in Sri Lanka.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-emerald-200 bg-white px-4 py-2 text-sm text-emerald-800 shadow-sm transition hover:-translate-y-0.5 hover:bg-emerald-50 hover:shadow"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex duration-300 animate-in fade-in slide-in-from-bottom-2 ${
                m.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-600 px-4 py-3 text-white shadow"
                    : "prose prose-sm max-w-[85%] rounded-2xl rounded-bl-sm border border-emerald-100 bg-white px-4 py-3 shadow-sm prose-a:text-emerald-700 prose-img:my-2 prose-img:h-44 prose-img:w-full prose-img:rounded-xl prose-img:object-cover"
                }
              >
                {m.role === "user" ? (
                  m.content
                ) : (
                  <>
                    {m.products && m.products.length > 0 && (
                      <div className="-mx-1 mb-3 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2">
                        {m.products.map((p) => (
                          <a
                            key={p.id}
                            href={p.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-44 flex-shrink-0 snap-start overflow-hidden rounded-xl border border-emerald-100 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
                          >
                            {p.image ? (
                              <ProductImage src={p.image} name={p.name} />
                            ) : (
                              <div className="flex h-36 w-full items-center justify-center bg-emerald-50 text-3xl">
                                🎁
                              </div>
                            )}
                            <div className="p-3">
                              {p.note && (
                                <p className="line-clamp-2 text-xs font-semibold text-gray-900">
                                  {p.note}
                                </p>
                              )}
                              <p
                                className={`line-clamp-2 text-xs text-gray-500 ${
                                  p.note ? "mt-0.5" : "font-medium text-gray-800"
                                }`}
                                lang="ja"
                              >
                                {p.name}
                              </p>
                              <p className="mt-1 text-sm font-bold text-emerald-700">
                                {p.price}
                              </p>
                              <span className="mt-2 inline-block rounded-full bg-emerald-600 px-3 py-1 text-[11px] font-semibold text-white">
                                View →
                              </span>
                            </div>
                          </a>
                        ))}
                      </div>
                    )}
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content}
                    </ReactMarkdown>
                    {m.retryText && (
                      <button
                        onClick={() => send(m.retryText!)}
                        className="mt-2 rounded-full border border-emerald-300 bg-emerald-50 px-4 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100"
                      >
                        🔄 Try again
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {status !== "idle" && (
            <div className="flex justify-start duration-300 animate-in fade-in">
              <div className="flex items-center gap-2 rounded-2xl border border-emerald-100 bg-white px-4 py-3 text-sm text-emerald-700 shadow-sm">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
                {status === "thinking" ? "Suki is thinking…" : status}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-emerald-100 bg-white/70 px-4 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-3xl gap-2">
          <textarea
            autoFocus
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height =
                Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder="Type in English, සිංහල, 日本語, Singlish..."
            disabled={status !== "idle"}
            className="flex-1 resize-none rounded-3xl border border-emerald-200 bg-white px-5 py-3 text-sm text-gray-900 placeholder:text-gray-400 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          />
          <button
            onClick={() => send(input)}
            disabled={status !== "idle"}
            className="rounded-full bg-emerald-600 px-6 py-3 text-sm font-semibold text-white shadow transition hover:bg-emerald-700 active:scale-95 disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </main>
  );
}

function friendlyToolName(name: string): string {
  const map: Record<string, string> = {
    mercari_search_items: "🔎 Searching Mercari…",
    rakuten_search_items: "🔎 Searching Rakuten…",
    rakuten_get_item: "🖼️ Fetching product details…",
  };
  return map[name] ?? "Working on it…";
}

// Rakuten's own image CDN already sizes thumbnails (?_ex=400x400 from the backend).
const cdn = (url: string) => url;

function ProductImage({ src, name }: { src?: string; name: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="flex h-36 w-full items-center justify-center bg-emerald-50 text-3xl">
        🎁
      </div>
    );
  }
  return (
    <img
      src={cdn(src)}
      alt={name}
      className="h-36 w-full object-cover"
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
