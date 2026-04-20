export function normalizeSymbol(symbol: string | null | undefined): string {
  return (symbol || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .replace(/^GOLD$|^XAUUSD$|^XAUUSD[A-Z]$|^GOLDUSD$|^GC[A-Z0-9]+$/g, "XAUUSD");
}

export function symbolsMatch(left: string | null | undefined, right: string | null | undefined): boolean {
  const normalizedLeft = normalizeSymbol(left);
  const normalizedRight = normalizeSymbol(right);
  if (!normalizedLeft || !normalizedRight) {
    return false;
  }
  return normalizedLeft === normalizedRight;
}
