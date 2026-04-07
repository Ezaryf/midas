import json
import logging
import os
import asyncio
from openai import AsyncOpenAI
from app.schemas.signal import TradeSignal
from app.services.pattern_recognition import Pattern
from typing import List, Optional

logger = logging.getLogger(__name__)

# Providers that support structured outputs (OpenAI beta.parse)
STRUCTURED_OUTPUT_PROVIDERS = {"openai", "grok"}

# Providers that need plain JSON mode + manual parsing
JSON_MODE_PROVIDERS = {"groq", "claude", "gemini"}

# Fallback chain: fast/free providers to try when primary fails
FALLBACK_PROVIDERS = ["groq", "gemini"]

# Provider → env var name for API key lookup
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "groq":   "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "grok":   "GROK_API_KEY",
    "claude": "CLAUDE_API_KEY",
}


class AITradingEngine:
    def __init__(self, api_key: str | None = None, provider: str = "openai"):
        self.provider = provider
        self._api_key = api_key
        base_urls = {
            "openai":  None,
            "claude":  "https://api.anthropic.com/v1",
            "gemini":  "https://generativelanguage.googleapis.com/v1beta/openai",
            "grok":    "https://api.x.ai/v1",
            "groq":    "https://api.groq.com/openai/v1",
        }
        models = {
            "openai": "gpt-4o",
            "claude": "claude-sonnet-4-5",
            "gemini": "gemini-2.0-flash",
            "grok":   "grok-3",
            "groq":   "llama-3.3-70b-versatile",
        }
        self.model = models.get(provider, "gpt-4o")
        base_url   = base_urls.get(provider)

        kwargs: dict = {"api_key": api_key} if api_key else {}
        if base_url:
            kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**kwargs)

    # ── Primary Signal Generation ────────────────────────────────────────────

    async def generate_signal(
        self,
        current_price: float,
        trend: str,
        indicators: dict,
        calendar_events: list,
        trading_style: str = "Intraday",
        patterns: Optional[List[Pattern]] = None,
    ) -> TradeSignal:
        # Format detected patterns
        pattern_info = "None detected"
        if patterns and len(patterns) > 0:
            pattern_lines = []
            for p in patterns[:3]:  # Top 3 patterns
                pattern_lines.append(
                    f"  • {p.type.value} ({p.direction}) - Confidence: {p.confidence:.0f}%\n"
                    f"    Entry: {p.entry_price:.2f}, SL: {p.stop_loss:.2f}, TP: {p.take_profit:.2f}\n"
                    f"    {p.description}"
                )
            pattern_info = "\n".join(pattern_lines)
        
        context = f"""You are 'Midas', an elite institutional quant trader specialising in XAU/USD (Gold).
Output a high-probability trade setup based on the data below.

⚠️ CRITICAL: This signal MUST be for {trading_style} trading style.
- Scalper: Quick trades, tight stops, 5-15min timeframes, RR 1.2-2.0
- Intraday: Same-day trades, 15min-1h timeframes, RR 1.5-2.5  
- Swing: Multi-day trades, 1h-4h timeframes, RR 2.0-3.5

TRADING STYLE: {trading_style} ← YOU MUST USE THIS EXACT VALUE
PRICE: {current_price}
TREND (EMA Stack): {trend}
RSI (14): {indicators.get('RSI_14', 'N/A')}
MACD: {indicators.get('MACD_12_26_9', 'N/A')}
ATR (14): {indicators.get('ATRr_14', 'N/A')}
CALENDAR EVENTS: {calendar_events if calendar_events else 'None'}

DETECTED PATTERNS (Chart & Candlestick):
{pattern_info}

RULES:
1. MANDATORY: Set trading_style field to EXACTLY "{trading_style}" (case-sensitive)
2. PRIORITIZE detected patterns - they are high-probability setups
3. If a strong pattern is detected (confidence >70%), use its entry/SL/TP levels
4. Stop loss = 1.5 × ATR from entry (or pattern SL if better)
5. TP1 and TP2 must match {trading_style} RR ratios
6. If conditions unclear and no patterns, set direction to HOLD
7. Do not hallucinate prices far from current price

⚠️ VERIFY: Your response MUST have trading_style="{trading_style}" """

        try:
            logger.info(f"Requesting signal from {self.provider} ({self.model})...")

            if self.provider in STRUCTURED_OUTPUT_PROVIDERS:
                # OpenAI / Grok — native structured outputs
                response = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": context},
                        {"role": "user",   "content": "Output the optimal trade setup."},
                    ],
                    response_format=TradeSignal,
                )
                signal = response.choices[0].message.parsed

            else:
                # Groq / Claude / Gemini — JSON mode + manual parse
                schema = TradeSignal.model_json_schema()
                prompt = (
                    context
                    + f"\n\nRespond ONLY with a valid JSON object matching this schema:\n{json.dumps(schema, indent=2)}"
                )
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a trading signal generator. Always respond with valid JSON only."},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                raw = response.choices[0].message.content or "{}"
                # Strip markdown code fences if present
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                signal = TradeSignal.model_validate_json(raw.strip())

            logger.info(f"Signal: {signal.direction} @ {signal.entry_price} (confidence {signal.confidence}%)")
            # CRITICAL FIX: Force trading_style to match request
            signal.trading_style = trading_style
            logger.info(f"✅ Trading style enforced: {signal.trading_style}")
            return signal

        except Exception as e:
            logger.error(f"AI signal generation failed ({self.provider}): {e}")
            raise  # Let caller handle — enables fallback chain

    # ── Fallback Chain ────────────────────────────────────────────────────────

    @staticmethod
    async def generate_signal_with_fallback(
        current_price: float,
        trend: str,
        indicators: dict,
        calendar_events: list,
        trading_style: str = "Intraday",
        patterns: Optional[List[Pattern]] = None,
        primary_provider: str = "openai",
        primary_api_key: str | None = None,
    ) -> TradeSignal:
        """
        Try primary provider, then fallback chain, then pattern-only signal.
        Never returns a HOLD/0% fallback — always attempts to build something useful.
        """
        # Build provider chain: primary first, then fallbacks (skip duplicates)
        chain = [primary_provider] + [p for p in FALLBACK_PROVIDERS if p != primary_provider]

        for provider in chain:
            api_key = primary_api_key if provider == primary_provider else _get_provider_key(provider)
            if not api_key:
                logger.debug(f"No API key for {provider} — skipping")
                continue

            try:
                engine = AITradingEngine(api_key=api_key, provider=provider)
                signal = await asyncio.wait_for(
                    engine.generate_signal(
                        current_price=current_price,
                        trend=trend,
                        indicators=indicators,
                        calendar_events=calendar_events,
                        trading_style=trading_style,
                        patterns=patterns,
                    ),
                    timeout=30.0,  # 30s timeout per provider
                )
                logger.info(f"✅ Signal generated via {provider}")
                return signal
            except asyncio.TimeoutError:
                logger.warning(f"Provider {provider} timed out — trying next")
            except Exception as e:
                logger.warning(f"Provider {provider} failed: {e} — trying next")

        # All AI providers failed — build signal from strongest pattern
        logger.warning("All AI providers failed — building pattern-only signal")
        return _build_pattern_signal(patterns, current_price, trend, trading_style)


