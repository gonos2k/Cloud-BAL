"""Replay the captured R32/R64 rain diffusion tendency at a failed cell."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct


HELPER_SOURCE = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/"
    "KIM_RDPS_MODL_V2026.2/dyn_em/module_big_step_utilities_em.F"
)
HELPER_ROUTINE_SHA256 = "cbcc347345a6449b9e5666407c5ef8c6a0db73a9a397d0e306ad14a085783ac3"
RAIN_PIDN = 12566.37109375
RAIN_LAMBDA_MIN = 961.0
RAIN_LAMBDA_MAX = 35000.0
RAIN_POWER = 3.0
RAIN_BOUNDS = (
    RAIN_PIDN / RAIN_LAMBDA_MAX**RAIN_POWER,
    RAIN_PIDN / RAIN_LAMBDA_MIN**RAIN_POWER,
)
QR_REGISTRY_INDEX = 4
QNR_REGISTRY_INDEX = 6
_TAGS = {"PR87_RAIN_DIFFUSION_PRE", "PR87_RAIN_DIFFUSION_POST"}
_VALUE_NAMES = (
    "dt_step", "khdq", "tendency", "field_center", "field_xminus", "field_xplus",
    "field_yminus", "field_yplus", "mut_center", "mut_xminus", "mut_xplus",
    "mut_yminus", "mut_yplus", "c1", "c2", "xkmhd_center", "xkmhd_xminus",
    "xkmhd_xplus", "xkmhd_yminus", "xkmhd_yplus", "msfux_xminus", "msfux_center",
    "msfux_xplus", "msfuy_xminus", "msfuy_center", "msfuy_xplus", "msfvx_inv_center",
    "msfvx_inv_yplus", "msfvy_center", "msfvy_yplus", "msftx", "msfty", "rdx", "rdy",
)


def _f32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def _bits32(value: float) -> int:
    return struct.unpack("!I", struct.pack("!f", value))[0]


def _add32(left: float, right: float) -> float:
    return _f32(_f32(left) + _f32(right))


def _sub32(left: float, right: float) -> float:
    return _f32(_f32(left) - _f32(right))


def _mul32(left: float, right: float) -> float:
    return _f32(_f32(left) * _f32(right))


def _div32(left: float, right: float) -> float:
    return _f32(_f32(left) / _f32(right))


def _coefficient32(values: dict[str, float], *, axis: str, plus: bool) -> float:
    if axis == "x":
        if plus:
            factor = _div32(values["msfux_xplus"], values["msfuy_xplus"])
            neighbor_xkmhd, neighbor_mut = values["xkmhd_xplus"], values["mut_xplus"]
        else:
            factor = _div32(values["msfux_center"], values["msfuy_center"])
            neighbor_xkmhd, neighbor_mut = values["xkmhd_xminus"], values["mut_xminus"]
    elif plus:
        factor = _mul32(values["msfvy_yplus"], values["msfvx_inv_yplus"])
        neighbor_xkmhd, neighbor_mut = values["xkmhd_yplus"], values["mut_yplus"]
    else:
        factor = _mul32(values["msfvy_center"], values["msfvx_inv_center"])
        neighbor_xkmhd, neighbor_mut = values["xkmhd_yminus"], values["mut_yminus"]
    xkmhd = _add32(values["xkmhd_center"], neighbor_xkmhd)
    mu = _add32(
        _add32(_mul32(values["c1"], values["mut_center"]), values["c2"]),
        _add32(_mul32(values["c1"], neighbor_mut), values["c2"]),
    )
    half = _f32(0.5)
    spacing = values["rdx"] if axis == "x" else values["rdy"]
    result = _mul32(factor, half)
    result = _mul32(result, xkmhd)
    result = _mul32(result, half)
    result = _mul32(result, mu)
    return _mul32(result, spacing)


def _stencil32(values: dict[str, float]) -> float:
    """Evaluate the helper's `name /= u,v,w` stencil with R32 rounding per op."""
    xminus = _coefficient32(values, axis="x", plus=False)
    xplus = _coefficient32(values, axis="x", plus=True)
    yminus = _coefficient32(values, axis="y", plus=False)
    yplus = _coefficient32(values, axis="y", plus=True)
    mrdx = _mul32(_mul32(values["msftx"], values["msfty"]), values["rdx"])
    mrdy = _mul32(_mul32(values["msftx"], values["msfty"]), values["rdy"])
    xgradient_plus = _sub32(values["field_xplus"], values["field_center"])
    xgradient_minus = _sub32(values["field_center"], values["field_xminus"])
    xflux = _sub32(_mul32(xplus, xgradient_plus), _mul32(xminus, xgradient_minus))
    ygradient_plus = _sub32(values["field_yplus"], values["field_center"])
    ygradient_minus = _sub32(values["field_center"], values["field_yminus"])
    yflux = _sub32(_mul32(yplus, ygradient_plus), _mul32(yminus, ygradient_minus))
    return _add32(_mul32(mrdx, xflux), _mul32(mrdy, yflux))


