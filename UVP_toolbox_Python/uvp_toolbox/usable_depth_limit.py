"""Detection of the usable depth limit from the instrument's black-image noise.

Translation of ``Ressources_partagees/UsableDepthLimit.m`` (Camille Catalano,
LOV, 2020/11) including its three methods.  The noise is highest near the
surface and decays to a plateau at depth; ``deep_black_limit`` is the depth
below which the black level is assumed to come from the instrument alone.

Original MATLAB script by Camille Catalano, LOV, 2020/11
"""

from __future__ import annotations

import warnings

import numpy as np

from .matlab_compat import movmean, num2str

__all__ = ["usable_depth_limit"]


def usable_depth_limit(depth, noise, deep_black_limit: float, method: str = "thres") -> float:
    """Return ``Zusable``: the depth above which images are noise-dominated.

    ``method`` is ``'thres'`` (default), ``'diff'`` or ``'diff2'``.  Returns
    ``0`` when there is only deep data and ``NaN`` when there are fewer than
    two points below ``deep_black_limit``.
    """
    depth = np.asarray(depth, dtype=float).ravel()
    noise = np.asarray(noise, dtype=float).ravel()

    aa = np.flatnonzero(depth <= deep_black_limit)
    if aa.size == 0:
        warnings.warn("WARNING : only deep data. Zlim is set to 0m")
        return 0.0
    mean_noise_surf = float(np.mean(noise[aa]))

    aa = np.flatnonzero(depth > deep_black_limit)
    if aa.size < 2:
        warnings.warn(f"WARNING : no data under {num2str(deep_black_limit)}m ! Zlim can not be computed")
        return float("nan")
    mean_noise_deep = float(np.mean(noise[aa]))
    std_noise_deep = float(np.std(noise[aa], ddof=1))

    movmean_noise = movmean(noise, 10)

    if method == "diff":
        return _usable_depth_limit_diff(depth, movmean_noise, mean_noise_surf, mean_noise_deep, std_noise_deep)
    if method == "diff2":
        return _usable_depth_limit_diff2(depth, movmean_noise, mean_noise_surf, mean_noise_deep, std_noise_deep)
    if method == "thres":
        return _usable_depth_limit_thres(depth, movmean_noise, mean_noise_deep, std_noise_deep)
    raise ValueError("ERROR : usable depth limit method not reconized !")


def _usable_depth_limit_diff(depth, noise, mean_noise_surf, mean_noise_deep, std_noise_deep) -> float:
    """Depth of the steepest decrease of the smoothed noise (min of ``diff``)."""
    if mean_noise_surf > mean_noise_deep + std_noise_deep * 5:
        d = np.diff(noise)
        aa = np.flatnonzero(d == np.nanmin(d))
        return float(depth[aa[0]])
    return 0.0


def _usable_depth_limit_diff2(depth, noise, mean_noise_surf, mean_noise_deep, std_noise_deep) -> float:
    """Depth of the inflection point (max of the second difference)."""
    if mean_noise_surf > mean_noise_deep + std_noise_deep * 5:
        d2 = np.diff(noise, 2)
        aa = np.flatnonzero(d2 == np.nanmax(d2))
        return float(depth[aa[0]])
    return 0.0


def _usable_depth_limit_thres(depth, movmean_noise, mean_noise_deep, std_noise_deep) -> float:
    """Deepest point where the smoothed noise exceeds ``mean + 5 * std`` of the
    deep noise; 0 when the surface noise never rises above it."""
    aa = np.flatnonzero(movmean_noise > mean_noise_deep + std_noise_deep * 5)
    if aa.size:
        return float(depth[aa[-1]])
    return 0.0
