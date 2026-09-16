"""Python translation of the LOV/NOC ``UVP_toolbox`` MATLAB code.

The package mirrors the MATLAB layout so each function can be traced back:

    Ressources_partagees/IO/Uvp6*.m          -> uvp6_io
    Ressources_partagees/IO/Read*.m          -> vector_io
    Ressources_partagees/seawater/sw_*.m     -> seawater
    Ressources_partagees/UsableDepthLimit.m  -> usable_depth_limit
    UVP6_samples_creation/DetectionVectorMetaFile.m       -> detection_vector_meta_file
    UVP6_samples_creation/CreateCTDfile.m + FillCTDtable*  -> ctd_file
    UVP6_samples_creation/GetMetaFromVectorMetaFile.m     -> get_meta_from_vector_meta_file
    UVP6_samples_creation/uvp6_create_samples_alr.m       -> create_samples (+ diagnostics)

``uvp6_create_samples_alr.py`` at the package root is the command-line driver.
"""

from .create_samples import create_samples

__all__ = ["create_samples"]
__version__ = "0.1.0"
