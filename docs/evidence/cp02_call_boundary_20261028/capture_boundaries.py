"""Read-only GDB capture for the archived CP02 LAPSPREP executable.

Load with GDB after setting the run environment. The script installs entry and
finish breakpoints, captures 20 shadow points at all 22 stored levels, runs the
inferior once, and writes JSON to CP02_CAPTURE_OUTPUT. It never assigns to or
calls functions in the inferior.
"""

import csv
import hashlib
import json
import os
import shlex
import struct
import sys
import traceback
from pathlib import Path

import gdb


EXPECTED_BINARY_SHA256 = "dbea173ec059afba40ae2d46193e5f5f33a63c18d02d4fd5db5ac23b504e2e65"
DEFAULT_POINTS_CSV = str(
    Path(__file__).resolve().parents[3]
    / "docs/evidence/cp02_initial_species_20261027/final/shadow/shadow_species_profiles.csv"
)
EXPECTED_POINT_COUNT = 20
EXPECTED_LEVEL_COUNT = 22
STATE_FIELDS = (
    "vapor",
    "cloud_water",
    "cloud_ice",
    "rain",
    "snow",
    "graupel",
    "temperature",
    "pressure",
)

output_claimed = False
points_digest = None
output_setting = os.environ.get("CP02_CAPTURE_OUTPUT")
output_path = Path(output_setting) if output_setting else None
points_path = Path(os.environ.get("CP02_SHADOW_POINTS_CSV", DEFAULT_POINTS_CSV))
records = []
errors = []
derive_entries = 0
derive_returns = 0
pipeline_entries = 0
pipeline_returns = 0
inferior_exit = None
finish_breakpoints = []
points = []


def write_report(status):
    if output_path is None or not output_claimed:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "cp02-gdb-boundary-capture-v1",
        "arm": os.environ.get("CLOUD_BAL_SHADOW_EXPERIMENT"),
        "gdb_version": gdb.VERSION,
        "status": status,
        "binary": gdb.current_progspace().filename,
        "expected_binary_sha256": EXPECTED_BINARY_SHA256,
        "points_csv": str(points_path),
        "points_csv_sha256": hashlib.sha256(points_path.read_bytes()).hexdigest()
        if points_path.is_file()
        else None,
        "point_indexing": "CSV shadow_i/shadow_j are zero-based; GDB Fortran indices add 1",
        "levels_captured": EXPECTED_LEVEL_COUNT,
        "fields_captured": list(STATE_FIELDS),
        "scope": "20 post-selected points, all 22 stored levels and eight fields. No full-grid process budget or forecast verification.",
        "density": {
            "status": "not_stored",
            "evidence": "DWARF cloud_bal_state_type has no density member",
        },
        "counts": {
            "derive_entries": derive_entries,
            "derive_returns": derive_returns,
            "pipeline_entries": pipeline_entries,
            "pipeline_returns": pipeline_returns,
        },
        "inferior_exit_code": inferior_exit,
        "errors": errors,
        "records": records,
    }
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temp_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temp_path.replace(output_path)


def fail(message):
    errors.append(str(message))
    write_report("FAILED_CAPTURE")
    return True


def load_points():
    if not points_path.is_file():
        raise RuntimeError("shadow points CSV is missing: " + str(points_path))

    by_location = {}
    with points_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"arm", "shadow_i", "shadow_j", "z_index"}
        if not required.issubset(reader.fieldnames or []):
            raise RuntimeError("shadow points CSV lacks required columns: " + str(sorted(required)))
        for row in reader:
            if row["arm"].strip().upper() != "HYDRO":
                continue
            try:
                i0, j0 = int(row["shadow_i"]), int(row["shadow_j"])
                z_index = int(row["z_index"])
            except (TypeError, ValueError) as exc:
                raise RuntimeError("invalid shadow_i/shadow_j/z_index in points CSV") from exc
            if i0 < 0 or j0 < 0:
                raise RuntimeError("shadow_i/shadow_j must be zero-based nonnegative indices")
            key = (i0, j0)
            item = by_location.setdefault(
                key,
                {
                    "point_id": row.get("losthit_rank", "").strip(),
                    "lat": row.get("lat", "").strip(),
                    "lon": row.get("lon", "").strip(),
                    "shadow_i_zero_based": i0,
                    "shadow_j_zero_based": j0,
                    "fortran_i": i0 + 1,
                    "fortran_j": j0 + 1,
                    "csv_z_indices": set(),
                },
            )
            item["csv_z_indices"].add(z_index)

    if len(by_location) != EXPECTED_POINT_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_POINT_COUNT} unique HYDRO points, found {len(by_location)}"
        )
    points = list(by_location.values())
    points.sort(key=lambda item: (item["shadow_j_zero_based"], item["shadow_i_zero_based"]))
    for point in points:
        point["csv_z_indices"] = sorted(point["csv_z_indices"])
        if point["csv_z_indices"] != list(range(EXPECTED_LEVEL_COUNT)):
            raise RuntimeError("Point is missing a stored level")
    return points


