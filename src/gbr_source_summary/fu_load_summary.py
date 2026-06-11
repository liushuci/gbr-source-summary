from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import GBRConfig
from .export import ensure_output_dir
from .workflows_fu import build_fu_export_summaries


REGION_NAME_MAP = {
    "CY": "Cape York",
    "WT": "Wet Tropics",
    "BU": "Burdekin",
    "MW": "Mackay Whitsunday",
    "FI": "Fitzroy",
    "BM": "Burnett Mary",
}

FU_ORDER = [
    "Bananas",
    "Conservation",
    "Cropping",
    "Dairy",
    "Forestry",
    "Grazing",
    "Horticulture",
    "Stream",
    "Sugarcane",
    "Urban + Other",
]

DEFAULT_CONSTITUENTS = ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]


def _load_unit(con: str) -> str:
    return "kt/year" if con.upper() in {"FS", "CS"} else "t/year"


def _areal_unit(con: str, fu: str) -> str:
    if fu == "Stream":
        return "t/km/year" if con.upper() in {"FS", "CS"} else "kg/km/year"
    return "t/ha/year" if con.upper() in {"FS", "CS"} else "kg/ha/year"


def _load_conversion(con: str, model_years: float) -> float:
    return (1e-6 if con.upper() in {"FS", "CS"} else 1e-3) / model_years


