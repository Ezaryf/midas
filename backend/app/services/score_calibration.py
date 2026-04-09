from __future__ import annotations

from dataclasses import dataclass


SCORE_TO_WIN_RATE = {
    (90, 100): 0.72,
    (80, 90): 0.58,
    (70, 80): 0.45,
    (60, 70): 0.32,
    (50, 60): 0.22,
    (0, 50): 0.12,
}

REGIME_ADJUSTMENT = {
    "trend_up": 1.10,
    "trend_down": 1.10,
    "range": 0.85,
    "compression": 0.85,
    "transition": 0.60,
}

SESSION_ADJUSTMENT = {
    "london": 1.05,
    "ny": 1.05,
    "asian": 0.90,
    "off": 0.75,
}


@dataclass(frozen=True)
class CalibrationResult:
    calibrated_confidence: float
    empirical_win_rate: float
    calibration_sample_size: int
    baseline_win_rate: float
    used_empirical_data: bool


class ScoreCalibrator:
    MIN_TOTAL_SAMPLES = 100
    MIN_BUCKET_SAMPLES = 15

    @classmethod
    def _baseline_win_rate(cls, raw_score: float) -> float:
        for (low, high), rate in SCORE_TO_WIN_RATE.items():
            if low <= raw_score < high or (high == 100 and raw_score <= 100):
                return rate
        return 0.12

    @classmethod
    def _fetch_empirical_stats(
        cls,
        *,
        setup_type: str | None,
        market_regime: str,
        session: str,
        raw_score: float,
    ) -> tuple[float, int, int]:
        try:
            from app.services.database import db

            return db.get_signal_outcome_calibration_stats(
                setup_type=setup_type,
                market_regime=market_regime,
                session=session,
                raw_score=raw_score,
            )
        except Exception:
            return 0.0, 0, 0

    @classmethod
    def get_calibrated_confidence(
        cls,
        *,
        raw_score: float,
        market_regime: str,
        session: str,
        execution_multiplier: float = 1.0,
        setup_type: str | None = None,
    ) -> CalibrationResult:
        baseline_win_rate = cls._baseline_win_rate(raw_score)
        empirical_rate, sample_size, total_samples = cls._fetch_empirical_stats(
            setup_type=setup_type,
            market_regime=market_regime,
            session=session,
            raw_score=raw_score,
        )

        use_empirical = total_samples >= cls.MIN_TOTAL_SAMPLES and sample_size >= cls.MIN_BUCKET_SAMPLES
        win_rate = empirical_rate if use_empirical else baseline_win_rate
        if sample_size > 0 and not use_empirical:
            shrink = min(sample_size / cls.MIN_BUCKET_SAMPLES, 1.0) * 0.2
            win_rate = (baseline_win_rate * (1.0 - shrink)) + (empirical_rate * shrink)

        confidence = win_rate * 100.0
        confidence *= REGIME_ADJUSTMENT.get(market_regime, 1.0)
        confidence *= SESSION_ADJUSTMENT.get(session, 1.0)
        confidence *= execution_multiplier
        confidence = max(0.0, min(confidence, 99.0))
        return CalibrationResult(
            calibrated_confidence=round(confidence, 1),
            empirical_win_rate=round(win_rate * 100.0, 1),
            calibration_sample_size=sample_size,
            baseline_win_rate=round(baseline_win_rate * 100.0, 1),
            used_empirical_data=use_empirical,
        )
