set startup-with-shell off
set debuginfod enabled off
set pagination off
set confirm off
set breakpoint pending off
set print elements 0
set language c

python
import glob
import hashlib
import json
import math
import os
import struct
import tempfile
import time
import gdb

OUTER_ENTRY_PC = 0x25df680
OUTER_RETURN_PC = 0x20c3722
INNER_CALL_PC = 0x25e0fe4
INNER_ENTRY_PC = 0x25e2490
INNER_RETURN_PC = 0x25e0fe9
EXPECTED_BINARY_SHA256 = "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168"
EXPECTED_SELECTION_SHA256 = "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e"
EXPECTED_BUILD_ID = "8baf18e56c6a582ccc7a27fb4d1653ad18fb8810"
REG_ARGS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
ARG_NAMES = """th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat xland rain rainncv snow snowncv sr refl_10cm diagflag do_radar_ref graupel graupelncv itimestep has_reqc has_reqi has_reqs re_cloud re_ice re_snow ids ide jds jde kds kde ims ime jms jme kms kme its ite jts jte kts kte""".split()
SCALAR_REAL = set(range(18, 42))
SCALAR_INT = {49, 50} | set(range(53, 57)) | set(range(60, 78))
ARRAY_3D = set(range(1, 18)) | {48} | set(range(57, 60))
ARRAY_2D = set(range(42, 48)) | {51, 52}
INNER_REG_NAMES = ("t", "q", "qci", "qrs", "nci", "nrs")
INNER_REGS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
TARGET_LABELS = {"P01_00", "P01_10", "P01_01", "P01_11",
                 "P05_00", "P05_10", "P05_01", "P05_11"}
WATCH_TARGET_RANK = {"P01_00": "3", "P05_00": "1"}
WATCH_FIELDS = ("qrs", "q")
MAX_WATCH_EVENTS = 256
NULLABLE_INNER_POSITIONS = {14, 17, 18, 21, 32, 39, 40, 41, 42, 43, 44, 47, 48}
EXPECTED_RANKS = int(os.environ.get("CP02_EXPECT_RANKS", "8"))
OUT = os.environ["CP02_CAPTURE_DIR"]
SELECTION_PATH = os.environ["CP02_SELECTION_JSON"]
SCRIPT_PATH = os.path.realpath(os.environ["CP02_CAPTURE_SCRIPT"])
CONTEXT_PATH = os.environ["CP02_STAGE_CONTEXT_JSON"]
EXPECTED_SCRIPT_SHA256 = os.environ["CP02_EXPECTED_SCRIPT_SHA256"]
RANK = None
STAGE = None
ARM = None
CONTEXT_SHA256 = None
CONTEXT = None
SELECTION = None
POINTS = None
STATE = {"record": None, "path": None, "outer_args": None,
         "outer_bounds": None, "outer_domain_bounds": None, "tile_bounds": None, "outer_call": 0,
         "current_inner": None, "watchpoints": [], "watch_events": 0,
         "watched_targets": set(), "success": False, "failure": None,
         "failure_details": {}, "event_ordinal": 0, "callback_ordinal": 0, "source_address": None, "b_address": None}

def stamp(event, inner=None):
    STATE["event_ordinal"] += 1
    event["event_ordinal"] = STATE["event_ordinal"]
    event["inner_call_id"] = inner["record"]["event_id"] if inner else None
    event["selected_inner_id"] = event["inner_call_id"]
    event["callback_ordinal"] = STATE["callback_ordinal"]
    return event

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def rank_name():
    for key in ("PMI_RANK", "PMIX_RANK", "OMPI_COMM_WORLD_RANK", "MPI_LOCALRANKID"):
        if key in os.environ:
            return str(os.environ[key])
    return "unknown"

def load_contract():
    global RANK, STAGE, ARM, CONTEXT_SHA256, CONTEXT, SELECTION, POINTS
    RANK = rank_name()
    if RANK not in {str(n) for n in range(EXPECTED_RANKS)}:
        raise RuntimeError("rank_outside_expected_set:" + RANK)
    binary = os.path.realpath(gdb.current_progspace().filename)
    binary_sha = sha256_file(binary)
    if binary_sha != EXPECTED_BINARY_SHA256:
        raise RuntimeError("binary_sha256_mismatch:" + binary_sha)
    if sha256_file(SCRIPT_PATH) != EXPECTED_SCRIPT_SHA256:
        raise RuntimeError("capture_script_sha256_mismatch")
    if sha256_file(SELECTION_PATH) != EXPECTED_SELECTION_SHA256:
        raise RuntimeError("selection_sha256_mismatch")
    with open(CONTEXT_PATH, encoding="utf-8") as stream:
        context = json.load(stream)
    CONTEXT = context
    CONTEXT_SHA256 = sha256_file(CONTEXT_PATH)
    STAGE = context.get("stage_id")
    ARM = context.get("arm")
    if not STAGE or not ARM:
        raise RuntimeError("stage_context_missing_stage_or_arm")
    if context.get("binary_sha256") != binary_sha:
        raise RuntimeError("stage_context_binary_sha256_mismatch")
    if context.get("build_id") != EXPECTED_BUILD_ID:
        raise RuntimeError("stage_context_build_id_mismatch")
    if context.get("selection_sha256") != EXPECTED_SELECTION_SHA256:
        raise RuntimeError("stage_context_selection_sha256_mismatch")
    if context.get("helper_sha256") != EXPECTED_SCRIPT_SHA256:
        raise RuntimeError("stage_context_helper_sha256_mismatch")
    if context.get("expected_ranks") != EXPECTED_RANKS:
        raise RuntimeError("stage_context_rank_count_mismatch")
    if not context.get("run_receipt_sha256") or not context.get("intel_profile"):
        raise RuntimeError("stage_context_missing_run_receipt_or_intel_profile")
    data = json.load(open(SELECTION_PATH, encoding="utf-8"))
    POINTS = data if isinstance(data, list) else data.get("points", [])
    coords = {(p["i"], p["j"], p.get("k", 1)) for p in POINTS}
    if len(POINTS) != 624 or len(coords) != 624:
        raise RuntimeError("selection_must_contain_624_unique_points")
    if not TARGET_LABELS.issubset({p.get("label") for p in POINTS}):
        raise RuntimeError("selection_missing_target_labels")
    SELECTION = {"sha256": EXPECTED_SELECTION_SHA256, "points": POINTS}

def atomic_json(path, record):
    fd, temporary = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".",
                                     suffix=".tmp", dir=OUT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def save_record():
    if STATE["record"] is not None:
        atomic_json(STATE["path"], STATE["record"])

def save_failure(stage, message):
    if STATE["failure"] is not None:
        return
    STATE["failure"] = {"stage": stage, "error": str(message)}
    try:
        pc = hex(int(gdb.parse_and_eval("$pc")))
        backtrace = gdb.execute("bt", to_string=True)
    except gdb.error:
        pc, backtrace = None, None
    path = os.path.join(OUT, "failed_%s_rank%s_pid%s.json" % (STAGE or "unknown", RANK or "unknown", gdb.selected_inferior().pid))
    atomic_json(path, {"status": "failed", "stage_id": STAGE, "arm": ARM,
                       "rank": RANK, "pid": gdb.selected_inferior().pid,
                       "pc": pc, "error": str(message), "backtrace": backtrace,
                       "stage_context_sha256": CONTEXT_SHA256,
                       "binary_sha256": EXPECTED_BINARY_SHA256,
                       "helper_sha256": EXPECTED_SCRIPT_SHA256,
                       "selection_sha256": EXPECTED_SELECTION_SHA256,
                       "failure_details": STATE["failure_details"]})
    if STATE["record"] is not None:
        STATE["record"]["status"] = "failed"
        STATE["record"]["failure"] = STATE["failure"]
        save_record()
    print("THERMO_CAPTURE_FAILED rank=%s stage=%s file=%s" % (RANK, stage, path))

