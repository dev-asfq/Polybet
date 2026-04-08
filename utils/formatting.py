"""Message formatting helpers."""

def usd(v: float) -> str:
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:.2f}"

def pct(v: float, plus=False) -> str:
    s = "+" if (plus and v > 0) else ""
    return f"{s}{v:.2f}%"

def cents(v: float) -> str:
    return f"{int(round(v * 100))}¢"

def score_bar(s: int) -> str:
    filled = s // 10
    return "█" * filled + "░" * (10 - filled)

def score_emoji(s: int) -> str:
    if s >= 90: return "🔥"
    if s >= 80: return "💎"
    if s >= 70: return "✅"
    if s >= 60: return "⚡"
    return "📊"

def platform_emoji(p: str) -> str:
    return "🟣" if "poly" in p.lower() else "🔵"

def trunc(s: str, n: int = 70) -> str:
    return s[:n] + "…" if len(s) > n else s

def div() -> str:
    return "─" * 32