def _coefficient64(values: dict[str, float], *, axis: str, plus: bool) -> float:
    if axis == "x":
        if plus:
            factor = values["msfux_xplus"] / values["msfuy_xplus"]
            neighbor_xkmhd, neighbor_mut = values["xkmhd_xplus"], values["mut_xplus"]
        else:
            factor = values["msfux_center"] / values["msfuy_center"]
            neighbor_xkmhd, neighbor_mut = values["xkmhd_xminus"], values["mut_xminus"]
    elif plus:
        factor = values["msfvy_yplus"] * values["msfvx_inv_yplus"]
        neighbor_xkmhd, neighbor_mut = values["xkmhd_yplus"], values["mut_yplus"]
    else:
        factor = values["msfvy_center"] * values["msfvx_inv_center"]
        neighbor_xkmhd, neighbor_mut = values["xkmhd_yminus"], values["mut_yminus"]
    xkmhd = values["xkmhd_center"] + neighbor_xkmhd
    mu = ((values["c1"] * values["mut_center"] + values["c2"]) +
          (values["c1"] * neighbor_mut + values["c2"]))
    spacing = values["rdx"] if axis == "x" else values["rdy"]
    return factor * 0.5 * xkmhd * 0.5 * mu * spacing


def _stencil64(values: dict[str, float]) -> float:
    """Evaluate the same source expression in R64 from exact R32 operands."""
    xminus = _coefficient64(values, axis="x", plus=False)
    xplus = _coefficient64(values, axis="x", plus=True)
    yminus = _coefficient64(values, axis="y", plus=False)
    yplus = _coefficient64(values, axis="y", plus=True)
    mrdx = values["msftx"] * values["msfty"] * values["rdx"]
    mrdy = values["msftx"] * values["msfty"] * values["rdy"]
    xflux = (xplus * (values["field_xplus"] - values["field_center"]) -
             xminus * (values["field_center"] - values["field_xminus"]))
    yflux = (yplus * (values["field_yplus"] - values["field_center"]) -
             yminus * (values["field_center"] - values["field_yminus"]))
    return mrdx * xflux + mrdy * yflux


def _parse_probe_lines(lines: list[str], source_name: str = "<memory>") -> list[dict]:
    records = []
    for line_number, line in enumerate(lines, 1):
        fields = line.split()
        if not fields or fields[0] not in _TAGS:
            continue
        if len(fields) != 8 + len(_VALUE_NAMES):
            raise ValueError(
                f"{source_name}:{line_number}: expected {8 + len(_VALUE_NAMES)} fields, got {len(fields)}"
            )
        tag = fields[0]
        rk, registry_index, i, j, k = map(int, fields[1:6])
        moist_step, mix2_off = (value.upper() == "T" for value in fields[6:8])
        try:
            numbers = [_f32(float(value.replace("D", "E").replace("d", "e")))
                       for value in fields[8:]]
        except ValueError as exc:
            raise ValueError(f"{source_name}:{line_number}: invalid numeric field") from exc
        records.append({
            "tag": tag, "rk": rk, "registry_index": registry_index,
            "i": i, "j": j, "k": k, "moist_step": moist_step,
            "mix2_off": mix2_off,
            "values": dict(zip(_VALUE_NAMES, numbers, strict=True)),
            "line_number": line_number,
        })
    return records


def _read_probe_records(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="strict") as stream:
        return _parse_probe_lines(stream.readlines(), str(path))


def _read_probe_records_from_text(source: str) -> list[dict]:
    return _parse_probe_lines(source.splitlines())


