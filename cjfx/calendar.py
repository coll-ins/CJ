"""Trading calendar: New York 17:00 day boundary and sessions, DST-aware.

Every clock time comes from the config as (tz, "HH:MM"). Conversion to UTC is
done by zoneinfo per date, so daylight saving is never a fixed offset.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd


def parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _offset(t: dtime) -> pd.Timedelta:
    return pd.Timedelta(hours=t.hour, minutes=t.minute)


def trading_day(ts_utc: pd.DatetimeIndex, boundary: dict) -> pd.DatetimeIndex:
    """Label each UTC timestamp with its trading day (tz-naive midnight date).

    A trading day D runs from boundary time on calendar day D-1 to boundary time on D,
    in the boundary's time zone. 17:00 New York Sunday belongs to Monday.
    """
    tz, t = boundary["tz"], parse_hhmm(boundary["time"])
    local = ts_utc.tz_convert(tz).tz_localize(None)
    return (local - _offset(t)).floor("D") + pd.Timedelta(days=1)


def local_to_utc(dates: pd.DatetimeIndex, spec: dict) -> pd.DatetimeIndex:
    """For each tz-naive calendar date, the UTC instant of spec time in spec tz."""
    t = parse_hhmm(spec["time"])
    wall = pd.DatetimeIndex(dates).normalize() + _offset(t)
    return wall.tz_localize(spec["tz"], nonexistent="shift_forward", ambiguous=True).tz_convert("UTC")


def day_bounds(days: pd.DatetimeIndex, boundary: dict) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """UTC [start, end) of each trading day label."""
    end = local_to_utc(days, boundary)
    start = local_to_utc(days - pd.Timedelta(days=1), boundary)
    return start, end


def session_bounds(days: pd.DatetimeIndex, session: dict, boundary: dict) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """UTC [start, end) of a session instance belonging to each trading day.

    The start is the session start time on the trading day's calendar date, moved back a
    day if that would fall at or after the trading day's end. The end is the first end time
    after the start.
    """
    days = pd.DatetimeIndex(days)
    _, day_end = day_bounds(days, boundary)
    start = local_to_utc(days, session["start"])
    back = start >= day_end
    if back.any():
        start = start.where(~back, local_to_utc(days - pd.Timedelta(days=1), session["start"]))
    end = local_to_utc(days, session["end"])
    fwd = end <= start
    if fwd.any():
        end = end.where(~fwd, local_to_utc(days + pd.Timedelta(days=1), session["end"]))
    return start, end


def in_sessions(ts_utc: pd.DatetimeIndex, session_names: list[str], cal: dict) -> np.ndarray:
    """Boolean mask: timestamp falls inside any of the named sessions."""
    ts_utc = pd.DatetimeIndex(ts_utc)
    days = trading_day(ts_utc, cal["day_boundary"])
    uniq = days.unique()
    mask = np.zeros(len(ts_utc), dtype=bool)
    pos = uniq.get_indexer(days)
    for name in session_names:
        s, e = session_bounds(uniq, cal["sessions"][name], cal["day_boundary"])
        sv, ev = s.as_unit('ns').asi8[pos], e.as_unit('ns').asi8[pos]
        t = ts_utc.as_unit('ns').asi8
        mask |= (t >= sv) & (t < ev)
    return mask


def friday_cutoff_mask(ts_utc: pd.DatetimeIndex, spec: dict) -> np.ndarray:
    """True where entries are blocked: Friday at or after spec time in spec tz."""
    local = pd.DatetimeIndex(ts_utc).tz_convert(spec["tz"])
    t = parse_hhmm(spec["time"])
    mins = local.hour * 60 + local.minute
    return np.asarray((local.dayofweek == 4) & (mins >= t.hour * 60 + t.minute))