def read_var(frame, name):
    try:
        return frame.read_var(name)
    except Exception as exc:
        raise RuntimeError(f"required DWARF argument {name!r} unavailable: {exc}") from exc


def state_address(value, label):
    address = value.address
    if address is None:
        raise RuntimeError(label + " has no readable inferior address")
    return int(address), value.type


def state_from_address(address, state_type):
    return gdb.Value(address).cast(state_type.pointer()).dereference()


def caller_output(address):
    """Resolve the actual returned state by address, including writer replay calls."""
    frame = gdb.newest_frame()
    block = frame.block()
    while block is not None:
        for symbol in block:
            if not (symbol.is_argument or symbol.is_variable):
                continue
            try:
                value = frame.read_var(symbol)
                if "cloud_bal_state_type" in str(value.type) and value.address is not None:
                    if int(value.address) == address:
                        return value, symbol.name
            except gdb.error:
                continue
        if block.function is not None:
            break
        block = block.superblock
    raise RuntimeError("No caller state matches captured output argument address")


def stack_names():
    names, frame = [], gdb.newest_frame()
    while frame is not None:
        names.append(frame.name())
        frame = frame.older()
    return names


def array_bounds(array_value, label):
    array_type = array_value.type
    if array_type.code != gdb.TYPE_CODE_ARRAY:
        raise RuntimeError(label + " value is not an allocated array")
    bounds = []
    for dim in range(3):
        try:
            lower, upper = array_type.range()
            array_type = array_type.target()
        except Exception as exc:
            raise RuntimeError(f"cannot read {label} dimension {dim}: {exc}") from exc
        bounds.append((int(lower), int(upper)))
    return list(reversed(bounds))


def array_element(array_value, i, j, k, label):
    try:
        return array_value[k][j][i]
    except Exception as exc:
        raise RuntimeError(f"cannot read {label}({i},{j},{k}): {exc}") from exc


def scalar_bytes(value, label):
    address = value.address
    if address is None:
        raise RuntimeError(label + " scalar has no readable address")
    size = int(value.type.sizeof)
    if size != 4:
        raise RuntimeError(f"{label} scalar has unexpected size {size}, expected 4")
    try:
        return bytes(gdb.selected_inferior().read_memory(int(address), size))
    except Exception as exc:
        raise RuntimeError(f"cannot read exact bytes for {label}: {exc}") from exc


def float_record(value, label):
    raw = scalar_bytes(value, label)
    number = struct.unpack("<f", raw)[0]
    return {"float_hex": number.hex(), "raw_bytes_le_hex": raw.hex()}


def logical_record(value, label):
    raw = scalar_bytes(value, label)
    number = struct.unpack("<i", raw)[0]
    return {"value": bool(number), "raw_bytes_le_hex": raw.hex()}