def _pair_records(records: list[dict]) -> list[dict]:
    pending: dict[tuple, list[dict]] = {}
    pairs = []
    for record in records:
        key = (record["rk"], record["registry_index"], record["i"], record["j"],
               record["k"], record["moist_step"])
        slot = pending.setdefault(key, [])
        slot.append(record)
        if len(slot) == 2:
            pre, post = slot
            if pre["tag"] != "PR87_RAIN_DIFFUSION_PRE" or post["tag"] != "PR87_RAIN_DIFFUSION_POST":
                raise ValueError(f"unpaired or out-of-order probe records at {key}")
            if pre["mix2_off"] or post["mix2_off"]:
                raise ValueError(f"probe traced disabled diffusion at {key}")
            before, after = pre["values"], post["values"]
            for name in _VALUE_NAMES:
                if name != "tendency" and _bits32(before[name]) != _bits32(after[name]):
                    raise ValueError(f"producer inputs changed across call at {key}: {name}")
            if pre["moist_step"] and pre["registry_index"] == QR_REGISTRY_INDEX:
                species = "QR"
            elif not pre["moist_step"] and pre["registry_index"] == QNR_REGISTRY_INDEX:
                species = "QNR"
            else:
                pending[key] = []
                continue
            delta32 = _stencil32(before)
            replayed_post = _add32(before["tendency"], delta32)
            pairs.append({
                "rk": pre["rk"], "registry_index": pre["registry_index"],
                "species": species,
                "i": pre["i"], "j": pre["j"], "k": pre["k"],
                "line_pre": pre["line_number"], "line_post": post["line_number"],
                "native_delta_r32": delta32,
                "native_post_replay_r32": replayed_post,
                "native_post_logged_r32": after["tendency"],
                "native_post_bit_match": _bits32(replayed_post) == _bits32(after["tendency"]),
                "r64_delta": _stencil64(before),
                "source_values": before,
            })
            pending[key] = []
    leftovers = {key: len(value) for key, value in pending.items() if value}
    if leftovers:
        raise ValueError(f"incomplete pre/post probe records: {leftovers}")
    index_sets: dict[str, set[int]] = {}
    for item in pairs:
        index_sets.setdefault(item["species"], set()).add(item["registry_index"])
    if any(len(indices) != 1 for indices in index_sets.values()):
        raise ValueError("registry index changed within a rain species")
    indices = {species: next(iter(values)) for species, values in index_sets.items()}
    if len(indices) == 2 and indices["QR"] == indices["QNR"]:
        raise ValueError("QR and QNR registry indices unexpectedly match")
    return pairs


def _read_full_rows(path: Path) -> list[list[float]]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", errors="strict") as stream:
        lines = stream.readlines()
    index = 0
    while index < len(lines):
        tokens = lines[index].split()
        index += 1
        if not tokens or tokens[0] != "FULL":
            continue
        values = tokens[1:]
        while len(values) < 20 and index < len(lines):
            values.extend(lines[index].split())
            index += 1
        if len(values) != 20:
            raise ValueError(f"malformed FULL row in {path}")
        rows.append([float(value.replace("D", "E").replace("d", "e")) for value in values])
    return rows


def _find_full_failure(path: Path, pair: dict) -> dict:
    candidates = [row for row in _read_full_rows(path)
                  if int(row[1]) == pair["rk"] and int(row[2]) == 3 and
                  tuple(map(int, row[3:6])) == (pair["i"], pair["j"], pair["k"])]
    if len(candidates) != 1:
        raise ValueError(f"expected one rain FULL row for {pair['i'],pair['j'],pair['k']}, found {len(candidates)}")
    (timestep, rk, pair_index, i, j, k, old_carrier, new_carrier, q_base, n_base,
     q_source, n_source, q_air, n_air, q_cont, n_cont, q_stored, n_stored,
     density, dt) = candidates[0]
    return {
        "timestep": int(timestep), "rk": int(rk), "pair_index": int(pair_index),
        "i": int(i), "j": int(j), "k": int(k),
        "old_carrier": old_carrier, "new_carrier": new_carrier,
        "q_base": q_base, "n_base": n_base, "q_source": q_source, "n_source": n_source,
        "q_air": q_air, "n_air": n_air,
        "q_continuous": q_cont, "n_continuous": n_cont,
        "q_stored": q_stored, "n_stored": n_stored, "dry_density": density,
        "dt": dt,
    }


def _relative_delta(delta64: float, delta32: float) -> float | None:
    scale = max(abs(delta64), abs(delta32))
    return (delta64 - delta32) / scale if scale else 0.0