def read_bytes(address, count):
    return bytes(gdb.selected_inferior().read_memory(int(address), int(count)))

def unpack_u64(address):
    return struct.unpack("=Q", read_bytes(address, 8))[0]

def unpack_i32(address):
    return struct.unpack("=i", read_bytes(address, 4))[0]

def raw_float(address):
    raw = read_bytes(address, 4)
    value = struct.unpack("=f", raw)[0]
    finite = math.isfinite(value)
    return {"address_hex": hex(int(address)), "raw_hex": raw.hex(),
            "value_f32": value if finite else None, "finite": finite}

def f32(value):
    return struct.unpack("=f", struct.pack("=f", float(value)))[0]

def ordered_f32_bits(raw):
    bits = struct.unpack("=I", raw)[0]
    return ((~bits) & 0xffffffff) if (bits & 0x80000000) else (bits | 0x80000000)

def within_one_ulp(raw_a, raw_b):
    return abs(ordered_f32_bits(raw_a) - ordered_f32_bits(raw_b)) <= 1

def outer_args_at_entry():
    rsp = int(gdb.parse_and_eval("$rsp"))
    regs = {name: int(gdb.parse_and_eval("$" + name)) for name in REG_ARGS}
    args = [regs[name] for name in REG_ARGS]
    args.extend(unpack_u64(rsp + 8 + 8 * n) for n in range(71))
    if len(args) != 77 or any(pointer == 0 for pointer in args):
        raise RuntimeError("outer_null_or_wrong_argument_count")
    return args, regs, rsp

def bounds_from_args(args, names):
    return {name: unpack_i32(args[ARG_NAMES.index(name)]) for name in names}

def array_offset(i, j, k, bounds, is_3d):
    nx = bounds["ime"] - bounds["ims"] + 1
    if is_3d:
        nk = bounds["kme"] - bounds["kms"] + 1
        return (i - bounds["ims"]) + (k - bounds["kms"]) * nx + (j - bounds["jms"]) * nx * nk
    return (i - bounds["ims"]) + (j - bounds["jms"]) * nx

def sample_outer(args, bounds, tile):
    result = []
    for point in POINTS:
        i, j, k = point["i"], point["j"], point.get("k", bounds["kms"])
        sample = {"label": point.get("label"), "i": i, "j": j, "k": k,
                  "status": None, "values": {}}
        if not (bounds["ims"] <= i <= bounds["ime"] and bounds["jms"] <= j <= bounds["jme"] and bounds["kms"] <= k <= bounds["kme"]):
            sample["status"] = "outside_memory_bounds"
            result.append(sample)
            continue
        if not (tile["its"] <= i <= tile["ite"] and tile["jts"] <= j <= tile["jte"] and tile["kts"] <= k <= tile["kte"]):
            sample["status"] = "not_owned_tile"
            result.append(sample)
            continue
        sample["status"] = "owned_tile"
        for number in sorted(ARRAY_3D | ARRAY_2D):
            name = ARG_NAMES[number - 1]
            offset = array_offset(i, j, k, bounds, number in ARRAY_3D)
            sample["values"][name] = dict(raw_float(args[number - 1] + 4 * offset), offset_f32=offset)
        result.append(sample)
    return result

def scalar_snapshot(args):
    values = {}
    for number in sorted(SCALAR_REAL | SCALAR_INT):
        name = ARG_NAMES[number - 1]
        raw = read_bytes(args[number - 1], 4)
        value = struct.unpack("=f" if number in SCALAR_REAL else "=i", raw)[0]
        finite = not isinstance(value, float) or math.isfinite(value)
        values[name] = {"arg": number, "raw_hex": raw.hex(),
                        "decoded": value if finite else None, "finite": finite}
    return values

def init_record():
    pid = gdb.selected_inferior().pid
    STATE["path"] = os.path.join(OUT, "raw_%s_rank%s_pid%s.json" % (STAGE, RANK, pid))
    if os.path.exists(STATE["path"]):
        raise RuntimeError("raw_capture_path_already_exists")
    maps_path = os.path.join(OUT, "maps_%s_rank%s_pid%s.txt" % (STAGE, RANK, pid))
    with open("/proc/%d/maps" % pid, encoding="utf-8") as stream:
        maps = stream.read()
    with open(maps_path, "x", encoding="utf-8") as stream:
        stream.write(maps)
        stream.flush()
        os.fsync(stream.fileno())
    STATE["record"] = {"status": "capturing", "stage_id": STAGE, "arm": ARM,
        "rank": RANK, "pid": pid, "started_unix_ns": time.time_ns(),
        "stage_context_sha256": CONTEXT_SHA256,
        "binary_sha256": EXPECTED_BINARY_SHA256,
        "build_id": EXPECTED_BUILD_ID,
        "helper_sha256": EXPECTED_SCRIPT_SHA256,
        "selection_sha256": EXPECTED_SELECTION_SHA256,
        "selection_points": len(POINTS), "expected_ranks": EXPECTED_RANKS,
        "proc_maps_file": maps_path, "proc_maps_sha256": sha256_file(maps_path),
        "run_receipt_sha256": CONTEXT["run_receipt_sha256"],
        "intel_profile": CONTEXT["intel_profile"],
        "gdb_version": gdb.execute("show version", to_string=True).splitlines()[0],
        "outer": None, "inner": [], "write_events": [], "preclamp_events": [], "producer_events": [], "source_events": [], "candidate_events": [], "b_events": []}

def read_pointer_args(registers, rsp, count):
    args = [registers[name] for name in INNER_REGS]
    args.extend(unpack_u64(rsp + 8 + 8 * n) for n in range(count - 6))
    if len(args) != count:
        raise RuntimeError("inner_null_or_wrong_argument_count")
    return args

def inner_arg_values(args):
    unavailable = [position for position in (32, 39, 40, 41, 42, 43, 44, 47, 48)
                   if args[position - 1] == 0]
    return {"ims": unpack_i32(args[44]), "ime": unpack_i32(args[45]),
            "kms": unpack_i32(args[48]), "kme": unpack_i32(args[49]),
            "its": unpack_i32(args[50]), "ite": unpack_i32(args[51]),
            "jts": unpack_i32(args[52]), "jte": unpack_i32(args[53]),
            "kts": unpack_i32(args[54]), "kte": unpack_i32(args[55]),
            "unavailable_argument_positions": unavailable}

def target_points_for_j(current_j, bounds):
    return [p for p in POINTS if p.get("label") in TARGET_LABELS and
            p.get("k") == 8 and p["j"] == current_j and
            bounds["its"] <= p["i"] <= bounds["ite"] and
            bounds["kts"] <= p["k"] <= bounds["kte"]]

