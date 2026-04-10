import asyncio
import logging
from app.services.analysis_pipeline import TradingEngine
from app.core.loop import STYLE_CONFIG

logging.basicConfig(level=logging.INFO)

async def run_diagnostics():
    style = "Scalper"
    symbol = "XAUUSD"
    
    engine = TradingEngine(STYLE_CONFIG)
    
    print(f"Running analysis cycle for {symbol} with style {style}...")
    try:
        response = await engine.analyze(
            trading_style=style,
            symbol=symbol,
            session_active=True,
            news_blocked=False,
            risk_blocked=False,
            publish=False
        )
    except Exception as e:
        print(f"Error during analysis: {e}")
        return

    if not response.data:
        print("No Analysis Batch produced.")
        return

    batch = response.data
    primary = batch.primary
    
    print("\n--- Primary Signal ---")
    print(f"Direction: {primary.direction}")
    print(f"Setup: {primary.setup_type}")
    print(f"Regime: {primary.market_regime}")
    print(f"Score: {primary.score}")
    print(f"Reasoning: {primary.reasoning}")
    
    if primary.direction == "HOLD":
        print("\n--- HOLD Reasons ---")
        for reason in primary.no_trade_reasons:
            print(f"  - {reason['code']}: {reason['message']}")
            
    print("\n--- Backups ---")
    for b in batch.backups:
        print(f"  - {b.setup_type} ({b.direction}) score={b.score}")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
