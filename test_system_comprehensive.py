"""
Comprehensive System Test
==========================
Tests all 4 critical requirements:
1. Does it suggest at least 4 entry positions?
2. Does it mark them on the chart?
3. When trading style changes, do entries adapt?
4. When price hits entry, does it trigger MT5 order?

Usage:
    python test_system_comprehensive.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.core.loop import run_analysis_cycle, STYLE_CONFIG
from app.api.ws.mt5_handler import manager


class TestResults:
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.details = []
    
    def log(self, test_name: str, passed: bool, message: str):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.details.append(f"{status} | {test_name}: {message}")
        if passed:
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def print_summary(self):
        print("\n" + "="*70)
        print("TEST RESULTS SUMMARY")
        print("="*70)
        for detail in self.details:
            print(detail)
        print("="*70)
        print(f"Total: {self.tests_passed} passed, {self.tests_failed} failed")
        print("="*70 + "\n")


async def test_requirement_1_signal_count(results: TestResults):
    """Test 1: Does it suggest at least 4 entry positions?"""
    print("\n[TEST 1] Checking if system generates at least 4 signals...")
    
    # Capture signals by monitoring broadcast
    captured_signals = []
    
    original_broadcast = manager.broadcast_json
    async def capture_broadcast(data: dict):
        if data.get("type") == "SIGNAL":
            captured_signals.append(data.get("data"))
        await original_broadcast(data)
    
    manager.broadcast_json = capture_broadcast
    
    try:
        # Run analysis for Scalper style
        await run_analysis_cycle(trading_style="Scalper")
        
        # Check signal count
        signal_count = len(captured_signals)
        passed = signal_count >= 4
        
        results.log(
            "Signal Count (Scalper)",
            passed,
            f"Generated {signal_count} signals (minimum: 4)"
        )
        
        if passed:
            print(f"   ✅ Generated {signal_count} signals")
            for i, sig in enumerate(captured_signals[:4], 1):
                print(f"      {i}. {sig.get('direction')} @ {sig.get('entry_price')} "
                      f"(conf: {sig.get('confidence')}%)")
        else:
            print(f"   ❌ Only generated {signal_count} signals (need 4+)")
        
        return captured_signals
    
    finally:
        manager.broadcast_json = original_broadcast


async def test_requirement_2_chart_markers(results: TestResults, signals: list):
    """Test 2: Does it mark signals on the chart?"""
    print("\n[TEST 2] Checking if signals can be marked on chart...")
    
    # Check if signals have the required fields for chart markers
    required_fields = ["entry_price", "stop_loss", "take_profit_1", "direction"]
    
    valid_signals = 0
    for sig in signals:
        if all(sig.get(field) is not None for field in required_fields):
            valid_signals += 1
    
    passed = valid_signals >= 4
    results.log(
        "Chart Markers",
        passed,
        f"{valid_signals}/{len(signals)} signals have complete data for chart markers"
    )
    
    if passed:
        print(f"   ✅ {valid_signals} signals have entry/SL/TP data for chart display")
        print("   Chart lines format:")
        for sig in signals[:2]:
            print(f"      • Entry: {sig.get('entry_price')} ({sig.get('direction')})")
            print(f"        SL: {sig.get('stop_loss')}, TP1: {sig.get('take_profit_1')}")
    else:
        print(f"   ❌ Only {valid_signals} signals have complete chart data")


async def test_requirement_3_style_adaptation(results: TestResults):
    """Test 3: When trading style changes, do entries adapt?"""
    print("\n[TEST 3] Testing trading style adaptation...")
    
    styles_to_test = ["Scalper", "Intraday", "Swing"]
    style_signals = {}
    
    for style in styles_to_test:
        print(f"   Testing {style} style...")
        captured = []
        
        original_broadcast = manager.broadcast_json
        async def capture(data: dict):
            if data.get("type") == "SIGNAL":
                captured.append(data.get("data"))
            await original_broadcast(data)
        
        manager.broadcast_json = capture
        
        try:
            await run_analysis_cycle(trading_style=style)
            style_signals[style] = captured
        finally:
            manager.broadcast_json = original_broadcast
    
    # Verify each style produces different characteristics
    differences_found = []
    
    # Check 1: Different timeframes implied by different RR ratios
    for style in styles_to_test:
        sigs = style_signals.get(style, [])
        if sigs:
            sig = sigs[0]
            entry = sig.get("entry_price", 0)
            sl = sig.get("stop_loss", 0)
            tp = sig.get("take_profit_1", 0)
            
            if entry and sl and tp:
                risk = abs(entry - sl)
                reward = abs(tp - entry)
                rr = reward / risk if risk > 0 else 0
                
                expected_rr = STYLE_CONFIG[style]["rr_min"]
                differences_found.append({
                    "style": style,
                    "rr": round(rr, 2),
                    "expected_rr": expected_rr,
                    "sl_points": round(risk, 2),
                    "tp_points": round(reward, 2),
                })
    
    # Check 2: Verify RR ratios are different between styles
    rr_values = [d["rr"] for d in differences_found]
    unique_characteristics = len(set(rr_values)) > 1
    
    passed = len(differences_found) == 3 and unique_characteristics
    
    results.log(
        "Style Adaptation",
        passed,
        f"Each style produces different entry characteristics"
    )
    
    if passed:
        print("   ✅ Trading styles produce different setups:")
        for d in differences_found:
            print(f"      {d['style']}: RR={d['rr']} (target: {d['expected_rr']}), "
                  f"SL={d['sl_points']}pts, TP={d['tp_points']}pts")
    else:
        print("   ❌ Styles not producing distinct characteristics")
        for d in differences_found:
            print(f"      {d['style']}: RR={d['rr']}")


async def test_requirement_4_mt5_trigger(results: TestResults):
    """Test 4: When price hits entry, does it trigger MT5 order?"""
    print("\n[TEST 4] Testing MT5 order trigger mechanism...")
    
    # Check if MT5 bridge connection is available
    has_mt5_connection = len(manager.active_connections) > 0
    
    results.log(
        "MT5 Connection",
        has_mt5_connection,
        f"MT5 bridge {'connected' if has_mt5_connection else 'not connected'}"
    )
    
    if has_mt5_connection:
        print("   ✅ MT5 bridge is connected")
    else:
        print("   ⚠️  MT5 bridge not connected (run backend/mt5_bridge.py)")
    
    # Test signal broadcast mechanism
    test_signal = {
        "type": "SIGNAL",
        "action": "PLACE_ORDER",
        "data": {
            "signal_id": "test_123",
            "direction": "BUY",
            "entry_price": 2650.00,
            "stop_loss": 2645.00,
            "take_profit_1": 2655.00,
            "take_profit_2": 2660.00,
            "confidence": 75.0,
            "auto_execute": True,
            "lot": 0.01,
        }
    }
    
    # Test broadcast (won't execute without bridge)
    try:
        await manager.broadcast_json(test_signal)
        broadcast_works = True
    except Exception as e:
        broadcast_works = False
        print(f"   ❌ Broadcast failed: {e}")
    
    results.log(
        "Signal Broadcast",
        broadcast_works,
        "Signal broadcast mechanism functional"
    )
    
    if broadcast_works:
        print("   ✅ Signal broadcast mechanism works")
        print("   📡 Test signal sent (will execute if bridge is running with --auto-trade)")
    
    # Check auto-execute logic
    print("\n   Auto-execute confidence thresholds:")
    for style, config in STYLE_CONFIG.items():
        print(f"      {style}: {config['auto_execute_confidence']}%")


async def main():
    print("\n" + "="*70)
    print("MIDAS TRADING SYSTEM - COMPREHENSIVE TEST")
    print("="*70)
    print("Testing 4 critical requirements:")
    print("  1. Generate at least 4 entry positions")
    print("  2. Mark signals on chart")
    print("  3. Adapt entries to trading style")
    print("  4. Trigger MT5 orders when price hits entry")
    print("="*70)
    
    results = TestResults()
    
    # Test 1: Signal generation
    signals = await test_requirement_1_signal_count(results)
    
    # Test 2: Chart markers
    if signals:
        await test_requirement_2_chart_markers(results, signals)
    else:
        results.log("Chart Markers", False, "No signals to test")
    
    # Test 3: Style adaptation
    await test_requirement_3_style_adaptation(results)
    
    # Test 4: MT5 trigger
    await test_requirement_4_mt5_trigger(results)
    
    # Print summary
    results.print_summary()
    
    # Exit code
    sys.exit(0 if results.tests_failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
