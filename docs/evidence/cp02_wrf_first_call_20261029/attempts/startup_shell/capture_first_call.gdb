set pagination off
set confirm off
set breakpoint pending off
set print elements 0

python
import json
import os
import struct
import time
import glob
import gdb

ARG_NAMES = """th q qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat xland rain rainncv snow snowncv sr refl_10cm diagflag do_radar_ref graupel graupelncv itimestep has_reqc has_reqi has_reqs re_cloud re_ice re_snow ids ide jds jde kds kde ims ime jms jme kms kme its ite jts jte kts kte""".split()
assert len(ARG_NAMES) == 77
REG_ARGS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
SCALAR_REAL = set(range(18, 42))
SCALAR_INT = {49, 50} | set(range(53, 57)) | set(range(60, 78))
ARRAY_3D = set(range(1, 18)) | {48} | set(range(57, 60))
ARRAY_2D = set(range(42, 48)) | {51, 52}
OUT = os.environ.get("CP02_CAPTURE_DIR", os.getcwd())
os.makedirs(OUT, exist_ok=True)
selection_path = os.environ.get("CP02_SELECTION_JSON")
if selection_path:
    with open(selection_path, encoding="utf-8") as f:
        selection = json.load(f)
    POINTS = selection if isinstance(selection, list) else selection.get("points", [])
else:
    POINTS = []
state = {}

def save_failure(stage, message):
    pid = gdb.selected_inferior().pid
    record = {"status": "failed_" + stage, "rank": rank_name(), "pid": pid,
              "pc": hex(int(gdb.parse_and_eval("$pc"))), "error": str(message),
              "backtrace": gdb.execute("bt", to_string=True)}
    path = os.path.join(OUT, "capture_rank%s_pid%s.failed.json" % (rank_name(), pid))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    print("CP02_KDM6_FAILED stage=%s rank=%s pid=%s file=%s" % (stage, rank_name(), pid, path))
    return record

def rank_name():
    for key in ("PMI_RANK", "PMIX_RANK", "OMPI_COMM_WORLD_RANK", "MPI_LOCALRANKID"):
        if key in os.environ:
            return os.environ[key]
    return "unknown"

def read_bytes(address, count):
    return bytes(gdb.selected_inferior().read_memory(address, count))

def unpack_u64(address):
    return struct.unpack("=Q", read_bytes(address, 8))[0]

def unpack_i32(address):
    return struct.unpack("=i", read_bytes(address, 4))[0]

def array_value(pointer, i, j, k, bounds, is_3d):
    ims, ime, jms, jme, kms, kme = bounds
    if is_3d:
        offset = (i - ims) + (k - kms) * (ime - ims + 1) + (j - jms) * (ime - ims + 1) * (kme - kms + 1)
    else:
        offset = (i - ims) + (j - jms) * (ime - ims + 1)
    raw = read_bytes(pointer + 4 * offset, 4)
    return {"offset_f32": offset, "raw_hex": raw.hex(), "value_f32": struct.unpack("=f", raw)[0]}

def capture_arrays(args, bounds):
    result = []
    ims, ime, jms, jme, kms, kme = bounds
    its, ite, jts, jte, kts, kte = state["tile_bounds"]
    for point in POINTS:
        sample = {"label": point.get("label"), "i_wrf_1based": point["i"], "j_wrf_1based": point["j"], "k_wrf_1based": point.get("k", bounds[4])}
        sample.update({"i": sample["i_wrf_1based"], "j": sample["j_wrf_1based"], "k": sample["k_wrf_1based"]})
        if not (ims <= sample["i"] <= ime and jms <= sample["j"] <= jme and kms <= sample["k"] <= kme):
            sample["status"] = "outside_memory_bounds"
            result.append(sample)
            continue
        if not (its <= sample["i"] <= ite and jts <= sample["j"] <= jte and kts <= sample["k"] <= kte):
            sample["status"] = "halo_or_not_owned"
            result.append(sample)
            continue
        sample["status"] = "owned_tile"
        values = {}
        for number in sorted(ARRAY_3D | ARRAY_2D):
            values[ARG_NAMES[number - 1]] = array_value(args[number - 1], sample["i"], sample["j"], sample["k"], bounds, number in ARRAY_3D)
        sample["values"] = values
        result.append(sample)
    return result