def derive_current_j(args, bounds):
    outer_bounds = STATE["outer_bounds"]
    outer_q = STATE["outer_args"][ARG_NAMES.index("q")]
    nxmem = outer_bounds["ime"] - outer_bounds["ims"] + 1
    nkmem = outer_bounds["kme"] - outer_bounds["kms"] + 1
    row_stride = 4 * nxmem * nkmem
    delta = args[1] - outer_q
    if delta < 0 or delta % row_stride != 0:
        raise RuntimeError("inner_q_pointer_not_aligned_to_outer_q_row")
    current_j = outer_bounds["jms"] + delta // row_stride
    if not outer_bounds["jms"] <= current_j <= outer_bounds["jme"]:
        raise RuntimeError("derived_inner_j_outside_outer_memory_bounds")
    if not STATE["tile_bounds"]["jts"] <= current_j <= STATE["tile_bounds"]["jte"]:
        raise RuntimeError("derived_inner_j_outside_outer_tile_bounds")
    if not bounds["jts"] <= current_j <= bounds["jte"]:
        raise RuntimeError("derived_inner_j_outside_inner_tile_bounds")
    return current_j, row_stride

def inner_offset(point, bounds):
    nx = bounds["ite"] - bounds["its"] + 1
    return (point["i"] - bounds["its"]) + (point["k"] - bounds["kts"]) * nx

def outer_entry_sample(label):
    if STATE["record"] is None or STATE["record"].get("outer") is None:
        raise RuntimeError("inner_call_without_outer_entry")
    point = next(p for p in POINTS if p.get("label") == label and p.get("k") == 8)
    for sample in STATE["record"]["outer"]["entry"]["samples"]:
        if (sample.get("label"), sample.get("i"), sample.get("j"), sample.get("k")) == (point["label"], point["i"], point["j"], point["k"]) and sample.get("status") == "owned_tile":
            return sample
    raise RuntimeError("target_not_owned_at_outer_entry:" + label)

def verify_inner_mapping(point, args, values, offset, current_j):
    outer = outer_entry_sample(point["label"])["values"]
    nxmem = values["ime"] - values["ims"] + 1
    q_offset = (point["i"] - values["ims"]) + (point["k"] - values["kms"]) * nxmem
    outer_args = STATE["outer_args"]
    outer_bounds = STATE["outer_bounds"]
    outer_tile = STATE["tile_bounds"]
    for name in ("ims", "ime", "kms", "kme"):
        if values[name] != outer_bounds[name]:
            raise RuntimeError("inner_outer_memory_bound_mismatch:" + name)
    for name in ("its", "ite", "jts", "jte", "kts", "kte"):
        if values[name] != outer_tile[name]:
            raise RuntimeError("inner_outer_tile_bound_mismatch:" + name)
    outer_nk = outer_bounds["kme"] - outer_bounds["kms"] + 1
    q_row_offset = (current_j - outer_bounds["jms"]) * nxmem * outer_nk
    expected_q_pointer = outer_args[ARG_NAMES.index("q")] + 4 * q_row_offset
    if args[1] != expected_q_pointer:
        raise RuntimeError("inner_q_pointer_does_not_alias_outer_q_row:" + point["label"])
    actual = {
        "qrs": raw_float(args[3] + 4 * offset),
        "qci": raw_float(args[2] + 4 * offset),
        "q": raw_float(args[1] + 4 * q_offset),
        "t": raw_float(args[0] + 4 * offset),
    }
    expected = {name: outer[name] for name in ("qr", "qc", "q", "th", "pii")}
    if actual["qrs"]["raw_hex"] != expected["qr"]["raw_hex"]:
        raise RuntimeError("qrs_outer_qr_entry_mismatch:" + point["label"])
    if actual["qci"]["raw_hex"] != expected["qc"]["raw_hex"]:
        raise RuntimeError("qci_outer_qc_entry_mismatch:" + point["label"])
    if actual["q"]["raw_hex"] != expected["q"]["raw_hex"]:
        raise RuntimeError("q_outer_entry_mismatch:" + point["label"])
    expected_t = f32(expected["th"]["value_f32"] * expected["pii"]["value_f32"])
    expected_t_raw = struct.pack("=f", expected_t)
    if not within_one_ulp(bytes.fromhex(actual["t"]["raw_hex"]), expected_t_raw):
        raise RuntimeError("t_th_times_pii_entry_mismatch:" + point["label"])
    return {"qrs_equals_outer_qr": True, "qci_equals_outer_qc": True,
            "q_equals_outer_q": True, "t_equals_real32_th_times_pii_within_1_ulp": True,
            "q_memory_offset_f32": q_offset, "tile_offset_f32": offset,
            "current_j_from_q_row_pointer": current_j,
            "candidate_entry_values": actual}

def inner_values_at(args, point, bounds):
    offset = inner_offset(point, bounds)
    nxmem = bounds["ime"] - bounds["ims"] + 1
    q_offset = (point["i"] - bounds["ims"]) + (point["k"] - bounds["kms"]) * nxmem
    return {"qrs": raw_float(args[3] + 4 * offset),
            "qci": raw_float(args[2] + 4 * offset),
            "q": raw_float(args[1] + 4 * q_offset),
            "t": raw_float(args[0] + 4 * offset),
            "nci": raw_float(args[4] + 4 * offset),
            "nrs": raw_float(args[5] + 4 * offset),
            "tile_offset_f32": offset, "q_memory_offset_f32": q_offset}

def delete_watchpoints():
    for breakpoint in list(STATE["watchpoints"]):
        try:
            breakpoint.delete()
        except gdb.error:
            pass
    STATE["watchpoints"] = []

def setup_watchpoints(target, args, point, bounds, offset):
    if target in STATE["watched_targets"]:
        return
    expected_rank = WATCH_TARGET_RANK[target]
    if RANK != expected_rank:
        raise RuntimeError("watch_target_owner_rank_mismatch:" + target)
    if len(STATE["watchpoints"]) != 0:
        raise RuntimeError("watchpoints_already_active")
    addrs = {"qrs": args[3] + 4 * offset, "qci": args[2] + 4 * offset,
             "q": args[1] + 4 * ((point["i"] - bounds["ims"]) + (point["k"] - bounds["kms"]) * (bounds["ime"] - bounds["ims"] + 1)),
             "t": args[0] + 4 * offset}
    STATE["watchpoints"].append(SourceArmBreakpoint(target, addrs["qrs"]))
    STATE["watchpoints"].append(BArmBreakpoint(target))
    for pc, role in ((0x25ef2cf, "before_upstream_2cf"), (0x25ef2f6, "before_frame_store_2f6"), (0x25ef2fb, "after_frame_store_2fb"), (0x25ef29d, "before_min_29d"), (0x25ef97a, "before_max_97a"), (0x25ef2a8, "writer_before_2a8"), (0x25ef2ae, "writer_after_2a8"), (0x25ef98f, "writer_before_98f"), (0x25ef995, "writer_after_98f")):
        STATE["watchpoints"].append(SourceWriterBreakpoint(pc, role, target))
    for pc, role in ((0x25f4e24, "before_sum"), (0x25f4e50, "before_clamp"), (0x25f4e58, "before_store"), (0x25f4e5e, "after_store")):
        bp = PreclampBreakpoint(pc, role, target, addrs["qrs"])
        STATE["watchpoints"].append(bp)
    for pc, role in ((0x25f4492, "before_load"), (0x25f4498, "after_load"),
                     (0x25f44a4, "before_compare"), (0x25f44be, "before_multiply"),
                     (0x25f44c2, "after_multiply"), (0x25f44f7, "branch_join"),
                     (0x25f4a59, "path_to_sum")):
        STATE["watchpoints"].append(ProducerBreakpoint(pc, role, target, addrs["qrs"]))
    for pc, role in ((0x25ef8ca, "before_array_load"), (0x25ef8d8, "before_subtract"),
                     (0x25ef8dc, "before_convert_to_double"), (0x25ef8e7, "before_double_multiply"),
                     (0x25ef928, "before_product"), (0x25ef933, "before_divide"),
                     (0x25ef93c, "before_convert_to_single"), (0x25ef940, "before_single_multiply"),
                     (0x25ef944, "before_compare"), (0x25ef947, "before_branch")):
        STATE["watchpoints"].append(CandidateBreakpoint(pc, role, target))
    try:
        for name in WATCH_FIELDS:
            expression = "*(unsigned int *)%s" % hex(addrs[name])
            bp = Watchpoint(expression, name, addrs[name])
            bp.silent = True
            STATE["watchpoints"].append(bp)
        if len(STATE["watchpoints"]) != 34:
            raise RuntimeError("expected_four_watchpoints")
    except Exception:
        delete_watchpoints()
        raise
    STATE["watched_targets"].add(target)
    print("THERMO_WATCH_ARMED rank=%s target=%s fields=%s" % (RANK, target, ",".join(WATCH_FIELDS)))

