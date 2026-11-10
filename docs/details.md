# UVP6 AUV sample creation: details

Settings, outputs and figures of the pipeline. For installing and running it, see the
[README](../README.md).

## Setup without Miniconda

Tested with Python 3.12 on Windows. In an existing environment: `pip install -r requirements.txt`.
For the script, VS Code with its **Python** and **Jupyter** extensions (Microsoft) is recommended:
the Jupyter extension, with the `ipykernel` package of the environment, gives the **Run Cell**
buttons. Select the `auv_uvp` environment as the Python interpreter.

## Data

**ALR (Autosub Long Range)**: one folder of CTD `.log` files and one folder of navigation `.csv` files, e.g.
`ALR004_ctd_data/` and `ALR004_nav_data/`. Every file directly inside each folder is read and
merged; subfolders are ignored. In future releases, the ALR CTD and NAV data will come in a single
netCDF file.

**Other AUVs (or ALR data exported to CSV)**: one folder of simple CSV files (`AUV_DATA_FORMAT =
"CSV"` in the script, "Simple CSV files (any AUV)" in the app). Each file has a header line and the
columns below; names are case-insensitive, other columns are ignored, several files are merged and
sorted by time.

| Column | Unit | |
| --- | --- | --- |
| `time` | Unix time in s, or ISO 8601 date-time in UTC (`2024-06-11T03:34:00Z`) | required |
| `pressure` or `depth` | dbar, or m (pressure is used when both are given; depth is taken as 1 m = 1 dbar) | required |
| `pitch` | degrees | required |
| `latitude`, `longitude` | decimal degrees | required |
| `temperature`, `conductivity`, `oxygen`, `roll` | as in the ALR files | optional, kept in the netCDF and CTD files |

```
time,pressure,pitch,latitude,longitude
1718076840.25,3.12,-21.4,62.81503,-20.29011
```

**UVP6**: a project created with UVPapp, named
`uvp6_<uvp6_serial_number>_<first_deployment_date>_<cruise_name>_<platform><platform_serial_number>`,
e.g. `uvp6_sn000227lp_20240807_dy180_biocarbon1_alr4`. `<first_deployment_date>` is the start date
of the deployment (`yyyymmdd`), not the date the project was created.

- The project must be complete, with all the UVPapp folders (`calibration`, `config`, `CTDdata`,
  `doc`, `ecodata`, `livecamera`, `log`, `meta`, `raw`, `results`), as `ALR4_demo` is: the
  pipeline does not create them, and cell 3 stops with the list of the missing ones.
- When the UVP6 restarted during the deployment, merge its sequences in UVPapp first: the pipeline
  uses the merged sequence (`_Merged-NNN`) and ignores the originals (`_UsedForMerge`).
- Close UVPapp before running, so that it does not have the project open while cell 4 writes the
  sample file and the CTD files.

## Settings of the script

At the top of [`run_UVP_toolbox.py`](../run_UVP_toolbox.py) (the app has the same settings):

| Setting | What it does |
| --- | --- |
| `VEHICLE_NAME` | Name of the AUV (letters, digits and `_`), e.g. `ALR004`. Starts the netCDF and figure names, names the `meta/auv_meta_alr004` folder and is written to the sample file. The app finds it from the data folder name (`ALR004_ctd_data`, `ALR004_csv_data`). |
| `CRUISE` | Cruise name, written to the sample file. |
| `AUV_DATA_FORMAT` | `"ALR"`: folders of ALR CTD `.log` and NAV `.csv` files; `"CSV"`: simple CSV files of any AUV (see Data). |
| `OUTPUT_DIR` | Folder for all figures. `None` asks with a dialog. |
| `PHASE_DETECTION` | Thresholds of the phase detection (any other `auv_data.detect_profiles` parameter can be added). The same values are drawn on the phase detection figure. |
| `DEPTH_INTEGRATION` | `integrationtime` of the depth-integrated samples (`P`: downcasts, upcasts, transitions), in m. 5 by default. |
| `TIME_INTEGRATION` | `integrationtime` of the time-integrated samples (`T`: transects, surface transects), in s. 3600 by default. |
| `UVP_PROJECT_DIRS` | Folders of a UVPapp project, checked in cell 3. |

In cell 4, `assume_yes=False` asks before replacing an existing sample file; `True` replaces it
without asking. Figure windows of the script open one at a time: close each one to continue.

Near the end of cell 4, two lines summarise the matching:

- `Matching UVP data times were not found for X of Y CTD/NAV files`: AUV phases with no UVP6 image
  in their time window.
- `Matching CTD/NAV files were not found for X of Y UVP images`: UVP6 images outside every matched
  phase.

## Outputs

```
<UVP6 project>/
├── config/cruise_info.txt                    # created if missing (cell 3)
├── meta/
│   ├── auv_meta_alr004/*.nc                  # one per AUV phase (cell 3)
│   ├── auv_meta_alr004/archives/<date>/*.nc  # netCDFs of the previous run (cell 3)
│   ├── uvp6_header_<project>.txt             # UVPapp sample file (cell 4)
│   └── archives/uvp6_header_<project>_<date>.txt   # previous sample files (cell 4)
└── CTDdata/<phase>.ctd                       # one per matched phase (cell 4)

<figures folder>/
├── ALR004_phase_detection.png                # cell 2
├── ALR004_phase_sectioning.png               # cell 2
├── uvp_auv_timedepth.png                     # cell 4, and below
├── uvp_auv_timedepth_fullspan.png
├── uvp_auv_sampling_intervals.png
├── daily_plots/uvp_auv_timedepth_<date>.png
├── overview_plots/uvp_auv_timedepth_all_days.png
├── uvp_auv_depth_agreement.png               # cell 4, quality checks
├── uvp_auv_coverage_map.png
├── uvp_auv_sample_sizes.png
├── qc_coverage.csv
└── qc_summary.txt
```

