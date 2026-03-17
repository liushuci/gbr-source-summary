from __future__ import annotations

from pathlib import Path
import argparse
import sys

import pandas as pd


EXPECTED_SCENARIOS = {"BASE", "PREDEV", "CHANGE"}
FS_CONSTITUENT = "FS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QA checks for GBR basin summary outputs."
    )

    parser.add_argument(
        "--folder",
        required=True,
        help="Folder containing basin summary outputs.",
    )
    parser.add_argument(
        "--run-label",
        required=True,
        help="Run label used in filenames, e.g. Gold_93_23",
    )
    parser.add_argument(
        "--reporting-units",
        default="report_card",
        choices=["raw", "report_card"],
        help="Expected reporting units for the outputs.",
    )
    parser.add_argument(
        "--generated-file",
        default=None,
        help="Optional explicit path to generated basin totals file.",
    )
    parser.add_argument(
        "--exported-file",
        default=None,
        help="Optional explicit path to exported basin totals file.",
    )

    return parser.parse_args()


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path)


def print_header(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(title)
    print(f"{'=' * 80}")


def report_pass(message: str) -> None:
    print(f"[PASS] {message}")


def report_fail(message: str) -> None:
    print(f"[FAIL] {message}")


def report_warn(message: str) -> None:
    print(f"[WARN] {message}")


def resolve_file_with_fallback(
    folder: Path,
    preferred_stem: str,
    fallback_stem: str | None,
    metric: str,
    run_label: str,
) -> Path:
    preferred = folder / f"{preferred_stem}_{metric}_{run_label}.csv"
    if preferred.exists():
        return preferred

    if fallback_stem is not None:
        fallback = folder / f"{fallback_stem}_{metric}_{run_label}.csv"
        if fallback.exists():
            report_warn(
                f"Using legacy filename {fallback.name} instead of {preferred.name}"
            )
            return fallback

    return preferred


def check_duplicate_keys(
    df: pd.DataFrame,
    key_cols: list[str],
    label: str,
) -> int:
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    dup_count = int(dup_mask.sum())

    if dup_count == 0:
        report_pass(f"{label}: no duplicate keys on {key_cols}")
        return 0

    report_fail(f"{label}: found {dup_count} duplicated rows on {key_cols}")
    print(
        df.loc[dup_mask, key_cols]
        .sort_values(key_cols)
        .head(20)
        .to_string(index=False)
    )
    return dup_count


def check_missing_scenarios(
    df: pd.DataFrame,
    label: str,
) -> int:
    if "Scenario" not in df.columns:
        report_fail(f"{label}: missing 'Scenario' column")
        return 1

    actual = set(df["Scenario"].dropna().astype(str).unique())
    missing = EXPECTED_SCENARIOS - actual
    extra = actual - EXPECTED_SCENARIOS

    issues = 0

    if missing:
        report_fail(f"{label}: missing scenarios: {sorted(missing)}")
        issues += len(missing)
    else:
        report_pass(f"{label}: all expected scenarios present")

    if extra:
        report_warn(f"{label}: unexpected scenarios present: {sorted(extra)}")
    else:
        report_pass(f"{label}: no unexpected scenarios")

    return issues


def expected_units_for_row(
    constituent: str,
    reporting_units: str,
    percent_table: bool = False,
) -> str:
    if percent_table:
        return "%"

    if reporting_units == "raw":
        return "kg"

    if constituent == FS_CONSTITUENT:
        return "kt/yr"
    return "t/yr"


def check_units(
    df: pd.DataFrame,
    label: str,
    reporting_units: str,
    value_col: str | None = None,
) -> int:
    if "Units" not in df.columns:
        report_fail(f"{label}: missing 'Units' column")
        return 1

    percent_table = value_col == "PercentReduction"

    if "Constituent" not in df.columns and not percent_table:
        report_fail(f"{label}: missing 'Constituent' column")
        return 1

    bad_rows: list[dict[str, object]] = []

    for idx, row in df.iterrows():
        expected = expected_units_for_row(
            constituent=row["Constituent"] if not percent_table else "",
            reporting_units=reporting_units,
            percent_table=percent_table,
        )
        actual = row["Units"]
        if pd.isna(actual) or str(actual) != expected:
            bad_rows.append(
                {
                    "row_index": idx,
                    "Constituent": row["Constituent"]
                    if "Constituent" in df.columns
                    else None,
                    "ActualUnits": actual,
                    "ExpectedUnits": expected,
                }
            )

    if not bad_rows:
        report_pass(f"{label}: units are consistent")
        return 0

    report_fail(f"{label}: found {len(bad_rows)} rows with unexpected units")
    print(pd.DataFrame(bad_rows).head(20).to_string(index=False))
    return len(bad_rows)


def check_nonnegative_values(
    df: pd.DataFrame,
    value_col: str,
    label: str,
) -> int:
    if value_col not in df.columns:
        report_fail(f"{label}: missing value column '{value_col}'")
        return 1

    vals = pd.to_numeric(df[value_col], errors="coerce")
    bad = df.loc[vals < 0].copy()

    if bad.empty:
        report_pass(f"{label}: no negative values in {value_col}")
        return 0

    report_warn(f"{label}: found {len(bad)} negative values in {value_col}")
    cols = [
        c
        for c in ["Scenario", "Region", "Basin", "Constituent", value_col]
        if c in bad.columns
    ]
    print(bad[cols].head(20).to_string(index=False))
    return len(bad)


def check_generated_ge_exported(
    generated_df: pd.DataFrame,
    exported_df: pd.DataFrame,
    generated_value_col: str,
    exported_value_col: str,
    label: str,
) -> int:
    required_cols = ["Scenario", "Region", "Basin", "Constituent"]

    missing_generated = [
        c for c in required_cols + [generated_value_col] if c not in generated_df.columns
    ]
    missing_exported = [
        c for c in required_cols + [exported_value_col] if c not in exported_df.columns
    ]

    if missing_generated:
        report_fail(f"{label}: generated file missing columns {missing_generated}")
        return 1
    if missing_exported:
        report_fail(f"{label}: exported file missing columns {missing_exported}")
        return 1

    merged = generated_df.merge(
        exported_df,
        on=required_cols,
        how="inner",
        suffixes=("_generated", "_exported"),
    )

    if merged.empty:
        report_fail(f"{label}: no matching rows found between generated and exported tables")
        return 1

    merged[generated_value_col] = pd.to_numeric(
        merged[generated_value_col], errors="coerce"
    )
    merged[exported_value_col] = pd.to_numeric(
        merged[exported_value_col], errors="coerce"
    )

    bad = merged.loc[
        merged[generated_value_col] + 1e-12 < merged[exported_value_col]
    ].copy()

    if bad.empty:
        report_pass(f"{label}: all matched rows satisfy generated >= exported")
        return 0

    report_warn(f"{label}: found {len(bad)} rows where generated < exported")
    cols = required_cols + [generated_value_col, exported_value_col]
    print(bad[cols].head(20).to_string(index=False))
    return len(bad)


def main() -> None:
    args = parse_args()

    folder = Path(args.folder)

    basin_fu_generated = folder / f"basin_fu_loads_generated_{args.run_label}.csv"
    basin_fu_exported = folder / f"basin_fu_loads_exported_{args.run_label}.csv"

    basin_totals_generated = (
        Path(args.generated_file)
        if args.generated_file
        else resolve_file_with_fallback(
            folder=folder,
            preferred_stem="basin_totals",
            fallback_stem="compare_ready",
            metric="generated",
            run_label=args.run_label,
        )
    )

    basin_totals_exported = (
        Path(args.exported_file)
        if args.exported_file
        else resolve_file_with_fallback(
            folder=folder,
            preferred_stem="basin_totals",
            fallback_stem="compare_ready",
            metric="exported",
            run_label=args.run_label,
        )
    )

    anthropogenic_generated = folder / f"anthropogenic_generated_{args.run_label}.csv"
    reduction_generated = folder / f"reduction_generated_{args.run_label}.csv"
    percent_generated = folder / f"percent_reduction_generated_{args.run_label}.csv"

    total_issues = 0

    print_header("Loading files")
    files_to_check = [
        basin_fu_generated,
        basin_fu_exported,
        basin_totals_generated,
        basin_totals_exported,
        anthropogenic_generated,
        reduction_generated,
        percent_generated,
    ]

    loaded: dict[str, pd.DataFrame] = {}
    for path in files_to_check:
        try:
            loaded[str(path)] = load_csv(path)
            report_pass(f"Loaded {path.name}")
        except FileNotFoundError as e:
            report_fail(str(e))
            total_issues += 1

    if total_issues > 0:
        print_header("Stopped")
        print("One or more required files are missing.")
        sys.exit(1)

    df_basin_fu_generated = loaded[str(basin_fu_generated)]
    df_basin_fu_exported = loaded[str(basin_fu_exported)]
    df_basin_totals_generated = loaded[str(basin_totals_generated)]
    df_basin_totals_exported = loaded[str(basin_totals_exported)]
    df_anth_generated = loaded[str(anthropogenic_generated)]
    df_red_generated = loaded[str(reduction_generated)]
    df_pct_generated = loaded[str(percent_generated)]

    print_header("Check: duplicate keys")
    total_issues += check_duplicate_keys(
        df_basin_fu_generated,
        ["Scenario", "Region", "Basin", "FU", "Constituent"],
        "basin_fu_loads_generated",
    )
    total_issues += check_duplicate_keys(
        df_basin_fu_exported,
        ["Scenario", "Region", "Basin", "FU", "Constituent"],
        "basin_fu_loads_exported",
    )
    total_issues += check_duplicate_keys(
        df_basin_totals_generated,
        ["Scenario", "Region", "Basin", "Constituent"],
        "basin_totals_generated",
    )
    total_issues += check_duplicate_keys(
        df_basin_totals_exported,
        ["Scenario", "Region", "Basin", "Constituent"],
        "basin_totals_exported",
    )
    total_issues += check_duplicate_keys(
        df_anth_generated,
        ["Region", "Basin", "Constituent"],
        "anthropogenic_generated",
    )
    total_issues += check_duplicate_keys(
        df_red_generated,
        ["Region", "Basin", "Constituent"],
        "reduction_generated",
    )
    total_issues += check_duplicate_keys(
        df_pct_generated,
        ["Region", "Basin", "Constituent"],
        "percent_reduction_generated",
    )

    print_header("Check: missing scenarios")
    total_issues += check_missing_scenarios(
        df_basin_fu_generated, "basin_fu_loads_generated"
    )
    total_issues += check_missing_scenarios(
        df_basin_fu_exported, "basin_fu_loads_exported"
    )
    total_issues += check_missing_scenarios(
        df_basin_totals_generated, "basin_totals_generated"
    )
    total_issues += check_missing_scenarios(
        df_basin_totals_exported, "basin_totals_exported"
    )

    print_header("Check: units")
    total_issues += check_units(
        df_basin_fu_generated,
        "basin_fu_loads_generated",
        reporting_units=args.reporting_units,
    )
    total_issues += check_units(
        df_basin_fu_exported,
        "basin_fu_loads_exported",
        reporting_units=args.reporting_units,
    )
    total_issues += check_units(
        df_basin_totals_generated,
        "basin_totals_generated",
        reporting_units=args.reporting_units,
    )
    total_issues += check_units(
        df_basin_totals_exported,
        "basin_totals_exported",
        reporting_units=args.reporting_units,
    )
    total_issues += check_units(
        df_anth_generated,
        "anthropogenic_generated",
        reporting_units=args.reporting_units,
        value_col="Anthropogenic",
    )
    total_issues += check_units(
        df_red_generated,
        "reduction_generated",
        reporting_units=args.reporting_units,
        value_col="Reduction",
    )
    total_issues += check_units(
        df_pct_generated,
        "percent_reduction_generated",
        reporting_units=args.reporting_units,
        value_col="PercentReduction",
    )

    print_header("Check: negative values")
    total_issues += check_nonnegative_values(
        df_basin_fu_generated, "LoadToStream", "basin_fu_loads_generated"
    )
    total_issues += check_nonnegative_values(
        df_basin_fu_exported, "LoadToRegExport", "basin_fu_loads_exported"
    )
    total_issues += check_nonnegative_values(
        df_basin_totals_generated, "LoadToStream", "basin_totals_generated"
    )
    total_issues += check_nonnegative_values(
        df_basin_totals_exported, "LoadToRegExport", "basin_totals_exported"
    )

    print_header("Check: generated load >= exported load")
    total_issues += check_generated_ge_exported(
        df_basin_totals_generated,
        df_basin_totals_exported,
        generated_value_col="LoadToStream",
        exported_value_col="LoadToRegExport",
        label="basin_totals generated vs exported",
    )

    print_header("Summary")
    if total_issues == 0:
        print("All QA checks passed.")
        sys.exit(0)

    print(f"QA completed with {total_issues} issue(s).")
    sys.exit(1)


if __name__ == "__main__":
    main()