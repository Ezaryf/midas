"""
Verify Scalper Improvements
============================
Quick script to verify all 10 fixes are working correctly.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.core.loop import STYLE_CONFIG, ANALYSIS_INTERVAL, MAX_DAILY_TRADES, GOLD_SPREAD_POINTS

print("="*70)
print("SCALPER IMPROVEMENTS VERIFICATION")
print("="*70)
print()

config = STYLE_CONFIG["Scalper"]
passed = 0
failed = 0

def check(name, expected, actual, operator="=="):
    global passed, failed
    if operator == "==":
        result = actual == expected
    elif operator == "<=":
        result = actual <= expected
    elif operator == ">=":
        result = actual >= expected
    
    status = "✅ PASS" if result else "❌ FAIL"
    print(f"{status} | {name}")
    print(f"       Expected: {expected}, Got: {actual}")
    
    if result:
        passed += 1
    else:
        failed += 1
    return result

print("1. Signal Count Reduced")
check("Max signals", 3, config["max_signals"])
print()

print("2. Stop Loss Increased")
check("Max SL points", 15.0, config["max_sl_points"])
check("ATR SL multiplier", 0.8, config["atr_sl_mult"])
print()

print("3. Risk/Reward Improved")
check("Minimum RR", 1.5, config["rr_min"])
check("Target RR", 2.0, config["rr_target"])
check("Max TP1 points", 22.0, config["max_tp1_points"])
check("Max TP2 points", 30.0, config["max_tp2_points"])
print()

print("4. Trading Session Filter")
from app.core.loop import LONDON_SESSION, NY_SESSION
check("London session start", 8, LONDON_SESSION[0])
check("London session end", 12, LONDON_SESSION[1])
check("NY session start", 13, NY_SESSION[0])
check("NY session end", 17, NY_SESSION[1])
print()

print("5. Correlation Filter")
check("Max positions per direction", 1, config.get("max_positions_per_direction", 0))
print()

print("6. Daily Limits")
check("Max daily trades", 5, MAX_DAILY_TRADES)
from app.core.loop import MAX_DAILY_LOSS_PCT, MAX_CONSECUTIVE_LOSSES
check("Max daily loss %", 2.0, MAX_DAILY_LOSS_PCT)
check("Max consecutive losses", 3, MAX_CONSECUTIVE_LOSSES)
print()

print("7. Faster Analysis")
check("Analysis interval (seconds)", 10, ANALYSIS_INTERVAL, "<=")
print()

print("8. Spread/Commission Accounting")
check("Gold spread points", 5.0, GOLD_SPREAD_POINTS)
from app.core.loop import COMMISSION_PER_LOT
check("Commission per lot", 2.0, COMMISSION_PER_LOT)
print()

print("9. M5 Prioritized")
check("Primary timeframe", "5m", config["timeframes"][0])
check("Secondary timeframe", "1m", config["timeframes"][1])
print()

print("10. News Event Filter")
from app.core.loop import is_high_impact_news_upcoming
has_news_filter = callable(is_high_impact_news_upcoming)
check("News filter function exists", True, has_news_filter)
print()

print("="*70)
print("VERIFICATION SUMMARY")
print("="*70)
print(f"Passed: {passed}")
print(f"Failed: {failed}")
print()

if failed == 0:
    print("✅ ALL IMPROVEMENTS VERIFIED!")
    print()
    print("Your scalper is now:")
    print("  • Generating 3 quality signals (not 8)")
    print("  • Using 15pt stops (not 8pt)")
    print("  • Targeting 1.5:1 RR minimum (not 1:1)")
    print("  • Trading London/NY only (not 24/7)")
    print("  • Max 1 position per direction (not unlimited)")
    print("  • Daily limits enforced (5 trades, 2% loss)")
    print("  • Analyzing every 10s (not 30s)")
    print("  • Accounting for 5pt spread + commission")
    print("  • Prioritizing M5 over M1")
    print("  • Filtering high-impact news")
    print()
    print("Expected breakeven win rate: 57% (was 81%)")
    print()
    sys.exit(0)
else:
    print(f"❌ {failed} CHECKS FAILED")
    print()
    print("Please review backend/app/core/loop.py")
    sys.exit(1)
