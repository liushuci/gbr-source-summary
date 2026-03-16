from pathlib import Path

out_dir = Path("outputs") / "CY_report"

print("\nChecking output folder:", out_dir.resolve())

if not out_dir.exists():
    print("Output directory does not exist.")
else:
    print("\nFiles:")
    for p in sorted(out_dir.glob("*")):
        print("-", p.name)

    regions_dir = out_dir / "regions"
    if regions_dir.exists():
        print("\nRegion files:")
        for p in sorted(regions_dir.glob("*")):
            print("-", p.name)