def _standardise_fu_names_in_series(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = s.index.astype(str)

    if "Dryland Cropping" in s.index or "Irrigated Cropping" in s.index:
        s["Cropping"] = s.get("Dryland Cropping", 0.0) + s.get("Irrigated Cropping", 0.0)

    if "Urban + Other" not in s.index:
        s["Urban + Other"] = s.get("Urban", 0.0) + s.get("Other", 0.0)

    if "Banana" in s.index and "Bananas" not in s.index:
        s["Bananas"] = s.get("Banana", 0.0)

    if "Sugracane" in s.index and "Sugarcane" not in s.index:
        s["Sugarcane"] = s.get("Sugracane", 0.0)

    for fu in FU_ORDER:
        if fu not in s.index:
            s[fu] = 0.0

    return pd.to_numeric(s[FU_ORDER], errors="coerce").fillna(0.0)


def _extract_fu_series_from_wide_summary(df: pd.DataFrame, constituent: str) -> pd.Series:
    """
    Accept either:
    1. wide format: FU | FS | CS | PN ...
    2. long format: FU | Constituent | LoadToRegExport (kg)
    3. single-constituent format indexed by FU with LoadToRegExport (kg)
    """

    df = df.copy()

    # Case 1: wide format
    if constituent in df.columns:
        if "FU" in df.columns:
            s = df.set_index("FU")[constituent].copy()
        else:
            s = df[constituent].copy()

        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    # Case 2: long format
    if {"FU", "Constituent", "LoadToRegExport (kg)"}.issubset(df.columns):
        work = df.loc[df["Constituent"].astype(str).str.upper() == constituent].copy()

        if work.empty:
            return pd.Series(dtype=float)

        s = (
            work.groupby("FU")["LoadToRegExport (kg)"]
            .sum()
        )

        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    # Case 3: already filtered single-constituent table
    if "LoadToRegExport (kg)" in df.columns:
        s = df["LoadToRegExport (kg)"].copy()

        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    raise KeyError(
        f"Constituent '{constituent}' not found. Available columns: {list(df.columns)}"
    )


def _clean_area_col_name(col: str) -> str:
    name = str(col).split("(")[0].strip()

    if name == "Banana":
        return "Bananas"
    if name == "Sugracane":
        return "Sugarcane"

    return name


def _prepare_fu_area_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = out.index.astype(str)
    out.columns = [_clean_area_col_name(c) for c in out.columns]

    if "Cropping" not in out.columns:
        out["Cropping"] = out.get("Dryland Cropping", 0.0) + out.get("Irrigated Cropping", 0.0)

    if "Urban + Other" not in out.columns:
        out["Urban + Other"] = out.get("Urban", 0.0) + out.get("Other", 0.0)

    for fu in FU_ORDER:
        if fu not in out.columns:
            out[fu] = 0.0

    out = out[FU_ORDER].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    if out.index.duplicated().any():
        out = out.groupby(out.index).sum()

    return out


def _safe_pie_plot(values: pd.Series, output_path: Path, title: str) -> None:
    s = values.copy()
    s = s.drop(labels=[x for x in s.index if str(x).startswith("Stream")], errors="ignore")
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]

    fig, ax = plt.subplots(figsize=(8, 8))

    if s.empty or s.sum() <= 0:
        ax.text(0.5, 0.5, "No positive load", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        s.plot.pie(
            ax=ax,
            autopct="%1.1f%%",
            labels=None,
            fontsize=0,
            pctdistance=0.1,
            radius=1.1,
            wedgeprops={"edgecolor": "k", "linewidth": 1},
        )

        pct = 100 * s.values / s.sum()
        ax.legend(
            [f"{n} - {p:.1f} %" for n, p in zip(s.index, pct)],
            bbox_to_anchor=(0.95, 0.61),
            ncol=1,
            fontsize=12,
        )
        ax.set_ylabel("")

    ax.set_title(title)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_fu_tonnage_vs_areal_by_region(
    fu_load_summary: dict[str, pd.DataFrame],
    fu_areal_load_summary: dict[str, pd.DataFrame],
    plot_dir: Path,
    files: dict[str, Path],
) -> None:
    tonnage_areal_dir = ensure_output_dir(plot_dir / "tonnage_areal")

    plot_specs = [
        {"fu": "Grazing", "constituent": "FS", "include_gbr": False},
        {"fu": "Stream", "constituent": "FS", "include_gbr": True},
        {"fu": "Sugarcane", "constituent": "DIN", "include_gbr": True},
        {"fu": "Sugarcane", "constituent": "DON", "include_gbr": True},
        {"fu": "Sugarcane", "constituent": "DIP", "include_gbr": True},
        {"fu": "Sugarcane", "constituent": "DOP", "include_gbr": True},
        {"fu": "Cropping", "constituent": "PN", "include_gbr": True},
        {"fu": "Cropping", "constituent": "PP", "include_gbr": True},
        {"fu": "Grazing", "constituent": "CS", "include_gbr": True},
    ]

    for spec in plot_specs:
        con = spec["constituent"]
        fu = spec["fu"]

        if con not in fu_load_summary or con not in fu_areal_load_summary:
            continue

        load_unit = _load_unit(con)
        areal_unit = _areal_unit(con, fu)

        load_col = f"{fu} ({load_unit})"
        areal_col = f"{fu} ({areal_unit})"

        load_df = fu_load_summary[con]
        areal_df = fu_areal_load_summary[con]

        if load_col not in load_df.columns or areal_col not in areal_df.columns:
            continue

        if spec["include_gbr"]:
            total_series = load_df[load_col].astype(float)
            areal_series = areal_df[areal_col].astype(float)
        else:
            total_series = load_df.loc[load_df.index != "GBR", load_col].astype(float)
            areal_series = areal_df.loc[areal_df.index != "GBR", areal_col].astype(float)

        total_series = total_series.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        areal_series = areal_series.replace([np.inf, -np.inf], np.nan).fillna(0.0)

        x = np.arange(len(total_series))

        fig, ax1 = plt.subplots(figsize=(6.8, 4.8))

        ax1.bar(
            x,
            total_series.values,
            width=0.35,
            color="m",
            edgecolor="black",
            label=load_unit,
            zorder=1,
        )
        ax1.set_ylabel(f"{con} ({load_unit})", size=8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(total_series.index, rotation=90)

        ax2 = ax1.twinx()
        ax2.bar(
            x,
            areal_series.values,
            width=0.18,
            color="g",
            edgecolor="black",
            label=areal_unit,
            zorder=2,
        )
        ax2.set_ylabel(f"{con} ({areal_unit})", size=8)

        ax1.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), fontsize=8, frameon=True)
        ax2.legend(loc="lower left", bbox_to_anchor=(0.18, 1.01), fontsize=8, frameon=True)

        fig.tight_layout()

        output_path = tonnage_areal_dir / f"{con}_exportTonnageArealGBR_{fu}.png"
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        files[f"fu_tonnage_areal_{con.lower()}_{fu.lower()}_png"] = output_path