def capture_entry():
    inf = gdb.selected_inferior()
    pid = inf.pid
    rsp = int(gdb.parse_and_eval("$rsp"))
    regs = {name: int(gdb.parse_and_eval("$" + name)) for name in REG_ARGS}
    args = [regs[name] for name in REG_ARGS]
    args.extend(unpack_u64(rsp + 8 + 8 * n) for n in range(71))
    if len(args) != 77 or any(pointer == 0 for pointer in args):
        print("CP02_KDM6_CAPTURE_ERROR=null_or_wrong_argument_count")
        return False

    bounds_names = ("ims", "ime", "jms", "jme", "kms", "kme")
    tile_names = ("its", "ite", "jts", "jte", "kts", "kte")
    bounds = [unpack_i32(args[ARG_NAMES.index(name)]) for name in bounds_names]
    tile_bounds = [unpack_i32(args[ARG_NAMES.index(name)]) for name in tile_names]
    spans = (bounds[1] - bounds[0] + 1, bounds[3] - bounds[2] + 1, bounds[5] - bounds[4] + 1)
    if any(span <= 0 or span > 1000 for span in spans):
        print("CP02_KDM6_CAPTURE_ERROR=invalid_or_oversized_memory_bounds " + repr(bounds))
        return False
    if any(tile_bounds[n] > tile_bounds[n + 1] for n in (0, 2, 4)):
        print("CP02_KDM6_CAPTURE_ERROR=invalid_tile_bounds " + repr(tile_bounds))
        return False
    if not (bounds[0] <= tile_bounds[0] <= tile_bounds[1] <= bounds[1] and bounds[2] <= tile_bounds[2] <= tile_bounds[3] <= bounds[3] and bounds[4] <= tile_bounds[4] <= tile_bounds[5] <= bounds[5]):
        print("CP02_KDM6_CAPTURE_ERROR=tile_outside_memory_bounds " + repr(tile_bounds))
        return False

    scalar_raw = {}
    for number in sorted(SCALAR_REAL | SCALAR_INT):
        raw = read_bytes(args[number - 1], 4)
        value = struct.unpack("=f" if number in SCALAR_REAL else "=i", raw)[0]
        scalar_raw[ARG_NAMES[number - 1]] = {"arg": number, "raw_hex": raw.hex(), "decoded": value}
    expected_step = int(os.environ.get("CP02_EXPECT_ITIMESTEP", "1"))
    expected_dt = float(os.environ.get("CP02_EXPECT_DT", "20"))
    if scalar_raw["itimestep"]["decoded"] != expected_step or abs(scalar_raw["delt"]["decoded"] - expected_dt) > 1.0e-5:
        print("CP02_KDM6_CAPTURE_ERROR=unexpected_step_or_dt " + repr((scalar_raw["itimestep"]["decoded"], scalar_raw["delt"]["decoded"], expected_step, expected_dt)))
        return False

    maps_path = os.path.join(OUT, "maps_rank%s_pid%s.txt" % (rank_name(), pid))
    try:
        with open("/proc/%d/maps" % pid, encoding="utf-8") as f:
            maps = f.read()
        with open(maps_path, "w", encoding="utf-8") as f:
            f.write(maps)
        maps_error = None
    except OSError as exc:
        maps_path = None
        maps_error = str(exc)

    state.update({"pid": pid, "args": args, "bounds": bounds, "tile_bounds": tile_bounds})
    pc = hex(int(gdb.parse_and_eval("$pc")))
    return_pc = hex(unpack_u64(rsp))
    if pc != "0x25df680" or return_pc != "0x20c3722":
        print("CP02_KDM6_CAPTURE_ERROR=pc_or_caller_return_mismatch " + repr((pc, return_pc)))
        return False
    entry = {
        "rank": rank_name(), "pid": pid, "binary_symbol": "module_mp_kdm6_mp_kdm6_",
        "pc": pc, "return_pc": return_pc,
        "rsp_hex": hex(rsp), "rsp_bytes_hex": read_bytes(rsp, 8).hex(),
        "backtrace": gdb.execute("bt", to_string=True),
        "registers_hex": {k: hex(v) for k, v in regs.items()},
        "argument_count": len(args),
        "arguments": [{"index": n, "name": name, "pointer_hex": hex(args[n - 1]), "location": ("register:" + REG_ARGS[n - 1]) if n <= 6 else "stack:+%d" % (8 + 8 * (n - 7))} for n, name in enumerate(ARG_NAMES, 1)],
        "raw_stack_hex_from_rsp_including_return_and_padding": read_bytes(rsp, 8 * 73).hex(),
        "memory_bounds_ims_ime_jms_jme_kms_kme": dict(zip(bounds_names, bounds)),
        "tile_bounds_its_ite_jts_jte_kts_kte": dict(zip(tile_names, tile_bounds)),
        "scalar_raw4": scalar_raw, "selection_points": POINTS,
        "maps_file": maps_path, "maps_error": maps_error,
        "samples": capture_arrays(args, bounds),
        "source_mapping_status": "candidate labels from co-located source; binary has no DWARF; cross-check runtime values"
    }
    state["record"] = {"entry": entry, "return": None}
    state["path"] = os.path.join(OUT, "capture_rank%s_pid%s.json" % (rank_name(), pid))
    with open(state["path"], "w", encoding="utf-8") as f:
        json.dump(state["record"], f, indent=2, sort_keys=True)
    print("CP02_KDM6_ENTRY rank=%s pid=%s args=%d bounds=%s tile=%s points=%d" % (rank_name(), pid, len(args), bounds, tile_bounds, len(POINTS)))
    print("CP02_CAPTURE_FILE=" + state["path"])
    print("CP02_MAPS_FILE=" + str(maps_path))
    return True

