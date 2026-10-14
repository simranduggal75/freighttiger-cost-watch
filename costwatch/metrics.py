"""Weekly cost per tonne-km and the two baselines defined in the brief."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

REQUIRED_COLUMNS = {
    "shipment_id", "origin", "destination", "route_type", "quantity_tonnes",
    "distance_km", "freight_cost_inr", "shipment_date",
}


def load_shipments(path) -> tuple[pd.DataFrame, int]:
    """Read the shipment file. Returns (clean rows, number of rows dropped as invalid)."""
    df = pd.read_csv(path, parse_dates=["shipment_date"])
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"shipment file is missing columns: {sorted(missing)}")
    valid = (
        (df.quantity_tonnes > 0) & (df.distance_km > 0)
        & (df.freight_cost_inr >= 0) & df.shipment_date.notna()
    )
    df = df[valid].copy()
    df["route"] = df.origin.str.strip() + "-" + df.destination.str.strip()
    return df, int((~valid).sum())


def week_start(dates: pd.Series) -> pd.Series:
    """Monday of the Monday-to-Sunday week containing each date."""
    return (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.normalize()


def weekly_metrics(shipments: pd.DataFrame) -> pd.DataFrame:
    """One row per (route, route_type, week): cost / (tonnes x km), summed over the week."""
    df = shipments.assign(
        week_of=week_start(shipments.shipment_date),
        tonne_km=shipments.quantity_tonnes * shipments.distance_km,
    )
    weekly = df.groupby(["route", "route_type", "week_of"], as_index=False).agg(
        shipments=("shipment_id", "count"),
        freight_cost_inr=("freight_cost_inr", "sum"),
        tonne_km=("tonne_km", "sum"),
    )
    weekly["cost_per_tonne_km"] = weekly.freight_cost_inr / weekly.tonne_km
    return weekly.sort_values(["route", "week_of"]).reset_index(drop=True)


def add_baselines(weekly: pd.DataFrame) -> pd.DataFrame:
    """Add own-history and similar-route baselines exactly as the brief defines them.

    own history  = mean of the weekly values in the (up to) 8 calendar weeks strictly
                   before this week; fewer weeks are used as-is, never padded.
    similar      = mean of the other routes' values with the same route_type, same week.
    """
    w = weekly.copy()
    own_avg = pd.Series(np.nan, index=w.index)
    own_used = pd.Series(0, index=w.index)
    for _, grp in w.groupby(["route", "route_type"], sort=False):
        by_week = grp.set_index("week_of").cost_per_tonne_km.to_dict()
        for idx, wk in zip(grp.index, grp.week_of):
            prior = [by_week[p] for k in range(1, config.BASELINE_WEEKS + 1)
                     if (p := wk - pd.Timedelta(weeks=k)) in by_week]
            if prior:
                own_avg[idx] = float(np.mean(prior))
                own_used[idx] = len(prior)
    w["own_avg"], w["own_weeks_used"] = own_avg, own_used

    key = ["route_type", "week_of"]
    total = w.groupby(key).cost_per_tonne_km.transform("sum")
    count = w.groupby(key).cost_per_tonne_km.transform("count")
    w["peers_used"] = count - 1
    w["peer_avg"] = np.where(count > 1, (total - w.cost_per_tonne_km) / (count - 1).clip(lower=1), np.nan)

    w["vs_own_pct"] = (w.cost_per_tonne_km / w.own_avg - 1) * 100
    w["vs_peer_pct"] = (w.cost_per_tonne_km / w.peer_avg - 1) * 100
    return w
