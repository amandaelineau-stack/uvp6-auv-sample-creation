"""Locate the vehicle metadata folder inside a UVP project (``meta`` for AUV, ``doc`` otherwise).

Translation of ``UVP6_samples_creation/DetectionVectorMetaFile.m``.

Original MATLAB script by Camille Catalano, LOV, 2020/11
"""

from __future__ import annotations

import gzip
import re
import shutil
import warnings
from pathlib import Path

import netCDF4

__all__ = ["detection_vector_meta_file"]


def detection_vector_meta_file(project_folder, vector_type: str) -> tuple[Path, str]:
    """Return ``(meta_data_folder, vector_sn)`` for the project.

    ``vector_sn`` is the platform label written to the ``ship`` column of the
    sample file (``Seaeplorer_###``, ``SeaGlider_###``, ``WMO#######`` or
    the AUV name, e.g. ``ALR004``).
    """
    doc = Path(project_folder) / "doc"

    if vector_type == "SeaExplorer":
        hits = sorted(doc.glob("SEA*"))
        if not hits:
            raise FileNotFoundError("ERROR : No metadata folder found in \\doc")
        vector_sn = "Seaeplorer_" + hits[0].name[3:6]
    elif vector_type == "SeaGlider":
        hits = sorted(doc.glob("SG*"))
        if not hits:
            raise FileNotFoundError("ERROR : No metadata folder found in \\doc")
        vector_sn = "SeaGlider_" + hits[0].name[2:5]
    elif vector_type == "float":
        hits = sorted(doc.glob("float*"))
        if not hits:
            raise FileNotFoundError("ERROR : No metadata folder found in \\doc")
        vector_sn = "WMO" + hits[0].name[-7:]
    elif vector_type == "AUV":
        # meta/auv_meta_<vehicle>; older projects: meta/alr_meta_sn<NNN>, or doc/ before #11
        meta = Path(project_folder) / "meta"
        hits = (sorted(meta.glob("auv_meta_*")) or sorted(meta.glob("alr_meta_sn*"))
                or sorted(doc.glob("alr_meta_sn*")))
        if not hits:
            raise FileNotFoundError('ERROR : No AUV metadata folder found in \\meta (expected "auv_meta_<vehicle>")')
        # the vehicle name is a global attribute of the phase netCDFs (alr_serial in older ones)
        vector_sn = None
        nc_list = sorted(hits[0].glob("*.nc")) if hits[0].is_dir() else []
        if nc_list:
            try:
                with netCDF4.Dataset(nc_list[0], "r") as ds:
                    attrs = ds.ncattrs()
                    attr = next((a for a in ("vehicle_name", "alr_serial") if a in attrs), None)
                    if attr:
                        vector_sn = re.sub(r"[^\w]", "", str(ds.getncattr(attr)))
            except OSError:
                pass
        if not vector_sn:  # from the folder name
            m = re.search(r"alr_meta_sn(\d+)", hits[0].name)
            vector_sn = ("ALR%03d" % int(m.group(1)) if m
                         else hits[0].name[len("auv_meta_"):].upper() or "AUV")
    else:
        raise ValueError(f"Unknown vector type {vector_type!r}")

    first = hits[0]
    meta_data_folder = first
    if not first.is_dir():
        # MATLAB: gunzip(meta_data_folder, folder); meta_data_folder = name(1:end-4).
        # Ported literally, including the four-character strip.
        target = first.parent / (first.name[:-3] if first.name.endswith(".gz") else first.name + ".out")
        with gzip.open(first, "rb") as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        meta_data_folder = first.parent / first.name[:-4]
        if not meta_data_folder.exists():
            warnings.warn(f"Decompressed {first.name} but {meta_data_folder} does not exist (literal port of the MATLAB name handling)")

    print(f"Vector meta data folder : {first.name}")
    return meta_data_folder, vector_sn
