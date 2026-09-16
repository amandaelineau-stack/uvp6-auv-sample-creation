"""Helpers reproducing the MATLAB built-in semantics the toolbox relies on.

Each function exists because the MATLAB original depends on a behaviour with
no drop-in NumPy/pandas equivalent: ``num2str``'s default precision,
``movmean``'s window alignment, ``datestr``'s fixed formats.  Keeping them in
one place makes the parity assumptions explicit and unit-testable.

Original MATLAB script by Camille Catalano, LOV, 2020/11
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

__all__ = [
    "num2str",
    "movmean",
    "epoch_seconds_to_datetime64",
    "finite_times",
    "seconds_between",
    "datestr_yyyymmdd_HHMMSS",
    "datestr_yyyymmddHHMMSSFFF",
]

_EPOCH_NS = np.datetime64("1970-01-01T00:00:00", "ns")


def num2str(x) -> str:
    """MATLAB ``num2str(x)`` for a scalar with the default format.

    MATLAB picks ``%.<n>g`` with ``n = min(max(floor(log10(|x|)) + 5, 5), 16)``
    ("keep 4 significant figures after the decimal point"), so ``pi`` becomes
    ``'3.1416'`` and ``-15.368508`` becomes ``'-15.3685'``.  Integers print in
    full and NaN/Inf keep MATLAB's capitalisation.
    """
    if isinstance(x, (bool, np.bool_)):
        return "1" if x else "0"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    x = float(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Inf" if x > 0 else "-Inf"
    xmax = abs(x) if x != 0 else 1.0
    ndgt = math.floor(math.log10(xmax))
    ndgt = min(max(ndgt + 5, 5), 16)
    return f"%.{ndgt}g" % x


def movmean(x, k: int) -> np.ndarray:
    """MATLAB ``movmean(x, k)`` with the default ``'shrink'`` endpoints and
    ``'includenan'`` NaN handling.

    For even ``k`` MATLAB centres the window on the current *and previous*
    element, i.e. ``x[i - k/2 : i + k/2 - 1]``; for odd ``k`` it is symmetric.
    Windows are truncated at the ends rather than padded, and any NaN inside a
    window makes that output NaN.
    """
    if k < 1:
        raise ValueError("window length must be >= 1")
    x = np.asarray(x, dtype=float).ravel()
    n = x.size
    if k % 2 == 0:
        kb, kf = k // 2, k // 2 - 1
    else:
        kb = kf = (k - 1) // 2
    idx = np.arange(n)
    lo = np.clip(idx - kb, 0, n)
    hi = np.clip(idx + kf + 1, 0, n)
    isnan = np.isnan(x)
    csum = np.concatenate(([0.0], np.cumsum(np.where(isnan, 0.0, x))))
    cnan = np.concatenate(([0], np.cumsum(isnan)))
    out = (csum[hi] - csum[lo]) / (hi - lo)
    out[(cnan[hi] - cnan[lo]) > 0] = np.nan
    return out


def epoch_seconds_to_datetime64(seconds) -> np.ndarray:
    """Seconds since 1970-01-01 UTC (float, NaN allowed) -> ``datetime64[ns]``.

    Replaces the MATLAB idiom ``TIME/86400 + datenum(1970,1,1)``; NaN -> NaT.
    """
    s = np.asarray(seconds, dtype=float)
    out = np.full(s.shape, np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    ok = np.isfinite(s)
    if ok.any():
        out[ok] = _EPOCH_NS + np.round(s[ok] * 1e9).astype(np.int64).astype("timedelta64[ns]")
    return out


def finite_times(t) -> np.ndarray:
    """Drop NaT entries (MATLAB ``min``/``max`` ignore NaN; NumPy's do not)."""
    t = np.asarray(t, dtype="datetime64[ns]").ravel()
    return t[~np.isnat(t)]


def seconds_between(later, earlier) -> np.ndarray:
    """Elementwise ``later - earlier`` in float seconds."""
    later = np.asarray(later, dtype="datetime64[ns]")
    earlier = np.asarray(earlier, dtype="datetime64[ns]")
    return (later - earlier) / np.timedelta64(1, "s")


def datestr_yyyymmdd_HHMMSS(t) -> str:
    """MATLAB ``datestr(t, 'yyyymmdd-HHMMss')`` — the sample file's ``sampledatetime``."""
    ts = pd.Timestamp(t)
    if pd.isna(ts):
        return "NaT"
    return ts.strftime("%Y%m%d-%H%M%S")


def datestr_yyyymmddHHMMSSFFF(times) -> list[str]:
    """MATLAB ``datestr(t, 'yyyymmddHHMMSSFFF')`` — the CTD file time column.

    17 characters, millisecond precision (rounded, as ``datestr`` does).
    NaT becomes an empty string.
    """
    idx = pd.DatetimeIndex(np.asarray(times, dtype="datetime64[ns]")).round("ms")
    formatted = idx.strftime("%Y%m%d%H%M%S%f")
    return [s[:-3] if isinstance(s, str) else "" for s in formatted]