- The phase netCDFs are saved in `meta/`, with the sample file: `raw`, `config` and `meta` are the
  folders needed for the science, and the ones backed up at some institutes. Projects processed
  before, with the netCDFs in `doc/alr_meta_sn004/` or `meta/alr_meta_sn004/` (before the pipeline was opened to all AUVs), are still read.
- Each phase netCDF holds `TIME`, `DEPTH_SCI` (CTD pressure), `DEPTH_ENG`, `DEPTH_SCI_INTERP`,
  `LAT`, `LON`, `TEMPERATURE`, `CONDUCTIVITY`, `OXYGEN`, `PITCH_ENG` and `ROLL_ENG`. The CTD files
  fill the UVPapp columns time, depth, pressure, temperature and conductivity, followed by all the
  netCDF variables.
- In the sample file, downcasts, upcasts and transitions are depth-integrated samples (`P`,
  `integrationtime` = `DEPTH_INTEGRATION`), transects and surface transects time-integrated samples
  (`T`, `integrationtime` = `TIME_INTEGRATION`).
- Cell 1 of the script saves the merged AUV data to `_cache_big_df.parquet` in the repository
  directory.

## Quality-control figures

Phases are coloured as in the documentation: d downcast (blue), u upcast (orange), t transect
(green), s surface transect (yellow), x transition (dark grey).

| Figure | What it shows | What to check |
| --- | --- | --- |
| `ALR004_phase_detection.png` | Depth, the two detection criteria (smoothed vertical velocity, and M = −pitch × vertical velocity) with their thresholds as grey bands, the pitch, and the profile numbering before/after the duration and back-fill filters. | Why a record got its phase; whether the thresholds suit the deployment. |
| `ALR004_phase_sectioning.png` | The deployment coloured by phase, the count of each phase type, and one block per phase (one phase = one netCDF file = one sample), with the segment boundaries. | Each dive split into a downcast and an upcast, no missed profile, no fragmented transect. |
| `uvp_auv_timedepth.png`, `…_fullspan.png`, `daily_plots/`, `overview_plots/` | UVP6 (dots) and AUV (line) depth, the UVP − AUV depth difference (10 s medians), and, in `…_fullspan.png`, the AUV → UVP clock offset of each 31 × 10 s window, coloured by r²; the median over reliable windows (r² ≥ 0.9) is printed and drawn. The AUV depth is drawn over the whole deployment, and the gaps of the coverage map are shaded red. | A constant depth difference points to a pressure offset, a difference growing with depth to a scale difference, and a non-zero median offset to a clock offset. |
| `uvp_auv_sampling_intervals.png` | Distribution of the time between two UVP6 images and two AUV records. | Gaps or irregular sampling. |
| `uvp_auv_depth_agreement.png` | UVP − AUV depth against AUV depth (10 s medians), with the fit UVP − AUV = scale × depth + offset + lag × vertical velocity, over the deployment and per day. | A WARNING when \|scale\| > 0.5 %, \|offset\| > 0.5 m or \|lag\| > 1 s. A scale near +1.97 % is what a UVP depth in mH₂O against an AUV pressure in dbar gives. A lag that grows day after day is a drifting clock. |
| `uvp_auv_coverage_map.png` | The AUV track seen from above, coloured by phase type where the UVP6 has images and red where it has none, with the time and position where each gap starts and ends; below, every phase on a time line. | Where and when the UVP6 did not record. A gap runs from the last UVP6 image before it to the first one after it, and is listed when it lasts 1 h or more (`MIN_GAP_HOURS` in `qc.py`). |
| `uvp_auv_sample_sizes.png` | Images per sample, by phase type, with the `qc_min_images` limit of `create_samples` (20 by default). | Very small samples, usually transitions, not worth processing in UVPapp. |

The quality checks of cell 4 are also printed and written to `qc_summary.txt`: the depth agreement,
the deployment (start, end, track length), a table of the phases by type (number, number with
images, images) and the gaps. The gaps are also in `qc_coverage.csv`: start and end time, duration,
start and end position, track length and the phases by type. Cell 2 prints the phase checks of
`auv_plots.check_phases`: the duration of each phase type, a warning for a segment without an
upcast, and a warning for a transition longer than 30 min.

## Re-running

- **After editing code in `main/` or `UVP_toolbox_Python/`**, restart the interactive window's
  kernel (script) or the app.
- **Cell 3** moves the netCDFs of the previous run to `meta/auv_meta_alr004/archives/<date>/` before
  writing the new ones, as cell 4 matches every `.nc` file of `meta/auv_meta_alr004/`.
- **Cell 4** moves the previous sample file to `meta/archives/`, with a `_YYYYMMDD-HHMMSS` suffix, as
  UVPapp does when the metadata are edited.
