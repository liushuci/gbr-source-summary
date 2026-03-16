from pathlib import Path
from gbr_source_summary import GBRConfig
from gbr_source_summary.io import load_source_outputs

print("script started")

cfg = GBRConfig(
    main_path=Path(r"F:\RC13_RC2023_24_Gold")
)

print("config created")
print(cfg.get_model_output_dir("CY", "BASE"))

data = load_source_outputs(cfg, region="CY", model="BASE")

print("data loaded")
print(data["regional_summary"].head())