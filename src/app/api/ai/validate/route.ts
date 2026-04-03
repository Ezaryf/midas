import { NextRequest, NextResponse } from "next/server";

const PROVIDER_CONFIG: Record<string, { baseUrl: string; model: string }> = {
  openai: { baseUrl: "https://api.openai.com/v1",                                    model: "gpt-4o-mini" },
  claude: { baseUrl: "https://api.anthropic.com/v1",                                 model: "claude-haiku-20240307" },
  gemini: { baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",      model: "gemini-2.0-flash" },
  grok:   { baseUrl: "https://api.x.ai/v1",                                          model: "grok-3" },
  groq:   { baseUrl: "https://api.groq.com/openai/v1",                               model: "llama-3.3-70b-versatile" },
};

export async function POST(req: NextRequest) {
  const { api_key, ai_provider = "openai" } = await req.json();

  if (!api_key) {
    return NextResponse.json({ status: "error", message: "No API key provided" }, { status: 400 });
  }

  const cfg = PROVIDER_CONFIG[ai_provider];
  if (!cfg) {
    return NextResponse.json({ status: "error", message: `Unknown provider: ${ai_provider}` }, { status: 400 });
  }

  try {
    const res = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${api_key}`,
        // Anthropic needs this extra header
        ...(ai_provider === "claude" ? { "anthropic-version": "2023-06-01" } : {}),
      },
      body: JSON.stringify({
        model: cfg.model,
        messages: [{ role: "user", content: "Reply with the single word: OK" }],
        max_tokens: 5,
      }),
      signal: AbortSignal.timeout(12_000),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      const msg = err?.error?.message ?? `HTTP ${res.status}`;
      return NextResponse.json({ status: "error", message: msg });
    }

    const data = await res.json();
    const reply = data?.choices?.[0]?.message?.content ?? "OK";
    return NextResponse.json({ status: "ok", model: cfg.model, reply: reply.trim() });

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Request failed";
    return NextResponse.json({ status: "error", message: msg });
  }
}
