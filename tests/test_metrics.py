import math

from gbr_source_summary.metrics import calc_nse, calc_pbias, calc_r2, calc_rsr


def test_calc_r2_perfect():
    obs = [1, 2, 3, 4]
    sim = [1, 2, 3, 4]
    assert calc_r2(obs, sim) == 1.0


def test_calc_nse_perfect():
    obs = [1, 2, 3, 4]
    sim = [1, 2, 3, 4]
    assert calc_nse(obs, sim) == 1.0


def test_calc_pbias_perfect():
    obs = [10, 20, 30]
    sim = [10, 20, 30]
    assert calc_pbias(obs, sim) == 0.0


def test_calc_rsr_perfect():
    obs = [1, 2, 3, 4]
    sim = [1, 2, 3, 4]
    assert calc_rsr(obs, sim) == 0.0


def test_calc_handles_nans():
    obs = [1, 2, None, 4]
    sim = [1, 2, 3, 4]
    assert not math.isnan(calc_r2(obs, sim))