"""Diagnostics from ``uvp6_create_samples_alr.m``: UVP-vs-ALR time-depth
comparison plots, the sliding r² clock-offset estimate, and sampling-interval
statistics.

Currently writes these figures:

    <outdir>/uvp_alr_timedepth.png                     2 panels, linear axes
    <outdir>/uvp_alr_timedepth_fullspan.png            3 panels incl. best offset
    <outdir>/daily_plots/uvp_alr_timedepth_<date>.png  one per day with data
    <outdir>/overview_plots/uvp_alr_timedepth_all_days.png
    <outdir>/uvp_alr_sampling_intervals.png
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .matlab_compat import finite_times, seconds_between

__all__ = [
    "BinnedDepths",
    "bin_depths",
    "lag_sweep",
    "plot_one_day",
    "make_timedepth_plots",
    "sampling_interval_diagnostics",
]

# MATLAB's default colour order: series 1 (UVP) blue, series 2 (ALR) orange.
C_UVP = "#0072BD"
C_ALR = "#D95319"
C_LAG = "#FF0000"

_EMPTY_T = np.array([], dtype="datetime64[ns]")
_EMPTY_F = np.array([], dtype=float)


def _as_times(t) -> np.ndarray:
    return np.asarray(t, dtype="datetime64[ns]").ravel()


def _day_floor(t):
    """``dateshift(t, 'start', 'day')``; a scalar in gives a scalar out."""
    out = np.asarray(t, dtype="datetime64[ns]").astype("datetime64[D]").astype("datetime64[ns]")
    return out[()] if out.ndim == 0 else out


def _ts(x) -> pd.Timestamp:
    x = np.asarray(x, dtype="datetime64[ns]")
    return pd.Timestamp(x[()] if x.ndim == 0 else x)


def _pydt(x):
    return _ts(x).to_pydatetime()


def _concat_series(times: Sequence, depths: Sequence) -> tuple[np.ndarray, np.ndarray]:
    ts, zs = [], []
    for t, z in zip(times, depths):
        t = _as_times(t)
        z = np.asarray(z, dtype=float).ravel()
        if t.size == 0 or z.size == 0:
            continue
        ts.append(t)
        zs.append(z)
    if not ts:
        return _EMPTY_T.copy(), _EMPTY_F.copy()
    return np.concatenate(ts), np.concatenate(zs)


# ---------------------------------------------------------------------------
# 10 s median binning (discretize + accumarray(@median))
# ---------------------------------------------------------------------------

@dataclass
class BinnedDepths:
    edges: np.ndarray
    centers: np.ndarray
    uvp_med: np.ndarray
    alr_med: np.ndarray
    abs_diff: np.ndarray
    rel_diff: np.ndarray

    @property
    def empty(self) -> bool:
        return self.centers.size == 0


def _bin_median(t: np.ndarray, z: np.ndarray, edges: np.ndarray, nb: int) -> np.ndarray:
    out = np.full(nb, np.nan)
    if t.size == 0 or nb == 0:
        return out
    b = np.searchsorted(edges, t, side="right") - 1
    b[t == edges[-1]] = nb - 1  # discretize closes the last bin on the right
    ok = (b >= 0) & (b < nb) & ~np.isnat(t)
    if not ok.any():
        return out
    keys = b[ok]
    vals = pd.Series(z[ok])
    med = vals.groupby(keys).median()
    has_nan = vals.isna().groupby(keys).any()  # MATLAB median propagates NaN
    out[med.index.to_numpy()] = med.to_numpy()
    out[has_nan.index.to_numpy()[has_nan.to_numpy()]] = np.nan
    return out


def bin_depths(t_uvp, z_uvp, t_alr, z_alr, bin_seconds: int = 10) -> BinnedDepths:
    """Median depth per ``bin_seconds`` bin across the joint UVP/ALR extent,
    plus absolute and relative (% of UVP) differences."""
    t_uvp = _as_times(t_uvp)
    z_uvp = np.asarray(z_uvp, dtype=float).ravel()
    t_alr = _as_times(t_alr)
    z_alr = np.asarray(z_alr, dtype=float).ravel()

    cands = [ft for ft in (finite_times(t_uvp), finite_times(t_alr)) if ft.size]
    if not cands:
        return BinnedDepths(_EMPTY_T.copy(), _EMPTY_T.copy(), _EMPTY_F.copy(), _EMPTY_F.copy(), _EMPTY_F.copy(), _EMPTY_F.copy())
    t_min = min(ft.min() for ft in cands)
    t_max = max(ft.max() for ft in cands)

    step = np.timedelta64(int(bin_seconds), "s")
    n_edges = int((t_max + step - t_min) // step) + 1  # t_min : step : t_max + step
    edges = t_min + np.arange(n_edges) * step
    centers = edges[:-1] + np.timedelta64(int(bin_seconds) * 500, "ms")
    nb = n_edges - 1

    uvp_med = _bin_median(t_uvp, z_uvp, edges, nb)
    alr_med = _bin_median(t_alr, z_alr, edges, nb)
    abs_diff = np.abs(uvp_med - alr_med)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_diff = 100.0 * (abs_diff / uvp_med)
    rel_diff[uvp_med == 0] = np.nan
    return BinnedDepths(edges, centers, uvp_med, alr_med, abs_diff, rel_diff)


# ---------------------------------------------------------------------------
# Sliding 31-bin r² lag estimation
# ---------------------------------------------------------------------------

def lag_sweep(binned: BinnedDepths, window_bins: int = 31, search_seconds: float = 60.0,
              default_bin_seconds: float = 10.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each ``window_bins``-wide window of jointly-valid bins, the lag (in
    bins, converted to seconds) that maximises r² between UVP and ALR depth.

    Returns ``(window_centre_times, best_lag_seconds, best_r2)``; all empty
    when fewer than ``window_bins`` bins are valid on both sides.
    """
    empty = (_EMPTY_T.copy(), _EMPTY_F.copy(), _EMPTY_F.copy())
    if binned.empty:
        return empty
    valid = np.isfinite(binned.uvp_med) & np.isfinite(binned.alr_med)
    if int(valid.sum()) < window_bins:
        return empty
    u = binned.uvp_med[valid]
    a = binned.alr_med[valid]
    t = binned.centers[valid]

    if t.size >= 2:
        bin_dt = float(np.median(seconds_between(t[1:], t[:-1])))
        if not np.isfinite(bin_dt) or bin_dt <= 0:
            bin_dt = default_bin_seconds
    else:
        bin_dt = default_bin_seconds

    n = u.size
    w = window_bins
    hw = w // 2
    lag_max = max(1, int(math.floor(search_seconds / bin_dt + 0.5)))
    n_centers = n - 2 * hw
    if n_centers <= 0:
        return empty

    U = sliding_window_view(u, w)[:n_centers]
    A = sliding_window_view(a, w)[:n_centers]
    Uc = U - U.mean(axis=1, keepdims=True)
    Ac = A - A.mean(axis=1, keepdims=True)
    su = np.einsum("ij,ij->i", Uc, Uc)
    sa = np.einsum("ij,ij->i", Ac, Ac)

    best_r2 = np.full(n_centers, -np.inf)
    best_lag = np.zeros(n_centers, dtype=int)
    for ell in range(-lag_max, lag_max + 1):
        lo = max(0, -ell)
        hi = min(n_centers, n_centers - ell)
        if hi <= lo:
            continue
        ci = np.arange(lo, hi)
        cj = ci + ell
        num = np.einsum("ij,ij->i", Uc[ci], Ac[cj])
        with np.errstate(divide="ignore", invalid="ignore"):
            r2 = num ** 2 / (su[ci] * sa[cj])
        better = np.isfinite(r2) & (r2 > best_r2[ci])
        best_r2[ci[better]] = r2[better]
        best_lag[ci[better]] = ell

    return t[hw:n - hw], best_lag * bin_dt, best_r2


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _in_window(t: np.ndarray, start, end) -> np.ndarray:
    if start is None or end is None:
        return np.ones(t.shape, dtype=bool)
    return (t >= start) & (t < end)


