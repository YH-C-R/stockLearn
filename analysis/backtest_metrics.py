from __future__ import annotations


def summarize_backtest(trades: list[dict]) -> dict:
    """Compute summary metrics from a list of completed trades.

    Parameters
    ----------
    trades : Output of run_backtest(). Incomplete trades (return is None) are
             ignored.

    Returns
    -------
    {
        "number_of_trades": int,
        "win_rate":         float,   # fraction of trades with return > 0
        "average_return":   float,   # mean per-trade return
        "total_return":     float,   # compounded return across all trades
        "max_drawdown":     float,   # worst peak-to-trough on equity curve
    }
    """
    completed = [t for t in trades if t["return"] is not None]

    if not completed:
        return {
            "number_of_trades": 0,
            "win_rate":         0.0,
            "average_return":   0.0,
            "total_return":     0.0,
            "max_drawdown":     0.0,
        }

    returns = [t["return"] for t in completed]
    n       = len(returns)

    win_rate       = sum(1 for r in returns if r > 0) / n
    average_return = sum(returns) / n

    # Compounded total return: multiply (1 + r) across all trades
    total_return = 1.0
    for r in returns:
        total_return *= (1 + r)
    total_return = round(total_return - 1, 6)

    max_drawdown = _max_drawdown(returns)

    return {
        "number_of_trades": n,
        "win_rate":         round(win_rate, 4),
        "average_return":   round(average_return, 6),
        "total_return":     total_return,
        "max_drawdown":     max_drawdown,
    }


def _max_drawdown(returns: list[float]) -> float:
    """Compute max drawdown from a sequential equity curve.

    Builds a cumulative equity curve starting at 1.0, then finds the
    largest peak-to-trough decline.
    """
    equity = 1.0
    peak   = 1.0
    max_dd = 0.0

    for r in returns:
        equity *= (1 + r)
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak
        if drawdown > max_dd:
            max_dd = drawdown

    return round(max_dd, 6)
