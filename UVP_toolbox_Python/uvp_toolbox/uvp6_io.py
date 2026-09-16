"""Readers for UVP6 sequence data files (``<sequence>_data.txt``).

Translation of ``Ressources_partagees/IO``

    Uvp6ReadMetalinesFromDatafile  -> read_metalines_from_datafile
    Uvp6ReadMetadataFromhwline     -> read_metadata_from_hwline
    Uvp6DatafileToArray            -> datafile_to_array
    Uvp6ReadDataFromDattable       -> read_data_from_dattable

File layout (one image per line, blank lines between records)::

    HW_CONF,<serial>,...;
    ACQ_CONF,...;
    yyyymmdd-HHMMSS-N,<depth>,<temp>,<flag>:<class>,<count>,<grey>,<x>;<class>,...
    yyyymmdd-HHMMSS-N,<depth>,<temp>,<flag>:OVER
    yyyymmdd-HHMMSS-N,<depth>,<temp>,<flag>:EMPTY

``flag == 1`` marks a data ("raw") image, anything else a black image.
The MATLAB reader returns three ``N x 900`` matrices; that is ~3 GB for a
140k-image sequence and the sample creator only ever needs black class 2, so
``read_data_from_dattable`` lets the caller ask for just the columns it wants.

Original MATLAB script by Camille Catalano, LOV, 2020/11
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

__all__ = [
    "N_CLASSES",
    "Uvp6HwConf",
    "Uvp6SequenceData",
    "read_metalines_from_datafile",
    "read_metadata_from_hwline",
    "datafile_to_array",
    "read_data_from_dattable",
    "read_uvp6_sequence",
    "parse_uvp6_timestamps",
]

N_CLASSES = 900  # widest object class kept by the MATLAB reader
CONFIG_MARKERS = ("HW_CONF", "ACQ_CONF", "TAXO_CONF")


def _str2double(s: str) -> float:
    """MATLAB ``str2double``: NaN for anything that is not a number."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return math.nan


# ---------------------------------------------------------------------------
# Uvp6ReadMetalinesFromDatafile
# ---------------------------------------------------------------------------

def read_metalines_from_datafile(file_path) -> tuple[str, Optional[str], Optional[str], str]:
    """Return ``(hw_line, empty_line, acq_line, taxo_line)`` from the first
    five lines of a data file.  Each configuration line is returned from its
    marker onwards, exactly as the MATLAB version does."""
    hw_line = empty_line = acq_line = None
    taxo_line = ""
    with open(file_path, "r", encoding="latin-1") as f:
        for _ in range(5):
            raw = f.readline()
            if raw == "":
                break
            tline = raw.rstrip("\r\n")
            if "HW_CONF" in tline:
                hw_line = tline[tline.index("HW_CONF"):]
            elif "ACQ_CONF" in tline:
                acq_line = tline[tline.index("ACQ_CONF"):]
            elif "TAXO_CONF" in tline:
                taxo_line = tline[tline.index("TAXO_CONF"):]
            elif tline == "":
                empty_line = tline
    if hw_line is None:
        raise ValueError(f"No HW_CONF line found in the first 5 lines of {file_path}")
    return hw_line, empty_line, acq_line, taxo_line


# ---------------------------------------------------------------------------
# Uvp6ReadMetadataFromhwline
# ---------------------------------------------------------------------------

@dataclass
class Uvp6HwConf:
    sn: str
    day: str
    light: str
    shutter: float
    threshold: float
    volume: float
    gain: float
    pixel: float          # mm, already divided by 1000 like the MATLAB code
    aa: float
    exp: float
    classes_limits: np.ndarray