def run_fu_load_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    *,
    constituents: list[str] | None = None,
    model: str = "BASE",
    regions: list[str] | None = None,
    basin_scale: str = "48",
    landuse_stream_path: str | Path | None = None,
    bundle_dirs: dict[str, Path] | None = None,
) -> dict[str, object]:

    constituents = constituents or DEFAULT_CONSTITUENTS
    constituents = [c.upper() for c in constituents]
    regions = regions or ["CY", "WT", "BU", "MW", "FI", "BM"]

    output_dir = ensure_output_dir(output_dir)
    plot_dir = ensure_output_dir(output_dir / "variousExports")
    gbr_plot_dir = ensure_output_dir(plot_dir / "GBR")
    regions_root_dir = ensure_output_dir(plot_dir / "regions")

    if landuse_stream_path is not None:
        landuse_stream_path = Path(landuse_stream_path)
    elif bundle_dirs and "landuse_rainfall" in bundle_dirs:
        landuse_stream_path = Path(bundle_dirs["landuse_rainfall"]) / "landuse_stream_summary.csv"
    else:
        landuse_stream_path = (
            Path(cfg.main_path)
            / "report_card_summary"
            / "landuse_rainfall"
            / "landuse_stream_summary.csv"
        )

    if not landuse_stream_path.exists():
        raise FileNotFoundError(f"Land use stream summary not found: {landuse_stream_path}")

    fu_area_summary_raw = pd.read_csv(landuse_stream_path, index_col=0)
    fu_area_summary = _prepare_fu_area_summary(fu_area_summary_raw)

    _, region_summaries, combined = build_fu_export_summaries(
        cfg=cfg,
        model=model,
        regions=regions,
        constituents=constituents,
        units="kg",
        basin_scale=basin_scale,
    )

    files: dict[str, Path] = {}
    fu_load_summary: dict[str, pd.DataFrame] = {}
    fu_areal_load_summary: dict[str, pd.DataFrame] = {}

    for con in constituents:
        rows = []

        for region in regions:
            s = _standardise_fu_names_in_series(
                _extract_fu_series_from_wide_summary(region_summaries[region], con)
            )
            s = s * _load_conversion(con, cfg.model_years)
            s.name = REGION_NAME_MAP.get(region, region)
            rows.append(s)

        g = _standardise_fu_names_in_series(_extract_fu_series_from_wide_summary(combined, con))
        g = g * _load_conversion(con, cfg.model_years)
        g.name = "GBR"
        rows.append(g)

        out = pd.DataFrame(rows).fillna(0.0).round(2)

        load_unit = _load_unit(con)
        out.columns = [f"{fu} ({load_unit})" for fu in FU_ORDER]
        fu_load_summary[con] = out

        load_path = output_dir / f"totalLoadperYear_{con}.csv"
        out.to_csv(load_path)
        files[f"fu_load_{con.lower()}_csv"] = load_path

        denominator = fu_area_summary.reindex(out.index).fillna(0.0)

        num = out.values.astype(float) * 1000.0
        den = denominator.values.astype(float)

        areal = np.divide(
            num,
            den,
            out=np.zeros_like(num, dtype=float),
            where=(den != 0) & np.isfinite(den),
        )
        areal = np.where(np.isfinite(areal), areal, 0.0)

        areal_columns = [f"{fu} ({_areal_unit(con, fu)})" for fu in FU_ORDER]

        adf = pd.DataFrame(areal, index=out.index, columns=areal_columns).round(3)
        fu_areal_load_summary[con] = adf

        areal_path = output_dir / f"arealLoadperYear_{con}.csv"
        adf.to_csv(areal_path)
        files[f"fu_areal_{con.lower()}_csv"] = areal_path

        gbr_plot_path = gbr_plot_dir / f"exportContributionGBR_{con}.png"
        _safe_pie_plot(
            values=out.loc["GBR"],
            output_path=gbr_plot_path,
            title=f"GBR FU export contribution - {con}",
        )
        files[f"fu_pie_gbr_{con.lower()}_png"] = gbr_plot_path

        for region_name in out.index:
            if region_name == "GBR":
                continue

            safe_region_name = str(region_name).replace(" ", "_").replace("/", "_")
            single_region_dir = ensure_output_dir(regions_root_dir / safe_region_name)

            region_plot_path = single_region_dir / f"exportContribution_{safe_region_name}_{con}.png"
            _safe_pie_plot(
                values=out.loc[region_name],
                output_path=region_plot_path,
                title=f"{region_name} FU export contribution - {con}",
            )

            files[f"fu_pie_region_{safe_region_name.lower()}_{con.lower()}_png"] = region_plot_path

    _plot_fu_tonnage_vs_areal_by_region(
        fu_load_summary=fu_load_summary,
        fu_areal_load_summary=fu_areal_load_summary,
        plot_dir=plot_dir,
        files=files,
    )

    return {
        "files": files,
        "fu_load_summary": fu_load_summary,
        "fu_areal_load_summary": fu_areal_load_summary,
    }