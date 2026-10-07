#!/usr/bin/env python3
"""Build an isolated PR69 dual-density source copy from the retained PR67 KDM6."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SELECTED_SHA256 = "9efc09257a46102073b6d5a3d7cd12eb9ecd485526bc6e9cb349e4b2b037680d"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact source anchor, found {count}")
    return source.replace(old, new, 1)


def density_role(line: str) -> tuple[str, str]:
    code = line.split("!", 1)[0].lower()
    if "den(i,k)" not in code:
        raise ValueError("line has no direct DEN(i,k) use")
    if "venfac(" in code:
        return "moist_gas_ventilation", "retain moist DEN"
    if "xka(" in code:
        return "thermal_conductivity_density_cancels", "retain moist DEN"
    if "viscos(" in code:
        return "dynamic_viscosity", "retain moist DEN"
    if "qi0 =" in code:
        return "unresolved_ice_threshold", "retain moist DEN pending equation units"
    if "diffac(" in code:
        return "growth_latent_carrier", "use dry carrier"
    carrier_markers = (
        "dend(", "den_tmp(", "lamdac(", "rslopec(", "lamdr_tmp(", "lamdc_tmp(",
        "lamdi_tmp(", "nrs(", "nci(", "pinuc =", "pfrzdtc =", "pfrzdtr =",
        "lencon", "nraut(", "pracw(", "praci(", "piacr(", "psaci(", "pgaci(",
        "pracs(", "psacr(", "pgacr(", "nmul", "pinud(", "ninud(", "nsaut(",
        "pcact(", "precs2", "precg2", "qrs(i,k,1)", "qci(i,k,1)",
        "qci(i,k,2)", "/(4*den(i,k))", "(3.*den(i,k))",
    )
    if any(marker in code for marker in carrier_markers):
        return "dry_mass_number_carrier", "use dry carrier"
    raise ValueError(f"unclassified density equation: {line.strip()}")


def inventory_density_uses(source: str) -> list[dict[str, object]]:
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lower().startswith("   subroutine kdm62d("))
    end = next(i for i in range(start + 1, len(lines)) if "end subroutine kdm62d" in lines[i].lower())
    records = []
    for index in range(start, end):
        code = lines[index].split("!", 1)[0].lower()
        if "den(i,k)" not in code:
            continue
        role, action = density_role(lines[index])
        records.append(
            {
                "source_line": index + 1,
                "role": role,
                "action": action,
                "density_references": code.count("den(i,k)"),
                "source": lines[index].strip(),
            }
        )
    if not records:
        raise SystemExit("selected KDM2D source has no mapped DEN(i,k) sites")
    return records


def route_density_uses(body: str, expected_inventory: list[dict[str, object]]) -> tuple[str, dict[str, int]]:
    lines = body.splitlines(keepends=True)
    actual: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        code = line.split("!", 1)[0].lower()
        if "den(i,k)" not in code:
            continue
        role, action = density_role(line)
        actual.append((index, role, action, code.count("den(i,k)")))
    expected_counts: dict[str, int] = {}
    for record in expected_inventory:
        role = str(record["role"])
        expected_counts[role] = expected_counts.get(role, 0) + int(record["density_references"])
    actual_counts: dict[str, int] = {}
    for _, role, _, references in actual:
        actual_counts[role] = actual_counts.get(role, 0) + references
    if actual_counts != expected_counts:
        raise SystemExit(f"selected DEN role count drift: expected {expected_counts}, saw {actual_counts}")
    for index, role, action, _ in reversed(actual):
        if action == "use dry carrier":
            lines[index] = lines[index].replace("den(i,k)", "den_carrier(i,k)")
    return "".join(lines), actual_counts


def transform(source: str) -> tuple[str, list[dict[str, object]], dict[str, int]]:
    density_inventory = inventory_density_uses(source)
    density_counts: dict[str, int] = {}
    source = replace_once(
        source,
        "   use module_mp_radar\n",
        "   use module_mp_radar\n   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n",
        "IEEE import",
    )
    helpers = '''
    pure elemental subroutine moist_to_dry_density(total_density, vapor_mixing_ratio, dry_density, valid)
      real, intent(in) :: total_density, vapor_mixing_ratio
      real, intent(out) :: dry_density
      logical, intent(out) :: valid
      dry_density = 0.0
      valid = .false.
      if (.not. ieee_is_finite(total_density) .or. .not. ieee_is_finite(vapor_mixing_ratio)) return
      if (total_density <= 0.0 .or. vapor_mixing_ratio < 0.0) return
      dry_density = total_density / (1.0 + vapor_mixing_ratio)
      valid = ieee_is_finite(dry_density) .and. dry_density > 0.0
    end subroutine moist_to_dry_density

    pure elemental subroutine specific_number_to_volume(number_per_kg, dry_density, number_per_m3, valid)
      real, intent(in) :: number_per_kg, dry_density
      real, intent(out) :: number_per_m3
      logical, intent(out) :: valid
      number_per_m3 = 0.0
      valid = .false.
      if (.not. ieee_is_finite(number_per_kg) .or. .not. ieee_is_finite(dry_density)) return
      if (number_per_kg < 0.0 .or. dry_density <= 0.0) return
      if (dry_density > 1.0) then
        if (number_per_kg > huge(number_per_kg) / dry_density) return
      end if
      number_per_m3 = number_per_kg * dry_density
      valid = ieee_is_finite(number_per_m3)
      if (number_per_kg > 0.0 .and. number_per_m3 == 0.0) valid = .false.
    end subroutine specific_number_to_volume

    pure elemental subroutine volume_number_to_specific(number_per_m3, dry_density, number_per_kg, valid)
      real, intent(in) :: number_per_m3, dry_density
      real, intent(out) :: number_per_kg
      logical, intent(out) :: valid
      number_per_kg = 0.0
      valid = .false.
      if (.not. ieee_is_finite(number_per_m3) .or. .not. ieee_is_finite(dry_density)) return
      if (number_per_m3 < 0.0 .or. dry_density <= 0.0) return
      if (dry_density < 1.0) then
        if (number_per_m3 > huge(number_per_m3) * dry_density) return
      end if
      number_per_kg = number_per_m3 / dry_density
      valid = ieee_is_finite(number_per_kg)
      if (number_per_m3 > 0.0 .and. number_per_kg == 0.0) valid = .false.
    end subroutine volume_number_to_specific
'''
    source = replace_once(source, "    contains\n", "    contains\n" + helpers, "unit helpers")

    source = replace_once(
        source,
        "   real, dimension(kts:kte) :: re_qc, re_qi, re_qs\n",
        "   real, dimension(kts:kte) :: re_qc, re_qi, re_qs\n"
        "   real, dimension(ims:ime,kms:kme) :: dry_density\n"
        "   real :: number_value\n"
        "   logical :: number_valid\n",
        "wrapper locals",
    )

    input_old = '''         t(i,k) = th(i,k,j)*pii(i,k,j)
         qci(i,k,1) = qc(i,k,j)
         qci(i,k,2) = qi(i,k,j)
         qrs(i,k,1) = qr(i,k,j)
         qrs(i,k,2) = qs(i,k,j)
         qrs(i,k,3) = qg(i,k,j)
         nci(i,k,1) = nc(i,k,j)
         nci(i,k,2) = ni(i,k,j)
         nci(i,k,3) = nn(i,k,j)
         nrs(i,k,1) = nr(i,k,j)     '''
    input_new = '''         t(i,k) = th(i,k,j)*pii(i,k,j)
         call moist_to_dry_density(den(i,k,j), q(i,k,j), dry_density(i,k), number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid moist-to-dry density'
         qci(i,k,1) = qc(i,k,j)
         qci(i,k,2) = qi(i,k,j)
         qrs(i,k,1) = qr(i,k,j)
         qrs(i,k,2) = qs(i,k,j)
         qrs(i,k,3) = qg(i,k,j)
#ifndef TEST_DIRECT_VOLUME
         call specific_number_to_volume(nc(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NC number basis input'
#else
         number_value = nc(i,k,j)
#endif
         nci(i,k,1) = number_value
#ifndef TEST_DIRECT_VOLUME
         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NI number basis input'
#else
         number_value = ni(i,k,j)
#endif
         nci(i,k,2) = number_value
#ifndef TEST_DIRECT_VOLUME
         call specific_number_to_volume(nn(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NN number basis input'
#else
         number_value = nn(i,k,j)
#endif
         nci(i,k,3) = number_value
#ifndef TEST_DIRECT_VOLUME
         call specific_number_to_volume(nr(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NR number basis input'
#else
         number_value = nr(i,k,j)
#endif
         nrs(i,k,1) = number_value'''
    source = replace_once(source, input_old, input_new, "public number inputs")

    output_old = '''         nr(i,k,j) = nrs(i,k,1)   
         nc(i,k,j) = nci(i,k,1)
         ni(i,k,j) = nci(i,k,2)
         nn(i,k,j) = nci(i,k,3)'''
    output_new = '''#ifndef TEST_DIRECT_VOLUME
         call volume_number_to_specific(nrs(i,k,1), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NR number basis output'
#else
         number_value = nrs(i,k,1)
#endif
         nr(i,k,j) = number_value
#ifndef TEST_DIRECT_VOLUME
         call volume_number_to_specific(nci(i,k,1), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NC number basis output'
#else
         number_value = nci(i,k,1)
#endif
         nc(i,k,j) = number_value
#ifndef TEST_DIRECT_VOLUME
         call volume_number_to_specific(nci(i,k,2), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NI number basis output'
#else
         number_value = nci(i,k,2)
#endif
         ni(i,k,j) = number_value
#ifndef TEST_DIRECT_VOLUME
         call volume_number_to_specific(nci(i,k,3), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NN number basis output'
#else
         number_value = nci(i,k,3)
#endif
         nn(i,k,j) = number_value'''
    source = replace_once(source, output_old, output_new, "public number outputs")

    source = replace_once(source, "           den1d(k)= den(i,k,j)\n", "           den1d(k)= dry_density(i,k)\n", "radius density")
    source = replace_once(source, "           nc1d(k) = nc(i,k,j)\n", "           nc1d(k) = nci(i,k,1)/dry_density(i,k)\n", "cloud radius number")
    source = replace_once(source, "           ni1d(k) = ni(i,k,j)\n", "           ni1d(k) = nci(i,k,2)/dry_density(i,k)\n", "ice radius number")
    source = replace_once(source, "          lamc = (pidnc*nc(k)/rqc(k))**(1./xbm_r)", "          lamc = (pidnc*rnc(k)/rqc(k))**(1./xbm_r)", "cloud radius moment")
    source = replace_once(source, "           lami = (pidni*ni(k)/rqi(k))**(1./xbm_i)", "           lami = (pidni*rni(k)/rqi(k))**(1./xbm_i)", "ice radius moment")

    begin = source.lower().index("   subroutine kdm62d(")
    finish = source.lower().index("   end subroutine kdm62d", begin)
    body = source[begin:finish]
    body, density_counts = route_density_uses(body, density_inventory)
    body = replace_once(
        body,
        "   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp\n",
        "   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp, den_carrier\n"
        "   logical :: carrier_valid\n",
        "carrier array",
    )
    old_dend = '''   do k = kts,kte
     do i = its,ite
       dend(i,k) = den(i,k)
     enddo
   enddo'''
    new_dend = '''! PR69 research split: DEN remains moist gas density; dry carrier follows Q and number moments.
   do k = kts,kte
     do i = its,ite
       call moist_to_dry_density(den(i,k), q(i,k), den_carrier(i,k), carrier_valid)
       if (.not. carrier_valid) error stop 'KDM6 invalid dry carrier density'
       dend(i,k) = den_carrier(i,k)
     enddo
   enddo'''
    body = replace_once(body, old_dend.replace("den(i,k)", "den_carrier(i,k)"), new_dend, "carrier initialization")
    source = source[:begin] + body + source[finish:]
    return source, density_inventory, density_counts


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pr69_transform_selected_kdm6.py INPUT OUTPUT")
    input_path, output_path = map(Path, sys.argv[1:])
    if input_path.resolve() == output_path.resolve():
        raise SystemExit("refusing to overwrite or alias the retained selected source")
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite existing transformed output: {output_path}")
    source_bytes = input_path.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    if digest != SELECTED_SHA256:
        raise SystemExit(f"selected source SHA-256 mismatch: {digest}")
    output, inventory, counts = transform(source_bytes.decode())
    with output_path.open("x") as stream:
        stream.write(output)
    inventory_path = output_path.with_suffix(".density_roles.json")
    with inventory_path.open("x") as stream:
        json.dump({"source_sha256": digest, "role_counts": counts, "uses": inventory}, stream, indent=2)
        stream.write("\n")
    print(f"SOURCE_SHA256 {digest}")
    print(f"TRANSFORMED_SHA256 {hashlib.sha256(output.encode()).hexdigest()}")
    print(f"DENSITY_ROLE_COUNTS {json.dumps(counts, sort_keys=True)}")


if __name__ == "__main__":
    main()
