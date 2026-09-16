"""Plotting of the outputs built by alr_data.py.

Nothing here loads, builds or writes data — every function takes a dataframe
that alr_data.py has already produced, and draws it.

    import alr_plots

    alr_plots.plot_pressure_overview(big_df)
    alr_plots.plot_profile_detection(profiles_df, custom_column="pitch", ...)
    alr_plots.plot_vertical_velocity(profiles_df)
    alr_plots.plot_series_pair(big_df_with_profiles, "Temperature", "position_lat")
    alr_plots.plot_profiles_and_transects(big_df_with_profiles)

Each function returns (fig, axs) so the notebook can tweak the result further.

Backend note: choose your matplotlib backend in the notebook, not here —
'%matplotlib inline' for figures in the notebook, or mpl.use('tkagg') for
interactive pan/zoom windows.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def truncate_cmap(name, minval=0.25, maxval=1.0, n=256):
    """Trim the pale end off a colormap so low values stay legible."""
    cmap = mpl.colormaps[name]
    return mpl.colors.LinearSegmentedColormap.from_list(
        f"trunc({name},{minval},{maxval})", cmap(np.linspace(minval, maxval, n))
    )


def to_pytime(series: pl.Series):
    """Convert Polars datetime column to numpy array of Python datetimes."""
    return np.array(series.to_list())


def split_by_flags(profiles_df):
    """Split a profiles dataframe into (profiles, not_profiles, transects, not_transects)."""
    clean = profiles_df.drop_nans()
    return (
        clean.filter(pl.col("is_profile").cast(pl.Boolean)),
        clean.filter(pl.col("is_profile").cast(pl.Boolean).not_()),
        clean.filter(pl.col("is_transect").cast(pl.Boolean)),
        clean.filter(pl.col("is_transect").cast(pl.Boolean).not_()),
    )


# ---------------------------------------------------------------------------
# 2.4  Inspecting the data
# ---------------------------------------------------------------------------

def plot_pressure_overview(big_df, font_size=18, show=True):
    """Pressure against time for the whole built dataframe (pre-profiling)."""
    plt.rcParams.update({
        "font.size": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
    })

    # Convert TIME column
    df_plot = big_df.with_columns(
        (pl.col("Timestamp") * 1e9).cast(pl.Datetime("ns")).alias("TIME")
    )

    time_vals = df_plot["TIME"].to_numpy()
    pressure_vals = df_plot["Pressure"].to_numpy()

    fig, axs = plt.subplots(1, 1, figsize=(18, 8), sharex=True)

    axs.plot(time_vals, pressure_vals, marker=".", markersize=1, ls="", c="tab:blue")
    axs.set_ylabel("Pressure (dbar)")
    axs.invert_yaxis()

    plt.tight_layout()
    if show:
        plt.show()

    return fig, axs


# ---------------------------------------------------------------------------
# 3.1  Profile detection results
# ---------------------------------------------------------------------------

def plot_profile_detection(
    profiles_df,
    custom_column="pitch",
    gradient_thresholds=[0.05, -0.05],
    cust_gradient_thresholds=[0.005, -0.005],
    show=True,
):
    """Five-panel view of what find_profiles decided.

    Panels: interpolated depth, vertical velocity, profile numbering, the custom
    column, and the -(custom * velocity) product used for the custom threshold.
    """
    profiles, not_profiles, transects, _ = split_by_flags(profiles_df)

    fig, axs = plt.subplots(5, 1, figsize=(18, 10), height_ratios=[3, 3, 1, 3, 3], sharex=True)

    axs[0].set(xlabel="Time", ylabel="Interpolated Depth")
    axs[1].set(xlabel="Time", ylabel="Vertical Velocity")
    axs[2].set(xlabel="Time", ylabel="Profile Number")
    axs[3].set(xlabel="Time", ylabel=custom_column)
    axs[4].set(xlabel="Time", ylabel=custom_column)

    # Profile vs not profile (depth + velocity)
    for data, col, label in zip([profiles, not_profiles, transects],
                                ["tab:blue", "tab:red", "tab:orange"],
                                ["Profile", "Not Profile", "Transect"]):
        axs[0].plot(data["TIME"].to_numpy(), -data["INTERP_DEPTH"].to_numpy(),
                    marker=".", markersize=1, ls="", c=col, label=label)
        axs[1].plot(data["TIME"].to_numpy(), data["smooth_grad"].to_numpy(),
                    marker=".", markersize=1, ls="", c=col, label=label)

    # Raw gradients + thresholds
    axs[1].plot(profiles_df["TIME"].to_numpy(), profiles_df["grad"].to_numpy(),
                c="k", alpha=0.1, label="Raw Velocity")
    for val, label in zip(gradient_thresholds, ["Gradient Thresholds", None]):
        axs[1].axhline(val, ls="--", color="gray", label=label)

    # Profile numbers, before and after the duration/backfill filtering
    axs[2].plot(profiles_df["TIME"].to_numpy(), profiles_df["profile_num"].to_numpy(), c="gray")
    axs[2].plot(profiles_df["TIME"].to_numpy(), profiles_df["profile_num_new"].to_numpy(), c="red")

    # Custom column
    if custom_column in profiles_df.columns:
        axs[3].plot(profiles_df["TIME"].to_numpy(),
                    profiles_df[custom_column].to_numpy(),
                    c="purple", marker=".", markersize=1, ls="", label=custom_column)
        axs[3].legend(loc="right")

        # -(custom * velocity) product, the quantity cust_gradient_thresholds acts on
        axs[4].plot(profiles_df["TIME"].to_numpy(),
                    -profiles_df[f"smooth_INTERP_{custom_column}"].to_numpy()
                    * profiles_df["smooth_grad"].to_numpy(),
                    c="purple", marker=".", markersize=1, ls="", label=custom_column)
        axs[4].legend(loc="right")
        axs[4].set_ylim([0, 0.05])

    for val, label in zip(cust_gradient_thresholds, ["Gradient Thresholds", None]):
        axs[4].axhline(val, ls="--", color="gray", label=label)

    for ax in axs[:2]:
        ax.legend(loc="upper right")

    plt.tight_layout()
    if show:
        plt.show()

    return fig, axs


# ---------------------------------------------------------------------------
# 3.2  Plotting just vertical velocities
# ---------------------------------------------------------------------------

def plot_vertical_velocity(profiles_df, ylim=(-0.5, 0.5), font_size=16,
                           font_family="Arial", show=True):
    """Vertical velocity alone, on a fixed y-axis, coloured by classification."""
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
    })

    profiles, not_profiles, transects, _ = split_by_flags(profiles_df)

    fig, axs = plt.subplots(1, 1, figsize=(18, 3), sharex=True)

    axs.set_xlabel("Time")
    axs.set_ylabel("Vertical Velocity (m/s)")
    axs.set_ylim(list(ylim))

    for data, col, label in zip(
            [profiles, not_profiles, transects],
            ["tab:blue", "tab:red", "tab:orange"],
            ["Profile", "Not Profile", "Transect"]):
        axs.plot(
            data["TIME"].to_numpy(),
            data["smooth_grad"].to_numpy(),
            marker=".", markersize=1, ls="", c=col, label=label
        )

    axs.legend(loc="upper right")

    plt.tight_layout()
    if show:
        plt.show()

    return fig, axs


# ---------------------------------------------------------------------------
# 4.0  Annotated dataframe
# ---------------------------------------------------------------------------

def plot_series_pair(big_df_with_profiles, var1="Temperature", var2="position_lat", show=True):
    """Two stacked panels of any two columns against time, sharing the x-axis."""
    df_plot = big_df_with_profiles

    time_vals = df_plot["TIME"].to_numpy()
    var1_vals = df_plot[var1].to_numpy()
    var2_vals = df_plot[var2].to_numpy()

    fig, axs = plt.subplots(2, 1, figsize=(18, 8), sharex=True)

    axs[0].plot(time_vals, var1_vals, marker=".", markersize=1, ls="", c="tab:blue")
    axs[0].set(ylabel=var1)
    axs[0].invert_yaxis()

    axs[1].plot(time_vals, var2_vals, marker=".", markersize=1, ls="", c="purple")
    axs[1].set(xlabel="Time", ylabel=var2)

    plt.tight_layout()
    if show:
        plt.show()

    return fig, axs


def plot_profiles_and_transects(big_df_with_profiles, show=True):
    """Three-panel summary: profiles (original vs filtered), raw pressure, transects.

    Each profile and transect gets its own shade, with inset colorbars keying
    the shade back to the profile/transect number.
    """
    time_vals = to_pytime(big_df_with_profiles["TIME"])
    pressure_vals = big_df_with_profiles["DEPTH"].to_numpy()
    profile_nums = big_df_with_profiles["profile_num"].to_numpy()
    transect_nums = big_df_with_profiles["transect_num"].to_numpy()
    profile_nums_new = big_df_with_profiles["profile_num_new"].to_numpy()

    fig, axs = plt.subplots(3, 1, figsize=(18, 12), height_ratios=[3, 3, 3], sharex=True)

    # === Profile plots ===
    unique_profiles = np.unique(profile_nums[profile_nums >= 0])
    unique_profiles_new = np.unique(profile_nums_new[profile_nums_new >= 0])

    cmap_orig = truncate_cmap("Blues")
    norm_orig = Normalize(vmin=unique_profiles.min(), vmax=unique_profiles.max())
    cmap_new = truncate_cmap("Reds")
    norm_new = Normalize(vmin=unique_profiles_new.min(), vmax=unique_profiles_new.max())

    # Original profiles (blue)
    for pid in unique_profiles:
        mask = profile_nums == pid
        axs[0].plot(time_vals[mask], pressure_vals[mask],
                    color=cmap_orig(norm_orig(pid)), lw=2, alpha=0.9)

    # Filtered profiles (red)
    for pid in unique_profiles_new:
        mask = profile_nums_new == pid
        axs[0].plot(time_vals[mask], pressure_vals[mask],
                    color=cmap_new(norm_new(pid)), lw=1.5, alpha=0.9)

    axs[0].invert_yaxis()
    axs[0].set(ylabel="Pressure (dbar)", title="Profiles (Original vs Filtered)")

    # Colorbars (inset)
    cax1 = inset_axes(axs[0], width="35%", height="4%", loc="lower left", borderpad=2)
    fig.colorbar(ScalarMappable(norm=norm_orig, cmap=cmap_orig),
                 cax=cax1, orientation="horizontal", label="Original profile #")
    cax2 = inset_axes(axs[0], width="35%", height="4%", loc="lower right", borderpad=2)
    fig.colorbar(ScalarMappable(norm=norm_new, cmap=cmap_new),
                 cax=cax2, orientation="horizontal", label="Filtered profile #")

    # === Raw pressure ===
    axs[1].plot(time_vals, pressure_vals, ".", markersize=1, c="tab:blue")
    axs[1].invert_yaxis()
    axs[1].set(ylabel="Pressure (dbar)")

    # === Transects ===
    unique_transects = np.unique(transect_nums[transect_nums >= 0])
    cmap_transects = truncate_cmap("Greens")
    norm_transects = Normalize(vmin=unique_transects.min(), vmax=unique_transects.max())

    for tid in unique_transects:
        mask = transect_nums == tid
        axs[2].plot(time_vals[mask], pressure_vals[mask],
                    color=cmap_transects(norm_transects(tid)), lw=1)

    axs[2].invert_yaxis()
    axs[2].set(ylabel="Pressure (dbar)", title="Transects")

    # Colorbar inset
    cax_tr = inset_axes(axs[2], width="50%", height="4%", loc="lower center", borderpad=1.5)
    fig.colorbar(ScalarMappable(norm=norm_transects, cmap=cmap_transects),
                 cax=cax_tr, orientation="horizontal", label="Transect number")

    fig.tight_layout()
    if show:
        plt.show()

    return fig, axs
