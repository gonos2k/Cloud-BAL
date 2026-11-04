import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "initialize_b1_rain_psd_prior", ROOT / "tools/initialize_b1_rain_psd_prior.py"
)
prior = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prior)

# Unit tests exercise the array contract with a compact array; production keeps
# the exact pinned B1 dimensions inside the CLI module.
prior.EXPECTED_SHAPE = (1, 1, 1, 4)

LAMBDA_CENTER = prior.LAMBDA_CENTER
NR_PER_QRAIN = prior.NR_PER_QRAIN
NRMAX = prior.NRMAX
EXPECTED_SHAPE = (1, 1, 1, 4)
PriorError = prior.PriorError
initialize_qnrain = prior.initialize_qnrain
validate_candidate_entry = prior.validate_candidate_entry


def _state():
    shape = EXPECTED_SHAPE
    qrain = np.zeros(shape, dtype=np.float32)
    qnrain = np.zeros(shape, dtype=np.float32)
    density = np.ones(shape, dtype=np.float32)
    called = np.zeros(shape, dtype=bool)
    qrain[0, 0, 0, :4] = [2.0e-9, 1.0e-9, 3.0e-6, 4.0e-6]
    qnrain[0, 0, 0, 3] = 7.0
    called[0, 0, 0, :2] = True
    called[0, 0, 0, 3] = True
    return qrain, qnrain, density, called


def _initialize(qrain, qnrain, density, called):
    return initialize_qnrain(qrain, qnrain, density, called)


def test_fills_only_called_active_exact_zero_number_cells():
    qrain, qnrain, density, called = _state()
    qnrain_before = qnrain.copy()
    output, result = _initialize(qrain, qnrain, density, called)

    assert output[0, 0, 0, 0] == np.float32(qrain[0, 0, 0, 0] * NR_PER_QRAIN)
    assert output[0, 0, 0, 1] == 0.0  # qrain equals, not exceeds, qcrmin
    assert output[0, 0, 0, 2] == 0.0  # not in the first-call active domain
    assert output[0, 0, 0, 3] == qnrain[0, 0, 0, 3]  # preserve nonzero Nr
    assert result["candidate_cells"] == 1
    assert result["lambda_center_m-1"] == LAMBDA_CENTER
    assert result["below_nrmin_cells"] == 0
    assert np.array_equal(qnrain, qnrain_before)


def test_rejects_density_that_exceeds_existing_internal_number_cap():
    qrain, qnrain, density, called = _state()
    density[0, 0, 0, 0] = NRMAX / (qrain[0, 0, 0, 0] * NR_PER_QRAIN) * 2.0
    with pytest.raises(PriorError, match="SOURCE_NUMBER_CAP_EXCEEDED"):
        _initialize(qrain, qnrain, density, called)


def test_baseline_entry_mass_may_differ_from_initial_wrfinput():
    qrain, qnrain, density, called = _state()
    output, result = _initialize(qrain, qnrain, density, called)

    assert result["candidate_cells"] == 1
    assert output[0, 0, 0, 0] > 0.0


def test_reports_but_does_not_raise_values_below_source_nrmin():
    qrain, qnrain, density, called = _state()
    density[0, 0, 0, 0] = 0.01 / (qrain[0, 0, 0, 0] * NR_PER_QRAIN) / 2.0
    output, result = _initialize(qrain, qnrain, density, called)

    assert result["below_nrmin_cells"] == 1
    assert output[0, 0, 0, 0] * density[0, 0, 0, 0] < 0.01


def test_rejects_nonboolean_called_mask_instead_of_coercing_it():
    qrain, qnrain, density, called = _state()
    called = called.astype(np.float64)
    called[0, 0, 0, 0] = np.nan
    with pytest.raises(PriorError, match="CALLED_MASK_MUST_BE_BOOLEAN"):
        _initialize(qrain, qnrain, density, called)


def test_rejects_empty_called_mask():
    qrain, qnrain, density, called = _state()
    called[:] = False
    with pytest.raises(PriorError, match="EMPTY_CALLED_DOMAIN"):
        _initialize(qrain, qnrain, density, called)


def test_candidate_entry_preflight_reports_startup_stage_changes():
    qrain, qnrain, density, called = _state()
    entry_qrain = qrain.copy()
    entry_qrain[0, 0, 0, 0] *= 1.5
    entry_qnrain = qnrain.copy()
    entry_qnrain[0, 0, 0, 0] = np.float32(qrain[0, 0, 0, 0] * NR_PER_QRAIN)
    result = validate_candidate_entry(qrain, entry_qrain, entry_qnrain, density, called)

    assert result["status"] == "PASS"
    assert result["startup_fields_are_distinct_stage"] is True
    assert result["entry_lambda_float32_formula_reconstruction_m-1"]["median"] != LAMBDA_CENTER