def read_metadata_from_hwline(hw_line: str) -> Uvp6HwConf:
    """Positional extraction from the ``HW_CONF`` line.

    Field 15 (1-based) is the instrument's IP address in firmware older than
    2022 and a number afterwards; the MATLAB code shifts every later index by
    two when it finds the newer layout.
    """
    s = re.split(r"[,;]", hw_line)  # CollapseDelimiters = false
    if len(s) < 27:
        raise ValueError(f"HW_CONF line too short ({len(s)} fields): {hw_line[:80]!r}")
    y = 0 if math.isnan(_str2double(s[14])) else 1
    return Uvp6HwConf(
        sn=s[1],
        day=s[24 - 2 * y],
        light=s[5],
        shutter=_str2double(s[16 - 2 * y]),
        threshold=_str2double(s[18 - 2 * y]),
        volume=_str2double(s[22 - 2 * y]),
        gain=_str2double(s[17 - 2 * y]),
        pixel=_str2double(s[21 - 2 * y]) / 1000.0,
        aa=_str2double(s[19 - 2 * y]),
        exp=_str2double(s[20 - 2 * y]),
        classes_limits=np.array([_str2double(v) for v in s[26 - 2 * y:-1]], dtype=float),
    )


# ---------------------------------------------------------------------------
# Uvp6DatafileToArray
# ---------------------------------------------------------------------------

def datafile_to_array(file_path) -> tuple[list[str], list[str], list[str]]:
    """Split every image line on its first ``:`` into ``(data, meta, taxo)``.

    Configuration lines and blank lines are not image records and are skipped
    (``readtable`` treats them as header lines).  When ``TAXO`` lines are
    present ``taxo[i]`` holds the taxonomy string for image ``i`` and ``'NaN'``
    otherwise; without any ``TAXO`` line ``taxo`` is empty, as in MATLAB.
    """
    data: list[str] = []
    meta: list[str] = []
    taxo: list[str] = []
    has_taxo = False
    with open(file_path, "r", encoding="latin-1") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            head = line.split(",", 1)[0]
            if head in CONFIG_MARKERS:
                continue
            m, sep, d = line.partition(":")
            if not sep:
                continue
            if m == "TAXO":
                has_taxo = True
                if taxo:
                    taxo[-1] = d
                continue
            meta.append(m)
            data.append(d)
            taxo.append("NaN")
    if not has_taxo:
        taxo = []
    return data, meta, taxo


# ---------------------------------------------------------------------------
# Uvp6ReadDataFromDattable
# ---------------------------------------------------------------------------

@dataclass
class Uvp6SequenceData:
    """Per-image vectors of a sequence.

    ``image_status``: 1 = overexposed, 2 = black, 3 = data, NaN = unknown.
    ``black``/``raw``/``raw_grey``: ``(n_images, n_classes)`` float arrays with
    NaN rows where the image is not of that kind — or ``None`` if not requested.
    """
    time: np.ndarray
    depth: np.ndarray
    image_status: np.ndarray
    black: Optional[np.ndarray] = None
    raw: Optional[np.ndarray] = None
    raw_grey: Optional[np.ndarray] = None

    @property
    def n_images(self) -> int:
        return int(self.depth.size)


def _iso_from_uvp6_stamp(s: str) -> str:
    """``yyyyMMdd-HHmmss[-SSS]`` -> ISO 8601 text NumPy can parse."""
    if len(s) >= 19:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}.{s[16:19]}"
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}"


def _parse_one_stamp(s: str) -> np.datetime64:
    # MATLAB tries the 19-character millisecond format first and falls back to
    # the 15-character one; anything else raises.
    if len(s) >= 19:
        try:
            return np.datetime64(_iso_from_uvp6_stamp(s[:19]), "ns")
        except ValueError:
            pass
    try:
        return np.datetime64(_iso_from_uvp6_stamp(s[:15]), "ns")
    except ValueError as exc:
        raise ValueError(f"Unrecognised UVP6 timestamp {s!r}") from exc


def parse_uvp6_timestamps(stamps: Sequence[str]) -> np.ndarray:
    """Vectorised timestamp parse with a per-element fallback that mirrors the
    MATLAB ``try 19 chars / catch 15 chars`` order."""
    if len(stamps) == 0:
        return np.array([], dtype="datetime64[ns]")
    try:
        return np.array([_iso_from_uvp6_stamp(s) for s in stamps], dtype="datetime64[ns]")
    except ValueError:
        return np.array([_parse_one_stamp(s) for s in stamps], dtype="datetime64[ns]")


