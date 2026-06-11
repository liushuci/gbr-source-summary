from __future__ import annotations

from importlib.resources import files


def package_data_path(*parts: str):
    """
    Return a path-like reference to packaged GBR reference data.
    """
    return files("gbr_source_summary").joinpath("data", *parts)