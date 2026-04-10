"""
Advanced pattern recognition for chart patterns and candlestick patterns.
Identifies high-probability setups for automated trading.
"""
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    # Chart Patterns
    HEAD_SHOULDERS = "Head & Shoulders"
    INVERSE_HEAD_SHOULDERS = "Inverse H&S"
    DOUBLE_TOP = "Double Top"
    DOUBLE_BOTTOM = "Double Bottom"
    TRIANGLE_ASCENDING = "Ascending Triangle"
    TRIANGLE_DESCENDING = "Descending Triangle"
    TRIANGLE_SYMMETRICAL = "Symmetrical Triangle"
    WEDGE_RISING = "Rising Wedge"
    WEDGE_FALLING = "Falling Wedge"
    FLAG_BULL = "Bull Flag"
    FLAG_BEAR = "Bear Flag"
    CHANNEL_UP = "Ascending Channel"
    CHANNEL_DOWN = "Descending Channel"
    
    # Candlestick Patterns
    HAMMER = "Hammer"
    INVERTED_HAMMER = "Inverted Hammer"
    SHOOTING_STAR = "Shooting Star"
    HANGING_MAN = "Hanging Man"
    ENGULFING_BULL = "Bullish Engulfing"
    ENGULFING_BEAR = "Bearish Engulfing"
    MORNING_STAR = "Morning Star"
    EVENING_STAR = "Evening Star"
    DOJI = "Doji"
    DRAGONFLY_DOJI = "Dragonfly Doji"
    GRAVESTONE_DOJI = "Gravestone Doji"
    THREE_WHITE_SOLDIERS = "Three White Soldiers"
    THREE_BLACK_CROWS = "Three Black Crows"
    PIERCING_LINE = "Piercing Line"
    DARK_CLOUD_COVER = "Dark Cloud Cover"


@dataclass
class Pattern:
    type: PatternType
    direction: str  # BUY, SELL
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    description: str
    detected_at: int  # bar index


