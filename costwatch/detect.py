"""Decide which route-weeks are candidates for review.

Two facts drive the design (see README, "Why not a flat threshold?"):
  * weekly noise is ~3%, so a flat +5% rule drowns in false alarms;
  * a route's gap to its peers is structural (Mumbai-Pune is always ~10% above
    Delhi-Jaipur), so "vs similar routes" must be judged against the route's own usual gap.

Every statistic for week t uses only weeks before t (no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def prior_robust_z(values: np.ndarray, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """z-score of values[t] against median/MAD of values[:t]; NaN until enough history."""
    z = np.full(len(values), np.nan)
    spread = np.full(len(values), np.nan)
    for t in range(len(values)):
        past = values[:t]
        past = past[~np.isnan(past)]
        if len(past) < config.MIN_OBS_FOR_SPREAD or np.isnan(values[t]):
            continue
        centre = np.median(past)
        sd = max(1.4826 * np.median(np.abs(past - centre)), floor)
        z[t] = (values[t] - centre) / sd
        spread[t] = sd
    return z, spread


def add_signals(w: pd.DataFrame) -> pd.DataFrame:
    """Add z-scores, trigger labels and a `candidate` flag to the weekly table."""
    w = w.sort_values(["route", "week_of"]).reset_index(drop=True).copy()
    w["z_own"] = np.nan
    w["z_peer"] = np.nan
    w["own_spread"] = np.nan
    for _, grp in w.groupby(["route", "route_type"], sort=False):
        z, spread = prior_robust_z(grp.vs_own_pct.to_numpy(float), config.OWN_SPREAD_FLOOR)
        w.loc[grp.index, "z_own"] = z
        w.loc[grp.index, "own_spread"] = spread
        zp, _ = prior_robust_z(grp.vs_peer_pct.to_numpy(float), config.PEER_SPREAD_FLOOR)
        w.loc[grp.index, "z_peer"] = zp

    judged = w.own_weeks_used >= config.MIN_PRIOR_WEEKS_TO_FLAG
    rising = w.vs_own_pct > 0
    w["rising"] = rising
    strong_own = judged & rising & (w.z_own >= config.Z_STRONG)
    strong_peer = judged & rising & (w.z_peer >= config.Z_STRONG)

    # Market-wide: several routes elevated in the same week -> a smaller rise is significant.
    elevated = judged & rising & (w.z_own >= config.Z_MARKET)
    reporting = (judged & w.z_own.notna()).groupby(w.week_of).transform("sum")
    n_elevated = elevated.groupby(w.week_of).transform("sum")
    need = np.maximum(config.MARKET_MIN_ROUTES, np.ceil(config.MARKET_MIN_SHARE * reporting))
    market = elevated & (n_elevated >= need)

    w["strong_own"], w["strong_peer"], w["market_wide"] = strong_own, strong_peer, market
    w["candidate"] = strong_own | strong_peer | market
    w["trigger"] = [
        "+".join(name for name, on in (
            ("own-history", o), ("similar-routes", p), ("market-wide", m)) if on)
        for o, p, m in zip(strong_own, strong_peer, market)
    ]
    return w
