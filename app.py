"""AUV–UVP6 pipeline in the browser: the four cells of run_UVP_toolbox.py behind a form.

Start it with start_app.bat (Windows) or:  python -m streamlit run app.py
Everything runs on this computer; no data leaves it.
"""
import contextlib
import io
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO / "main"), str(REPO / "UVP_toolbox_Python")]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st
from PIL import Image

import auv_data
import auv_plots
from uvp_toolbox.create_samples import create_samples
from uvp_toolbox.prompts import NullPrompter

UVP_PROJECT_DIRS = ("calibration", "config", "CTDdata", "doc", "ecodata",
                    "livecamera", "log", "meta", "raw", "results")
ALR_FORMAT, CSV_FORMAT = "ALR CTD and NAV files", "Simple CSV files (any AUV)"
BUTTON_WIDTH = 420  # px, the Run and Download buttons

st.set_page_config(page_title="AUV–UVP6 pipeline", page_icon=Image.open(REPO / "auv_app.ico"), layout="wide")


# ---------------------------------------------------------------- folders
def browse(key):
    """Folder dialog of this computer (the app runs locally); a file dialog for the CSV file."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    start = st.session_state.get(key) or str(Path.home())
    if key == "csv":
        start = str(Path(start).parent) if Path(start).is_file() else start
        path = filedialog.askopenfilename(initialdir=start, parent=root, title="Choose the CSV file of the AUV",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    else:
        path = filedialog.askdirectory(initialdir=start, parent=root)
    root.destroy()
    if path:
        st.session_state[key] = str(Path(path))
        if key == "deployment":
            fill_from_deployment(Path(path))


def fill_from_deployment(folder):
    """ALR4_demo layout: <vehicle>_ctd_data, <vehicle>_nav_data (or <vehicle>_csv_data), uvp6_* and a figures
    folder."""
    st.session_state["deployment_note"] = ""
    if folder.name.lower().startswith("uvp6_") or all((folder / d).is_dir() for d in ("raw", "meta")):
        # the UVP6 project itself was chosen: the AUV data folders are elsewhere
        st.session_state["project"] = str(folder)
        st.session_state["figures"] = str(folder / "diagnostic_figures")
        st.session_state["deployment_note"] = (
            "This folder is the UVP6 project itself: it is used as the UVP6 project folder. "
            "Choose the AUV data folders below (or choose the folder that holds them and the project).")
        st.session_state["vehicle"] = guess_vehicle(folder.name) or st.session_state["vehicle"]
        return
    subs = [p for p in folder.iterdir() if p.is_dir()]
    pick = lambda test: next((str(p) for p in subs if test(p.name.lower())), "")
    st.session_state["ctd"] = pick(lambda n: n.endswith("ctd_data")) or st.session_state.get("ctd", "")
    st.session_state["nav"] = pick(lambda n: n.endswith("nav_data")) or st.session_state.get("nav", "")
    loose_csv = sorted(p for p in folder.glob("*.csv") if p.is_file())  # CSV files directly in the deployment folder
    st.session_state["csv"] = (pick(lambda n: n.endswith(("csv_data", "vehicle_data")))
                               or (str(loose_csv[0]) if len(loose_csv) == 1 else str(folder) if loose_csv else "")
                               or st.session_state.get("csv", ""))
    if st.session_state["csv"] and not st.session_state["ctd"]:
        st.session_state["vformat"] = CSV_FORMAT
    st.session_state["project"] = pick(lambda n: n.startswith("uvp6_")) or st.session_state.get("project", "")
    st.session_state["figures"] = pick(lambda n: "figure" in n) or str(folder / "diagnostic_figures")
    data = st.session_state["csv"] if st.session_state["vformat"] == CSV_FORMAT else st.session_state["ctd"]
    data = str(Path(data).parent) if data and Path(data).is_file() else data
    st.session_state["vehicle"] = (guess_vehicle(Path(data).name if data else "")
                                   or guess_vehicle(Path(st.session_state["project"]).name)
                                   or st.session_state["vehicle"])


def guess_vehicle(name):
    """AUV name from a folder name: ALR004_ctd_data, ALR004_csv_data -> ALR004; uvp6_…_alr4 -> ALR004."""
    m = re.match(r"([A-Za-z0-9]+)_(?:ctd|nav|csv|vehicle)_data$", name)
    if m:
        return m.group(1)
    m = re.search(r"_alr(\d+)$", name.lower())
    return f"ALR{int(m.group(1)):03d}" if m else ""


def folder_input(label, key, help_, on_change=None, status=None):
    """Folder (or file) field; `status` = (ok, text) is shown in its title, green when ok, red otherwise."""
    if status is not None:
        ok, text = status
        label = f":green[✅ **{label}** · {text}]" if ok else f":red[⚠️ **{label}** · {text}]"
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    c1.text_input(label, key=key, help=help_, on_change=on_change)
    c2.button("Browse…", key=f"b_{key}", on_click=browse, args=(key,), use_container_width=True)
    return Path(st.session_state[key]) if st.session_state.get(key) else None


def files_status(folder, pattern):
    if not folder:
        return False, "not chosen yet"
    if not folder.is_dir():
        return False, "folder not found"
    n = len(auv_data.list_data_files(folder, pattern))
    return n > 0, f"{n} {pattern[1:]} file{'s' if n != 1 else ''} found" if n else f"no {pattern[1:]} file in this folder"


def csv_files(path):
    """The CSV file chosen, or every .csv file of the folder chosen."""
    return [path] if path.is_file() else sorted(auv_data.list_data_files(path, "*.csv"))


def csv_status(path):
    """Simple CSV file(s) of the AUV: found, and with the required columns."""
    if path and path.is_file():
        if path.suffix.lower() != ".csv":
            return False, "not a .csv file"
        ok, text = True, "1 .csv file"
    else:
        ok, text = files_status(path, "*.csv")
    if not ok:
        return ok, text
    for f in csv_files(path):
        try:
            missing = auv_data.simple_csv_missing_columns(f)
        except Exception as e:  # unreadable file
            return False, f"{Path(f).name} cannot be read: {e}"
        if missing:
            return False, f"{Path(f).name} has no column {', '.join(missing)}"
    return True, text + ", columns found"


def project_status(project):
    if not project:
        return False, "not chosen yet"
    if not project.is_dir():
        return False, "folder not found"
    missing = [d for d in UVP_PROJECT_DIRS if not (project / d).is_dir()]
    if missing:
        return False, f"not a complete UVPapp project, missing folder{'s' if len(missing) > 1 else ''}: {', '.join(missing)}"
    seqs = [p for p in (project / "raw").iterdir() if p.is_dir()]
    used = sum(p.name.endswith("_UsedForMerge") for p in seqs)
    n = len(seqs) - used
    if n != 1:
        return False, (f"{n} sequences in raw/: merge them in UVPapp first" if n else "no UVP6 sequence in raw/")
    # netCDF (HDF5) cannot write past the 260-character Windows path limit
    longest = len(str(project.resolve() / "meta" / "auv_meta_alr000" / "archives" / "ALR000_yyyymmdd_0000_0000_x0000.nc"))
    if longest > 259:
        return False, (f"path too long for Windows ({longest} > 259 characters for the netCDF files): "
                       "move the deployment folder to a shorter path, e.g. C:\\data")
    return True, "complete UVPapp project, 1 sequence in raw/" + (f" ({used} merged sequences ignored)" if used else "")


def figures_status(figures):
    if not figures:
        return False, "not chosen yet"
    return True, "found" if figures.is_dir() else "will be created"


# ---------------------------------------------------------------- pipeline
def run_pipeline(vehicle, project, figures, name, cruise, depth_int, time_int, thresholds, log):
    """The four cells of run_UVP_toolbox.py. `vehicle` = ("ALR", ctd, nav) or ("CSV", csv file or folder).
    `log` receives the printed text of each step."""
    figures.mkdir(parents=True, exist_ok=True)
    out = {}

    with st.status("1. Load and parse the vehicle data", expanded=False) as s:
        with capture(log, "1"):
            if vehicle[0] == "CSV":
                big_df = auv_data.load_simple_csv(csv_files(vehicle[1]), verbose=True)
            else:
                big_df = auv_data.load_alr_files(sorted(auv_data.list_data_files(vehicle[1], "*.log")),
                                                 sorted(auv_data.list_data_files(vehicle[2], "*.csv")), verbose=True)
        s.update(label=f"1. Vehicle data loaded: {big_df.height:,} records", state="complete")

    with st.status("2. Identify the AUV phases", expanded=False) as s:
        with capture(log, "2"):
            df, profiles_df = auv_data.detect_profiles(big_df, **thresholds)
            df = auv_data.attach_profiles(df, profiles_df)
            fig, _ = auv_plots.plot_phase_detection(profiles_df, **thresholds, show=False)
            fig.savefig(figures / f"{name}_phase_detection.png", dpi=150)
            fig, _ = auv_plots.plot_phase_sectioning(df, show=False)
            fig.savefig(figures / f"{name}_phase_sectioning.png", dpi=150)
            plt.close("all")
            out["phase_warnings"] = auv_plots.check_phases(df)
        s.update(label="2. AUV phases identified", state="complete")

    with st.status("3. Generate one netCDF file per AUV phase", expanded=False) as s:
        with capture(log, "3"):
            meta_dir = project / "meta" / auv_data.meta_folder_name(name)
            meta_dir.mkdir(exist_ok=True)
            cruise_info = project / "config" / "cruise_info.txt"
            if not cruise_info.exists() and cruise:
                cruise_info.write_text(f"UVP project cruise info \nname: {cruise}\n", encoding="latin-1")
            old_nc = sorted(meta_dir.glob("*.nc"))
            if old_nc:  # cell 4 reads every .nc of meta_dir
                archive = meta_dir / "archives" / datetime.now().strftime("%Y%m%d-%H%M%S")
                archive.mkdir(parents=True)
                for f in old_nc:
                    shutil.move(str(f), str(archive / f.name))
                print(f"Moved {len(old_nc)} netCDF(s) of the previous run to {archive}")
            written = auv_data.export_auv_netcdf(df, vehicle_name=name, output_dir=str(meta_dir), max_files=None)
        out["n_netcdf"], out["meta_dir"] = len(written), meta_dir
        s.update(label=f"3. {len(written)} phase netCDF files written", state="complete")

    with st.status("4. Generate the UVPapp sample file", expanded=False) as s:
        with capture(log, "4"):
            out["sample_file"] = create_samples(project, cruise=cruise or None, plots_dir=figures,
                                                depth_integration=depth_int, time_integration=time_int,
                                                prompter=NullPrompter(), assume_yes=True)
            plt.close("all")
        s.update(label=f"4. Sample file written: {out['sample_file'].name}", state="complete")
    return out


@contextlib.contextmanager
def capture(log, step):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            yield
    finally:
        log[step] = buf.getvalue()


# ---------------------------------------------------------------- page
st.title("AUV–UVP6 sample creation")
st.caption("Creates the UVPapp sample file of a UVP6 deployment on an autonomous underwater vehicle (AUV), "
           "such as the Autosub Long Range (ALR), from the AUV data (ALR CTD and navigation files, or simple "
           "CSV files) and the UVP6 project. Everything runs on this computer.")

for k, v in (("deployment", ""), ("ctd", ""), ("nav", ""), ("csv", ""), ("vformat", ALR_FORMAT), ("project", ""), ("figures", ""), ("vehicle", "ALR004")):
    st.session_state.setdefault(k, v)
# the deployment folder can be given in the address: http://localhost:8501/?deployment=C:\ALR\ALR4_demo
from_url = st.query_params.get("deployment", "")
if not st.session_state["deployment"] and from_url and Path(from_url).is_dir():
    st.session_state["deployment"] = from_url
    fill_from_deployment(Path(st.session_state["deployment"]))

st.header("1 · Choose the data folders")
st.write("Choose the folder of the deployment (as **ALR4_demo**): the four folders below are found in it. "
         "You can also choose each folder yourself. Each title turns green once its folder is ready.")
folder_input("Deployment folder", "deployment",
             "Folder holding <vehicle>_ctd_data and <vehicle>_nav_data (or the CSV file of the AUV) and the uvp6_… project",
             on_change=lambda: Path(st.session_state["deployment"]).is_dir()
             and fill_from_deployment(Path(st.session_state["deployment"])))
if st.session_state.get("deployment_note"):
    st.info(st.session_state["deployment_note"])
as_path = lambda key: Path(st.session_state[key]) if st.session_state.get(key) else None
csv_mode = st.session_state["vformat"] == CSV_FORMAT
statuses = ([csv_status(as_path("csv"))] if csv_mode else
            [files_status(as_path("ctd"), "*.log"), files_status(as_path("nav"), "*.csv")])
statuses += [project_status(as_path("project")), figures_status(as_path("figures"))]
ok = all(good for good, _ in statuses)
with st.container(border=True):
    st.radio("AUV data format", (ALR_FORMAT, CSV_FORMAT), key="vformat", horizontal=True,
             help="Simple CSV: one or more .csv files with the columns time (Unix seconds or ISO 8601 UTC), "
                  "pressure (dbar) or depth (m), pitch (degrees), latitude, longitude; optional temperature, "
                  "conductivity, oxygen, roll")
    if csv_mode:
        st.caption("Click **Browse…** to choose the CSV file of the AUV. If the data are split into several CSV "
                   "files, type instead the path of the folder that holds them: every .csv file in it is read.")
        vehicle = ("CSV", folder_input("AUV CSV file", "csv",
                                       "One .csv file, or a folder: every .csv file directly in it is read",
                                       status=statuses[0]))
    else:
        vehicle = ("ALR", folder_input("ALR CTD folder", "ctd", "Every .log file directly in this folder is read",
                                       status=statuses[0]),
                   folder_input("ALR NAV folder", "nav", "Every .csv file directly in this folder is read",
                                status=statuses[1]))
    project = folder_input("UVP6 project folder (UVPapp)", "project",
                           "uvp6_<sn>_<date>_<cruise>_<platform>: a complete UVPapp project, sequences merged",
                           status=statuses[-2])
    figures = folder_input("Figures folder", "figures", "Where the figures are saved", status=statuses[-1])

st.header("2 · Check the processing settings")
c1, c2, c3, c4 = st.columns(4)
c1.text_input("AUV name", key="vehicle",
              help="Letters, digits and _, e.g. ALR004: starts the netCDF and figure names and is written to "
                   "the sample file. Found from the name of the data folder when possible")
name_ok = bool(re.fullmatch(r"\w+", st.session_state["vehicle"].strip(), re.ASCII))
if not name_ok:
    c1.caption(":red[AUV name: letters, digits and _ only]")
cruise = c2.text_input("Cruise", help="Leave empty to read it from config/cruise_info.txt")
depth_int = c3.number_input("Depth bin of d/u/x samples (m)", min_value=1, value=5,
                            help="Sample file 'integrationtime' of depth-integrated samples")
time_int = c4.number_input("Time bin of t/s samples (s)", min_value=60, value=3600, step=60,
                           help="Sample file 'integrationtime' of time-integrated samples")
with st.expander("Phase detection thresholds (advanced)"):
    a1, a2 = st.columns(2)
    g = a1.number_input("Depth gradient threshold (criterion 1)", value=0.05, format="%.3f",
                        help="gradient_thresholds = [+g, −g]")
    cg = a2.number_input("−pitch × velocity threshold (criterion 2)", value=0.005, format="%.4f",
                         help="cust_gradient_thresholds = [+c, −c]")
thresholds = dict(gradient_thresholds=[g, -g], cust_gradient_thresholds=[cg, -cg])

st.header("3 · Run the pipeline")
st.write("The four steps run one after the other: load the AUV data, identify the AUV phases, write one "
         "netCDF file per phase, and create the sample header file for UVPapp.")
if project and (project / "meta").is_dir() and any((project / "meta").glob("uvp6_header_*.txt")):
    st.info("This project already has a sample file: it will be moved to meta/archives/, "
            "and the phase netCDF files of the previous run to meta/auv_meta_…/archives/.", icon="ℹ️")
if not ok:
    st.caption(":red[Choose the folders above first: the button is enabled once all their titles are green.]")
if st.button("Run the pipeline", type="primary", disabled=not (ok and name_ok), width=BUTTON_WIDTH):
    log = {}
    try:
        res = run_pipeline(vehicle, project, figures, st.session_state["vehicle"].strip(), cruise.strip(), depth_int, time_int,
                           thresholds, log)
        st.session_state["result"] = dict(res, figures=figures, log=log, vehicle=st.session_state["vehicle"].strip())
        st.session_state.pop("error", None)
    except Exception as e:  # shown in the page, with the log of the steps that ran
        st.session_state["error"] = (f"{type(e).__name__}: {e}", log)
        st.session_state.pop("result", None)

if "error" in st.session_state:
    msg, log = st.session_state["error"]
    st.error(f"The pipeline stopped: {msg}", icon="🛑")
    for step, text in log.items():
        with st.expander(f"Messages of step {step}"):
            st.code(text or "(none)")

# ---------------------------------------------------------------- results
res = st.session_state.get("result")
if res:
    st.header("4 · Results: sample header file, checks and figures")
    fig_dir, name = res["figures"], res["vehicle"]
    sample = res["sample_file"]
    st.download_button("Download the sample header file for UVPapp", sample.read_bytes(), file_name=sample.name,
                       type="primary", width=BUTTON_WIDTH)
    st.caption(f"Also saved in the UVP6 project: {sample}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Phase netCDF files", res["n_netcdf"])
    c2.metric("Samples", max(0, len(sample.read_text(encoding="cp1252").splitlines()) - 1))
    c3.metric("Phase warnings", len(res["phase_warnings"]))

    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(fig_dir.rglob("*")):
            if f.suffix.lower() in (".png", ".txt", ".csv"):
                z.write(f, f.relative_to(fig_dir))
    st.download_button("Download all figures and QC files (zip)", zipped.getvalue(),
                       file_name=f"{name}_figures.zip", mime="application/zip", width=BUTTON_WIDTH)

    def show(name, cap):
        path = fig_dir / name
        if path.exists():
            st.image(str(path), caption=cap)
            st.download_button(f"Download {path.name}", path.read_bytes(), file_name=path.name,
                               mime="image/png", key=f"dl_{name}")

    t1, t2, t3, t4 = st.tabs(["Phases", "Quality checks", "Time–depth", "Messages"])
    with t1:
        for w in res["phase_warnings"]:
            st.warning(w)
        show(f"{name}_phase_sectioning.png", "Phase sectioning: one block per phase (one netCDF file, one sample)")
        show(f"{name}_phase_detection.png", "Phase detection: the two criteria and their thresholds")
    with t2:
        summary = fig_dir / "qc_summary.txt"
        if summary.exists():
            text = summary.read_text(encoding="utf-8")
            (st.warning if "WARNING" in text else st.info)("Summary of the quality checks (qc_summary.txt)")
            st.code(text)
        show("uvp_auv_depth_agreement.png", "Depth agreement between the UVP6 and the AUV")
        show("uvp_auv_coverage_map.png", "UVP6 coverage: AUV track, red where the UVP6 has no image")
        show("uvp_auv_sample_sizes.png", "Number of images per sample")
    with t3:
        show("uvp_auv_timedepth_fullspan.png", "UVP6 and AUV depth over the deployment")
        show("overview_plots/uvp_auv_timedepth_all_days.png", "One panel per day")
        show("uvp_auv_sampling_intervals.png", "Sampling intervals")
    with t4:
        for step, text in res["log"].items():
            with st.expander(f"Messages of step {step}"):
                st.code(text or "(none)")
    st.caption(f"All figures are in {fig_dir}.")
