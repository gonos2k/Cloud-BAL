#!/usr/bin/env python3
"""Prove two NetCDF inputs differ only in the reftime variable data."""
from __future__ import annotations

import sys

import netCDF4
import numpy as np


def attrs(obj):
    return {name: getattr(obj, name) for name in obj.ncattrs()}


def attrs_equal(left, right):
    if set(left) != set(right):
        return False
    for name in left:
        a, b = left[name], right[name]
        if isinstance(a, (list, tuple, np.ndarray)) or isinstance(b, (list, tuple, np.ndarray)):
            if not np.array_equal(np.asarray(a), np.asarray(b)):
                return False
        elif a != b:
            return False
    return True


def raw_equal(left, right):
    left = np.asarray(left)
    right = np.asarray(right)
    if left.dtype.kind in "fc" and right.dtype.kind in "fc":
        return np.array_equal(left, right, equal_nan=True)
    return np.array_equal(left, right)


def same_except_reftime(original: str, mutated: str) -> None:
    with netCDF4.Dataset(original) as left, netCDF4.Dataset(mutated) as right:
        if set(left.dimensions) != set(right.dimensions):
            raise AssertionError("dimension names changed")
        for name in left.dimensions:
            if (len(left.dimensions[name]) != len(right.dimensions[name])
                    or left.dimensions[name].isunlimited()
                    != right.dimensions[name].isunlimited()):
                raise AssertionError(f"dimension changed: {name}")
        if not attrs_equal(attrs(left), attrs(right)):
            raise AssertionError("global attributes changed")
        if set(left.variables) != set(right.variables):
            raise AssertionError("variable names changed")
        for name in left.variables:
            a, b = left.variables[name], right.variables[name]
            if a.dimensions != b.dimensions or not attrs_equal(attrs(a), attrs(b)):
                raise AssertionError(f"metadata changed: {name}")
            if a.dtype != b.dtype:
                raise AssertionError(f"dtype changed: {name}")
            left_value, right_value = a[:], b[:]
            left_mask = np.ma.getmaskarray(left_value)
            right_mask = np.ma.getmaskarray(right_value)
            if not np.array_equal(left_mask, right_mask):
                raise AssertionError(f"mask changed: {name}")
            if name == "reftime":
                if raw_equal(left_value.data, right_value.data):
                    raise AssertionError("reftime did not change")
            elif not raw_equal(left_value.data, right_value.data):
                raise AssertionError(f"data changed outside reftime: {name}")


def check_times(path: str, expected_reftime: float, expected_valtime: float) -> None:
    with netCDF4.Dataset(path) as dataset:
        for name, expected in (("reftime", expected_reftime), ("valtime", expected_valtime)):
            value = dataset.variables[name][:]
            if np.any(np.ma.getmaskarray(value)):
                raise AssertionError(f"{name} is masked")
            if not raw_equal(value.data, np.asarray([expected])):
                raise AssertionError(f"{name} does not equal expected epoch")
        if float(dataset.variables["reftime"][0]) > float(dataset.variables["valtime"][0]):
            raise AssertionError("mutated reftime is after valid time")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: verify_only_reftime.py ORIGINAL MUTATED REFTIME VALTIME")
    original, mutated = sys.argv[1:3]
    expected_reftime, expected_valtime = map(float, sys.argv[3:5])
    check_times(original, expected_reftime - 3600.0, expected_valtime)
    check_times(mutated, expected_reftime, expected_valtime)
    same_except_reftime(original, mutated)
    print(f"ONLY_REFTIME_CHANGED mutated_reftime={int(expected_reftime)} valid_time={int(expected_valtime)}")
