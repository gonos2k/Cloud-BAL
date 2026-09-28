#!/usr/bin/env python3
"""Check an actual closed WPS/SHADOW pair in an isolated publication root."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from cloud_bal_transaction import (OutputTransaction, TransactionError, _current,
                                   _directory_identity, _product_record)
from verify_shadow_wps_pair import PAIR_PRODUCTS, verify_snapshot


def copy_pair(transaction: OutputTransaction, source: Path) -> None:
    for product in PAIR_PRODUCTS:
        shutil.copyfile(source / product, transaction.resolve_output(product))


def make_transaction(root: Path, name: str, source: Path, valid_time: int) -> OutputTransaction:
    transaction = OutputTransaction(root, name)
    transaction.begin(PAIR_PRODUCTS, source_commit="0" * 40,
                      configuration="pressure-pair-research-only",
                      valid_time=valid_time, require_validation=True)
    copy_pair(transaction, source)
    return transaction


def rejected(action, message: str) -> None:
    try:
        action()
    except (AssertionError, TransactionError, ValueError):
        return
    raise AssertionError(message)


def claimed_receipt(receipt: dict, transaction: OutputTransaction) -> dict:
    """Claim a PASS for changed bytes so commit must execute its own validator."""
    claim = deepcopy(receipt)
    claim["transaction_id"] = transaction.transaction_id
    claim["snapshot_identity"] = _directory_identity(transaction.snapshot)
    claim["products"] = [
        _product_record(transaction.snapshot / product, product)
        for product in sorted(PAIR_PRODUCTS)
    ]
    return claim


def run(source: Path) -> None:
    if not all((source / product).is_file() for product in PAIR_PRODUCTS):
        raise ValueError("actual pair fixture is incomplete")
    with netCDF4.Dataset(source / PAIR_PRODUCTS[2]) as dataset:
        valid_time = int(dataset.valid_time_epoch)
    with tempfile.TemporaryDirectory(prefix="cloud-bal-pair-", dir="/var/tmp") as directory:
        root = Path(directory) / "publication"
        initial = OutputTransaction(root, "prior")
        initial.begin(["marker"], source_commit="0" * 40,
                      configuration="prior-research-generation")
        initial.resolve_output("marker").write_bytes(b"prior")
        initial.commit()

        good = make_transaction(root, "good", source, valid_time)
        snapshot = good.prepare()
        receipt = verify_snapshot(snapshot)
        assert receipt["validator"]["name"] == "verify_shadow_wps_pair"
        assert [item["path"] for item in receipt["products"]] == list(PAIR_PRODUCTS)
        good.commit(validation_receipt=receipt)
        assert _current(root).name == "good"

        bad_wps = make_transaction(root, "bad-wps", source, valid_time)
        candidate_path = bad_wps.resolve_output("candidate.wps")
        payload = bytearray(candidate_path.read_bytes())
        payload[-12] ^= 1
        candidate_path.write_bytes(payload)
        bad_wps.prepare()
        rejected(lambda: verify_snapshot(bad_wps.snapshot),
                 "changed WPS bytes passed pair readback")
        rejected(lambda: bad_wps.commit(validation_receipt=claimed_receipt(receipt, bad_wps)),
                 "changed WPS bytes were published")
        assert _current(root).name == "good"

        bad_shadow = make_transaction(root, "bad-shadow", source, valid_time)
        with netCDF4.Dataset(bad_shadow.resolve_output("candidate.wps.shadow.nc"), "r+") as dataset:
            variable = dataset["candidate_temperature"]
            domain = np.asarray(dataset["above_ground"][:], dtype=bool)
            z, y, x = np.argwhere(domain)[0]
            variable[z, y, x] = np.float32(variable[z, y, x] + 1.0)
        bad_shadow.prepare()
        rejected(lambda: verify_snapshot(bad_shadow.snapshot),
                 "changed SHADOW candidate passed pair readback")
        rejected(lambda: bad_shadow.commit(validation_receipt=claimed_receipt(receipt, bad_shadow)),
                 "changed SHADOW candidate was published")
        assert _current(root).name == "good"

        stale = make_transaction(root, "stale", source, valid_time)
        stale.prepare()
        stale_receipt = verify_snapshot(stale.snapshot)
        with netCDF4.Dataset(stale.snapshot / "candidate.wps.shadow.nc", "r+") as dataset:
            dataset.setncattr("pair_stale_marker", 1)
        rejected(lambda: stale.commit(validation_receipt=stale_receipt),
                 "stale pair receipt published")
        assert _current(root).name == "good"
    print("Actual WPS/SHADOW pair transaction validation passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    run(parser.parse_args().fixture)
