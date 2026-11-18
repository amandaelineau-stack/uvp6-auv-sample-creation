"""Where each figure and QC file goes under the figures folder.

    <figures>/
    ├── phase_qc/
    │   ├── <AUV>_phase_detection.png
    │   └── <AUV>_phase_sectioning.png
    └── qc/
        ├── qc_summary.txt
        ├── depth_time_agreement_check/
        │   ├── overview_plots/
        │   │   ├── uvp_auv_depth_time_deployment.png
        │   │   ├── uvp_auv_depth_time_regression_offset.png
        │   │   └── uvp_auv_timedepth_all_days.png
        │   └── daily_plots/
        │       └── uvp_auv_timedepth_<date>.png
        ├── coverage_check/
        │   ├── uvp_auv_coverage_map.png
        │   └── qc_coverage.csv
        └── sample_size_interval_check/
            ├── uvp_auv_sampling_intervals.png
            └── uvp_auv_sample_sizes.png

The toolbox, ``run_UVP_toolbox.py`` and ``app.py`` all take paths from here,
so a name or folder changes in one place.
"""

from __future__ import annotations

from pathlib import Path

PHASE_QC_DIR = "phase_qc"
QC_DIR = "qc"
DEPTH_TIME_DIR = f"{QC_DIR}/depth_time_agreement_check"
OVERVIEW_DIR = f"{DEPTH_TIME_DIR}/overview_plots"
DAILY_DIR = f"{DEPTH_TIME_DIR}/daily_plots"
COVERAGE_DIR = f"{QC_DIR}/coverage_check"
SAMPLE_DIR = f"{QC_DIR}/sample_size_interval_check"

# Path of each output, relative to the figures folder
FIGURES = {
    "phase_detection": f"{PHASE_QC_DIR}/{{vehicle}}_phase_detection.png",
    "phase_sectioning": f"{PHASE_QC_DIR}/{{vehicle}}_phase_sectioning.png",
    "qc_summary": f"{QC_DIR}/qc_summary.txt",
    "depth_time_deployment": f"{OVERVIEW_DIR}/uvp_auv_depth_time_deployment.png",
    "depth_time_regression": f"{OVERVIEW_DIR}/uvp_auv_depth_time_regression_offset.png",
    "all_days": f"{OVERVIEW_DIR}/uvp_auv_timedepth_all_days.png",
    "daily": f"{DAILY_DIR}/uvp_auv_timedepth_{{date}}.png",
    "coverage_map": f"{COVERAGE_DIR}/uvp_auv_coverage_map.png",
    "coverage_csv": f"{COVERAGE_DIR}/qc_coverage.csv",
    "sampling_intervals": f"{SAMPLE_DIR}/uvp_auv_sampling_intervals.png",
    "sample_sizes": f"{SAMPLE_DIR}/uvp_auv_sample_sizes.png",
}


def figure_path(figures_dir, key: str, mkdir: bool = True, **fields) -> Path:
    """The path of output ``key`` under ``figures_dir``, its folder created
    unless ``mkdir`` is False; ``fields`` fill ``{vehicle}`` and ``{date}``."""
    path = Path(figures_dir) / FIGURES[key].format(**fields)
    if mkdir:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path
