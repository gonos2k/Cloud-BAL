"""Independent checks and conservative transfers for hydrometeor moments.

All mixing ratios and number concentrations use a dry-air basis.  This module
validates supplied fields; it never fills, floors, clips, or mutates them.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np


DRY_AIR_BASIS = "dry_air"
MASS_UNITS = "kg kg-1"
NUMBER_UNITS = "kg-1"
BULK_VOLUME_UNITS = "m3 kg-1"


def _array(value: Any, name: str) -> tuple[np.ndarray | None, str | None]:
    if value is None:
        return None, f"MISSING_FIELD:{name}"
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        return None, f"MASKED_FIELD:{name}"
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError):
        return None, f"NONREAL_FIELD:{name}"
    if not (np.issubdtype(raw.dtype, np.integer)
            or np.issubdtype(raw.dtype, np.floating)):
        return None, f"NONREAL_FIELD:{name}"
    try:
        result = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return None, f"NONREAL_FIELD:{name}"
    if not np.all(np.isfinite(result)):
        return None, f"NONFINITE_FIELD:{name}"
    if np.any(result < 0.0):
        return None, f"NEGATIVE_FIELD:{name}"
    return result, None


def _report(status: str, reason: str, *, valid: bool | None = False,
            violation_count: int = 0, checked_count: int = 0,
            violation_mask: np.ndarray | None = None,
            bound_source: str | None = None,
            uncertainty_description: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "valid": valid,
        "reason": reason,
        "violation_count": violation_count,
        "checked_count": checked_count,
        "violation_mask": violation_mask,
        "mutated_input": False,
        "source_authentication": "NOT_ASSESSED",
        "bound_source": bound_source,
        "uncertainty_description": uncertainty_description,
    }


def _bound_declaration_issue(source: str | None, uncertainty: str | None) -> str | None:
    if source is None or uncertainty is None:
        return "PHYSICAL_BOUND_DECLARATION_MISSING"
    if (not isinstance(source, str) or not source.strip()
            or not isinstance(uncertainty, str) or not uncertainty.strip()):
        return "INVALID_PHYSICAL_BOUND_DECLARATION"
    return None


def _real_scalar(value: Any) -> float | None:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError):
        return None
    if (raw.ndim != 0 or not (np.issubdtype(raw.dtype, np.integer)
                              or np.issubdtype(raw.dtype, np.floating))):
        return None
    converted = float(raw)
    return converted if np.isfinite(converted) else None


def _conservation_error(
    before_terms: np.ndarray,
    after_terms: np.ndarray,
    weights: np.ndarray,
    *,
    donor_count: int,
    target_count: int,
) -> dict[str, float]:
    """Separate arithmetic roundoff from the supplied weight-closure residual."""
    with np.errstate(over="ignore", invalid="ignore"):
        before = float(np.sum(before_terms))
        after = float(np.sum(after_terms))
    if not np.isfinite(before) or not np.isfinite(after):
        raise ValueError("NONFINITE_CONSERVATION_TOTAL")
    epsilon = np.finfo(np.float64).eps
    operations = 2 * donor_count + 2 * target_count + 4
    product = operations * epsilon
    gamma = product / (1.0 - product)
    # Extensive terms are nonnegative. Scale each finite total before adding;
    # their unscaled sum can overflow even when both totals are representable.
    roundoff_bound = gamma * before + gamma * after
    closure = float(np.sum(np.abs(np.sum(weights, axis=0) - 1.0) * np.abs(before_terms)))
    return {
        "before": before,
        "after": after,
        "absolute_difference": abs(after - before),
        "roundoff_bound": roundoff_bound,
        "weight_closure_error": closure,
    }


def validate_mass_number(
    mass: Any,
    number: Any | None,
    *,
    mass_units: str,
    number_units: str,
    mass_basis: str,
    number_basis: str,
    particle_mass_min_kg: float | None,
    particle_mass_max_kg: float | None,
    bound_source: str | None = None,
    uncertainty_description: str | None = None,
) -> dict[str, Any]:
    """Check ``m_min*N <= r <= m_max*N`` for declared dry-air moments.

    ``number=None`` explicitly reports an unsupported number moment.  Bounds
    constrain mean particle mass ``r/N``, not individual particle extrema;
    they are independent declarations, not inferred from the checked fields.
    """
    r, issue = _array(mass, "mass")
    if issue:
        return _report("REJECTED", issue)
    if mass_units != MASS_UNITS or number_units != NUMBER_UNITS:
        return _report("REJECTED", "UNEXPECTED_UNITS")
    if mass_basis != DRY_AIR_BASIS or number_basis != DRY_AIR_BASIS:
        return _report("REJECTED", "BASIS_MISMATCH")
    if r.size == 0:
        return _report("UNSUPPORTED", "EMPTY_VALIDATION_DOMAIN", valid=None)
    if number is None:
        return _report("UNSUPPORTED", "NUMBER_MOMENT_UNSUPPORTED", valid=None)
    n, issue = _array(number, "number")
    if issue:
        return _report("REJECTED", issue)
    if n.shape != r.shape:
        return _report("REJECTED", "SHAPE_MISMATCH")
    issue = _bound_declaration_issue(bound_source, uncertainty_description)
    if issue:
        status = "UNSUPPORTED" if issue == "PHYSICAL_BOUND_DECLARATION_MISSING" else "REJECTED"
        return _report(status, issue, valid=None)
    if particle_mass_min_kg is None or particle_mass_max_kg is None:
        return _report("UNSUPPORTED", "PARTICLE_MASS_BOUNDS_MISSING", valid=None)
    lower_mass = _real_scalar(particle_mass_min_kg)
    upper_mass = _real_scalar(particle_mass_max_kg)
    if lower_mass is None or upper_mass is None or lower_mass <= 0.0 or upper_mass < lower_mass:
        return _report("REJECTED", "INVALID_PARTICLE_MASS_BOUNDS")
    with np.errstate(over="ignore", invalid="ignore"):
        lower = lower_mass * n
        upper = upper_mass * n
    if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
        return _report("REJECTED", "PARTICLE_BOUND_PRODUCT_NONFINITE")
    eps = 16.0 * np.finfo(np.float64).eps
    lower_tolerance = eps * np.maximum(np.abs(r), np.abs(lower))
    upper_tolerance = eps * np.maximum(np.abs(r), np.abs(upper))
    impossible = ((r < lower - lower_tolerance)
                  | (r > upper + upper_tolerance)
                  | ((r == 0.0) & (n > 0.0))
                  | ((n == 0.0) & (r > 0.0)))
    count = int(np.count_nonzero(impossible))
    return _report(
        "FAIL" if count else "PASS_SCOPED",
        "MASS_NUMBER_OUTSIDE_DECLARED_PARTICLE_BOUNDS" if count else "WITHIN_DECLARED_PARTICLE_BOUNDS",
        valid=count == 0,
        violation_count=count,
        checked_count=int(r.size),
        violation_mask=impossible,
        bound_source=bound_source,
        uncertainty_description=uncertainty_description,
    )


def validate_bulk_volume(
    mass: Any,
    bulk_volume: Any | None,
    *,
    mass_units: str,
    volume_units: str,
    mass_basis: str,
    volume_basis: str,
    bulk_density_min_kg_m3: float | None,
    bulk_density_max_kg_m3: float | None,
    bound_source: str | None = None,
    uncertainty_description: str | None = None,
) -> dict[str, Any]:
    """Check ``r/rho_max <= BG <= r/rho_min`` on a dry-air basis."""
    r, issue = _array(mass, "mass")
    if issue:
        return _report("REJECTED", issue)
    if mass_units != MASS_UNITS or volume_units != BULK_VOLUME_UNITS:
        return _report("REJECTED", "UNEXPECTED_UNITS")
    if mass_basis != DRY_AIR_BASIS or volume_basis != DRY_AIR_BASIS:
        return _report("REJECTED", "BASIS_MISMATCH")
    if r.size == 0:
        return _report("UNSUPPORTED", "EMPTY_VALIDATION_DOMAIN", valid=None)
    if bulk_volume is None:
        return _report("UNSUPPORTED", "BULK_VOLUME_MOMENT_UNSUPPORTED", valid=None)
    bg, issue = _array(bulk_volume, "bulk_volume")
    if issue:
        return _report("REJECTED", issue)
    if bg.shape != r.shape:
        return _report("REJECTED", "SHAPE_MISMATCH")
    issue = _bound_declaration_issue(bound_source, uncertainty_description)
    if issue:
        status = "UNSUPPORTED" if issue == "PHYSICAL_BOUND_DECLARATION_MISSING" else "REJECTED"
        return _report(status, issue, valid=None)
    if bulk_density_min_kg_m3 is None or bulk_density_max_kg_m3 is None:
        return _report("UNSUPPORTED", "BULK_DENSITY_BOUNDS_MISSING", valid=None)
    rho_min = _real_scalar(bulk_density_min_kg_m3)
    rho_max = _real_scalar(bulk_density_max_kg_m3)
    if rho_min is None or rho_max is None or rho_min <= 0.0 or rho_max < rho_min:
        return _report("REJECTED", "INVALID_BULK_DENSITY_BOUNDS")
    lower_volume = r / rho_max
    upper_volume = r / rho_min
    eps = 16.0 * np.finfo(np.float64).eps
    lower_tolerance = eps * np.maximum(np.abs(bg), np.abs(lower_volume))
    upper_tolerance = eps * np.maximum(np.abs(bg), np.abs(upper_volume))
    impossible = ((bg < lower_volume - lower_tolerance)
                  | (bg > upper_volume + upper_tolerance)
                  | ((bg == 0.0) & (r > 0.0))
                  | ((r == 0.0) & (bg > 0.0)))
    count = int(np.count_nonzero(impossible))
    return _report(
        "FAIL" if count else "PASS_SCOPED",
        "MASS_VOLUME_OUTSIDE_DECLARED_DENSITY_BOUNDS" if count else "WITHIN_DECLARED_DENSITY_BOUNDS",
        valid=count == 0,
        violation_count=count,
        checked_count=int(r.size),
        violation_mask=impossible,
        bound_source=bound_source,
        uncertainty_description=uncertainty_description,
    )


def conservative_remap_moments(
    dry_air_mass: Any,
    weights: Any,
    mass_mixing_ratios: Mapping[str, Any],
    number_concentrations: Mapping[str, Any],
    bulk_volume_moments: Mapping[str, Any],
    *,
    particle_mass_bounds_kg: Mapping[str, tuple[float, float]],
    bulk_density_bounds_kg_m3: Mapping[str, tuple[float, float]],
    particle_mass_bound_source: Mapping[str, str],
    particle_mass_uncertainty: Mapping[str, str],
    bulk_density_bound_source: Mapping[str, str],
    bulk_density_uncertainty: Mapping[str, str],
    mass_units: str,
    number_units: str,
    volume_units: str,
    mass_basis: str,
    number_basis: str,
    volume_basis: str,
) -> dict[str, Any]:
    """Remap declared extensive moments with one column-stochastic matrix.

    ``weights[target, donor]`` distributes each donor's dry mass among target
    cells.  Closed-domain columns must each sum to one. Each available ratio is
    transferred as ``dry_mass * ratio`` and
    divided by remapped dry mass.  A missing species entry or a ``None`` value
    is returned as unsupported; it is never replaced with zero.

    This is a manufactured conservative remap helper, not a sedimentation rule.
    """
    md, issue = _array(dry_air_mass, "dry_air_mass")
    if issue:
        raise ValueError(issue)
    w, issue = _array(weights, "weights")
    if issue:
        raise ValueError("NEGATIVE_REMAP_WEIGHT" if issue == "NEGATIVE_FIELD:weights" else issue)
    if md.ndim != 1 or w.ndim != 2 or w.shape[1] != md.size or w.shape[0] == 0:
        raise ValueError("MALFORMED_REMAP_SHAPE")
    if (not isinstance(mass_mixing_ratios, Mapping)
            or not isinstance(number_concentrations, Mapping)
            or not isinstance(bulk_volume_moments, Mapping)):
        raise ValueError("INVALID_MOMENT_MAPPING")
    declarations = (
        ("particle_mass_bounds_kg", particle_mass_bounds_kg),
        ("bulk_density_bounds_kg_m3", bulk_density_bounds_kg_m3),
        ("particle_mass_bound_source", particle_mass_bound_source),
        ("particle_mass_uncertainty", particle_mass_uncertainty),
        ("bulk_density_bound_source", bulk_density_bound_source),
        ("bulk_density_uncertainty", bulk_density_uncertainty),
    )
    for name, declaration in declarations:
        if not isinstance(declaration, Mapping):
            raise ValueError(f"INVALID_DECLARATION_MAPPING:{name}")
    if np.any(md <= 0.0):
        raise ValueError("NONPOSITIVE_DONOR_DRY_MASS")
    if not mass_mixing_ratios:
        raise ValueError("NO_SPECIES_MASS_FIELDS")
    species_names = set(mass_mixing_ratios)
    if (set(number_concentrations) - species_names
            or set(bulk_volume_moments) - species_names):
        raise ValueError("MOMENT_WITHOUT_SPECIES_MASS")
    if (mass_units != MASS_UNITS or number_units != NUMBER_UNITS
            or volume_units != BULK_VOLUME_UNITS):
        raise ValueError("UNEXPECTED_UNITS")
    if (mass_basis != DRY_AIR_BASIS or number_basis != DRY_AIR_BASIS
            or volume_basis != DRY_AIR_BASIS):
        raise ValueError("BASIS_MISMATCH")
    if np.any(w < 0.0):
        raise ValueError("NEGATIVE_REMAP_WEIGHT")
    column_sums = np.sum(w, axis=0)
    tolerance = 64.0 * np.finfo(np.float64).eps * max(1, w.shape[0])
    if not np.all(np.abs(column_sums - 1.0) <= tolerance):
        raise ValueError("REMAP_WEIGHTS_MUST_CONSERVE_EACH_DONOR")
    remapped_dry_mass = w @ md
    if not np.all(np.isfinite(remapped_dry_mass)) or np.any(remapped_dry_mass <= 0.0):
        raise ValueError("ZERO_OR_INVALID_TARGET_DRY_MASS")

    mass_out: dict[str, np.ndarray] = {}
    number_out: dict[str, np.ndarray | None] = {}
    volume_out: dict[str, np.ndarray | None] = {}
    validation: dict[str, dict[str, Any]] = {}
    unsupported: dict[str, list[str]] = {}
    conservation: dict[str, dict[str, float]] = {}

    for species, donor_mass_ratio in mass_mixing_ratios.items():
        r, issue = _array(donor_mass_ratio, f"mass:{species}")
        if issue:
            raise ValueError(issue)
        if r.shape != md.shape:
            raise ValueError(f"MALFORMED_MASS_SHAPE:{species}")
        if (not np.all(np.isfinite(md * r))):
            raise ValueError(f"NONFINITE_MASS_EXTENSIVE:{species}")
        mass_out[species] = (w @ (md * r)) / remapped_dry_mass

        n_raw = number_concentrations.get(species)
        if n_raw is None:
            number_out[species] = None
            n_check = _report("UNSUPPORTED", "NUMBER_MOMENT_UNSUPPORTED", valid=None)
            unsupported.setdefault(species, []).append("number")
        else:
            n, issue = _array(n_raw, f"number:{species}")
            if issue:
                raise ValueError(issue)
            if n.shape != md.shape:
                raise ValueError(f"MALFORMED_NUMBER_SHAPE:{species}")
            bounds = particle_mass_bounds_kg.get(species)
            if bounds is None or len(bounds) != 2:
                raise ValueError(f"MISSING_PARTICLE_MASS_BOUNDS:{species}")
            source = particle_mass_bound_source.get(species)
            uncertainty = particle_mass_uncertainty.get(species)
            donor_check = validate_mass_number(
                r, n,
                mass_units=mass_units, number_units=number_units,
                mass_basis=mass_basis, number_basis=number_basis,
                particle_mass_min_kg=bounds[0], particle_mass_max_kg=bounds[1],
                bound_source=source, uncertainty_description=uncertainty,
            )
            if donor_check["status"] != "PASS_SCOPED":
                raise ValueError(f"DONOR_MASS_NUMBER_INVALID:{species}:{donor_check['reason']}")
            if not np.all(np.isfinite(md * n)):
                raise ValueError(f"NONFINITE_NUMBER_EXTENSIVE:{species}")
            number_out[species] = (w @ (md * n)) / remapped_dry_mass
            n_check = validate_mass_number(
                mass_out[species], number_out[species],
                mass_units=mass_units, number_units=number_units,
                mass_basis=mass_basis, number_basis=number_basis,
                particle_mass_min_kg=bounds[0], particle_mass_max_kg=bounds[1],
                bound_source=source, uncertainty_description=uncertainty,
            )
            if n_check["status"] == "FAIL":
                raise ValueError(f"REMAPPED_MASS_NUMBER_UNREALIZABLE:{species}")
            if n_check["status"] == "REJECTED":
                raise ValueError(f"REMAPPED_MASS_NUMBER_REJECTED:{species}:{n_check['reason']}")

        bg_raw = bulk_volume_moments.get(species)
        if bg_raw is None:
            volume_out[species] = None
            bg_check = _report("UNSUPPORTED", "BULK_VOLUME_MOMENT_UNSUPPORTED", valid=None)
            unsupported.setdefault(species, []).append("bulk_volume")
        else:
            bg, issue = _array(bg_raw, f"bulk_volume:{species}")
            if issue:
                raise ValueError(issue)
            if bg.shape != md.shape:
                raise ValueError(f"MALFORMED_VOLUME_SHAPE:{species}")
            bounds = bulk_density_bounds_kg_m3.get(species)
            if bounds is None or len(bounds) != 2:
                raise ValueError(f"MISSING_BULK_DENSITY_BOUNDS:{species}")
            source = bulk_density_bound_source.get(species)
            uncertainty = bulk_density_uncertainty.get(species)
            donor_check = validate_bulk_volume(
                r, bg,
                mass_units=mass_units, volume_units=volume_units,
                mass_basis=mass_basis, volume_basis=volume_basis,
                bulk_density_min_kg_m3=bounds[0], bulk_density_max_kg_m3=bounds[1],
                bound_source=source, uncertainty_description=uncertainty,
            )
            if donor_check["status"] != "PASS_SCOPED":
                raise ValueError(f"DONOR_MASS_VOLUME_INVALID:{species}:{donor_check['reason']}")
            if not np.all(np.isfinite(md * bg)):
                raise ValueError(f"NONFINITE_VOLUME_EXTENSIVE:{species}")
            volume_out[species] = (w @ (md * bg)) / remapped_dry_mass
            bg_check = validate_bulk_volume(
                mass_out[species], volume_out[species],
                mass_units=mass_units, volume_units=volume_units,
                mass_basis=mass_basis, volume_basis=volume_basis,
                bulk_density_min_kg_m3=bounds[0], bulk_density_max_kg_m3=bounds[1],
                bound_source=source, uncertainty_description=uncertainty,
            )
            if bg_check["status"] == "FAIL":
                raise ValueError(f"REMAPPED_MASS_VOLUME_UNREALIZABLE:{species}")
            if bg_check["status"] == "REJECTED":
                raise ValueError(f"REMAPPED_MASS_VOLUME_REJECTED:{species}:{bg_check['reason']}")

        validation[species] = {"number": n_check, "bulk_volume": bg_check}

    dry_conservation = _conservation_error(
        md, remapped_dry_mass, w,
        donor_count=md.size, target_count=remapped_dry_mass.size,
    )
    conservation["dry_air_mass"] = dry_conservation
    if dry_conservation["absolute_difference"] > (
        dry_conservation["roundoff_bound"]
        + dry_conservation["weight_closure_error"]
    ):
        raise ValueError("DRY_MASS_CONSERVATION_FAILED")
    for species, source_ratio in mass_mixing_ratios.items():
        donor_r = np.asarray(source_ratio, dtype=np.float64)
        mass_conservation = _conservation_error(
            md * donor_r, remapped_dry_mass * mass_out[species], w,
            donor_count=md.size, target_count=remapped_dry_mass.size,
        )
        conservation[f"mass:{species}"] = mass_conservation
        if mass_conservation["absolute_difference"] > (
            mass_conservation["roundoff_bound"]
            + mass_conservation["weight_closure_error"]
        ):
            raise ValueError(f"MASS_CONSERVATION_FAILED:{species}")
        for values, output, name in (
            (number_concentrations.get(species), number_out[species], "NUMBER"),
            (bulk_volume_moments.get(species), volume_out[species], "VOLUME"),
        ):
            if values is None:
                continue
            source_values = np.asarray(values, dtype=np.float64)
            moment_conservation = _conservation_error(
                md * source_values, remapped_dry_mass * output, w,
                donor_count=md.size, target_count=remapped_dry_mass.size,
            )
            conservation[f"{name.lower()}:{species}"] = moment_conservation
            if moment_conservation["absolute_difference"] > (
                moment_conservation["roundoff_bound"]
                + moment_conservation["weight_closure_error"]
            ):
                raise ValueError(f"{name}_CONSERVATION_FAILED:{species}")

    return {
        "dry_air_mass": remapped_dry_mass,
        "mass_mixing_ratios": mass_out,
        "number_concentrations": number_out,
        "bulk_volume_moments": volume_out,
        "validation": validation,
        "conservation": conservation,
        "unsupported": unsupported,
        "mutated_input": False,
    }