def _plot_top(ax, start, end, uvp_time_series, uvp_depth_series, have_alr, t_alr, z_alr,
              uvp_ms=4, alr_ms=8, legend=True, title=None):
    added = False
    for tt, zz in zip(uvp_time_series, uvp_depth_series):
        tt = _as_times(tt)
        zz = np.asarray(zz, dtype=float).ravel()
        if tt.size == 0 or zz.size == 0:
            continue
        sel = _in_window(tt, start, end)
        if sel.any():
            ax.plot(tt[sel], zz[sel], ".", ms=uvp_ms, color=C_UVP, label="UVP" if not added else "_nolegend_")
            added = True
    if have_alr:
        sel_a = _in_window(t_alr, start, end)
        if sel_a.any():
            ax.plot(t_alr[sel_a], z_alr[sel_a], ".", ms=alr_ms, color=C_ALR, label="ALR")
    ax.grid(True)
    ax.invert_yaxis()
    ax.set_xlabel("Time")
    ax.set_ylabel("Depth (m)")
    if legend and ax.get_legend_handles_labels()[0]:
        ax.legend(loc="best")
    if title:
        ax.set_title(title)


def _plot_bottom(ax, start, end, centers, rel_diff, abs_diff, log_left=True, lw=1.0,
                 ylabel_left="Depth Difference (%)", ylabel_right="Depth Difference (m)"):
    ax.grid(True)
    ax_r = ax.twinx()
    if log_left:
        rel_plot = np.array(rel_diff, dtype=float, copy=True)
        rel_plot[rel_plot <= 0] = np.nan  # sanitise for the log axis
        ax.set_yscale("log")
        ax.set_ylim(0.1, 1000)
    else:
        rel_plot = rel_diff
    if centers.size:
        sel_b = _in_window(centers, start, end)
        if sel_b.any():
            ax.plot(centers[sel_b], rel_plot[sel_b], "-", lw=lw, color=C_UVP)
            ax_r.plot(centers[sel_b], abs_diff[sel_b], "-", lw=lw, color=C_ALR)
    ax.set_ylabel(ylabel_left, color=C_UVP)
    ax.tick_params(axis="y", colors=C_UVP)
    ax_r.set_ylabel(ylabel_right, color=C_ALR)
    ax_r.tick_params(axis="y", colors=C_ALR)
    return ax_r