def _get_provider_key(provider: str) -> str | None:
    """Look up API key for a provider from environment."""
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if env_var:
        return os.getenv(env_var)
    # Also check the generic AI_API_KEY
    return os.getenv("AI_API_KEY")


def _build_pattern_signal(
    patterns: Optional[List[Pattern]],
    current_price: float,
    trend: str,
    trading_style: str,
) -> TradeSignal:
    """
    Build a trade signal purely from pattern data when all AI providers fail.
    Uses the strongest detected pattern, or a trend-aligned ATR fallback.
    """
    if patterns and len(patterns) > 0:
        # Use the highest-confidence pattern
        best = max(patterns, key=lambda p: p.confidence)
        if best.confidence >= 55 and best.direction in ("BUY", "SELL"):
            return TradeSignal(
                direction=best.direction,
                entry_price=best.entry_price,
                stop_loss=best.stop_loss,
                take_profit_1=best.take_profit,
                take_profit_2=best.take_profit,  # Will be clamped by loop
                confidence=round(best.confidence * 0.8, 1),  # Discount without AI confirmation
                reasoning=f"Pattern-only (AI unavailable): {best.type.value} — {best.description}",
                trading_style=trading_style,
            )

    # No usable patterns — return HOLD (safe default)
    return TradeSignal(
        direction="HOLD",
        entry_price=current_price,
        stop_loss=current_price,
        take_profit_1=current_price,
        take_profit_2=current_price,
        confidence=0,
        reasoning="All AI providers failed and no strong patterns detected — no trade recommended",
        trading_style=trading_style,
    )
