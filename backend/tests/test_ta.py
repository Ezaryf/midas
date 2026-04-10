import pandas as pd
from app.services.technical_analysis import compute_indicators, analyze_trend

def test_indicators():
    # Make a dummy pandas dataframe of 200 items representing mock candles
    data = {
        'open': [2400.0 + i for i in range(200)],
        'high': [2405.0 + i for i in range(200)],
        'low': [2395.0 + i for i in range(200)],
        'close': [2402.0 + i for i in range(200)],
        'volume': [1000 + i for i in range(200)],
    }
    df = pd.DataFrame(data)
    
    # Compute
    df_result = compute_indicators(df)
    
    # Print the last row of indicators
    print("=== Last Row of Indicators ===")
    print(df_result.iloc[-1][['close', 'EMA_9', 'EMA_21', 'EMA_50', 'EMA_200', 'RSI_14', 'MACD_12_26_9', 'ATRr_14']])
    
    # Check trend
    trend = analyze_trend(df_result)
    print(f"\nTrend Analysis: {trend}")

if __name__ == "__main__":
    test_indicators()
