"""EOS-80 seawater density, ported verbatim from ``Ressources_partagees/seawater``.

    sw_smow  -> sw_smow   density of Standard Mean Ocean Water
    sw_dens0 -> sw_dens0  density at atmospheric pressure
    sw_seck  -> sw_seck   secant bulk modulus
    sw_dens  -> sw_dens   density at pressure P

Only ``sw_dens`` is called by the toolbox (SeaExplorer oxygen conversion).
Inputs broadcast like NumPy arrays; ``P`` is in decibars.

Original MATLAB script by Camille Catalano, LOV, 2020/11
"""

from __future__ import annotations

import numpy as np

__all__ = ["sw_smow", "sw_dens0", "sw_seck", "sw_dens"]


def sw_smow(T):
    """Density (kg/m^3) of Standard Mean Ocean Water at temperature ``T`` (deg C)."""
    T = np.asarray(T, dtype=float)
    a0 = 999.842594
    a1 = 6.793952e-2
    a2 = -9.095290e-3
    a3 = 1.001685e-4
    a4 = -1.120083e-6
    a5 = 6.536332e-9
    return a0 + (a1 + (a2 + (a3 + (a4 + a5 * T) * T) * T) * T) * T


def sw_dens0(S, T):
    """Density (kg/m^3) at atmospheric pressure, ``S`` in psu, ``T`` in deg C."""
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    b0 = 8.24493e-1
    b1 = -4.0899e-3
    b2 = 7.6438e-5
    b3 = -8.2467e-7
    b4 = 5.3875e-9
    c0 = -5.72466e-3
    c1 = 1.0227e-4
    c2 = -1.6546e-6
    d0 = 4.8314e-4
    return (sw_smow(T)
            + (b0 + (b1 + (b2 + (b3 + b4 * T) * T) * T) * T) * S
            + (c0 + (c1 + c2 * T) * T) * S * np.sqrt(S)
            + d0 * S ** 2)


def sw_seck(S, T, P):
    """Secant bulk modulus (bars); ``P`` in decibars."""
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    P = np.asarray(P, dtype=float) / 10.0  # db -> atmospheric pressure units

    h3 = -5.77905e-7
    h2 = 1.16092e-4
    h1 = 1.43713e-3
    h0 = 3.239908
    AW = h0 + (h1 + (h2 + h3 * T) * T) * T

    k2 = 5.2787e-8
    k1 = -6.12293e-6
    k0 = 8.50935e-5
    BW = k0 + (k1 + k2 * T) * T

    e4 = -5.155288e-5
    e3 = 1.360477e-2
    e2 = -2.327105
    e1 = 148.4206
    e0 = 19652.21
    KW = e0 + (e1 + (e2 + (e3 + e4 * T) * T) * T) * T

    j0 = 1.91075e-4
    i2 = -1.6078e-6
    i1 = -1.0981e-5
    i0 = 2.2838e-3
    SR = np.sqrt(S)
    A = AW + (i0 + (i1 + i2 * T) * T + j0 * SR) * S

    m2 = 9.1697e-10
    m1 = 2.0816e-8
    m0 = -9.9348e-7
    B = BW + (m0 + (m1 + m2 * T) * T) * S

    f3 = -6.1670e-5
    f2 = 1.09987e-2
    f1 = -0.603459
    f0 = 54.6746
    g2 = -5.3009e-4
    g1 = 1.6483e-2
    g0 = 7.944e-2
    K0 = KW + (f0 + (f1 + (f2 + f3 * T) * T) * T + (g0 + (g1 + g2 * T) * T) * SR) * S

    return K0 + (A + B * P) * P


def sw_dens(S, T, P):
    """Density (kg/m^3) of seawater at salinity ``S`` (psu), temperature ``T``
    (deg C) and pressure ``P`` (db)."""
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    P = np.asarray(P, dtype=float)
    densP0 = sw_dens0(S, T)
    K = sw_seck(S, T, P)
    return densP0 / (1.0 - (P / 10.0) / K)