def extract_state(stage, state_value, call_number):
    inferior = gdb.selected_inferior()
    state_type = state_value.type
    try:
        available_fields = {field.name.lower() for field in state_type.fields() if field.name}
    except Exception as exc:
        raise RuntimeError("cannot inspect state DWARF members: " + str(exc)) from exc

    missing_density = "density" not in available_fields and "rho" not in available_fields
    result = {
        "stage": stage,
        "stack": stack_names(),
        "call_number": call_number,
        "state_type": str(state_type),
        "points": [],
        "missing_fields": {},
    }
    if missing_density:
        result["missing_fields"]["density"] = "not stored on cloud_bal_state_type"

    arrays = {}
    for field_name in STATE_FIELDS:
        if field_name not in available_fields:
            raise RuntimeError("required state member is absent: " + field_name)
        try:
            field_value = state_value[field_name]
            array_value = field_value["value"]
            valid_value = field_value["valid"]
        except Exception as exc:
            raise RuntimeError(f"cannot read {field_name}%value/valid: {exc}") from exc
        bounds = array_bounds(array_value, field_name + "%value")
        shape = [upper - lower + 1 for lower, upper in bounds]
        if bounds != [(1, 235), (1, 283), (1, 22)]:
            raise RuntimeError(
                f"{field_name} unexpected Fortran bounds: {bounds}"
            )
        if array_value.type.target().target().target().sizeof != 4:
            raise RuntimeError(f"{field_name} values are not REAL*4 as expected")
        arrays[field_name] = {
            "value": array_value,
            "valid": valid_value,
            "bounds": bounds,
            "shape": shape,
        }
        result.setdefault("field_shapes", {})[field_name] = {
            "fortran_bounds_i_j_k": bounds,
            "shape_i_j_k": shape,
        }

    above_ground = None
    if "above_ground" in available_fields:
        above_ground = state_value["above_ground"]
        above_bounds = array_bounds(above_ground, "above_ground")
        if (above_bounds[2][1] - above_bounds[2][0] + 1) != EXPECTED_LEVEL_COUNT:
            raise RuntimeError("above_ground layer count differs from 22")
    else:
        result["missing_fields"]["above_ground"] = "not stored on cloud_bal_state_type"

    for point in points:
        i, j = point["fortran_i"], point["fortran_j"]
        sampled = {
            "point_id": point["point_id"],
            "lat": point["lat"],
            "lon": point["lon"],
            "shadow_i_zero_based": point["shadow_i_zero_based"],
            "shadow_j_zero_based": point["shadow_j_zero_based"],
            "fortran_i": i,
            "fortran_j": j,
            "levels": [],
        }
        for field_name, descriptor in arrays.items():
            if not (
                descriptor["bounds"][0][0] <= i <= descriptor["bounds"][0][1]
                and descriptor["bounds"][1][0] <= j <= descriptor["bounds"][1][1]
            ):
                raise RuntimeError(
                    f"point ({i},{j}) is outside {field_name} bounds {descriptor['bounds']}"
                )
        for k in range(1, EXPECTED_LEVEL_COUNT + 1):
            level = {"fortran_k": k}
            if above_ground is not None:
                level["above_ground"] = logical_record(
                    array_element(above_ground, i, j, k, "above_ground"),
                    f"above_ground({i},{j},{k})",
                )
            for field_name, descriptor in arrays.items():
                value = array_element(descriptor["value"], i, j, k, field_name + "%value")
                valid = array_element(descriptor["valid"], i, j, k, field_name + "%valid")
                level[field_name] = float_record(value, f"{field_name}%value({i},{j},{k})")
                level[field_name]["valid"] = logical_record(
                    valid, f"{field_name}%valid({i},{j},{k})"
                )
            sampled["levels"].append(level)
        result["points"].append(sampled)
    return result


def save_record(record):
    records.append(record)
    write_report("CAPTURE_IN_PROGRESS")


def current_frame(function_name):
    frame = gdb.newest_frame()
    if frame is None:
        raise RuntimeError("GDB has no current frame at " + function_name)
    if frame.name().split("::")[-1] != function_name:
        raise RuntimeError(f"unexpected frame {frame.name()!r}")
    return frame


class DeriveEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__("cloud_bal_column_physics::derive_column_physics", internal=True)

    def stop(self):
        global derive_entries
        try:
            frame = current_frame("derive_column_physics")
            derive_entries += 1
            state_in = read_var(frame, "state_in")
            state_out = read_var(frame, "state_out")
            out_address, out_type = state_address(state_out, "derive state_out")
            state_copy = state_from_address(state_address(state_in, "derive state_in")[0], state_in.type)
            save_record(extract_state("derive_entry_state_in", state_copy, derive_entries))
            bp = DeriveFinish(frame, out_address, out_type, derive_entries)
            finish_breakpoints.append(bp)
            return False
        except Exception:
            return fail(traceback.format_exc())


class DeriveFinish(gdb.FinishBreakpoint):
    def __init__(self, frame, out_address, out_type, call_number):
        super().__init__(frame, internal=True)
        self.out_address = out_address
        self.out_type = out_type
        self.call_number = call_number

    def stop(self):
        global derive_returns
        try:
            state_out, caller_symbol = caller_output(self.out_address)
            record = extract_state("derive_return_state_out", state_out, self.call_number)
            record["output_binding"] = {"argument_address": hex(self.out_address), "caller_symbol": caller_symbol, "caller_address": hex(int(state_out.address))}
            derive_returns += 1
            save_record(record)
            if self in finish_breakpoints:
                finish_breakpoints.remove(self)
            return False
        except Exception:
            return fail(traceback.format_exc())


class PipelineEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__("cloud_bal_pipeline::run_cloud_bal_pipeline", internal=True)

    def stop(self):
        global pipeline_entries
        try:
            frame = current_frame("run_cloud_bal_pipeline")
            pipeline_entries += 1
            state_in = read_var(frame, "state_in")
            candidate_out = read_var(frame, "candidate_out")
            out_address, out_type = state_address(candidate_out, "pipeline candidate_out")
            state_copy = state_from_address(state_address(state_in, "pipeline state_in")[0], state_in.type)
            save_record(extract_state("pipeline_entry_state_in", state_copy, pipeline_entries))
            bp = PipelineFinish(frame, out_address, out_type, pipeline_entries)
            finish_breakpoints.append(bp)
            return False
        except Exception:
            return fail(traceback.format_exc())


class PipelineFinish(gdb.FinishBreakpoint):
    def __init__(self, frame, out_address, out_type, call_number):
        super().__init__(frame, internal=True)
        self.out_address = out_address
        self.out_type = out_type
        self.call_number = call_number

    def stop(self):
        global pipeline_returns
        try:
            candidate, caller_symbol = caller_output(self.out_address)
            record = extract_state("pipeline_return_candidate_out", candidate, self.call_number)
            record["output_binding"] = {"argument_address": hex(self.out_address), "caller_symbol": caller_symbol, "caller_address": hex(int(candidate.address))}
            pipeline_returns += 1
            save_record(record)
            if self in finish_breakpoints:
                finish_breakpoints.remove(self)
            return False
        except Exception:
            return fail(traceback.format_exc())


def on_exited(event):
    global inferior_exit
    inferior_exit = getattr(event, "exit_code", None)


def finish_run():
    expected_derive = {"HYDRO": 2, "LIQUID_RADAR_RH1": 6}.get(os.environ.get("CLOUD_BAL_SHADOW_EXPERIMENT"))
    valid = (
        not errors
        and inferior_exit == 0
        and derive_entries == expected_derive
        and derive_entries == derive_returns
        and pipeline_entries == 2
        and pipeline_returns == pipeline_entries
        and len(points) == EXPECTED_POINT_COUNT
    )
    write_report("CAPTURE_COMPLETE" if valid else "FAILED_CAPTURE")
    if not valid:
        raise RuntimeError(
            "capture gates failed: exit=%r derive=%d/%d pipeline=%d/%d errors=%d"
            % (
                inferior_exit,
                derive_entries,
                derive_returns,
                pipeline_entries,
                pipeline_returns,
                len(errors),
            )
        )


def main():
    global points, output_claimed, points_digest
    if not os.environ.get("CP02_CAPTURE_OUTPUT"):
        raise RuntimeError("CP02_CAPTURE_OUTPUT must name the JSON output file")
    if gdb.current_progspace().filename is None:
        raise RuntimeError("GDB has no executable loaded")
    binary_path = Path(gdb.current_progspace().filename)
    binary_sha = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    if binary_sha != EXPECTED_BINARY_SHA256:
        raise RuntimeError(
            f"binary digest mismatch: expected {EXPECTED_BINARY_SHA256}, got {binary_sha}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write("{}\n")
    output_claimed = True
    points_digest = hashlib.sha256(points_path.read_bytes()).hexdigest()
    points = load_points()
    gdb.execute("set language fortran", to_string=True)
    gdb.execute("set startup-with-shell off", to_string=True)
    gdb.execute("set disable-randomization off", to_string=True)
    gdb.execute("set pagination off", to_string=True)
    gdb.execute("set confirm off", to_string=True)
    gdb.events.exited.connect(on_exited)
    DeriveEntry()
    PipelineEntry()
    args = shlex.split(os.environ.get("CP02_CAPTURE_ARGS", "262281200"))
    command = "run" + (" " + " ".join(shlex.quote(arg) for arg in args) if args else "")
    gdb.execute(command)
    if hashlib.sha256(points_path.read_bytes()).hexdigest() != points_digest:
        raise RuntimeError("Point mapping changed during capture")
    if hashlib.sha256(binary_path.read_bytes()).hexdigest() != EXPECTED_BINARY_SHA256:
        raise RuntimeError("Binary changed during capture")
    finish_run()


try:
    main()
except Exception:
    errors.append(traceback.format_exc())
    write_report("FAILED_CAPTURE")
    print("CP02 boundary capture failed; see " + str(output_path), file=sys.stderr)
    raise