def capture_return():
    pc = hex(int(gdb.parse_and_eval("$pc")))
    expected_pc = state["record"]["entry"]["return_pc"]
    if pc != expected_pc:
        state["record"]["status"] = "failed_return_pc_mismatch"
        state["record"]["return"] = {"pc": pc, "expected_pc": expected_pc,
                                      "backtrace": gdb.execute("bt", to_string=True)}
    else:
        state["record"]["status"] = "return_captured"
        state["record"]["return"] = {"pc": pc, "backtrace": gdb.execute("bt", to_string=True),
                                      "samples": capture_arrays(state["args"], state["bounds"])}
    with open(state["path"], "w", encoding="utf-8") as f:
        json.dump(state["record"], f, indent=2, sort_keys=True)
    print("CP02_KDM6_RETURN rank=%s pid=%s pc=%s" % (rank_name(), state["pid"], pc))
    print("CP02_CAPTURE_FILE=" + state["path"])
    expected_ranks = int(os.environ.get("CP02_EXPECT_RANKS", "8"))
    deadline = time.time() + float(os.environ.get("CP02_PEER_WAIT_SECONDS", "60"))
    pending = set(str(n) for n in range(expected_ranks))
    while pending and time.time() < deadline:
        for rank in list(pending):
            files = glob.glob(os.path.join(OUT, "capture_rank%s_pid*.json" % rank))
            failed = glob.glob(os.path.join(OUT, "capture_rank%s_pid*.failed.json" % rank))
            complete = False
            for path in files:
                try:
                    with open(path, encoding="utf-8") as f:
                        complete = json.load(f).get("status") == "return_captured"
                except (OSError, ValueError):
                    complete = False
                if complete:
                    break
            if complete or failed:
                pending.remove(rank)
        if pending:
            time.sleep(0.1)
    if pending:
        print("CP02_KDM6_PEER_WAIT_TIMEOUT missing_or_incomplete_ranks=" + ",".join(sorted(pending)))
    else:
        print("CP02_KDM6_PEERS_SETTLED ranks=%d" % expected_ranks)
    return True

class ReturnBreakpoint(gdb.Breakpoint):
    def __init__(self, address):
        super().__init__("*" + address, temporary=True, internal=True)
    def stop(self):
        try:
            return capture_return()
        except Exception as exc:
            save_failure("return", repr(exc))
            return True

class EntryBreakpoint(gdb.Breakpoint):
    def __init__(self):
        super().__init__("*0x25df680", temporary=False, internal=True)
    def stop(self):
        try:
            ok = capture_entry()
        except Exception as exc:
            save_failure("entry", repr(exc))
            return True
        if not ok:
            save_failure("entry", "ABI or input sanity gate rejected capture")
            return True
        ReturnBreakpoint(state["record"]["entry"]["return_pc"])
        return False

EntryBreakpoint()
end

run
quit