def plot_one_day(ax_top, ax_bot, day_start, day_end, uvp_time_series, uvp_depth_series,
                 have_alr, t_alr, z_alr, centers, rel_diff, abs_diff):
    """The MATLAB ``plot_one_day`` helper: raw markers on top, relative (log,
    left) and absolute (right) depth differences below, x axes linked."""
    _plot_top(ax_top, day_start, day_end, uvp_time_series, uvp_depth_series, have_alr, t_alr, z_alr,
              title=f"UVP & ALR time–depth ({_ts(day_start):%Y-%m-%d})")
    _plot_bottom(ax_bot, day_start, day_end, centers, rel_diff, abs_diff, log_left=True, lw=1.0)
    ax_top.set_xlim(_pydt(day_start), _pydt(day_end))
    ax_bot.set_xlim(_pydt(day_start), _pydt(day_end))
    ax_top.sharex(ax_bot)


# ---------------------------------------------------------------------------
# The plotting blocks of the driver
# ---------------------------------------------------------------------------

def make_timedepth_plots(outdir, uvp_time_series: Sequence, uvp_depth_series: Sequence,
                         alr_time=None, alr_depth=None, verbose: bool = True) -> dict[str, Path]:
    """Write every time-depth diagnostic figure and return their paths."""
    outdir = Path(outdir)
    daily_dir = outdir / "daily_plots"
    overview_dir = outdir / "overview_plots"
    for d in (outdir, daily_dir, overview_dir):
        d.mkdir(parents=True, exist_ok=True)

    t_uvp, z_uvp = _concat_series(uvp_time_series, uvp_depth_series)
    have_alr = alr_time is not None and np.asarray(alr_time).size > 0
    t_alr = _as_times(alr_time) if have_alr else _EMPTY_T.copy()
    z_alr = np.asarray(alr_depth, dtype=float).ravel() if have_alr else _EMPTY_F.copy()

    binned = bin_depths(t_uvp, z_uvp, t_alr, z_alr)
    centers, rel_diff, abs_diff = binned.centers, binned.rel_diff, binned.abs_diff
    written: dict[str, Path] = {}

    # ---- (1) combined 2-panel figure with linear difference axes
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.5), constrained_layout=True)
    _plot_top(ax1, None, None, uvp_time_series, uvp_depth_series, have_alr, t_alr, z_alr, title="UVP & ALR time–depth")
    _plot_bottom(ax2, None, None, centers, rel_diff, abs_diff, log_left=False)
    ax2.set_xlabel("Time")
    ax2.set_title("Absolute and Relative percentage depth difference\n((UVP - ALR) / Median UVP) * 100, 10 s median bins")
    ax1.sharex(ax2)
    out = outdir / "uvp_alr_timedepth.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    written["timedepth"] = out
    if verbose:
        print(f"Saved diagnostic plot to: {out}")

    # ---- full extent, whole days
    if not binned.empty:
        full_start = _day_floor(centers.min())
        full_end = _day_floor(centers.max()) + np.timedelta64(1, "D")
    elif t_uvp.size:
        ft = finite_times(t_uvp)
        full_start = _day_floor(ft.min())
        full_end = _day_floor(ft.max()) + np.timedelta64(1, "D")
    elif t_alr.size:
        ft = finite_times(t_alr)
        full_start = _day_floor(ft.min())
        full_end = _day_floor(ft.max()) + np.timedelta64(1, "D")
    else:
        raise ValueError("No time data to plot.")

    lag_times, lag_best_sec, _r2 = lag_sweep(binned) if have_alr else (_EMPTY_T.copy(), _EMPTY_F.copy(), _EMPTY_F.copy())

    # ---- (2) full-span 3-panel figure
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10.5), constrained_layout=True)
    plot_one_day(ax1, ax2, full_start, full_end, uvp_time_series, uvp_depth_series,
                 have_alr, t_alr, z_alr, centers, rel_diff, abs_diff)
    ax3.grid(True)
    if lag_best_sec.size:
        ax3.plot(lag_times, lag_best_sec, "x", ms=6, mew=1.2, color=C_LAG)
    ax3.set_ylabel("Best offset (s) — 31-bin r²")
    ax3.set_xlabel("Time")
    ax3.set_title("ALR → UVP offset (seconds)")
    ax3.set_xlim(_pydt(full_start), _pydt(full_end))
    ax3.sharex(ax2)
    out = outdir / "uvp_alr_timedepth_fullspan.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    written["fullspan"] = out
    if verbose:
        print(f"Saved full-span diagnostic plot to: {out}")

    # ---- (3) daily plots
    if not binned.empty:
        day_starts = np.unique(_day_floor(centers[~np.isnat(centers)]))
    else:
        cands = np.concatenate([finite_times(t_uvp), finite_times(t_alr)])
        day_starts = np.unique(_day_floor(cands))

    one_day = np.timedelta64(1, "D")
    daily: list[Path] = []
    for ds in day_starts:
        de = ds + one_day
        has_uvp = t_uvp.size > 0 and bool(((t_uvp >= ds) & (t_uvp < de)).any())
        has_alr = have_alr and bool(((t_alr >= ds) & (t_alr < de)).any())
        has_bins = centers.size > 0 and bool(((centers >= ds) & (centers < de) & (~np.isnan(abs_diff) | ~np.isnan(rel_diff))).any())
        if not (has_uvp or has_alr or has_bins):
            continue
        fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 7.5), constrained_layout=True)
        plot_one_day(ax_top, ax_bot, ds, de, uvp_time_series, uvp_depth_series,
                     have_alr, t_alr, z_alr, centers, rel_diff, abs_diff)
        out = daily_dir / f"uvp_alr_timedepth_{_ts(ds):%Y-%m-%d}.png"
        fig.savefig(out, dpi=150)
        plt.close(fig)
        daily.append(out)
        if verbose:
            print(f"Saved daily plot to: {out}")
    written["daily"] = daily

    # ---- (4) overview: every day in its own top/bottom pair of tiles.
    # (The MATLAB grid is sized for one tile per day but draws two, so it never
    #  completed; the layout here is what that code intends.)
    ndays = len(day_starts)
    if ndays > 0:
        cols = min(4, ndays)
        rows = int(math.ceil(ndays / cols))
        fig = plt.figure(figsize=(4.4 * cols, 5.4 * rows), constrained_layout=True)
        gs = fig.add_gridspec(2 * rows, cols, height_ratios=[3, 2] * rows)
        for i, ds in enumerate(day_starts):
            de = ds + one_day
            r, c = divmod(i, cols)
            ax_top = fig.add_subplot(gs[2 * r, c])
            ax_bot = fig.add_subplot(gs[2 * r + 1, c])
            _plot_top(ax_top, ds, de, uvp_time_series, uvp_depth_series, have_alr, t_alr, z_alr,
                      uvp_ms=2, alr_ms=4, legend=False, title=f"{_ts(ds):%Y-%m-%d}")
            ax_top.set_xlabel("")
            # tiles are narrow: a few concise time ticks instead of hourly date stamps
            locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
            ax_top.xaxis.set_major_locator(locator)
            ax_top.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            _plot_bottom(ax_bot, ds, de, centers, rel_diff, abs_diff, log_left=True, lw=0.75,
                         ylabel_left="Δdepth (%)", ylabel_right="Δdepth (m)")
            ax_top.set_xlim(_pydt(ds), _pydt(de))
            ax_bot.set_xlim(_pydt(ds), _pydt(de))
            ax_bot.sharex(ax_top)
            ax_bot.set_xlabel("")
            ax_bot.tick_params(axis="x", labelbottom=False)
        out = overview_dir / "uvp_alr_timedepth_all_days.png"
        fig.savefig(out, dpi=200)
        plt.close(fig)
        written["overview"] = out
        if verbose:
            print(f"Saved overview multipanel to: {out}")

    return written


