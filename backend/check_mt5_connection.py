"""
Quick diagnostic script to check MT5 connection and configuration.
Run this to verify everything is set up correctly.

Usage: python check_mt5_connection.py
"""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    print("⚠️  python-dotenv not installed")

print("\n" + "="*60)
print("  MIDAS MT5 CONNECTION DIAGNOSTIC")
print("="*60 + "\n")

# Check 1: MT5 Package
print("1. Checking MetaTrader5 package...")
try:
    import MetaTrader5 as mt5
    print("   ✅ MetaTrader5 package installed")
except ImportError:
    print("   ❌ MetaTrader5 package NOT installed")
    print("   Fix: pip install MetaTrader5")
    sys.exit(1)

# Check 2: MT5 Initialization
print("\n2. Checking MT5 terminal...")
if not mt5.initialize():
    err = mt5.last_error()
    print(f"   ❌ MT5 initialization failed: {err}")
    if err[0] == -6:
        print("   Fix: Open MetaTrader 5 and login first")
    sys.exit(1)

terminal = mt5.terminal_info()
print(f"   ✅ MT5 terminal: {terminal.name if terminal else 'unknown'}")

# Check 3: Account Info
print("\n3. Checking account...")
info = mt5.account_info()
if info:
    print(f"   ✅ Account: {info.name}")
    print(f"   ✅ Server: {info.server}")
    print(f"   ✅ Balance: {info.balance} {info.currency}")
    print(f"   ✅ Leverage: 1:{info.leverage}")
else:
    print("   ❌ No account info available")

# Check 4: Symbol
print("\n4. Checking symbol...")
SYMBOL = os.getenv("MT5_SYMBOL", "XAUUSD")
candidates = [SYMBOL, "XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.", "GOLD."]
resolved = None

for sym in candidates:
    mt5.symbol_select(sym, True)
    info_sym = mt5.symbol_info(sym)
    if info_sym is not None:
        resolved = sym
        break

if resolved:
    tick = mt5.symbol_info_tick(resolved)
    print(f"   ✅ Symbol: {resolved}")
    if tick:
        print(f"   ✅ Bid: {tick.bid}")
        print(f"   ✅ Ask: {tick.ask}")
        print(f"   ✅ Spread: {tick.ask - tick.bid:.2f}")
    else:
        print("   ⚠️  No tick data (market might be closed)")
else:
    print(f"   ❌ Symbol not found. Tried: {candidates}")
    print("   Fix: Check Market Watch in MT5 for correct symbol name")

# Check 5: Trading Permissions
print("\n5. Checking trading permissions...")
if info:
    if info.trade_allowed:
        print("   ✅ Trading allowed on account")
    else:
        print("   ❌ Trading NOT allowed on account")
        print("   Fix: Check with broker or account settings")
    
    if info.trade_expert:
        print("   ✅ Expert Advisors allowed")
    else:
        print("   ❌ Expert Advisors NOT allowed")
        print("   Fix: Tools → Options → Expert Advisors → Allow automated trading")

# Check 6: Environment Variables
print("\n6. Checking configuration...")
MT5_LOGIN = os.getenv("MT5_LOGIN")
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")
WS_URL = os.getenv("MIDAS_WS_URL", "ws://localhost:8000/ws/mt5")
DEFAULT_LOT = os.getenv("DEFAULT_LOT", "0.01")

if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
    print(f"   ✅ MT5_LOGIN: {MT5_LOGIN}")
    print(f"   ✅ MT5_SERVER: {MT5_SERVER}")
    print(f"   ✅ MT5_PASSWORD: {'*' * len(MT5_PASSWORD)}")
else:
    print("   ⚠️  No credentials in .env (will use open terminal session)")

print(f"   ✅ MT5_SYMBOL: {SYMBOL}")
print(f"   ✅ DEFAULT_LOT: {DEFAULT_LOT}")
print(f"   ✅ MIDAS_WS_URL: {WS_URL}")

# Check 7: Backend Connection
print("\n7. Checking backend connection...")
try:
    import requests
    response = requests.get("http://localhost:8000/api/health", timeout=2)
    if response.status_code == 200:
        print("   ✅ Backend is running on http://localhost:8000")
    else:
        print(f"   ⚠️  Backend returned status {response.status_code}")
except requests.exceptions.ConnectionError:
    print("   ❌ Backend is NOT running")
    print("   Fix: cd backend && uvicorn main:app --reload")
except ImportError:
    print("   ⚠️  requests package not installed (skipping backend check)")
except Exception as e:
    print(f"   ⚠️  Backend check failed: {e}")

# Check 8: Test Order (Dry Run)
print("\n8. Testing order parameters...")
if resolved and tick:
    test_signal = {
        "direction": "BUY",
        "entry_price": tick.ask,
        "stop_loss": tick.ask - 30,
        "take_profit_1": tick.ask + 30,
        "lot": float(DEFAULT_LOT),
    }
    print(f"   ✅ Test signal: {test_signal['direction']} @ {test_signal['entry_price']}")
    print(f"   ✅ SL: {test_signal['stop_loss']} (30 points)")
    print(f"   ✅ TP: {test_signal['take_profit_1']} (30 points)")
    print(f"   ✅ Lot: {test_signal['lot']}")
    print("   ℹ️  This is a DRY RUN - no actual order placed")
else:
    print("   ⚠️  Cannot test - no symbol or tick data")

# Summary
print("\n" + "="*60)
print("  DIAGNOSTIC SUMMARY")
print("="*60)

issues = []
if not mt5.initialize():
    issues.append("MT5 not initialized")
if not info:
    issues.append("No account info")
if not resolved:
    issues.append("Symbol not found")
if info and not info.trade_allowed:
    issues.append("Trading not allowed")
if info and not info.trade_expert:
    issues.append("Expert Advisors not allowed")

if issues:
    print("\n❌ ISSUES FOUND:")
    for issue in issues:
        print(f"   - {issue}")
    print("\nRead MT5_TROUBLESHOOTING.md for solutions")
else:
    print("\n✅ ALL CHECKS PASSED!")
    print("\nYou can now run:")
    print("   python mt5_bridge.py --auto-trade")

print("\n" + "="*60 + "\n")

mt5.shutdown()
