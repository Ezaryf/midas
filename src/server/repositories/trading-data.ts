import type { PerformanceStats } from "@/hooks/usePerformance";
import type { TradeSignal } from "@/lib/types";
import { getPrismaClient } from "@/lib/prisma";

function mapSignalRow(row: Record<string, unknown>): TradeSignal {
  return {
    id: row.id as string | undefined,
    signal_id: row.id as string | undefined,
    symbol: row.symbol as string | undefined,
    analysis_batch_id: row.analysis_batch_id as string | undefined,
    timestamp: (row.created_at as string | undefined),
    direction: row.direction as TradeSignal["direction"],
    entry_price: Number(row.entry_price ?? 0),
    stop_loss: Number(row.stop_loss ?? 0),
    take_profit_1: Number(row.take_profit_1 ?? 0),
    take_profit_2: Number(row.take_profit_2 ?? 0),
    confidence: Number(row.confidence ?? 0),
    reasoning: String(row.reasoning ?? ""),
    trading_style: row.trading_style as TradeSignal["trading_style"],
    setup_type: row.setup_type as string | undefined,
    market_regime: row.market_regime as string | undefined,
    score: row.score == null ? undefined : Number(row.score),
    rank: row.rank == null ? undefined : Number(row.rank),
    is_primary: row.is_primary == null ? undefined : Boolean(row.is_primary),
    entry_window_low: row.entry_window_low == null ? undefined : Number(row.entry_window_low),
    entry_window_high: row.entry_window_high == null ? undefined : Number(row.entry_window_high),
    context_tags: Array.isArray(row.context_tags) ? (row.context_tags as string[]) : [],
    source: row.source as string | undefined,
    status: row.status as TradeSignal["status"],
    outcome: row.outcome == null ? undefined : Number(row.outcome),
  };
}

function emptyPerformance(): PerformanceStats {
  return {
    totalSignals: 0,
    wins: 0,
    losses: 0,
    winRate: 0,
    grossProfit: 0,
    grossLoss: 0,
    totalPnl: 0,
    todayPnl: 0,
    weekPnl: 0,
    profitFactor: 0,
  };
}

export async function listSignals(limit = 50): Promise<TradeSignal[]> {
  const prisma = getPrismaClient();
  if (!prisma) return [];

  try {
    const rows = await prisma.$queryRawUnsafe(
      `SELECT * FROM signals ORDER BY created_at DESC LIMIT ?`,
      limit,
    ) as Record<string, unknown>[];
    return rows.map(mapSignalRow);
  } catch (e) {
    console.error("[trading-data] listSignals error:", e);
    return [];
  }
}

export async function clearSignals(): Promise<void> {
  const prisma = getPrismaClient();
  if (!prisma) return;

  try {
    await prisma.$executeRawUnsafe(`DELETE FROM signals`);
  } catch (e) {
    console.error("[trading-data] clearSignals error:", e);
  }
}

export async function getPerformance(): Promise<PerformanceStats> {
  const prisma = getPrismaClient();
  if (!prisma) return emptyPerformance();

  try {
    const rows = await prisma.$queryRawUnsafe(
      `SELECT
        COUNT(*) as total_signals,
        SUM(CASE WHEN outcome > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN outcome < 0 THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN outcome > 0 THEN outcome ELSE 0 END) as gross_profit,
        SUM(CASE WHEN outcome < 0 THEN ABS(outcome) ELSE 0 END) as gross_loss,
        SUM(COALESCE(outcome, 0)) as total_pnl
      FROM signals
      WHERE status IN ('HIT_TP1', 'HIT_TP2', 'STOPPED')`,
    ) as Record<string, unknown>[];

    const row = rows[0];
    if (!row) return emptyPerformance();

    const total = Number(row.total_signals ?? 0);
    const wins = Number(row.wins ?? 0);
    const losses = Number(row.losses ?? 0);
    const gp = Number(row.gross_profit ?? 0);
    const gl = Number(row.gross_loss ?? 0);

    return {
      totalSignals: total,
      wins,
      losses,
      winRate: total > 0 ? Number(((wins / total) * 100).toFixed(1)) : 0,
      grossProfit: gp,
      grossLoss: gl,
      totalPnl: Number(row.total_pnl ?? 0),
      todayPnl: 0,
      weekPnl: 0,
      profitFactor: gl > 0 ? Number((gp / gl).toFixed(2)) : gp > 0 ? 999 : 0,
    };
  } catch (e) {
    console.error("[trading-data] getPerformance error:", e);
    return emptyPerformance();
  }
}