def replay(stdout: Path, full_failure: Path) -> dict:
    records = _read_probe_records(stdout)
    pairs = _pair_records(records)
    if not pairs:
        raise ValueError("no complete rain diffusion pre/post pairs found")
    # The native updater writes the failure ledger immediately after the failing
    # grouped stage; its coordinates/RK identify the final matching QR/QNR call.
    latest: dict[str, dict] = {}
    for pair in pairs:
        if pair["rk"] == 1 and (pair["i"], pair["j"], pair["k"]) == (110, 5, 18):
            latest[pair["species"]] = pair
    if set(latest) != {"QR", "QNR"}:
        raise ValueError("missing selected QR and QNR records at (110,5,18), RK1")
    selected = []
    source_row = None
    precision_deltas = {}
    for species in ("QR", "QNR"):
        pair = latest[species]
        row = _find_full_failure(full_failure, pair)
        if source_row is None:
            source_row = row
        elif any(source_row[key] != row[key] for key in ("timestep", "old_carrier", "new_carrier", "dry_density")):
            raise ValueError("QR/QNR FULL rows do not share the same timestep/carrier/density")
        values = pair["source_values"]
        delta64 = pair["r64_delta"]
        delta32 = pair["native_delta_r32"]
        if species == "QR":
            source_rate = row["q_source"]
            air_rate = row["q_air"]
        else:
            source_rate = row["n_source"]
            air_rate = row["n_air"]
        post = pair["native_post_logged_r32"]
        precision_deltas[species] = delta64 - delta32
        selected.append({
            "species": species, "registry_index": pair["registry_index"],
            "native_post_bit_match": pair["native_post_bit_match"],
            "native_delta_r32": delta32, "r64_delta": delta64,
            "delta64_over_delta32": delta64 / delta32 if delta32 else None,
            "r64_minus_r32_fraction_of_larger_delta": _relative_delta(delta64, delta32),
            "post_r32": post,
            "full_qn_source_r64": source_rate,
            "full_qn_source_cast_r32": _f32(source_rate),
            "full_source_rate_bit_match": _bits32(post) == _bits32(_f32(source_rate)),
            "air_rate_r64": air_rate,
            "full_qn_source_over_native_delta_r32": source_rate / delta32 if delta32 else None,
            "dt_step": values["dt_step"],
        })
    assert source_row is not None
    dt = latest["QR"]["source_values"]["dt_step"]
    if _bits32(dt) != _bits32(latest["QNR"]["source_values"]["dt_step"]):
        raise ValueError("QR/QNR traces have different timestep values")
    base_q = (source_row["old_carrier"] * source_row["q_base"] +
              dt * (source_row["q_source"] + source_row["q_air"] +
                   precision_deltas["QR"])) / source_row["new_carrier"]
    base_n = (source_row["old_carrier"] * source_row["n_base"] +
              dt * (source_row["n_source"] + source_row["n_air"] +
                   precision_deltas["QNR"])) / source_row["new_carrier"]
    q_ratio = source_row["q_continuous"] / source_row["n_continuous"] if source_row["n_continuous"] else None
    corrected_q_ratio = base_q / base_n if base_n else None
    lower, upper = RAIN_BOUNDS
    return {
        "helper_source_sha256": HELPER_ROUTINE_SHA256,
        "full_failure_timestep": source_row["timestep"],
        "full_failure_cell": [source_row["i"], source_row["j"], source_row["k"]],
        "full_failure_pair": "QR/QNR",
        "registry_indices": {"QR": QR_REGISTRY_INDEX, "QNR": QNR_REGISTRY_INDEX},
        "rain_pair_bounds": {"minimum_q_over_n": lower, "maximum_q_over_n": upper},
        "full_continuous_candidate": [source_row["q_continuous"], source_row["n_continuous"]],
        "full_continuous_q_over_n": q_ratio,
        "full_continuous_candidate_in_strict_cone": (
            q_ratio is not None and lower <= q_ratio <= upper),
        "r64_diffusion_corrected_candidate": [base_q, base_n],
        "r64_diffusion_corrected_q_over_n": corrected_q_ratio,
        "r64_diffusion_corrected_candidate_in_strict_cone": (
            corrected_q_ratio is not None and lower <= corrected_q_ratio <= upper),
        "source_base": [source_row["q_base"], source_row["n_base"]],
        "full_qn_rates": [source_row["q_source"], source_row["n_source"]],
        "probe_replays": selected,
    }


def _procedure_text(source: str) -> str:
    start_marker = "SUBROUTINE horizontal_diffusion ("
    end_marker = "\nEND SUBROUTINE horizontal_diffusion\n"
    start = source.find(start_marker)
    if start < 0:
        raise ValueError("pinned helper source lacks horizontal_diffusion")
    end = source.find(end_marker, start)
    if end < 0:
        raise ValueError("unterminated horizontal_diffusion procedure")
    return source[start:end + len(end_marker) - 1]


def require_helper_source(path: Path = HELPER_SOURCE) -> dict:
    source = path.read_text(encoding="utf-8")
    procedure = _procedure_text(source)
    actual = hashlib.sha256(procedure.encode("utf-8")).hexdigest()
    if actual != HELPER_ROUTINE_SHA256:
        raise ValueError(f"horizontal_diffusion source hash mismatch: {actual}")
    return {"path": str(path), "routine_sha256": actual}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--full-failure", type=Path, required=True)
    parser.add_argument("--helper-source", type=Path, default=HELPER_SOURCE)
    args = parser.parse_args()
    helper = require_helper_source(args.helper_source)
    result = replay(args.stdout, args.full_failure)
    result["helper_source"] = helper
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
