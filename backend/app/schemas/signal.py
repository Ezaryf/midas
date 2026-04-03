from pydantic import BaseModel, Field
from typing import Literal

class TradeSignal(BaseModel):
    direction: Literal["BUY", "SELL", "HOLD"] = Field(
        ..., description="The directional bias of the trade. If HOLD, no trade is recommended."
    )
    entry_price: float = Field(
        ..., description="The optimal entry price for the trade."
    )
    stop_loss: float = Field(
        ..., description="The stop loss price to invalidate the setup. Must be placed logically behind structure."
    )
    take_profit_1: float = Field(
        ..., description="The first conservative take profit target (TP1)."
    )
    take_profit_2: float = Field(
        ..., description="The secondary, more aggressive take profit target (TP2)."
    )
    confidence: float = Field(
        ..., description="A score from 0 to 100 representing the model's confidence in this setup.", ge=0, le=100
    )
    reasoning: str = Field(
        ..., description="A concise, two-sentence explanation of the trade rationale based on technicals and fundamentals."
    )
    trading_style: Literal["Scalper", "Intraday", "Swing"] = Field(
        ..., description="The inferred holding period/style this setup is built for."
    )