class PatternRecognizer:
    """Detects chart and candlestick patterns in OHLCV data."""
    
    def __init__(self, min_confidence: float = 50.0):
        self.min_confidence = min_confidence
        
    def detect_all_patterns(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect all patterns in the dataframe."""
        patterns = []
        
        # Chart patterns (need more bars)
        if len(df) >= 50:
            patterns.extend(self._detect_chart_patterns(df))
        
        # Candlestick patterns (need fewer bars)
        if len(df) >= 5:
            patterns.extend(self._detect_candlestick_patterns(df))
        
        # Filter by confidence
        patterns = [p for p in patterns if p.confidence >= self.min_confidence]
        
        # Sort by confidence descending
        patterns.sort(key=lambda x: x.confidence, reverse=True)
        
        return patterns
    
    # ═══════════════════════════════════════════════════════════════════════
    # CHART PATTERNS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _detect_chart_patterns(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect swing-based chart patterns."""
        patterns = []
        
        # Find swing highs and lows
        swings = self._find_swings(df)
        
        if len(swings) < 5:
            return patterns
        
        # Check for various patterns
        patterns.extend(self._check_head_shoulders(df, swings))
        patterns.extend(self._check_double_top_bottom(df, swings))
        patterns.extend(self._check_triangles(df, swings))
        patterns.extend(self._check_flags(df, swings))
        patterns.extend(self._check_channels(df, swings))
        
        return patterns
    
    def _find_swings(self, df: pd.DataFrame, window: int = 5) -> List[Dict]:
        """Find swing highs and lows."""
        swings = []
        
        for i in range(window, len(df) - window):
            # Swing high
            if df.iloc[i]['high'] == df.iloc[i-window:i+window+1]['high'].max():
                swings.append({
                    'type': 'high',
                    'index': i,
                    'price': df.iloc[i]['high'],
                    'time': df.index[i]
                })
            
            # Swing low
            if df.iloc[i]['low'] == df.iloc[i-window:i+window+1]['low'].min():
                swings.append({
                    'type': 'low',
                    'index': i,
                    'price': df.iloc[i]['low'],
                    'time': df.index[i]
                })
        
        return sorted(swings, key=lambda x: x['index'])
    
    def _check_head_shoulders(self, df: pd.DataFrame, swings: List[Dict]) -> List[Pattern]:
        """Detect Head & Shoulders patterns."""
        patterns = []
        highs = [s for s in swings if s['type'] == 'high']
        
        if len(highs) < 3:
            return patterns
        
        # Check last 3 highs for H&S
        for i in range(len(highs) - 2):
            left = highs[i]
            head = highs[i + 1]
            right = highs[i + 2]
            
            # Head should be highest
            if head['price'] > left['price'] and head['price'] > right['price']:
                # Shoulders should be roughly equal (within 1%)
                shoulder_diff = abs(left['price'] - right['price']) / left['price']
                
                if shoulder_diff < 0.01:
                    current_price = df.iloc[-1]['close']
                    neckline = min(left['price'], right['price']) * 0.998
                    
                    # Pattern is valid if price is near neckline
                    if current_price <= neckline * 1.005:
                        target = neckline - (head['price'] - neckline)
                        
                        patterns.append(Pattern(
                            type=PatternType.HEAD_SHOULDERS,
                            direction="SELL",
                            confidence=75.0 + (1 - shoulder_diff) * 10,
                            entry_price=neckline,
                            stop_loss=head['price'] * 1.002,
                            take_profit=target,
                            description=f"H&S pattern with neckline at {neckline:.2f}",
                            detected_at=len(df) - 1
                        ))
        
        return patterns
    
    def _check_double_top_bottom(self, df: pd.DataFrame, swings: List[Dict]) -> List[Pattern]:
        """Detect Double Top/Bottom patterns."""
        patterns = []
        
        # Double Top
        highs = [s for s in swings if s['type'] == 'high']
        if len(highs) >= 2:
            for i in range(len(highs) - 1):
                first = highs[i]
                second = highs[i + 1]
                
                # Tops should be within 0.5%
                diff = abs(first['price'] - second['price']) / first['price']
                if diff < 0.005:
                    current_price = df.iloc[-1]['close']
                    support = df.iloc[first['index']:second['index']]['low'].min()
                    
                    if current_price <= support * 1.003:
                        target = support - (first['price'] - support)
                        
                        patterns.append(Pattern(
                            type=PatternType.DOUBLE_TOP,
                            direction="SELL",
                            confidence=70.0 + (1 - diff) * 15,
                            entry_price=support,
                            stop_loss=first['price'] * 1.002,
                            take_profit=target,
                            description=f"Double top at {first['price']:.2f}",
                            detected_at=len(df) - 1
                        ))
        
        # Double Bottom
        lows = [s for s in swings if s['type'] == 'low']
        if len(lows) >= 2:
            for i in range(len(lows) - 1):
                first = lows[i]
                second = lows[i + 1]
                
                diff = abs(first['price'] - second['price']) / first['price']
                if diff < 0.005:
                    current_price = df.iloc[-1]['close']
                    resistance = df.iloc[first['index']:second['index']]['high'].max()
                    
                    if current_price >= resistance * 0.997:
                        target = resistance + (resistance - first['price'])
                        
                        patterns.append(Pattern(
                            type=PatternType.DOUBLE_BOTTOM,
                            direction="BUY",
                            confidence=70.0 + (1 - diff) * 15,
                            entry_price=resistance,
                            stop_loss=first['price'] * 0.998,
                            take_profit=target,
                            description=f"Double bottom at {first['price']:.2f}",
                            detected_at=len(df) - 1
                        ))
        
        return patterns
    
    def _check_triangles(self, df: pd.DataFrame, swings: List[Dict]) -> List[Pattern]:
        """Detect triangle patterns."""
        patterns = []
        
        if len(swings) < 4:
            return patterns
        
        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']
        
        # Ascending Triangle (flat top, rising lows)
        if len(highs) >= 2 and len(lows) >= 2:
            recent_highs = highs[-2:]
            recent_lows = lows[-2:]
            
            high_flat = abs(recent_highs[0]['price'] - recent_highs[1]['price']) / recent_highs[0]['price'] < 0.003
            lows_rising = recent_lows[1]['price'] > recent_lows[0]['price']
            
            if high_flat and lows_rising:
                resistance = recent_highs[0]['price']
                current_price = df.iloc[-1]['close']
                
                if current_price >= resistance * 0.998:
                    target = resistance + (resistance - recent_lows[0]['price']) * 0.6
                    
                    patterns.append(Pattern(
                        type=PatternType.TRIANGLE_ASCENDING,
                        direction="BUY",
                        confidence=72.0,
                        entry_price=resistance * 1.001,
                        stop_loss=recent_lows[-1]['price'] * 0.998,
                        take_profit=target,
                        description=f"Ascending triangle breakout at {resistance:.2f}",
                        detected_at=len(df) - 1
                    ))
        
        return patterns
    
    def _check_flags(self, df: pd.DataFrame, swings: List[Dict]) -> List[Pattern]:
        """Detect bull/bear flag patterns."""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        # Bull Flag: strong uptrend + consolidation
        recent_20 = df.iloc[-20:]
        prev_20 = df.iloc[-40:-20] if len(df) >= 40 else df.iloc[:20]
        
        # Check for prior strong move
        prev_change = (prev_20.iloc[-1]['close'] - prev_20.iloc[0]['close']) / prev_20.iloc[0]['close']
        
        # Check for consolidation (low volatility)
        recent_range = (recent_20['high'].max() - recent_20['low'].min()) / recent_20['close'].mean()
        
        if prev_change > 0.02 and recent_range < 0.015:  # 2% move, 1.5% consolidation
            current_price = df.iloc[-1]['close']
            flag_high = recent_20['high'].max()
            flag_low = recent_20['low'].min()
            
            if current_price >= flag_high * 0.999:
                target = current_price + (prev_20.iloc[-1]['close'] - prev_20.iloc[0]['close'])
                
                patterns.append(Pattern(
                    type=PatternType.FLAG_BULL,
                    direction="BUY",
                    confidence=68.0,
                    entry_price=flag_high,
                    stop_loss=flag_low * 0.998,
                    take_profit=target,
                    description="Bull flag breakout",
                    detected_at=len(df) - 1
                ))
        
        return patterns
    
    def _check_channels(self, df: pd.DataFrame, swings: List[Dict]) -> List[Pattern]:
        """Detect channel patterns."""
        patterns = []
        
        if len(df) < 50:
            return patterns
        
        # Simple channel detection using linear regression
        recent = df.iloc[-50:]
        highs = recent['high'].values
        lows = recent['low'].values
        x = np.arange(len(recent))
        
        # Fit lines to highs and lows
        high_slope = np.polyfit(x, highs, 1)[0]
        low_slope = np.polyfit(x, lows, 1)[0]
        
        # Ascending channel
        if high_slope > 0 and low_slope > 0 and abs(high_slope - low_slope) / high_slope < 0.2:
            current_price = df.iloc[-1]['close']
            channel_high = recent['high'].iloc[-5:].max()
            channel_low = recent['low'].iloc[-5:].min()
            
            # Buy at channel bottom
            if current_price <= channel_low * 1.002:
                patterns.append(Pattern(
                    type=PatternType.CHANNEL_UP,
                    direction="BUY",
                    confidence=65.0,
                    entry_price=channel_low,
                    stop_loss=channel_low * 0.995,
                    take_profit=channel_high,
                    description="Ascending channel - buy at support",
                    detected_at=len(df) - 1
                ))
        
        return patterns
    
    # ═══════════════════════════════════════════════════════════════════════
    # CANDLESTICK PATTERNS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect candlestick patterns in recent bars."""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        # Check last few candles
        patterns.extend(self._check_hammer(df))
        patterns.extend(self._check_engulfing(df))
        patterns.extend(self._check_morning_evening_star(df))
        patterns.extend(self._check_doji(df))
        patterns.extend(self._check_three_soldiers_crows(df))
        patterns.extend(self._check_piercing_dark_cloud(df))
        
        return patterns
    
    def _check_hammer(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect hammer and shooting star patterns."""
        patterns = []
        last = df.iloc[-1]
        
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        
        if total_range == 0:
            return patterns
        
        upper_shadow = last['high'] - max(last['open'], last['close'])
        lower_shadow = min(last['open'], last['close']) - last['low']
        
        # Hammer (bullish reversal)
        if lower_shadow > body * 2 and upper_shadow < body * 0.3 and body / total_range > 0.2:
            # Check if in downtrend
            if len(df) >= 10:
                prev_trend = df.iloc[-10:-1]['close'].mean()
                if last['close'] < prev_trend:
                    atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                    
                    patterns.append(Pattern(
                        type=PatternType.HAMMER,
                        direction="BUY",
                        confidence=70.0,
                        entry_price=last['close'] * 1.001,
                        stop_loss=last['low'] * 0.998,
                        take_profit=last['close'] + atr * 2,
                        description="Hammer - bullish reversal",
                        detected_at=len(df) - 1
                    ))
        
        # Shooting Star (bearish reversal)
        if upper_shadow > body * 2 and lower_shadow < body * 0.3 and body / total_range > 0.2:
            if len(df) >= 10:
                prev_trend = df.iloc[-10:-1]['close'].mean()
                if last['close'] > prev_trend:
                    atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                    
                    patterns.append(Pattern(
                        type=PatternType.SHOOTING_STAR,
                        direction="SELL",
                        confidence=70.0,
                        entry_price=last['close'] * 0.999,
                        stop_loss=last['high'] * 1.002,
                        take_profit=last['close'] - atr * 2,
                        description="Shooting star - bearish reversal",
                        detected_at=len(df) - 1
                    ))
        
        return patterns
    
    def _check_engulfing(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect bullish/bearish engulfing patterns."""
        patterns = []
        
        if len(df) < 2:
            return patterns
        
        prev = df.iloc[-2]
        last = df.iloc[-1]
        
        prev_body = abs(prev['close'] - prev['open'])
        last_body = abs(last['close'] - last['open'])
        
        # Bullish Engulfing
        if prev['close'] < prev['open'] and last['close'] > last['open']:
            if last['open'] <= prev['close'] and last['close'] >= prev['open'] and last_body > prev_body:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.ENGULFING_BULL,
                    direction="BUY",
                    confidence=75.0,
                    entry_price=last['close'] * 1.0005,
                    stop_loss=last['low'] * 0.998,
                    take_profit=last['close'] + atr * 2.5,
                    description="Bullish engulfing - strong reversal",
                    detected_at=len(df) - 1
                ))
        
        # Bearish Engulfing
        if prev['close'] > prev['open'] and last['close'] < last['open']:
            if last['open'] >= prev['close'] and last['close'] <= prev['open'] and last_body > prev_body:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.ENGULFING_BEAR,
                    direction="SELL",
                    confidence=75.0,
                    entry_price=last['close'] * 0.9995,
                    stop_loss=last['high'] * 1.002,
                    take_profit=last['close'] - atr * 2.5,
                    description="Bearish engulfing - strong reversal",
                    detected_at=len(df) - 1
                ))
        
        return patterns
    
    def _check_morning_evening_star(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect morning/evening star patterns."""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]
        
        c2_body = abs(c2['close'] - c2['open'])
        c2_range = c2['high'] - c2['low']
        
        # Morning Star (bullish)
        if c1['close'] < c1['open'] and c2_body / c2_range < 0.3 and c3['close'] > c3['open']:
            if c3['close'] > (c1['open'] + c1['close']) / 2:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.MORNING_STAR,
                    direction="BUY",
                    confidence=78.0,
                    entry_price=c3['close'] * 1.0005,
                    stop_loss=c2['low'] * 0.998,
                    take_profit=c3['close'] + atr * 3,
                    description="Morning star - strong bullish reversal",
                    detected_at=len(df) - 1
                ))
        
        # Evening Star (bearish)
        if c1['close'] > c1['open'] and c2_body / c2_range < 0.3 and c3['close'] < c3['open']:
            if c3['close'] < (c1['open'] + c1['close']) / 2:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.EVENING_STAR,
                    direction="SELL",
                    confidence=78.0,
                    entry_price=c3['close'] * 0.9995,
                    stop_loss=c2['high'] * 1.002,
                    take_profit=c3['close'] - atr * 3,
                    description="Evening star - strong bearish reversal",
                    detected_at=len(df) - 1
                ))
        
        return patterns
    
    def _check_doji(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect doji patterns."""
        patterns = []
        last = df.iloc[-1]
        
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        
        if total_range == 0:
            return patterns
        
        # Doji: body is less than 10% of total range
        if body / total_range < 0.1:
            upper_shadow = last['high'] - max(last['open'], last['close'])
            lower_shadow = min(last['open'], last['close']) - last['low']
            
            # Dragonfly Doji (bullish)
            if lower_shadow > total_range * 0.6 and upper_shadow < total_range * 0.1:
                if len(df) >= 10 and last['close'] < df.iloc[-10:-1]['close'].mean():
                    atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                    
                    patterns.append(Pattern(
                        type=PatternType.DRAGONFLY_DOJI,
                        direction="BUY",
                        confidence=68.0,
                        entry_price=last['close'] * 1.001,
                        stop_loss=last['low'] * 0.998,
                        take_profit=last['close'] + atr * 2,
                        description="Dragonfly doji - potential reversal",
                        detected_at=len(df) - 1
                    ))
            
            # Gravestone Doji (bearish)
            elif upper_shadow > total_range * 0.6 and lower_shadow < total_range * 0.1:
                if len(df) >= 10 and last['close'] > df.iloc[-10:-1]['close'].mean():
                    atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                    
                    patterns.append(Pattern(
                        type=PatternType.GRAVESTONE_DOJI,
                        direction="SELL",
                        confidence=68.0,
                        entry_price=last['close'] * 0.999,
                        stop_loss=last['high'] * 1.002,
                        take_profit=last['close'] - atr * 2,
                        description="Gravestone doji - potential reversal",
                        detected_at=len(df) - 1
                    ))
        
        return patterns
    
    def _check_three_soldiers_crows(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect three white soldiers / three black crows."""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        
        # Three White Soldiers (bullish)
        if (c1['close'] > c1['open'] and c2['close'] > c2['open'] and c3['close'] > c3['open'] and
            c2['close'] > c1['close'] and c3['close'] > c2['close']):
            atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
            
            patterns.append(Pattern(
                type=PatternType.THREE_WHITE_SOLDIERS,
                direction="BUY",
                confidence=76.0,
                entry_price=c3['close'] * 1.0005,
                stop_loss=c1['low'] * 0.998,
                take_profit=c3['close'] + atr * 3,
                description="Three white soldiers - strong bullish momentum",
                detected_at=len(df) - 1
            ))
        
        # Three Black Crows (bearish)
        if (c1['close'] < c1['open'] and c2['close'] < c2['open'] and c3['close'] < c3['open'] and
            c2['close'] < c1['close'] and c3['close'] < c2['close']):
            atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
            
            patterns.append(Pattern(
                type=PatternType.THREE_BLACK_CROWS,
                direction="SELL",
                confidence=76.0,
                entry_price=c3['close'] * 0.9995,
                stop_loss=c1['high'] * 1.002,
                take_profit=c3['close'] - atr * 3,
                description="Three black crows - strong bearish momentum",
                detected_at=len(df) - 1
            ))
        
        return patterns
    
    def _check_piercing_dark_cloud(self, df: pd.DataFrame) -> List[Pattern]:
        """Detect piercing line and dark cloud cover."""
        patterns = []
        
        if len(df) < 2:
            return patterns
        
        prev = df.iloc[-2]
        last = df.iloc[-1]
        
        prev_mid = (prev['open'] + prev['close']) / 2
        
        # Piercing Line (bullish)
        if prev['close'] < prev['open'] and last['close'] > last['open']:
            if last['open'] < prev['low'] and last['close'] > prev_mid and last['close'] < prev['open']:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.PIERCING_LINE,
                    direction="BUY",
                    confidence=72.0,
                    entry_price=last['close'] * 1.0005,
                    stop_loss=last['low'] * 0.998,
                    take_profit=last['close'] + atr * 2.5,
                    description="Piercing line - bullish reversal",
                    detected_at=len(df) - 1
                ))
        
        # Dark Cloud Cover (bearish)
        if prev['close'] > prev['open'] and last['close'] < last['open']:
            if last['open'] > prev['high'] and last['close'] < prev_mid and last['close'] > prev['open']:
                atr = df.iloc[-14:]['high'].sub(df.iloc[-14:]['low']).mean()
                
                patterns.append(Pattern(
                    type=PatternType.DARK_CLOUD_COVER,
                    direction="SELL",
                    confidence=72.0,
                    entry_price=last['close'] * 0.9995,
                    stop_loss=last['high'] * 1.002,
                    take_profit=last['close'] - atr * 2.5,
                    description="Dark cloud cover - bearish reversal",
                    detected_at=len(df) - 1
                ))
        
        return patterns