# ---------------------------------------------------------------------------
# Sampling interval diagnostics
# ---------------------------------------------------------------------------

def _intervals(times: Sequence) -> np.ndarray:
    parts = []
    for tt in times:
        tt = _as_times(tt)
        if tt.size < 2:
            continue
        parts.append(seconds_between(tt[1:], tt[:-1]))
    return np.concatenate(parts) if parts else _EMPTY_F.copy()


def _report(label: str, x: np.ndarray) -> None:
    if x.size == 0:
        import warnings
        warnings.warn(f"No valid {label} time intervals found.")
    else:
        # ASCII only: a cp1252 Windows console cannot print the MATLAB 'Δt'
        print(f"{label} median dt = {np.nanmedian(x):.3f} s (mean = {np.nanmean(x):.3f} s, N={x.size})")


def sampling_interval_diagnostics(outdir, uvp_time_series: Sequence, alr_time=None) -> dict:
    """Print median/mean sampling intervals and save the histogram figure."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    print("\n--- Sampling interval diagnostics ---")
    uvp_intervals = _intervals(uvp_time_series)
    _report("UVP", uvp_intervals)
    alr_intervals = _intervals([alr_time]) if alr_time is not None and np.asarray(alr_time).size > 1 else _EMPTY_F.copy()
    _report("ALR", alr_intervals)

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    for x, label, color in ((uvp_intervals, "UVP", C_UVP), (alr_intervals, "ALR", C_ALR)):
        x = x[np.isfinite(x)]
        if x.size == 0:
            continue
        bins = np.arange(math.floor(x.min()), math.floor(x.max()) + 2, 1.0)  # BinWidth 1
        ax.hist(x, bins=bins, alpha=0.6, label=label, color=color)
    ax.grid(True)
    ax.set_xlabel("Interval between measurements (s)")
    ax.set_ylabel("Count")
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    ax.set_title("UVP vs ALR sampling interval distribution")
    out = outdir / "uvp_alr_sampling_intervals.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return {"uvp_intervals": uvp_intervals, "alr_intervals": alr_intervals, "figure": out}
