"""Read-only GDB capture for CP02 derive and its pressure-state callee.

This is a separate evidence format from capture_boundaries.py. It captures
derive arguments plus calls to saturation_adjust_pressure_state during the
first HYDRO derive invocation. It never assigns to or calls inferior functions.
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
EXPECTED_ARRAY_BOUNDS = [(1, 235), (1, 283), (1, EXPECTED_LEVEL_COUNT)]
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
inner_entries = 0
inner_returns = 0
refresh_entries = 0
refresh_returns = 0
derive_abi_entries = 0
candidate_boundary_counts = {}
first_hydro_derive_active = False
radar_probe_enabled = os.environ.get("CP02_CAPTURE_RADAR_INPUTS") == "1"
radar_local_records = []
radar_status_addresses = {}
radar_local_breakpoints = []


def write_report(status):
    if output_path is None or not output_claimed:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "cp02-gdb-inner-capture-v1",
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
        "scope": "20 post-selected points x 22 stored levels. Captures eight meteorological fields and available state grid mass metrics; inner calls may legitimately be zero. No full-grid process budget or forecast verification.",
        "density": {
            "status": "not_stored",
            "evidence": "DWARF cloud_bal_state_type has no density member",
        },
        "counts": {
            "derive_entries": derive_entries,
            "derive_returns": derive_returns,
            "pipeline_entries": pipeline_entries,
            "pipeline_returns": pipeline_returns,
            "saturation_adjust_pressure_state_entries": inner_entries,
            "saturation_adjust_pressure_state_returns": inner_returns,
            "saturation_adjust_pressure_state_gate": "balanced_zero_or_more_calls",
            "refresh_dry_air_mass_measure_entries": refresh_entries,
            "refresh_dry_air_mass_measure_returns": refresh_returns,
            "refresh_dry_air_mass_measure_gate": "balanced_zero_or_more_calls",
            "derive_preprologue_abi_entries": derive_abi_entries,
            "candidate_boundary_counts": candidate_boundary_counts,
        },
        "inferior_exit_code": inferior_exit,
        "errors": errors,
        "records": records,
    }
    if radar_probe_enabled:
        payload["radar_probe_scope"] = "First HYDRO derive, canonical 20 points x 22 levels; no inferred values for unvisited branches"
        payload["radar_local_records"] = radar_local_records
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


def scalar_record(value, label):
    """Read a scalar only when its address and bytes are available."""
    try:
        address = value.address
        size = int(value.type.sizeof)
        if address is None or size not in (1, 2, 4, 8):
            return {"status": "unreadable", "reason": "no address or unsupported scalar width"}
        raw = bytes(gdb.selected_inferior().read_memory(int(address), size))
        return {"status": "readable", "type": str(value.type), "address": hex(int(address)), "raw_bytes_le_hex": raw.hex()}
    except Exception as exc:
        return {"status": "unreadable", "reason": str(exc)}


def immediate_scalar_members(value, label):
    result = {"status": "readable", "type": str(value.type), "address": None, "fields": {}}
    try:
        if value.address is not None:
            result["address"] = hex(int(value.address))
        for field in value.type.fields():
            if not field.name:
                continue
            member = value[field.name]
            if member.type.code in (gdb.TYPE_CODE_INT, gdb.TYPE_CODE_FLT, gdb.TYPE_CODE_BOOL, gdb.TYPE_CODE_ENUM):
                result["fields"][field.name] = scalar_record(member, label + "." + field.name)
            elif member.type.code == gdb.TYPE_CODE_ARRAY:
                result["fields"][field.name] = array_scalar_members(member, label + "." + field.name)
    except Exception as exc:
        result["status"] = "partially_readable"
        result["reason"] = str(exc)
    return result


def array_scalar_members(value, label):
    bounds = []
    array_type = value.type
    try:
        while array_type.code == gdb.TYPE_CODE_ARRAY:
            lower, upper = array_type.range()
            bounds.append((int(lower), int(upper)))
            array_type = array_type.target()
        values = []

        def visit(current, dim, indices):
            if dim == len(bounds):
                values.append({"indices": indices, **scalar_record(current, label + str(tuple(indices)))})
                return
            lower, upper = bounds[dim]
            for index in range(lower, upper + 1):
                visit(current[index], dim + 1, indices + [index])

        visit(value, 0, [])
        return {"status": "readable", "bounds": bounds, "values": values}
    except Exception as exc:
        return {"status": "unreadable", "bounds": bounds, "reason": str(exc)}


def scalar_members_from_frame(frame, name):
    try:
        return immediate_scalar_members(read_var(frame, name), name)
    except Exception as exc:
        return {"status": "unreadable", "reason": str(exc)}


def storage_from_frame(frame, name):
    try:
        value = read_var(frame, name)
        address = value.address
        if address is None:
            return {"status": "unreadable", "reason": name + " has no readable storage address", "type": str(value.type)}
        return {"status": "storage_only", "address": int(address), "type": value.type}
    except Exception as exc:
        return {"status": "unreadable", "reason": str(exc)}


def serializable_storage(storage):
    if storage.get("status") != "storage_only":
        return storage
    return {"status": "storage_only", "address": hex(storage["address"]), "type": str(storage["type"])}


def read_storage(address, value_type, label):
    if address is None:
        return {"status": "unreadable", "reason": label + " has no readable storage address", "type": str(value_type)}
    try:
        value = gdb.Value(address).cast(value_type.pointer()).dereference()
        if value.type.code in (gdb.TYPE_CODE_INT, gdb.TYPE_CODE_FLT, gdb.TYPE_CODE_BOOL, gdb.TYPE_CODE_ENUM):
            return scalar_record(value, label)
        return immediate_scalar_members(value, label)
    except Exception as exc:
        return {"status": "unreadable", "reason": str(exc), "address": hex(address), "type": str(value_type)}


def raw_pointer_slot(inferior, address, label):
    try:
        raw = bytes(inferior.read_memory(address, 8))
        pointer = int.from_bytes(raw, "little", signed=False)
        return {"slot_address": hex(address), "raw_bytes_le_hex": raw.hex(),
                "pointer_value": hex(pointer), "slot_value": "null" if pointer == 0 else "nonzero"}
    except Exception as exc:
        return {"slot_address": hex(address), "status": "unreadable", "reason": str(exc)}


def optional_state(frame):
    """Record evaluation_state presence separately from state readability."""
    result = {"presence": "unresolved", "readability": "unresolved"}
    try:
        value = frame.read_var("evaluation_state")
    except Exception as exc:
        result.update(presence="unresolved", readability="unreadable", reason=str(exc))
        return result
    result["presence"] = "DWARF_value_available"
    try:
        address, value_type = state_address(value, "evaluation_state")
        result["address"] = hex(address)
        result["readability"] = "readable"
        state_copy = state_from_address(address, value_type)
        result["fields"] = extract_state("evaluation_state", state_copy, derive_entries)
    except Exception as exc:
        result["readability"] = "unreadable"
        result["reason"] = str(exc)
    return result


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

    result["grid_mass_metrics"] = {}
    try:
        grid = state_value["grid"]
    except Exception as exc:
        result["grid_mass_metrics"]["status"] = "unreadable"
        result["grid_mass_metrics"]["reason"] = str(exc)
        grid = None
    if grid is not None:
        for metric_name in ("pressure_mass_measure", "dry_air_mass_measure"):
            try:
                metric = grid[metric_name]
                bounds = array_bounds(metric, "grid." + metric_name)
                if bounds != EXPECTED_ARRAY_BOUNDS:
                    result["grid_mass_metrics"][metric_name] = {"status": "invalid_descriptor", "type": str(metric.type), "bounds_i_j_k": bounds, "expected_bounds_i_j_k": EXPECTED_ARRAY_BOUNDS}
                    continue
                metric_record = {"status": "readable", "type": str(metric.type), "bounds_i_j_k": bounds, "points": []}
                for point in points:
                    i, j = point["fortran_i"], point["fortran_j"]
                    sampled_levels = []
                    for k in range(1, EXPECTED_LEVEL_COUNT + 1):
                        value = array_element(metric, i, j, k, "grid." + metric_name)
                        sampled_levels.append({"fortran_k": k, **scalar_record(value, f"grid.{metric_name}({i},{j},{k})")})
                    metric_record["points"].append({"point_id": point["point_id"], "fortran_i": i, "fortran_j": j, "levels": sampled_levels})
                result["grid_mass_metrics"][metric_name] = metric_record
            except Exception as exc:
                result["grid_mass_metrics"][metric_name] = {"status": "unreadable", "reason": str(exc)}

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
        if bounds != EXPECTED_ARRAY_BOUNDS:
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


def sampled_array(value, name):
    bounds = array_bounds(value, name)
    if bounds != EXPECTED_ARRAY_BOUNDS:
        raise RuntimeError(f"{name}: invalid descriptor bounds {bounds}")
    items = []
    for point in points:
        i, j = point["fortran_i"], point["fortran_j"]
        levels = [{"fortran_k": k, **scalar_record(array_element(value, i, j, k, name), f"{name}({i},{j},{k})")}
                  for k in range(1, EXPECTED_LEVEL_COUNT + 1)]
        items.append({"point_id": point["point_id"], "fortran_i": i, "fortran_j": j, "levels": levels})
    return {"status": "readable", "type": str(value.type),
            "value_address": hex(int(value.address)) if value.address is not None else None,
            "bounds_i_j_k": bounds, "points": items}


def selected_field(frame, name):
    try:
        value = read_var(frame, name)
        if value.type.code == gdb.TYPE_CODE_ARRAY:
            return sampled_array(value, name)
        return scalar_record(value, name)
    except Exception as exc:
        return {"status": "unreadable", "reason": str(exc)}


def capture_derive_arguments(frame, call_number, parent_role):
    try:
        config = immediate_scalar_members(read_var(frame, "config"), "config")
    except Exception as exc:
        config = {"status": "unreadable", "reason": str(exc)}
    budgets = {}
    for name in ("thermo_budget", "analysis_budget"):
        budgets[name] = serializable_storage(storage_from_frame(frame, name))
    record = {
        "stage": "derive_arguments",
        "call_number": call_number,
        "actual_pc": hex(int(frame.pc())),
        "parent": {"role": parent_role, "pipeline_call_number": pipeline_entries},
        "config": config,
        "thermo_active": selected_field(frame, "thermo_active"),
        "thermo_surface": selected_field(frame, "thermo_surface"),
        "target_rh": selected_field(frame, "target_rh"),
        "budgets": budgets,
        "evaluation_state": optional_state(frame),
    }
    save_record(record)


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
        super().__init__("*0x5f4af7", internal=True)

    def stop(self):
        global derive_entries
        try:
            frame = current_frame("derive_column_physics")
            derive_entries += 1
            global first_hydro_derive_active
            first_hydro_derive_active = derive_entries == 1 and os.environ.get("CLOUD_BAL_SHADOW_EXPERIMENT") == "HYDRO"
            parent_role = "primary" if pipeline_entries == 1 else "writer" if pipeline_entries >= 2 else "unresolved"
            state_in = read_var(frame, "state_in")
            state_out = read_var(frame, "state_out")
            out_address, out_type = state_address(state_out, "derive state_out")
            budget_storage = {name: storage_from_frame(frame, name) for name in ("thermo_budget", "analysis_budget")}
            state_copy = state_from_address(state_address(state_in, "derive state_in")[0], state_in.type)
            entry_record = extract_state("derive_entry_state_in", state_copy, derive_entries)
            entry_record["actual_pc"] = hex(int(frame.pc()))
            save_record(entry_record)
            capture_derive_arguments(frame, derive_entries, parent_role)
            bp = DeriveFinish(frame, out_address, out_type, derive_entries, budget_storage, parent_role)
            finish_breakpoints.append(bp)
            return False
        except Exception:
            return fail(traceback.format_exc())


class DeriveAbiEntry(gdb.Breakpoint):
    """Capture only ABI register/stack pointer words before the derive prologue."""
    def __init__(self):
        super().__init__("*0x5f4970", internal=True)

    def stop(self):
        global derive_abi_entries
        try:
            frame = gdb.selected_frame()
            inferior = gdb.selected_inferior()
            rsp = int(frame.read_register("rsp"))
            r8 = int(frame.read_register("r8"))
            r9 = int(frame.read_register("r9"))
            derive_abi_entries += 1
            save_record({"stage": "derive_preprologue_abi_pointers",
                         "call_number": derive_abi_entries,
                         "parent": {"role": "primary" if pipeline_entries == 1 else "writer" if pipeline_entries >= 2 else "unresolved",
                                    "pipeline_call_number": pipeline_entries},
                         "instruction_address": "0x5f4970", "actual_pc": hex(int(frame.pc())), "rsp": hex(rsp),
                         "r8_thermo_active_pointer": {"pointer_value": hex(r8), "slot_value": "null" if r8 == 0 else "nonzero"},
                         "r9_thermo_surface_pointer": {"pointer_value": hex(r9), "slot_value": "null" if r9 == 0 else "nonzero"},
                         "stack_pointer_words": {
                             "target_rh_arg7": raw_pointer_slot(inferior, rsp + 8, "target_rh"),
                             "thermo_budget_arg8": raw_pointer_slot(inferior, rsp + 16, "thermo_budget"),
                             "analysis_budget_arg9": raw_pointer_slot(inferior, rsp + 24, "analysis_budget"),
                             "evaluation_state_arg10": raw_pointer_slot(inferior, rsp + 32, "evaluation_state"),
                         },
                         "interpretation": "Raw call ABI pointer slots only; nonzero does not establish semantic optionality."})
            return False
        except Exception:
            return fail(traceback.format_exc())


class DeriveFinish(gdb.FinishBreakpoint):
    def __init__(self, frame, out_address, out_type, call_number, budget_storage, parent_role):
        super().__init__(frame, internal=True)
        self.out_address = out_address
        self.out_type = out_type
        self.call_number = call_number
        self.budget_storage = budget_storage
        self.parent_role = parent_role

    def stop(self):
        global derive_returns
        try:
            state_out, caller_symbol = caller_output(self.out_address)
            record = extract_state("derive_return_state_out", state_out, self.call_number)
            record["parent"] = {"role": self.parent_role, "pipeline_call_number": pipeline_entries}
            record["output_binding"] = {"argument_address": hex(self.out_address), "caller_symbol": caller_symbol, "caller_address": hex(int(state_out.address))}
            record["budgets_return"] = {}
            for name, storage in self.budget_storage.items():
                if storage.get("status") == "storage_only":
                    record["budgets_return"][name] = read_storage(storage["address"], storage["type"], name + "_return")
                else:
                    record["budgets_return"][name] = storage
            derive_returns += 1
            global first_hydro_derive_active
            if self.call_number == 1:
                first_hydro_derive_active = False
            save_record(record)
            if self in finish_breakpoints:
                finish_breakpoints.remove(self)
            return False
        except Exception:
            return fail(traceback.format_exc())


class SaturationEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x6701c2", internal=True)

    def stop(self):
        global inner_entries
        try:
            stack = stack_names()
            if not first_hydro_derive_active or not any(name.split("::")[-1] == "derive_column_physics" for name in stack):
                return False
            frame = current_frame("saturation_adjust_pressure_state")
            inner_entries += 1
            state_in = read_var(frame, "state_in")
            input_address, _ = state_address(state_in, "saturation state_in")
            try:
                input_state = extract_state("saturation_entry_state_in", state_in, inner_entries)
            except Exception as exc:
                input_state = {"status": "unreadable", "reason": str(exc)}
            output_address, output_type = state_address(read_var(frame, "state_out"), "saturation state_out")
            budget_value, budget_address = read_var(frame, "budget"), read_var(frame, "budget").address
            result_value, result_address = read_var(frame, "result"), read_var(frame, "result").address
            save_record({"stage": "saturation_adjust_pressure_state_entry", "actual_pc": hex(int(frame.pc())), "parent": {"role": "first_hydro_derive", "derive_call_number": derive_entries}, "call_number": inner_entries,
                         "stack": stack, "state_in": input_state,
                         "active": selected_field(frame, "active"),
                         "target_rh": selected_field(frame, "target_rh"),
                         "surface": selected_field(frame, "surface"),
                         "output_storage": {"state_out": {"address": hex(output_address), "type": str(output_type)},
                                            "budget": {"address": hex(int(budget_address)) if budget_address is not None else None, "type": str(budget_value.type)},
                                            "result": {"address": hex(int(result_address)) if result_address is not None else None, "type": str(result_value.type)},
                                            "state_in_address": hex(input_address)}})
            bp = SaturationFinish(frame, inner_entries, output_address, output_type,
                                  [input_address],
                                  budget_address, budget_value.type, result_address, result_value.type)
            finish_breakpoints.append(bp)
            return False
        except Exception:
            return fail(traceback.format_exc())


class SaturationFinish(gdb.FinishBreakpoint):
    def __init__(self, frame, call_number, output_address, output_type, input_addresses,
                 budget_address, budget_type, result_address, result_type):
        super().__init__(frame, internal=True)
        self.call_number = call_number
        self.input_addresses = input_addresses
        self.output_address = int(output_address)
        self.output_type = output_type
        self.budget_address = int(budget_address) if budget_address is not None else None
        self.budget_type = budget_type
        self.result_address = int(result_address) if result_address is not None else None
        self.result_type = result_type

    def stop(self):
        global inner_returns
        try:
            caller = gdb.newest_frame()
            state_out, caller_symbol = caller_output(self.output_address)
            output_state = extract_state("saturation_return_state_out", state_out, self.call_number)
            output_state["output_binding"] = {"argument_address": hex(self.output_address), "caller_symbol": caller_symbol,
                                               "caller_address": hex(int(state_out.address)),
                                               "address_matches_input": self.output_address in self.input_addresses}
            def returned_members(address, value_type, label):
                if address is None:
                    return {"status": "unreadable", "reason": label + " has no readable storage address", "type": str(value_type)}
                try:
                    value = gdb.Value(address).cast(value_type.pointer()).dereference()
                    return immediate_scalar_members(value, label)
                except Exception as exc:
                    return {"status": "unreadable", "reason": str(exc), "address": hex(address), "type": str(value_type)}
            returned_budget = returned_members(self.budget_address, self.budget_type, "budget_return")
            returned_result = returned_members(self.result_address, self.result_type, "result_return")
            inner_returns += 1
            save_record({"stage": "saturation_adjust_pressure_state_return", "parent": {"role": "first_hydro_derive", "derive_call_number": derive_entries}, "call_number": self.call_number,
                         "caller": caller.name(), "state_out": output_state,
                         "budget_return": returned_budget, "result_return": returned_result,
                         "input_addresses": [hex(address) for address in self.input_addresses]})
            if self in finish_breakpoints:
                finish_breakpoints.remove(self)
            return False
        except Exception:
            return fail(traceback.format_exc())


class RefreshMassEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x5ab212", internal=True)

    def stop(self):
        global refresh_entries
        try:
            stack = stack_names()
            if not first_hydro_derive_active or not any(name.split("::")[-1] == "derive_column_physics" for name in stack):
                return False
            frame = current_frame("refresh_dry_air_mass_measure")
            refresh_entries += 1
            state_value = read_var(frame, "state")
            state_out_address, state_type = state_address(state_value, "refresh state")
            status_storage = storage_from_frame(frame, "status")
            try:
                state_snapshot = extract_state("refresh_dry_air_mass_measure_entry_state", state_value, refresh_entries)
            except Exception as exc:
                state_snapshot = {"status": "unreadable", "reason": str(exc)}
            save_record({"stage": "refresh_dry_air_mass_measure_entry", "actual_pc": hex(int(frame.pc())),
                         "parent": {"role": "first_hydro_derive", "derive_call_number": derive_entries},
                         "call_number": refresh_entries, "stack": stack,
                         "state_address": hex(state_out_address), "state": state_snapshot,
                         "status_storage": {"address": hex(status_storage["address"]), "type": str(status_storage["type"])}
                         if status_storage.get("status") == "storage_only" else status_storage})
            bp = RefreshMassFinish(frame, refresh_entries, state_out_address, status_storage)
            finish_breakpoints.append(bp)
            return False
        except Exception:
            return fail(traceback.format_exc())


class RefreshMassFinish(gdb.FinishBreakpoint):
    def __init__(self, frame, call_number, state_address_value, status_storage):
        super().__init__(frame, internal=True)
        self.call_number = call_number
        self.state_address_value = state_address_value
        self.status_storage = status_storage

    def stop(self):
        global refresh_returns
        try:
            state_out, caller_symbol = caller_output(self.state_address_value)
            state_snapshot = extract_state("refresh_dry_air_mass_measure_return_state", state_out, self.call_number)
            state_snapshot["output_binding"] = {"argument_address": hex(self.state_address_value),
                                                 "caller_symbol": caller_symbol,
                                                 "caller_address": hex(int(state_out.address))}
            status = self.status_storage
            if status.get("status") == "storage_only":
                status = read_storage(status["address"], status["type"], "refresh_status_return")
            refresh_returns += 1
            save_record({"stage": "refresh_dry_air_mass_measure_return",
                         "parent": {"role": "first_hydro_derive", "derive_call_number": derive_entries},
                         "call_number": self.call_number, "state": state_snapshot,
                         "status_return": status})
            if self in finish_breakpoints:
                finish_breakpoints.remove(self)
            return False
        except Exception:
            return fail(traceback.format_exc())


def radar_boundary(frame, label, phase):
    names = ("radar_observed", "phase", "phase_uncertain", "zlinear", "radar_derived")
    result = {"inputs": {name: selected_field(frame, name) for name in names}}
    if phase == "pre":
        state_pointer = int(frame.read_register("rdi"))
        cfg_pointer = int(frame.read_register("rsi" if label == "diagnose_radar_cells" else "rdx"))
        state = state_from_address(state_pointer, read_var(frame, "state_in").type)
        cfg = state_from_address(cfg_pointer, read_var(frame, "config").type)
        result["actual_input_state"] = extract_state(label + "_actual_input", state, derive_entries)
        result["actual_input_state"]["address"] = hex(state_pointer)
        result["cfg"] = immediate_scalar_members(cfg, "actual_cfg")
        if label == "diagnose_radar_cells":
            result["actual_observation_state"] = {}
            for name in ("radar_reflectivity", "precipitation_phase"):
                field = state[name]
                result["actual_observation_state"][name] = {
                    member: sampled_array(field[member], name + "%" + member)
                    for member in ("value", "valid", "quality", "source")
                }
        offset = 24 if label == "diagnose_radar_cells" else 32
        slot = raw_pointer_slot(gdb.selected_inferior(), int(frame.read_register("rsp")) + offset, "status")
        address = int(slot["pointer_value"], 16)
        if not address:
            raise RuntimeError(label + " has null status storage")
        radar_status_addresses[label] = address
        result["status_storage"] = slot
    else:
        address = radar_status_addresses[label]
        raw = bytes(gdb.selected_inferior().read_memory(address, 4))
        result["status_return"] = {"status": "readable", "type": "INTEGER*4", "address": hex(address),
                                   "raw_bytes_le_hex": raw.hex(), "value": struct.unpack("<i", raw)[0]}
    return result


class RadarLocal(gdb.Breakpoint):
    """Sample actual density/phase operands only at selected diagnose loop cells."""
    def __init__(self, stage, address):
        super().__init__("*" + hex(address), internal=True)
        self.stage = stage
        self.enabled = False
        radar_local_breakpoints.append(self)

    def stop(self):
        try:
            if not first_hydro_derive_active:
                return False
            frame = gdb.newest_frame()
            loop_frame = frame.older() if self.stage == "density_entry" else frame
            if loop_frame.name().split("::")[-1] != "diagnose_radar_cells":
                return False
            i, j, k = (int(read_var(loop_frame, name)) for name in ("i", "j", "k"))
            if (i, j) not in {(p["fortran_i"], p["fortran_j"]) for p in points} or not 1 <= k <= EXPECTED_LEVEL_COUNT:
                return False
            record = {"stage": self.stage, "fortran_i": i, "fortran_j": j, "fortran_k": k,
                      "parent_derive_call": derive_entries, "actual_pc": hex(int(frame.pc())),
                      "diagnose_frame_address": hex(int(loop_frame.read_register("rbp"))), "values": {}}
            names = {"density_entry": ("pressure", "temperature", "vapor"),
                     "density_return": ("rho_d",),
                     "phase_allocation_return": ("rho_d", "total", "new_rain", "new_snow", "new_graupel", "allocation_status")}
            if self.stage == "store_after":
                for name in ("rain", "snow", "graupel"):
                    record["values"][name] = scalar_record(array_element(read_var(frame, name), i, j, k, name), name)
            else:
                for name in names[self.stage]:
                    record["values"][name] = scalar_record(read_var(frame, name), name)
            if any(v.get("status") != "readable" for v in record["values"].values()):
                raise RuntimeError("unreadable selected radar operand: " + str(record))
            radar_local_records.append(record)
            return False
        except Exception:
            return fail(traceback.format_exc())


class CallerBoundary(gdb.Breakpoint):
    """Sample caller-owned arrays immediately before/after their helper call."""
    def __init__(self, label, address, phase, arrays, candidate_state=False):
        super().__init__("*" + hex(address), internal=True)
        self.label = label
        self.phase = phase
        self.arrays = arrays
        self.candidate_state = candidate_state

    def stop(self):
        try:
            stack = stack_names()
            if not first_hydro_derive_active or not any(name.split("::")[-1] == "derive_column_physics" for name in stack):
                return False
            frame = gdb.newest_frame()
            counts = candidate_boundary_counts.setdefault(self.label, {"entries": 0, "returns": 0})
            if self.phase == "pre":
                counts["entries"] += 1
                call_number = counts["entries"]
            else:
                counts["returns"] += 1
                call_number = counts["returns"]
            arrays_record = {name: selected_field(frame, name) for name in self.arrays}
            record = {"stage": self.label + "_" + self.phase,
                      "actual_pc": hex(int(frame.pc())),
                      "caller": frame.name(),
                      "caller_frame_address": hex(int(frame.read_register("rbp"))),
                      "parent": {"role": "first_hydro_derive", "derive_call_number": derive_entries},
                      "call_number": call_number, "stack": stack,
                      "arrays": arrays_record}
            if radar_probe_enabled and self.label in ("diagnose_radar_cells", "publish_hydrometeor_candidate"):
                record["radar"] = radar_boundary(frame, self.label, self.phase)
                if self.label == "diagnose_radar_cells":
                    for breakpoint in radar_local_breakpoints:
                        breakpoint.enabled = self.phase == "pre"
            if self.candidate_state:
                try:
                    candidate = read_var(frame, "candidate")
                    if self.phase == "pre":
                        address, value_type = state_address(candidate, "publish candidate")
                        record["candidate_storage"] = {"address": hex(address), "type": str(value_type)}
                        try:
                            record["candidate_state_pre"] = extract_state("publish_candidate_pre", candidate, call_number)
                            record["candidate_state_pre"]["address"] = hex(address)
                        except Exception as exc:
                            record["candidate_state_pre"] = {"status": "unreadable", "address": hex(address), "reason": str(exc)}
                    else:
                        record["candidate_storage_address"] = hex(int(candidate.address)) if candidate.address is not None else None
                        record["candidate_state"] = extract_state("publish_candidate_post", candidate, call_number)
                        record["candidate_state"]["address"] = hex(int(candidate.address))
                except Exception as exc:
                    record["candidate_state_status"] = {"status": "unreadable", "reason": str(exc)}
            save_record(record)
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
        and inner_entries == inner_returns
        and refresh_entries == refresh_returns
        and all(counts.get("entries", 0) == counts.get("returns", 0) for counts in candidate_boundary_counts.values())
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
    SaturationEntry()
    RefreshMassEntry()
    for name, before_pc, after_pc, candidate_state in (
        ("transport_precipitation_flux", 0x60876f, 0x608774, False),
        ("diagnose_radar_cells", 0x608905, 0x60890a, False),
        ("publish_hydrometeor_candidate", 0x60a301, 0x60a306, True),
    ):
        sample_arrays = ("rain", "snow", "graupel")
        CallerBoundary(name, before_pc, "pre", sample_arrays, candidate_state)
        CallerBoundary(name, after_pc, "post", sample_arrays, candidate_state)
    DeriveAbiEntry()
    if radar_probe_enabled:
        if os.environ.get("CLOUD_BAL_SHADOW_EXPERIMENT") != "HYDRO":
            raise RuntimeError("radar input probe is scoped to HYDRO")
        RadarLocal("density_entry", 0x59e995)
        RadarLocal("density_return", 0x6373ee)
        RadarLocal("phase_allocation_return", 0x637653)
        RadarLocal("store_after", 0x63777f)
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
