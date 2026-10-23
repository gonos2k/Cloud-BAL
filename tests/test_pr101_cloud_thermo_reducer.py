from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/pr101_cloud_thermo_reducer.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pr101_cloud_thermo_reducer", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(full: int) -> dict:
    m = load_module()
    f32 = m._f32
    t0, p, qv, qc, dt, xl, cpm = map(f32, (270., 80000., .002, .001, 1., 2.5e6, 1004.))
    basis_q, basis_t = map(f32, (.0022, 271.))
    psat, ttp, xa, xb, ep2, qmin = map(f32, (611.2, 273.16, 5.0, 19.0, .622, 1.e-12))
    pcond = f32(-.001) if full else f32(-.00025)
    work = f32(-.002) if full else f32(-.0005)
    extent = qc if full else f32(-f32(pcond * dt))
    bounded = f32(max(f32(-f32(pcond * dt)), 0.))
    request = f32(max(f32(-work), 0.))
    qv1 = f32(qv + extent) if full else f32(qv - f32(pcond * dt))
    qc1 = 0. if full else f32(qc + f32(pcond * dt))
    t1 = f32(t0 - f32(f32(extent * xl) / cpm)) if full else f32(
        t0 + f32(f32(f32(pcond * xl) / cpm) * dt))
    es0, qs0 = m.source_liquid_qs(basis_t, p, psat, ttp, xa, xb, ep2, qmin)
    es1, qs1 = m.source_liquid_qs(t0, p, psat, ttp, xa, xb, ep2, qmin)
    es2, qs2 = m.source_liquid_qs(t1, p, psat, ttp, xa, xb, ep2, qmin)
    rh0 = f32(max(f32(basis_q / qs0), qmin))
    rh1 = f32(max(f32(qv / qs1), qmin))
    rh2 = f32(max(f32(qv1 / qs2), qmin))
    values = [t0, p, qv, qc, es1, qs1, work, pcond, dt, xl, cpm, basis_q, basis_t,
              psat, ttp, xa, xb, ep2, qmin, es0, qs0, es2, qs2, rh0, rh1, rh2, request, bounded, extent,
              qv1, qc1, t1, qv1-qv, qc1-qc, t1-t0]
    row = dict(zip(m.VALUE_NAMES, values, strict=True))
    row.update(pressure=p, dtcld=dt, full_evaporation=bool(full),
               timestep=1, loop=1, i=134, j=16, k=4)
    return row


@pytest.mark.parametrize("full", [False, True])
def test_source_branch_state_and_temperature_arithmetic(full):
    load_module().validate_row(record(int(full)))


def test_rejects_reported_store_that_differs_from_source(full=False):
    row = record(int(full))
    row["qc_after"] += 1e-5
    with pytest.raises(ValueError, match="stored qv/qc/T"):
        load_module().validate_row(row)


def test_parse_row_retains_source_phase_and_location():
    module = load_module()
    row = record(1)
    values = " ".join(f"{row[name]:.17E}" for name in module.VALUE_NAMES)
    parsed = module.parse_row(
        f"PR101THERMO_LIQUID,1,16,3,134,4,1,{module._bits(row['t_before'])} {values}\n")
    assert parsed["full_evaporation"] is True
    assert (parsed["timestep"], parsed["j"], parsed["loop"], parsed["i"], parsed["k"]) == (1, 16, 3, 134, 4)
    assert module._bits(parsed["es_liquid"]) == module._bits(row["es_liquid"])
    assert parsed["t_before_bits"] == module._bits(row["t_before"])


def test_rejects_unexpected_source_phase():
    module = load_module()
    values = " ".join(["1.0"] * len(module.VALUE_NAMES))
    with pytest.raises(ValueError, match="malformed PR101"):
        module.parse_row(f"PR101THERMO_ICE,1,16,3,134,4,1,1099000000 {values}\n")


def test_rejects_temperature_bits_that_do_not_match_value():
    module = load_module()
    row = record(0)
    values = " ".join(f"{row[name]:.17E}" for name in module.VALUE_NAMES)
    with pytest.raises(ValueError, match="bits disagree"):
        module.parse_row(f"PR101THERMO_LIQUID,1,16,3,134,4,0,0 {values}\n")


def test_unbounded_and_bounded_evaporation_are_distinct_for_full_branch():
    row = record(1)
    assert row["unbounded_evaporation"] > row["bounded_evaporation"]


def test_python_transcendental_oracle_is_advisory_only():
    module = load_module()
    row = record(0)
    row["es_liquid"] += 1.0e-3
    module.validate_row(row)
    assert row["saturation_oracle_ulp_differences"]["es_liquid"] > 1


def test_rejects_duplicate_arm_keys_in_contrast():
    module = load_module()
    row = record(0)
    with pytest.raises(ValueError, match="duplicate thermodynamic event key"):
        module.contrast([row, row], [row])


@pytest.mark.parametrize("meta", [
    "0,16,3,134,4,0,0", "1,0,3,134,4,0,0", "1,16,0,134,4,0,0",
])
def test_rejects_invalid_coordinates_and_loop(meta):
    module = load_module()
    values = " ".join(["1.0"] * len(module.VALUE_NAMES))
    with pytest.raises(ValueError, match="invalid timestep"):
        module.parse_row(f"PR101THERMO_LIQUID,{meta} {values}\n")
