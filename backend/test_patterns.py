"""
Quick test script for pattern recognition system.
Run: python test_patterns.py
"""
import sys
from app.services.technical_analysis import fetch_ohlcv, compute_indicators
from app.services.pattern_recognition import PatternRecognizer

def test_pattern_detection():
    print("🔍 Testing Pattern Recognition System\n")
    
    # Fetch data
    print("📊 Fetching OHLCV data from Yahoo Finance...")
    df = fetch_ohlcv(interval="15m", range_="5d")
    
    if df is None or len(df) < 30:
        print("❌ Failed to fetch sufficient data")
        return
    
    print(f"✅ Fetched {len(df)} bars")
    print(f"   Latest close: {df.iloc[-1]['close']:.2f}")
    print(f"   Date range: {df.index[0]} to {df.index[-1]}\n")
    
    # Compute indicators
    print("📈 Computing technical indicators...")
    df = compute_indicators(df)
    print(f"✅ Indicators computed")
    print(f"   RSI: {df.iloc[-1].get('RSI_14', 0):.2f}")
    print(f"   EMA 9: {df.iloc[-1].get('EMA_9', 0):.2f}")
    print(f"   ATR: {df.iloc[-1].get('ATRr_14', 0):.2f}\n")
    
    # Detect patterns
    print("🎯 Detecting patterns...")
    recognizer = PatternRecognizer(min_confidence=60.0)  # Lower threshold for testing
    patterns = recognizer.detect_all_patterns(df)
    
    if not patterns:
        print("⚠️  No patterns detected (try lowering confidence threshold)")
        return
    
    print(f"✅ Detected {len(patterns)} patterns:\n")
    
    for i, pattern in enumerate(patterns[:5], 1):  # Show top 5
        print(f"{i}. {pattern.type.value}")
        print(f"   Direction: {pattern.direction}")
        print(f"   Confidence: {pattern.confidence:.1f}%")
        print(f"   Entry: {pattern.entry_price:.2f}")
        print(f"   Stop Loss: {pattern.stop_loss:.2f}")
        print(f"   Take Profit: {pattern.take_profit:.2f}")
        print(f"   Description: {pattern.description}")
        print()
    
    print("✨ Pattern detection test complete!")

if __name__ == "__main__":
    try:
        test_pattern_detection()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