def watch_event(bp):
    inner = STATE["current_inner"]
    if inner is None:
        save_failure("watchpoint", "watchpoint_event_without_active_inner_call")
        return True
    breakpoint_info = gdb.execute("info breakpoints %d" % bp.number, to_string=True).lower()
    hardware_type = getattr(gdb, "BP_HARDWARE_WATCHPOINT", None)
    if bp.type not in (gdb.BP_WATCHPOINT, hardware_type):
        save_failure("watchpoint_type", "watchpoint_not_hardware")
        return True
    if "hardware watchpoint" not in breakpoint_info and "hw watchpoint" not in breakpoint_info:
        save_failure("watchpoint_type", "gdb_did_not_report_hardware_watchpoint")
        return True
    STATE["watch_events"] += 1
    if STATE["watch_events"] > MAX_WATCH_EVENTS:
        save_failure("watchpoint_overflow", "watch_event_limit=%d" % MAX_WATCH_EVENTS)
        return True
    point = inner["watch_point"]
    values = inner_values_at(inner["args"], point, inner["bounds"])
    event = {"ordinal": STATE["watch_events"], "target": point["label"],
             "field": bp.field_name, "watched_address_hex": hex(bp.watched_address),
             "mechanism": "hardware_write_watchpoint_unsigned_32_bit",
             "gdb_breakpoint_type": str(bp.type),
             "gdb_breakpoint_info": breakpoint_info.strip(),
             "rank": RANK, "pid": gdb.selected_inferior().pid,
             "pc_after_write_hex": hex(int(gdb.parse_and_eval("$pc"))),
             "registers_at_watchpoint": gdb.execute("info all-registers", to_string=True),
             "backtrace": gdb.execute("bt", to_string=True),
             "instructions_near_pc": gdb.execute("x/8i $pc-16", to_string=True),
             "raw_before_hex": inner["last_values"][bp.field_name]["raw_hex"],
             "raw_after_hex": values[bp.field_name]["raw_hex"],
             "values_after_write": values}
    stamp(event, inner)
    STATE["record"]["write_events"].append(event)
    inner["last_values"] = values
    save_record()
    return False


def raw_double(address):
    raw = read_bytes(address, 8)
    value = struct.unpack("=d", raw)[0]
    return {"address_hex": hex(int(address)), "raw_hex": raw.hex(),
            "value_f64": value if math.isfinite(value) else None, "finite": math.isfinite(value)}