def _parse_histogram(d: str, n_classes: int) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """MATLAB ``str2num(line)`` -> ``[class, count, grey, x]`` rows, then
    ``line(class) = count`` for ``class <= n_classes``.

    Returns ``None`` where ``str2num`` would have returned ``[]`` (unparsable
    text or a ragged row), which the MATLAB loop silently turns into zeros.
    """
    txt = d.strip().rstrip(";,").replace(";", ",")
    if not txt:
        return None
    try:
        arr = np.array(txt.split(","), dtype=float)
    except ValueError:
        return None
    if arr.size % 4 != 0:
        return None
    m = arr.reshape(-1, 4)
    cls = m[:, 0]
    ok = (cls >= 1) & (cls <= n_classes) & (cls == np.floor(cls))
    idx = cls[ok].astype(np.intp) - 1
    counts = np.zeros(n_classes)
    grey = np.zeros(n_classes)
    counts[idx] = m[ok, 1]
    grey[idx] = m[ok, 2]
    return counts, grey


def read_data_from_dattable(
    meta: Sequence[str],
    data: Sequence[str],
    n_classes: int = N_CLASSES,
    want: Sequence[str] = ("black", "raw", "grey"),
    verbose: bool = False,
) -> Uvp6SequenceData:
    """Decode the image records produced by :func:`datafile_to_array`.

    ``want`` selects which of ``'black'``, ``'raw'``, ``'grey'`` histograms are
    built and ``n_classes`` how many size classes are kept (MATLAB: all three,
    900 classes).  The sample creator asks for ``('black',)`` and 2 classes.
    """
    n = len(data)
    if len(meta) != n:
        raise ValueError("meta and data must have the same length")
    want = tuple(want)
    want_black = "black" in want
    want_raw = "raw" in want
    want_grey = "grey" in want

    depth = np.full(n, np.nan)
    flags = np.full(n, np.nan)
    status = np.full(n, np.nan)
    stamps: list[str] = []
    for h, m in enumerate(meta):
        c = m.split(",")
        if len(c) < 4:
            raise ValueError(f"image {h + 1}: expected 4 metadata fields, got {len(c)}: {m!r}")
        stamps.append(c[0])
        depth[h] = _str2double(c[1])
        flags[h] = _str2double(c[3])
    time = parse_uvp6_timestamps(stamps)

    black = np.full((n, n_classes), np.nan) if want_black else None
    raw = np.full((n, n_classes), np.nan) if want_raw else None
    grey = np.full((n, n_classes), np.nan) if want_grey else None
    zeros = np.zeros(n_classes)
    unparsable = 0

    for h, d in enumerate(data):
        if verbose and h and h % 5000 == 0:
            print(f"{h} of {n}")
        is_data_image = flags[h] == 1
        if "OVER" in d:
            status[h] = 1
            continue
        if "EMPTY" in d:
            if is_data_image:
                if raw is not None:
                    raw[h] = 0
                if grey is not None:
                    grey[h] = 0
                status[h] = 3
            else:
                if black is not None:
                    black[h] = 0
                status[h] = 2
            continue
        if is_data_image:
            status[h] = 3
            if raw is not None or grey is not None:
                parsed = _parse_histogram(d, n_classes)
                if parsed is None:
                    unparsable += 1
                    counts, grey_line = zeros, zeros
                else:
                    counts, grey_line = parsed
                if raw is not None:
                    raw[h] = counts
                if grey is not None:
                    grey[h] = grey_line
        else:
            status[h] = 2
            if black is not None:
                parsed = _parse_histogram(d, n_classes)
                if parsed is None:
                    unparsable += 1
                    black[h] = 0
                else:
                    black[h] = parsed[0]

    if unparsable:
        warnings.warn(f"{unparsable} image histogram line(s) could not be parsed and were set to zeros")
    return Uvp6SequenceData(time=time, depth=depth, image_status=status, black=black, raw=raw, raw_grey=grey)


def read_uvp6_sequence(file_path, **kwargs) -> Uvp6SequenceData:
    """``datafile_to_array`` + ``read_data_from_dattable`` in one call."""
    data, meta, _ = datafile_to_array(Path(file_path))
    return read_data_from_dattable(meta, data, **kwargs)
