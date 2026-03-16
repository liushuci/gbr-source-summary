"""
Region selection helpers for gbr_source_summary.

This module provides a consistent way to interpret region selections for
workflows. It supports:
- a single region string, e.g. "CY"
- a list of regions, e.g. ["CY", "WT"]
- all configured GBR regions when region=None
"""

from __future__ import annotations

from collections.abc import Sequence

from .config import GBRConfig


def resolve_regions(
    cfg: GBRConfig,
    region: str | None = None,
    regions: Sequence[str] | None = None,
) -> list[str]:
    """
    Resolve user region selection into a validated region list.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    region : str | None
        A single region code.
    regions : Sequence[str] | None
        Multiple region codes.

    Returns
    -------
    list[str]
        Validated list of region codes.

    Raises
    ------
    ValueError
        If both region and regions are provided, or if any invalid region is found.
    """
    if region is not None and regions is not None:
        raise ValueError("Provide either 'region' or 'regions', not both.")

    if region is None and regions is None:
        selected = list(cfg.regions)
    elif region is not None:
        selected = [region]
    else:
        selected = list(regions)

    invalid = [r for r in selected if r not in cfg.regions]
    if invalid:
        raise ValueError(
            f"Invalid regions: {invalid}. Valid GBR regions are: {cfg.regions}"
        )

    return selected