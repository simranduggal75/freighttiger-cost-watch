import numpy as np
import pandas as pd

from costwatch import metrics


def _ship(route, d, qty, km, cost, rtype="Short"):
    o, dest = route.split("-")
    return dict(shipment_id=f"S{abs(hash((route, d, cost))) % 10**8}", origin=o, destination=dest,
                route_type=rtype, quantity_tonnes=qty, distance_km=km, freight_cost_inr=cost,
                shipment_date=pd.Timestamp(d), route=route)


def test_week_runs_monday_to_sunday():
    dates = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-07", "2024-01-08"]))  # Mon, Sun, Mon
    got = metrics.week_start(dates).dt.strftime("%Y-%m-%d").tolist()
    assert got == ["2024-01-01", "2024-01-01", "2024-01-08"]


def test_cost_is_ratio_of_sums_not_mean_of_ratios():
    rows = [_ship("A-B", "2024-01-01", 10, 100, 1000),   # 1.0 per tonne-km
            _ship("A-B", "2024-01-02", 30, 100, 6000)]   # 2.0 per tonne-km
    w = metrics.weekly_metrics(pd.DataFrame(rows))
    assert len(w) == 1
    assert np.isclose(w.cost_per_tonne_km[0], 7000 / (10 * 100 + 30 * 100))  # 1.75, not 1.5


def _series(route, values, rtype="Short", start="2024-01-01"):
    weeks = pd.date_range(start, periods=len(values), freq="W-MON")
    return pd.DataFrame([dict(route=route, route_type=rtype, week_of=w, cost_per_tonne_km=v,
                              shipments=3, freight_cost_inr=0, tonne_km=1)
                         for w, v in zip(weeks, values)])


def test_own_history_excludes_current_week_and_uses_available_weeks():
    w = metrics.add_baselines(_series("A-B", [1, 2, 3, 4]))
    assert np.isnan(w.own_avg[0]) and w.own_weeks_used[0] == 0       # nothing before week 1
    assert w.own_avg[1] == 1 and w.own_weeks_used[1] == 1            # one prior week, not padded
    assert w.own_avg[3] == 2 and w.own_weeks_used[3] == 3            # mean(1,2,3), excludes the 4


def test_own_history_is_capped_at_eight_prior_weeks():
    w = metrics.add_baselines(_series("A-B", list(range(1, 13))))   # values 1..12
    assert w.own_weeks_used.iloc[11] == 8
    assert w.own_avg.iloc[11] == np.mean(range(4, 12))               # weeks 4..11 are the 8 before week 12


def test_peer_average_excludes_the_route_itself():
    df = pd.concat([_series("A-B", [1.0, 1.0]), _series("C-D", [3.0, 5.0]), _series("E-F", [5.0, 7.0])])
    w = metrics.add_baselines(df.reset_index(drop=True))
    row = w[(w.route == "A-B") & (w.week_of == w.week_of.min())].iloc[0]
    assert row.peer_avg == 4.0          # mean(3, 5): excludes its own 1.0
    assert row.peers_used == 2


def test_peers_are_only_same_route_type():
    df = pd.concat([_series("A-B", [1.0], "Short"), _series("C-D", [9.0], "Long")]).reset_index(drop=True)
    w = metrics.add_baselines(df)
    assert w.peer_avg.isna().all()      # no other Short route that week