def _candidate_entry(qrain_value, nr_value):
    initial_qrain = np.zeros(EXPECTED_SHAPE, dtype=np.float32)
    entry_qrain = np.zeros_like(initial_qrain)
    entry_qnrain = np.zeros_like(initial_qrain)
    density = np.ones_like(initial_qrain)
    called = np.zeros(EXPECTED_SHAPE, dtype=bool)
    entry_qrain.flat[0] = np.float32(qrain_value)
    entry_qnrain.flat[0] = np.float32(nr_value)
    called.flat[0] = True
    return validate_candidate_entry(initial_qrain, entry_qrain, entry_qnrain, density, called)


def test_candidate_entry_uses_inclusive_source_activation_thresholds():
    qcrmin_result = _candidate_entry(np.float32(prior.QCRMIN), 1.0)
    nrmin_result = _candidate_entry(1.0e-6, np.float32(prior.NRMIN))

    assert qcrmin_result["schema"] == "b1_rain_psd_candidate_entry_preflight_v2"
    assert qcrmin_result["source_active_candidate_entry_cells"] == 1
    assert qcrmin_result["entry_source_guard_inactive_cells"] == 0
    assert qcrmin_result["entry_below_source_qcrmin_cells"] == 0
    assert nrmin_result["source_active_candidate_entry_cells"] == 1
    assert nrmin_result["entry_below_source_nrmin_cells"] == 0


def test_slope_floor_diagnostic_uses_961_and_exposes_float32_rounding():
    near_floor = _candidate_entry(1.0e-6, 0.07062508)  # reconstructs about 960.999
    nominal_floor = _candidate_entry(1.0e-6, 0.07062530)  # reconstructs about 961.0004
    between_old_diagnostic_and_floor = _candidate_entry(1.0e-6, 0.07489768)  # about 980

    near_stats = near_floor["entry_lambda_float32_formula_reconstruction_m-1"]
    nominal_stats = nominal_floor["entry_lambda_float32_formula_reconstruction_m-1"]
    between_stats = between_old_diagnostic_and_floor["entry_lambda_float32_formula_reconstruction_m-1"]
    assert near_stats["source_slope_floor_m-1"] == 961.0
    assert near_stats["lambda_reconstruction_dtype"] == "float32"
    assert near_stats["min"] < 961.0
    assert near_stats["below_source_slope_floor_cells"] == 1
    assert nominal_stats["min"] == pytest.approx(961.000366, abs=1e-6)
    assert nominal_stats["below_source_slope_floor_cells"] == 0
    assert between_stats["min"] == pytest.approx(980.00067, abs=1e-4)
    assert between_stats["below_source_slope_floor_cells"] == 0


def test_candidate_entry_reports_negative_values_as_source_guard_inactive():
    qrain, qnrain, density, called = _state()
    entry_qrain = qrain.copy()
    entry_qnrain = qnrain.copy()
    entry_qnrain[0, 0, 0, 0] = np.float32(qrain[0, 0, 0, 0] * NR_PER_QRAIN)
    entry_qrain[0, 0, 0, 1] = np.float32(-1.0e-14)
    entry_qnrain[0, 0, 0, 3] = np.float32(-1.0e-6)

    result = validate_candidate_entry(qrain, entry_qrain, entry_qnrain, density, called)

    assert result["entry_negative_qrain_cells_source_guard_inactive"] == 1
    assert result["entry_negative_qnrain_cells_source_guard_inactive"] == 1


def test_candidate_entry_preflight_rejects_source_number_cap_exceedance():
    qrain, qnrain, density, called = _state()
    entry_qnrain = qnrain.copy()
    entry_qnrain[0, 0, 0, 0] = np.float32(qrain[0, 0, 0, 0] * NR_PER_QRAIN)
    density[0, 0, 0, 0] = NRMAX / entry_qnrain[0, 0, 0, 0] * 2.0

    with pytest.raises(PriorError, match="CANDIDATE_ENTRY_SOURCE_NUMBER_CAP_EXCEEDED"):
        validate_candidate_entry(qrain, qrain, entry_qnrain, density, called)


def test_rejects_dangling_symlink_output_without_touching_target(tmp_path):
    output = tmp_path / "candidate.nc"
    target = tmp_path / "absent.nc"
    output.symlink_to(target)

    with pytest.raises(PriorError, match="OUTPUT_ALREADY_EXISTS"):
        prior.prepare_candidate(tmp_path / "missing-input.nc", tmp_path / "missing-entry.npz", "0" * 64, output)


def test_cli_receipt_guard_does_not_overwrite_existing_path(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("retained\n")

    status = prior.main([
        "--input", str(tmp_path / "missing-input.nc"),
        "--baseline-density-capture", str(tmp_path / "missing-entry.npz"),
        "--baseline-density-capture-sha256", "0" * 64,
        "--output", str(tmp_path / "candidate.nc"),
        "--receipt", str(receipt),
    ])

    assert status == 2
    assert receipt.read_text() == "retained\n"
