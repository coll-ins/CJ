import pandas as pd

from cjfx.calendar import day_bounds, friday_cutoff_mask, in_sessions, session_bounds, trading_day


def T(s):
    return pd.DatetimeIndex([pd.Timestamp(s, tz="UTC")])


def test_day_boundary_follows_new_york_dst(cfg):
    b = cfg["calendar"]["day_boundary"]
    # summer (EDT, UTC-4): 17:00 NY = 21:00 UTC
    assert trading_day(T("2023-07-10 20:59"), b)[0] == pd.Timestamp("2023-07-10")
    assert trading_day(T("2023-07-10 21:00"), b)[0] == pd.Timestamp("2023-07-11")
    # winter (EST, UTC-5): 17:00 NY = 22:00 UTC
    assert trading_day(T("2023-01-10 21:30"), b)[0] == pd.Timestamp("2023-01-10")
    assert trading_day(T("2023-01-10 22:00"), b)[0] == pd.Timestamp("2023-01-11")
    s, e = day_bounds(pd.DatetimeIndex([pd.Timestamp("2023-07-11"), pd.Timestamp("2023-01-11")]), b)
    assert e[0] == pd.Timestamp("2023-07-11 21:00", tz="UTC")
    assert e[1] == pd.Timestamp("2023-01-11 22:00", tz="UTC")


def test_sunday_open_belongs_to_monday(cfg):
    b = cfg["calendar"]["day_boundary"]
    assert trading_day(T("2023-03-05 22:05"), b)[0] == pd.Timestamp("2023-03-06")


def test_us_uk_dst_gap_weeks(cfg):
    # 2023-03-13: US already on EDT, UK still on GMT -> London 08:00 = 08:00 UTC, NY 17:00 = 21:00 UTC
    cal = cfg["calendar"]
    d = pd.DatetimeIndex([pd.Timestamp("2023-03-14")])
    s, e = session_bounds(d, cal["sessions"]["london_ny"], cal["day_boundary"])
    assert s[0] == pd.Timestamp("2023-03-14 08:00", tz="UTC")
    assert e[0] == pd.Timestamp("2023-03-14 21:00", tz="UTC")
    s, e = session_bounds(d, cal["sessions"]["asian"], cal["day_boundary"])
    assert s[0] == pd.Timestamp("2023-03-13 21:00", tz="UTC")
    assert e[0] == pd.Timestamp("2023-03-14 08:00", tz="UTC")
    # summer: London 08:00 BST = 07:00 UTC
    d = pd.DatetimeIndex([pd.Timestamp("2023-07-12")])
    s, _ = session_bounds(d, cal["sessions"]["london_ny"], cal["day_boundary"])
    assert s[0] == pd.Timestamp("2023-07-12 07:00", tz="UTC")


def test_in_sessions(cfg):
    cal = cfg["calendar"]
    ts = pd.DatetimeIndex(pd.to_datetime(["2023-07-12 06:30", "2023-07-12 07:30", "2023-07-12 21:30"], utc=True))
    assert list(in_sessions(ts, ["london_ny"], cal)) == [False, True, False]
    assert list(in_sessions(ts, ["asian", "london_ny"], cal)) == [True, True, True]


def test_friday_cutoff_is_new_york_local(cfg):
    spec = cfg["fixed_for_now"]["friday_no_entry_after"]
    ts = pd.DatetimeIndex(pd.to_datetime(["2023-07-14 19:59", "2023-07-14 20:00", "2023-01-13 20:30", "2023-01-13 21:00"], utc=True))
    assert list(friday_cutoff_mask(ts, spec)) == [False, True, False, True]
