from gbr_source_summary.naming import (
    standardise_constituent_names,
    standardise_management_unit_names,
)


def test_standardise_constituent_names():
    vals = ["Sediment - Fine", "N_DIN", "P_DOP"]
    out = standardise_constituent_names(vals).tolist()
    assert out == ["FS", "DIN", "DOP"]


def test_standardise_management_unit_names():
    vals = ["Jacky Jacky Creek", "PlaneC", "Waterpark"]
    out = standardise_management_unit_names(vals).tolist()
    assert out == ["Jacky Jacky", "Plane", "Water Park"]