"""Load and validate the H001 YAML config, and expand the research grid."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "h001.yaml"

GRID_KEYS = ("zone_base", "liquidity", "stop", "exit", "entry_sessions")
KNOWN_OPTIONS = {
    "zone_base": {"consecutive_3", "nearest_3"},
    "liquidity": {"h1_swing", "prev_day", "asian_session", "equal_levels"},
    "stop": {"sweep_wick", "confirmation_swing"},
    "exit": {"fixed_3r", "extended", "trailing", "partial"},
    "execution": {"swing_h1", "intraday_m5"},
    "setup_type": {"continuation", "reversal_one", "reversal_both"},
}


class ConfigError(ValueError):
    pass


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG) as fh:
        raw = yaml.safe_load(fh)
    if "h001" not in raw:
        raise ConfigError("config must have a top-level 'h001' key")
    cfg = raw["h001"]
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    for key in ("calendar", "instruments", "costs", "grid", "fixed_for_now", "validation", "strategies"):
        if key not in cfg:
            raise ConfigError(f"missing section: {key}")
    for k in GRID_KEYS:
        opts = cfg["grid"].get(k)
        if not opts:
            raise ConfigError(f"grid.{k} is empty")
        if k in KNOWN_OPTIONS:
            bad = set(opts) - KNOWN_OPTIONS[k]
            if bad:
                raise ConfigError(f"grid.{k}: unknown options {sorted(bad)}")
    sets = cfg["calendar"]["entry_session_sets"]
    for opt in cfg["grid"]["entry_sessions"]:
        if opt not in sets:
            raise ConfigError(f"entry_sessions option {opt!r} not defined in calendar.entry_session_sets")
        for s in sets[opt]:
            if s not in cfg["calendar"]["sessions"]:
                raise ConfigError(f"session {s!r} not defined")
    for k in ("execution", "setup_type"):
        bad = set(cfg["strategies"][k]) - KNOWN_OPTIONS[k]
        if bad:
            raise ConfigError(f"strategies.{k}: unknown {sorted(bad)}")
    for pair in cfg["instruments"]:
        if pair not in cfg["pip_size"]:
            raise ConfigError(f"pip_size missing for {pair}")
        if pair not in cfg["costs"]["spread_floor_pips"]:
            raise ConfigError(f"costs.spread_floor_pips missing for {pair}")


@dataclass(frozen=True)
class GridPoint:
    zone_base: str
    liquidity: str
    stop: str
    exit: str
    entry_sessions: str

    @property
    def scan_key(self) -> tuple:
        """Options that change which setups are found (stop/exit only change the trade)."""
        return (self.zone_base, self.liquidity, self.entry_sessions)

    @property
    def id(self) -> str:
        return "|".join((self.zone_base, self.liquidity, self.stop, self.exit, self.entry_sessions))


def grid_points(cfg: dict) -> Iterator[GridPoint]:
    g = cfg["grid"]
    for combo in itertools.product(*(g[k] for k in GRID_KEYS)):
        yield GridPoint(*combo)


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


def scaled(cfg: dict, dotted_key: str, factor: float) -> dict:
    """Copy of cfg with one fixed_for_now numeric setting scaled (sensitivity test).

    dotted_key is relative to fixed_for_now, e.g. "swing_k.h1" or "impulse_atr_h4".
    Integer settings are rounded and kept >= 1.
    """
    out = copy.deepcopy(cfg)
    node: Any = out["fixed_for_now"]
    parts = dotted_key.split(".")
    for p in parts[:-1]:
        node = node[p]
    old = node[parts[-1]]
    if isinstance(old, bool) or not isinstance(old, (int, float)):
        raise ConfigError(f"{dotted_key} is not numeric")
    new = old * factor
    if isinstance(old, int):
        new = max(1, int(round(new)))
        if new == old:  # make sure an integer actually moves
            new = old + (1 if factor > 1 else -1)
            new = max(1, new)
    node[parts[-1]] = new
    return out


def numeric_fixed_keys(cfg: dict) -> list[str]:
    keys: list[str] = []

    def walk(node, prefix):
        for k, v in node.items():
            path = f"{prefix}{k}"
            if isinstance(v, dict):
                walk(v, path + ".")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                keys.append(path)

    walk(cfg["fixed_for_now"], "")
    return keys