class CandidateBreakpoint(gdb.Breakpoint):
    def __init__(self, pc, role, target):
        super().__init__("*" + hex(pc), internal=True)
        self.role, self.target = role, target
    def stop(self):
        try:
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or inner["watch_point"]["label"] != self.target:
                return False
            index = int(gdb.parse_and_eval("$r15"))
            rbx = int(gdb.parse_and_eval("$rbx"))
            if unpack_u64(rbx + 0xb0) + 4 * index != STATE["b_address"]:
                return False
            operands = {}
            for offset in (0x1b8, 0xb0, 0x120):
                operands["array_0x%x" % offset] = raw_float(unpack_u64(rbx + offset) + 4 * index)
            for offset in (0xe8, 0x160):
                operands["array_0x%x" % offset] = raw_double(unpack_u64(rbx + offset) + 8 * index)
            operands["constant_34b9028"] = raw_float(0x34b9028)
            operands["constant_34bbaf4"] = raw_float(0x34bbaf4)
            for offset in (0x18, 0x50, 0x140):
                operands["frame_0x%x" % offset] = raw_float(rbx + offset)
            regs = {}
            for name in ("xmm0", "xmm1", "xmm2", "xmm4", "xmm5", "xmm6"):
                bits = int(gdb.parse_and_eval("$%s.v2_int64[0]" % name)) & 0xffffffffffffffff
                raw = struct.pack("<Q", bits)
                d, f = struct.unpack("<d", raw)[0], struct.unpack("<f", raw[:4])[0]
                regs[name] = {"raw_hex64": raw.hex(), "value_f64": d if math.isfinite(d) else None,
                              "raw_hex32": raw[:4].hex(), "value_f32": f if math.isfinite(f) else None}
            event = {"role": self.role, "target": self.target,
                     "pc_hex": hex(int(gdb.parse_and_eval("$pc"))), "index_r15": index,
                     "frame_rbx_hex": hex(rbx), "frame_rbx_raw_hex": read_bytes(rbx, 0x960).hex(), "operands": operands, "scalar_registers": regs,
                     "mxcsr": int(gdb.parse_and_eval("$mxcsr")),
                     "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True)}
            stamp(event, inner); STATE["record"]["candidate_events"].append(event); save_record()
            return False
        except Exception as exc:
            save_failure("candidate_breakpoint", repr(exc)); return True

class BArmBreakpoint(gdb.Breakpoint):
    def __init__(self, target):
        super().__init__("*0x25e2fc0", internal=True)
        self.target = target
    def stop(self):
        try:
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or inner["watch_point"]["label"] != self.target:
                return False
            rbx = int(gdb.parse_and_eval("$rbx"))
            base = unpack_u64(rbx + 0x648)
            offset = inner_offset(inner["watch_point"], inner["bounds"])
            if not base or base != int(gdb.parse_and_eval("$rax")):
                raise RuntimeError("b_allocation_base_mismatch")
            address = base + 4 * offset
            STATE["b_address"] = address
            STATE["watchpoints"].append(BWatchpoint(address))
            event = {"role": "arm", "target": self.target, "pc_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "address_hex": hex(address), "base_hex": hex(base), "offset_f32": offset,
                     "value": raw_float(address)}
            stamp(event, inner); STATE["record"]["b_events"].append(event); save_record()
            self.enabled = False
            return False
        except Exception as exc:
            save_failure("b_arm", repr(exc)); return True

class BWatchpoint(gdb.Breakpoint):
    def __init__(self, address):
        super().__init__("*(unsigned int *)" + hex(address), gdb.BP_WATCHPOINT, wp_class=gdb.WP_ACCESS, internal=False)
        self.address, self.last = address, raw_float(address)
        info = gdb.execute("info breakpoints %d" % self.number, to_string=True).lower()
        if "acc watchpoint" not in info or self.type != gdb.BP_ACCESS_WATCHPOINT:
            self.delete(); raise RuntimeError("b_watch_not_hardware:" + info)
    def stop(self):
        try:
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or self.address != STATE["b_address"]:
                raise RuntimeError("b_watch_without_active_target_or_address")
            after = raw_float(self.address)
            event = {"role": "watch_access", "target": inner["watch_point"]["label"],
                     "pc_after_access_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "address_hex": hex(self.address), "before": self.last, "after": after,
                     "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True),
                     "instructions_near_pc": gdb.execute("x/8i $pc-16", to_string=True)}
            stamp(event, inner); STATE["record"]["b_events"].append(event)
            self.last = after; save_record(); return False
        except Exception as exc:
            save_failure("b_watch", repr(exc)); return True

class SourceArmBreakpoint(gdb.Breakpoint):
    def __init__(self, target, qrs_address):
        super().__init__("*0x25ef187", internal=True)
        self.target, self.qrs_address = target, qrs_address
    def stop(self):
        try:
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or inner["watch_point"]["label"] != self.target:
                return False
            rbx = int(gdb.parse_and_eval("$rbx"))
            base = unpack_u64(rbx + 0x728)
            qrs_base = unpack_u64(rbx + 0x1f0)
            address = base + self.qrs_address - qrs_base
            offset = self.qrs_address - qrs_base
            bounds = inner["bounds"]
            extent = (bounds["ite"] - bounds["its"] + 1) * (bounds["kte"] - bounds["kts"] + 1)
            if not base or qrs_base != inner["args"][3] or offset < 0 or offset % 4 or offset // 4 >= extent:
                raise RuntimeError("invalid_source_watch_mapping")
            STATE["source_address"] = address
            bp = SourceWatchpoint(address)
            STATE["watchpoints"].append(bp)
            b_base = unpack_u64(rbx + 0xb0)
            if b_base + offset != STATE["b_address"]:
                raise RuntimeError("b_mapping_mismatch_at_source_arm")
            event = {"role": "arm", "target": self.target, "pc_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "address_hex": hex(address), "source_base_hex": hex(base),
                     "qrs_base_hex": hex(qrs_base), "qrs_address_hex": hex(self.qrs_address),
                     "source": raw_float(address), "frame_rbx_hex": hex(rbx),
                     "frame_rbx_raw_hex": read_bytes(rbx, 0x960).hex(),
                     "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True)}
            stamp(event, inner)
            STATE["record"]["source_events"].append(event)
            save_record()
            self.enabled = False
            return False
        except Exception as exc:
            save_failure("source_arm", repr(exc)); return True

class SourceWriterBreakpoint(gdb.Breakpoint):
    def __init__(self, pc, role, target):
        super().__init__("*" + hex(pc), internal=True)
        self.role, self.target = role, target
    def stop(self):
        try:
            address = STATE["source_address"]
            if address is None:
                return False
            rbx = int(gdb.parse_and_eval("$rbx"))
            base = unpack_u64(rbx + 0x180) if self.role.startswith("before_") or self.role == "after_frame_store_2fb" else int(gdb.parse_and_eval("$rax"))
            dest = base + 4 * int(gdb.parse_and_eval("$r15"))
            if dest != address:
                return False
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or inner["watch_point"]["label"] != self.target:
                raise RuntimeError("source_writer_target_context_mismatch")
            rbx = int(gdb.parse_and_eval("$rbx"))
            regs = {}
            for name in ("xmm%d" % n for n in range(16)):
                bits = int(gdb.parse_and_eval("$%s.v4_int32[0]" % name)) & 0xffffffff
                raw = struct.pack("<I", bits); value = struct.unpack("<f", raw)[0]
                regs[name] = {"raw_hex": raw.hex(), "value_f32": value if math.isfinite(value) else None}
            event = {"role": self.role, "target": self.target, "pc_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "address_hex": hex(address), "source": raw_float(address),
                     "frame_rbx_hex": hex(rbx), "frame_rbx_raw_hex": read_bytes(rbx, 0x960).hex(),
                     "scalar_registers": regs, "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True),
                     "operands": {"frame_0x18": raw_float(rbx + 0x18), "frame_0x140": raw_float(rbx + 0x140), "constant_34bbaf4": raw_float(0x34bbaf4), "array_0x120": raw_float(unpack_u64(rbx + 0x120) + 4 * int(gdb.parse_and_eval("$r15"))), "array_0xb0": raw_float(unpack_u64(rbx + 0xb0) + 4 * int(gdb.parse_and_eval("$r15")))},
                     "backtrace": gdb.execute("bt", to_string=True),
                     "values": inner_values_at(inner["args"], inner["watch_point"], inner["bounds"])}
            stamp(event, inner); STATE["record"]["source_events"].append(event); save_record()
            return False
        except Exception as exc:
            save_failure("source_writer", repr(exc)); return True

class SourceWatchpoint(gdb.Breakpoint):
    def __init__(self, address):
        super().__init__("*(unsigned int *)" + hex(address), gdb.BP_WATCHPOINT, wp_class=gdb.WP_ACCESS, internal=False)
        self.address = address
        self.last = raw_float(address)
        info = gdb.execute("info breakpoints %d" % self.number, to_string=True).lower()
        if "acc watchpoint" not in info or self.type != gdb.BP_ACCESS_WATCHPOINT:
            self.delete(); raise RuntimeError("source_watch_not_hardware:" + info)
    def stop(self):
        try:
            inner = STATE["current_inner"]
            if not inner or not inner["watch_point"] or self.address != STATE["source_address"]:
                raise RuntimeError("source_watch_without_active_target_or_address")
            after = raw_float(self.address)
            event = {"role": "watch_access", "target": inner["watch_point"]["label"],
                     "pc_after_write_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "address_hex": hex(self.address), "before": self.last, "after": after,
                     "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True),
                     "instructions_near_pc": gdb.execute("x/8i $pc-16", to_string=True),
                     "backtrace": gdb.execute("bt", to_string=True)}
            stamp(event, inner); STATE["record"]["source_events"].append(event)
            self.last = after; save_record(); return False
        except Exception as exc:
            save_failure("source_watch", repr(exc)); return True

class PreclampBreakpoint(gdb.Breakpoint):
    def __init__(self, pc, role, target, address):
        super().__init__("*" + hex(pc), internal=True)
        self.condition = "(unsigned long)$r12 + 4 * (unsigned long)$r8 == %d" % address
        self.role, self.target, self.address = role, target, address
    def stop(self):
        try:
            destination = int(gdb.parse_and_eval("$r12")) + 4 * int(gdb.parse_and_eval("$r8"))
            if destination != self.address:
                return False
            inner = STATE["current_inner"]
            if not inner or inner["watch_point"]["label"] != self.target:
                raise RuntimeError("preclamp_target_context_mismatch")
            registers = {}
            for name in ("xmm2", "xmm6", "xmm7", "xmm9", "xmm10", "xmm14", "xmm15"):
                bits = int(gdb.parse_and_eval("$%s.v4_int32[0]" % name)) & 0xffffffff
                raw = struct.pack("<I", bits)
                value = struct.unpack("<f", raw)[0]
                registers[name] = {"raw_hex": raw.hex(), "value_f32": value if math.isfinite(value) else None, "finite": math.isfinite(value)}
            rbx = int(gdb.parse_and_eval("$rbx"))
            event = {"target": self.target, "role": self.role, "pc_hex": hex(int(gdb.parse_and_eval("$pc"))),
                     "rank": RANK, "pid": gdb.selected_inferior().pid,
                     "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True),
                     "scalar_registers": registers, "backtrace": gdb.execute("bt", to_string=True),
                     "instructions": gdb.execute("x/20i 0x25f4dff", to_string=True),
                     "frame_rbx_hex": hex(rbx), "frame_rbx_raw_hex": read_bytes(rbx, 0x500).hex(),
                     "qrs_address_hex": hex(self.address),
                     "values": inner_values_at(inner["args"], inner["watch_point"], inner["bounds"])}
            stamp(event, inner)
            STATE["record"]["preclamp_events"].append(event)
            save_record()
            return False
        except Exception as exc:
            save_failure("preclamp_breakpoint", repr(exc))
            return True

class ProducerBreakpoint(gdb.Breakpoint):
    def __init__(self, pc, role, target, address):
        super().__init__("*" + hex(pc), internal=True)
        self.role, self.target, self.address = role, target, address
        self.condition = "*(unsigned long *)($rbx+0x18) + 4 * (unsigned long)$r8 == %d" % address
    def stop(self):
        try:
            rbx = int(gdb.parse_and_eval("$rbx"))
            index = int(gdb.parse_and_eval("$r8"))
            destination_base = unpack_u64(rbx + 0x18)
            destination = destination_base + 4 * index
            # Python breakpoint callbacks can run regardless of GDB condition.
            if destination != self.address:
                return False
            inner = STATE["current_inner"]
            if not inner or inner["watch_point"]["label"] != self.target:
                raise RuntimeError("producer_target_context_mismatch")
            source_base = unpack_u64(rbx + 0xc0)
            source_address = source_base + 4 * index
            regs = {}
            for name in ("xmm%d" % n for n in range(16)):
                bits = int(gdb.parse_and_eval("$%s.v4_int32[0]" % name)) & 0xffffffff
                raw = struct.pack("<I", bits)
                value = struct.unpack("<f", raw)[0]
                regs[name] = {"raw_hex": raw.hex(), "value_f32": value if math.isfinite(value) else None, "finite": math.isfinite(value)}
            event = {"target": self.target, "role": self.role,
                "pc_hex": hex(int(gdb.parse_and_eval("$pc"))), "rank": RANK,
                "pid": gdb.selected_inferior().pid, "inner_event_id": inner["record"]["event_id"],
                "qrs_address_hex": hex(self.address), "qrs_base_hex": hex(destination_base),
                "index_r8": index, "frame_rbx_hex": hex(rbx),
                "frame_rbx_raw_hex": read_bytes(rbx, 0x500).hex(),
                "source_base_hex": hex(source_base), "source": raw_float(source_address),
                "frame_scale_0x140": raw_float(rbx + 0x140),
                "scalar_registers": regs, "registers_at_breakpoint": gdb.execute("info all-registers", to_string=True),
                "backtrace": gdb.execute("bt", to_string=True),
                "values": inner_values_at(inner["args"], inner["watch_point"], inner["bounds"])}
            if self.role == "before_load" and source_address != STATE["source_address"]:
                raise RuntimeError("source_address_mismatch_at_load")
            stamp(event, inner)
            STATE["record"]["producer_events"].append(event)
            save_record()
            return False
        except Exception as exc:
            save_failure("producer_breakpoint", repr(exc))
            return True

class Watchpoint(gdb.Breakpoint):
    def __init__(self, expression, field_name, watched_address):
        super().__init__(expression, gdb.BP_WATCHPOINT,
                         wp_class=gdb.WP_WRITE, internal=False)
        self.field_name = field_name
        self.watched_address = watched_address
        info = gdb.execute("info breakpoints %d" % self.number, to_string=True).lower()
        hardware_type = getattr(gdb, "BP_HARDWARE_WATCHPOINT", None)
        if self.type not in (gdb.BP_WATCHPOINT, hardware_type) or ("hardware watchpoint" not in info and "hw watchpoint" not in info):
            self.delete()
            raise RuntimeError("gdb_did_not_report_hardware_watchpoint")
    def stop(self):
        try:
            return watch_event(self)
        except Exception as exc:
            save_failure("watchpoint", repr(exc))
            return True

class InnerReturnBreakpoint(gdb.Breakpoint):
    def __init__(self, address):
        super().__init__("*" + hex(address), internal=True)
    def stop(self):
        if STATE["current_inner"] is None:
            return False
        try:
            return capture_inner_return()
        except Exception as exc:
            save_failure("inner_return", repr(exc))
            return True

class InnerEntryBreakpoint(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*" + hex(INNER_ENTRY_PC), internal=True)
    def stop(self):
        try:
            capture_inner_entry()
            return False
        except Exception as exc:
            save_failure("inner_entry", repr(exc))
            return True

def capture_inner_entry():
    pc = int(gdb.parse_and_eval("$pc"))
    rsp = int(gdb.parse_and_eval("$rsp"))
    regs = {name: int(gdb.parse_and_eval("$" + name)) for name in INNER_REGS}
    args = read_pointer_args(regs, rsp, 62)
    null_positions = [n for n, pointer in enumerate(args, 1) if pointer == 0]
    STATE["failure_details"] = {"inner_argument_count": len(args),
        "inner_argument_pointers_hex": [hex(pointer) for pointer in args],
        "inner_null_argument_positions": null_positions,
        "nullable_positions_allowed": sorted(NULLABLE_INNER_POSITIONS),
        "caller_stack_offsets_for_args_59_62": [416, 424, 432, 440],
        "callee_stack_offsets_for_args_59_62": [424, 432, 440, 448]}
    if any(position not in NULLABLE_INNER_POSITIONS for position in null_positions):
        raise RuntimeError("inner_null_pointer_outside_binary_confirmed_nullable_slots:" + repr(null_positions))
    required_positions = set(range(1, 7)) | {45, 46, 49, 50, 51, 52, 53, 54, 55, 56}
    missing_required = sorted(position for position in required_positions if args[position - 1] == 0)
    if missing_required:
        raise RuntimeError("inner_required_pointer_null:" + repr(missing_required))
    values = inner_arg_values(args)
    expected_return = unpack_u64(rsp)
    if pc != INNER_ENTRY_PC or expected_return != INNER_RETURN_PC:
        raise RuntimeError("inner_pc_or_return_mismatch:%s:%s" % (hex(pc), hex(expected_return)))
    for name in ("ims", "ime", "kms", "kme", "its", "ite", "kts", "kte"):
        if values[name] < -10000 or values[name] > 100000:
            raise RuntimeError("implausible_inner_bound:" + name)
    for name in ("jts", "jte"):
        if values[name] < -10000 or values[name] > 100000:
            raise RuntimeError("implausible_inner_bound:" + name)
    if values["ite"] < values["its"] or values["kte"] < values["kts"]:
        raise RuntimeError("invalid_inner_tile_bounds")
    if not (values["ims"] <= values["its"] <= values["ite"] <= values["ime"] and
            values["kms"] <= values["kts"] <= values["kte"] <= values["kme"]):
        raise RuntimeError("inner_tile_outside_memory_bounds")
    if STATE["record"] is None or STATE["record"].get("outer") is None:
        return
    current_j, row_stride = derive_current_j(args, values)
    values["current_j_from_q_pointer"] = current_j
    values["q_row_stride_bytes"] = row_stride
    q_row_delta = args[1] - STATE["outer_args"][ARG_NAMES.index("q")]
    points = target_points_for_j(current_j, values)
    if not points:
        return
    inner_record = {"event_id": len(STATE["record"]["inner"]) + 1,
        "rank": RANK, "pid": gdb.selected_inferior().pid,
        "entry_pc": hex(pc), "return_pc": hex(expected_return),
        "rsp_hex": hex(rsp), "registers_hex": {k: hex(v) for k, v in regs.items()},
        "argument_count": len(args), "argument_pointers_hex": [hex(v) for v in args],
        "null_argument_positions": null_positions,
        "stack_hex_from_rsp": read_bytes(rsp, 8 * 58).hex(),
        "callsite_pc": hex(INNER_CALL_PC),
        "candidate_bounds": values, "candidate_labels_are_source_derived": True,
        "unavailable_argument_positions": values["unavailable_argument_positions"],
        "current_j_provenance": {"method": "inner_q_pointer_minus_outer_q_base_divided_by_outer_memory_row_stride",
            "inner_q_pointer_hex": hex(args[1]),
            "outer_q_base_pointer_hex": hex(STATE["outer_args"][ARG_NAMES.index("q")]),
            "byte_delta": q_row_delta, "row_stride_bytes": row_stride,
            "derived_current_j": current_j},
        "nullable_pointer_positions": null_positions,
        "backtrace": gdb.execute("bt", to_string=True),
        "points": [], "return": None, "watch_target": None}
    watch_point = None
    for point in points:
        offset = inner_offset(point, values)
        if not (values["its"] <= point["i"] <= values["ite"] and values["kts"] <= point["k"] <= values["kte"]):
            raise RuntimeError("inner_selected_point_outside_tile:" + point["label"])
        if point["j"] != current_j:
            raise RuntimeError("selected_point_j_differs_from_q_row:" + point["label"])
        mapping = verify_inner_mapping(point, args, values, offset, current_j)
        inner_record["points"].append({"label": point["label"], "i": point["i"],
            "j": point["j"], "k": point["k"], "entry": inner_values_at(args, point, values),
            "entry_mapping_checks": mapping})
        if point.get("label") in WATCH_TARGET_RANK:
            if RANK != WATCH_TARGET_RANK[point["label"]]:
                raise RuntimeError("watch_target_wrong_owner_rank:" + point["label"])
            watch_point = point
    stamp(inner_record)
    inner_record["inner_call_id"] = inner_record["event_id"]
    inner_record["selected_inner_id"] = inner_record["event_id"]
    STATE["record"]["inner"].append(inner_record)
    STATE["current_inner"] = {"record": inner_record, "args": args,
        "bounds": values, "watch_point": watch_point,
        "last_values": inner_values_at(args, watch_point, values) if watch_point else None}
    if watch_point is not None:
        offset = inner_offset(watch_point, values)
        setup_watchpoints(watch_point["label"], args, watch_point, values, offset)
        inner_record["watch_target"] = watch_point["label"]
    save_record()

def capture_inner_return():
    inner = STATE["current_inner"]
    if inner is None:
        raise RuntimeError("inner_return_without_matching_entry")
    actual_pc = int(gdb.parse_and_eval("$pc"))
    if actual_pc != INNER_RETURN_PC:
        raise RuntimeError("inner_return_pc_mismatch:" + hex(actual_pc))
    record = inner["record"]
    return_points = [{"label": x["label"], "i": x["i"], "j": x["j"], "k": x["k"]}
                     for x in record["points"]]
    record["return"] = {"pc": hex(actual_pc),
        "backtrace": gdb.execute("bt", to_string=True),
        "points": [{"label": p["label"], "values": inner_values_at(inner["args"], p, inner["bounds"])}
                   for p in return_points]}
    stamp(record["return"], inner)
    target_label = inner["watch_point"]["label"] if inner["watch_point"] else None
    target_events = [event for event in STATE["record"]["write_events"] if event["target"] == target_label]
    record["watch_event_count"] = len(target_events)
    record["first_qrs_watch_event"] = next((event["ordinal"] for event in target_events if event["field"] == "qrs"), None)
    if inner["watch_point"] is not None:
        entry_values = next(point["entry"] for point in record["points"]
                            if point["label"] == target_label)
        return_values = next(point["values"] for point in record["return"]["points"]
                             if point["label"] == target_label)
        for field in WATCH_FIELDS:
            if entry_values[field]["raw_hex"] != return_values[field]["raw_hex"] and not any(event["field"] == field for event in target_events):
                raise RuntimeError("watched_value_changed_without_event:" + field + ":" + target_label)
    delete_watchpoints()
    STATE["current_inner"] = None
    STATE["source_address"] = None
    STATE["b_address"] = None
    save_record()
    return False

class OuterReturnBreakpoint(gdb.Breakpoint):
    def __init__(self, address):
        super().__init__("*" + hex(address), temporary=True, internal=True)
    def stop(self):
        try:
            return capture_outer_return()
        except Exception as exc:
            save_failure("outer_return", repr(exc))
            return True

class OuterEntryBreakpoint(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*" + hex(OUTER_ENTRY_PC), internal=True)
    def stop(self):
        try:
            capture_outer_entry()
            return False
        except Exception as exc:
            save_failure("outer_entry", repr(exc))
            return True

def capture_outer_entry():
    if STATE["outer_call"] != 0:
        raise RuntimeError("unexpected_second_outer_kdm6_call")
    pc = int(gdb.parse_and_eval("$pc"))
    args, regs, rsp = outer_args_at_entry()
    domain = bounds_from_args(args, ("ids", "ide", "jds", "jde", "kds", "kde"))
    bounds = bounds_from_args(args, ("ims", "ime", "jms", "jme", "kms", "kme"))
    tile = bounds_from_args(args, ("its", "ite", "jts", "jte", "kts", "kte"))
    nx, nj, nk = bounds["ime"]-bounds["ims"]+1, bounds["jme"]-bounds["jms"]+1, bounds["kme"]-bounds["kms"]+1
    if pc != OUTER_ENTRY_PC or any(span <= 0 or span > 1000 for span in (nx, nj, nk)):
        raise RuntimeError("outer_pc_or_extent_invalid")
    if not (bounds["ims"] <= tile["its"] <= tile["ite"] <= bounds["ime"] and
            bounds["jms"] <= tile["jts"] <= tile["jte"] <= bounds["jme"] and
            bounds["kms"] <= tile["kts"] <= tile["kte"] <= bounds["kme"]):
        raise RuntimeError("outer_tile_outside_memory_bounds")
    rsp_return = unpack_u64(rsp)
    if rsp_return != OUTER_RETURN_PC:
        raise RuntimeError("outer_caller_return_mismatch:" + hex(rsp_return))
    timestep = unpack_i32(args[ARG_NAMES.index("itimestep")])
    delt = struct.unpack("=f", read_bytes(args[ARG_NAMES.index("delt")], 4))[0]
    if timestep != 1 or delt != 20.0:
        raise RuntimeError("unexpected_first_call_step_or_dt:%s:%s" % (timestep, delt))
    if STATE["record"] is None:
        init_record()
    samples = sample_outer(args, bounds, tile)
    entry = {"pc": hex(pc), "return_pc": hex(rsp_return), "rsp_hex": hex(rsp),
        "backtrace": gdb.execute("bt", to_string=True),
        "registers_hex": {k: hex(v) for k, v in regs.items()},
        "argument_count": len(args), "arguments": [
            {"index": n, "candidate_name": name, "pointer_hex": hex(args[n-1]),
             "location": ("register:"+REG_ARGS[n-1]) if n <= 6 else "stack:+%d" % (8+8*(n-7))}
            for n, name in enumerate(ARG_NAMES, 1)],
        "stack_hex_from_rsp": read_bytes(rsp, 8*73).hex(),
        "domain_bounds": domain, "memory_bounds": bounds, "tile_bounds": tile,
        "scalar_raw4": scalar_snapshot(args), "observed_itimestep": timestep,
        "observed_delt": delt, "samples": samples}
    stamp(entry)
    STATE["record"]["outer"] = {"entry": entry, "return": None}
    STATE["outer_args"] = args
    STATE["outer_bounds"] = bounds
    STATE["outer_domain_bounds"] = domain
    STATE["tile_bounds"] = tile
    STATE["outer_call"] = 1
    save_record()
    OuterReturnBreakpoint(rsp_return)
    print("THERMO_OUTER_ENTRY rank=%s arm=%s step=%d dt=%s selected=%d" % (RANK, ARM, timestep, delt, len(samples)))

def capture_outer_return():
    if STATE["record"] is None or STATE["record"].get("outer") is None:
        raise RuntimeError("outer_return_without_entry")
    pc = int(gdb.parse_and_eval("$pc"))
    if pc != OUTER_RETURN_PC:
        raise RuntimeError("outer_return_pc_mismatch:" + hex(pc))
    samples = sample_outer(STATE["outer_args"], STATE["outer_bounds"], STATE["tile_bounds"])
    STATE["record"]["outer"]["return"] = {"pc": hex(pc),
        "backtrace": gdb.execute("bt", to_string=True), "samples": samples}
    stamp(STATE["record"]["outer"]["return"])
    STATE["record"]["status"] = "first_outer_returned"
    STATE["record"]["finished_unix_ns"] = time.time_ns()
    save_record()
    STATE["success"] = peer_wait_complete()
    print("THERMO_OUTER_RETURN rank=%s arm=%s status=%s" % (RANK, ARM, STATE["record"]["status"]))
    return True

def peer_wait_complete():
    deadline = time.time() + float(os.environ.get("CP02_PEER_WAIT_SECONDS", "120"))
    expected = {str(n) for n in range(EXPECTED_RANKS)}
    while time.time() < deadline:
        failures = glob.glob(os.path.join(OUT, "failed_%s_rank*.json" % STAGE))
        if failures:
            save_failure("peer_failure", failures[0])
            return False
        records = {}
        for path in glob.glob(os.path.join(OUT, "raw_%s_rank*_pid*.json" % STAGE)):
            try:
                with open(path, encoding="utf-8") as stream:
                    record = json.load(stream)
                rank = str(record.get("rank"))
                if rank in records:
                    save_failure("peer_duplicate_rank", "multiple_raw_records_for_rank=" + rank)
                    return False
                records[rank] = record
            except (OSError, ValueError):
                continue
        if set(records) == expected and all(r.get("status") in ("first_outer_returned", "all_ranks_settled") for r in records.values()):
            if any(r.get("stage_context_sha256") != CONTEXT_SHA256 or
                   r.get("binary_sha256") != EXPECTED_BINARY_SHA256 or
                   r.get("helper_sha256") != EXPECTED_SCRIPT_SHA256 or
                   r.get("selection_sha256") != EXPECTED_SELECTION_SHA256 or
                   r.get("run_receipt_sha256") != CONTEXT["run_receipt_sha256"] for r in records.values()):
                save_failure("peer_hash_binding", "peer_record_hash_binding_mismatch")
                return False
            entry_counts = {label: 0 for label in TARGET_LABELS}
            return_counts = {label: 0 for label in TARGET_LABELS}
            watch_target_counts = {label: 0 for label in WATCH_TARGET_RANK}
            for r in records.values():
                for event in r.get("inner", []):
                    if event.get("watch_target") in watch_target_counts:
                        watch_target_counts[event["watch_target"]] += 1
                    for point in event.get("points", []):
                        entry_counts[point["label"]] += 1
                    for point in (event.get("return") or {}).get("points", []):
                        return_counts[point["label"]] += 1
            if any(entry_counts[label] != 1 or return_counts[label] != 1 for label in TARGET_LABELS):
                save_failure("peer_target_coverage", "inner_target_entry_return_counts=" + repr((entry_counts, return_counts)))
                return False
            if any(watch_target_counts[label] != 1 for label in WATCH_TARGET_RANK):
                save_failure("peer_watch_target_coverage", "watch_target_counts=" + repr(watch_target_counts))
                return False
            if STATE["record"]["status"] != "all_ranks_settled":
                STATE["record"]["status"] = "all_ranks_settled"
                STATE["record"]["settled_rank_count"] = EXPECTED_RANKS
                save_record()
            # Do not quit/MPI-abort while another rank is still saving its acknowledgement.
            if all(r.get("status") == "all_ranks_settled" for r in records.values()):
                return True
        time.sleep(0.1)
    save_failure("peer_wait_timeout", "missing_or_incomplete_ranks=" + repr(sorted(expected-set(records))))
    return False

try:
    if not os.path.isdir(OUT):
        raise RuntimeError("capture_stage_directory_missing")
    if len(ARG_NAMES) != 77:
        raise RuntimeError("outer_abi_name_count_mismatch")
    load_contract()
except Exception as exc:
    save_failure("preflight", repr(exc))
    raise

# Count every breakpoint callback, including callbacks rejected by target guards.
def count_callbacks(method):
    def counted(self):
        STATE["callback_ordinal"] += 1
        return method(self)
    return counted

for breakpoint_class in (OuterEntryBreakpoint, OuterReturnBreakpoint, InnerEntryBreakpoint,
                         InnerReturnBreakpoint, SourceArmBreakpoint, SourceWriterBreakpoint,
                         SourceWatchpoint, BArmBreakpoint, BWatchpoint, CandidateBreakpoint, PreclampBreakpoint,
                         ProducerBreakpoint, Watchpoint):
    breakpoint_class.stop = count_callbacks(breakpoint_class.stop)

OuterEntryBreakpoint()
InnerEntryBreakpoint()
InnerReturnBreakpoint(INNER_RETURN_PC)
end

run

python
if not STATE.get("success"):
    if STATE.get("failure") is None:
        save_failure("incomplete_run", "GDB ended before all expected ranks completed first KDM6 return")
gdb.execute("quit 0" if STATE.get("success") else "quit 1")
end
