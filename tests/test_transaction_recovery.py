#!/usr/bin/env python3
"""Real fsync fault injection and explicit generation recovery, on private roots."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cloud_bal_transaction as transaction


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cloud-bal-recovery-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'publication'
        self.old = self.candidate('old')
        self.old.commit()
        self.old_bytes = (self.old.generation / 'deep/nested/product').read_bytes()

    def candidate(self, name, *, require_validation=False):
        item = transaction.OutputTransaction(self.root, name)
        item.begin(['deep/nested/product'], source_commit='0' * 40,
                   configuration='recovery-fault-test', valid_time=1,
                   require_validation=require_validation)
        item.resolve_output('deep/nested/product').write_bytes(name.encode())
        return item

    def validation_receipt(self, candidate, snapshot):
        return {
            'schema': 1,
            'status': 'PASS',
            'transaction_id': candidate.transaction_id,
            'snapshot_identity': [snapshot.stat().st_dev, snapshot.stat().st_ino],
            'validator': {
                'name': 'validate_shadow_diagnostics',
                'source_sha256': transaction._trusted_validator_source_sha256(
                    'validate_shadow_diagnostics'
                ),
            },
            'products': [transaction._product_record(
                snapshot / 'deep/nested/product', 'deep/nested/product'
            )],
        }

    def fixture_semantic_dispatch(self, candidate):
        """Isolate transaction mechanics; real semantic dispatch has separate tests."""
        def validate(name, snapshot):
            self.assertEqual(name, 'validate_shadow_diagnostics')
            self.assertEqual((snapshot / 'deep/nested/product').read_bytes(),
                             candidate.transaction_id.encode())
            return self.validation_receipt(candidate, snapshot)
        mock = patch.object(transaction, '_execute_trusted_validator', side_effect=validate)
        dispatcher = mock.start()
        self.addCleanup(mock.stop)
        self.addCleanup(dispatcher.assert_called_once)

    def assert_old_unchanged(self):
        self.assertEqual((self.old.generation / 'deep/nested/product').read_bytes(), self.old_bytes)
        transaction._verify_generation(self.old.generation, 'old')

    def test_every_commit_fsync_failure(self):
        """Sweep every actual fsync call, including metadata and both rename parents."""
        probe = self.candidate('probe')
        trace = []
        real_fsync = os.fsync
        def record(fd):
            trace.append(os.readlink(f'/proc/self/fd/{fd}'))
            real_fsync(fd)
        with patch.object(transaction.os, 'fsync', side_effect=record):
            probe.commit()
        self.assertEqual(trace[-1], str(self.root))
        last = lambda path: max(index for index, item in enumerate(trace)
                                if item == str(path))
        self.assertLess(last(probe.snapshot / 'deep/nested'),
                        last(probe.snapshot / 'deep'))
        self.assertLess(last(probe.snapshot / 'deep'), last(probe.snapshot))
        self.assertLess(last(probe.snapshot), last(probe.generations))
        print(f'Commit fsync boundaries exercised: {len(trace)}')
        for fail_index in range(len(trace)):
            with self.subTest(boundary=fail_index, path=trace[fail_index]):
                candidate = self.candidate(f'fault{fail_index}')
                before = transaction._current(self.root).name
                count = 0
                def fail_once(fd):
                    nonlocal count
                    index = count
                    count += 1
                    if index == fail_index:
                        raise OSError(errno.EIO, 'injected fsync failure')
                    real_fsync(fd)
                with patch.object(transaction.os, 'fsync', side_effect=fail_once):
                    with self.assertRaises((transaction.TransactionError, OSError)) as caught:
                        candidate.commit()
                self.assertEqual(count, fail_index + 1)
                if isinstance(caught.exception, transaction.PublicationUncertainError):
                    self.assertEqual(fail_index, len(trace) - 1)
                    self.assertEqual(transaction._current(self.root), candidate.generation)
                else:
                    self.assertEqual(transaction._current(self.root).name, before)
                if candidate.generation.exists():
                    manifest_before = (candidate.generation / 'MANIFEST.json').read_bytes()
                    with self.assertRaises(transaction.TransactionError):
                        candidate.commit()
                    candidate.recover()
                    candidate.recover()
                    self.assertEqual(transaction._current(self.root), candidate.generation)
                    self.assertEqual((candidate.generation / 'MANIFEST.json').read_bytes(), manifest_before)
                else:
                    with self.assertRaises(transaction.TransactionError):
                        candidate.recover()
                    # Fresh identity is safe after a pre-publication failure.
                    fresh = self.candidate(f'retry{fail_index}')
                    fresh.commit()
                self.assert_old_unchanged()

    def rename_without_publish(self, name):
        item = self.candidate(name)
        with patch.dict(os.environ, {'CLOUD_BAL_FAIL_AT': 'after_generation_rename'}):
            with self.assertRaises(transaction.TransactionError):
                item.commit()
        return item

    def test_recovery_rejects_changed_current(self):
        abandoned = self.rename_without_publish('abandoned')
        newer = self.candidate('newer')
        newer.commit()
        with self.assertRaisesRegex(transaction.TransactionError, 'current generation changed'):
            abandoned.recover()
        self.assertEqual(transaction._current(self.root), newer.generation)

    def test_recovery_rejects_tamper(self):
        abandoned = self.rename_without_publish('tampered')
        (abandoned.generation / 'deep/nested/product').write_bytes(b'forged')
        with self.assertRaises(transaction.TransactionError):
            abandoned.recover()
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_recovery_rejects_stale_temporary_pointer(self):
        abandoned = self.rename_without_publish('temporary')
        temporary = self.root / '.current.temporary.tmp'
        temporary.symlink_to('generations/old')
        with self.assertRaisesRegex(transaction.TransactionError, 'publication pointer is unsafe'):
            abandoned.recover()
        self.assertEqual(os.readlink(temporary), 'generations/old')
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_recovery_reuses_matching_orphan_pointer(self):
        abandoned = self.rename_without_publish('orphan')
        temporary = self.root / '.current.orphan.tmp'
        temporary.symlink_to('generations/orphan')
        abandoned.recover()
        self.assertFalse(temporary.is_symlink())
        self.assertEqual(transaction._current(self.root), abandoned.generation)
        abandoned.recover()

    def test_retained_writer_fd_is_detached_before_publication(self):
        """A writer that outlives commit cannot mutate the published inode."""
        candidate = self.candidate('retained_writer')
        product = candidate.resolve_output('deep/nested/product')
        writer_fd = os.open(product, os.O_RDWR)
        ready_read, ready_write = os.pipe()
        release_read, release_write = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(ready_read)
            os.close(release_write)
            try:
                os.write(ready_write, b'ready')
                os.read(release_read, 1)
                os.pwrite(writer_fd, b'retained writer mutation', 0)
            finally:
                os.close(writer_fd)
                os.close(ready_write)
                os.close(release_read)
            os._exit(0)

        os.close(ready_write)
        os.close(release_read)
        try:
            self.assertEqual(os.read(ready_read, len(b'ready')), b'ready')
            original_inode = os.fstat(writer_fd).st_ino
            manifest = candidate.commit()
            os.write(release_write, b'go')
            _, status = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)

            published = candidate.generation / 'deep/nested/product'
            self.assertNotEqual(original_inode, published.stat().st_ino)
            self.assertEqual(published.read_bytes(), b'retained_writer')
            self.assertEqual(
                manifest['products'][0]['sha256'],
                hashlib.sha256(b'retained_writer').hexdigest(),
            )
            self.assertEqual(transaction._current(self.root), candidate.generation)
        finally:
            os.close(writer_fd)
            os.close(ready_read)
            os.close(release_write)
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(child, 0)
            except ChildProcessError:
                pass

    def test_semantic_receipt_binds_prepared_snapshot(self):
        """A validated snapshot survives later staging mutation and publishes."""
        candidate = self.candidate('validated_snapshot', require_validation=True)
        self.fixture_semantic_dispatch(candidate)
        source = candidate.resolve_output('deep/nested/product')
        snapshot = candidate.prepare()
        receipt = self.validation_receipt(candidate, snapshot)
        writer_fd = os.open(source, os.O_RDWR)
        try:
            os.pwrite(writer_fd, b'staging mutation after validation', 0)
            manifest = candidate.commit(validation_receipt=receipt)
        finally:
            os.close(writer_fd)
        self.assertEqual(
            (candidate.generation / 'deep/nested/product').read_bytes(),
            b'validated_snapshot',
        )
        self.assertEqual(manifest['validation'], receipt)
        self.assertEqual(transaction._current(self.root), candidate.generation)

    def test_validated_snapshot_ignores_retained_staging_fifo(self):
        """Publication does not reopen producer paths after snapshot validation."""
        candidate = self.candidate('validated_fifo', require_validation=True)
        self.fixture_semantic_dispatch(candidate)
        product = candidate.resolve_output('deep/nested/product')
        writer_fd = os.open(product, os.O_RDWR)
        try:
            snapshot = candidate.prepare()
            receipt = self.validation_receipt(candidate, snapshot)
            product.unlink()
            os.mkfifo(product)
            os.pwrite(writer_fd, b'retained writer mutation', 0)
            signal.alarm(3)
            try:
                manifest = candidate.commit(validation_receipt=receipt)
            finally:
                signal.alarm(0)
        finally:
            os.close(writer_fd)
        self.assertEqual(
            (candidate.generation / 'deep/nested/product').read_bytes(),
            b'validated_fifo',
        )
        self.assertEqual(manifest['validation'], receipt)
        self.assertTrue(product.is_fifo())
        self.assertEqual(transaction._current(self.root), candidate.generation)

    def test_validation_receipt_rejects_snapshot_mutation(self):
        """A retained snapshot descriptor cannot bypass semantic hash binding."""
        candidate = self.candidate('snapshot_tamper', require_validation=True)
        snapshot = candidate.prepare()
        receipt = self.validation_receipt(candidate, snapshot)
        writer_fd = os.open(snapshot / 'deep/nested/product', os.O_RDWR)
        try:
            os.pwrite(writer_fd, b'unvalidated snapshot mutation', 0)
            with self.assertRaisesRegex(
                transaction.TransactionError, 'receipt products differ'
            ):
                candidate.commit(validation_receipt=receipt)
        finally:
            os.close(writer_fd)
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_required_validation_rejects_untrusted_validator(self):
        """Required transactions accept only the designated validator source."""
        candidate = self.candidate('untrusted_validator', require_validation=True)
        snapshot = candidate.prepare()
        receipt = self.validation_receipt(candidate, snapshot)
        receipt['validator'] = {
            'name': 'untrusted-forger',
            'source_sha256': '0' * 64,
        }
        with self.assertRaisesRegex(
            transaction.TransactionError, 'validator is not trusted'
        ):
            candidate.commit(validation_receipt=receipt)
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_validation_receipt_rejects_snapshot_fifo_without_blocking(self):
        """A replaced snapshot product fails closed without a blocking open."""
        candidate = self.candidate('snapshot_fifo', require_validation=True)
        snapshot = candidate.prepare()
        receipt = self.validation_receipt(candidate, snapshot)
        snapshot_product = snapshot / 'deep/nested/product'
        snapshot_product.unlink()
        os.mkfifo(snapshot_product)
        signal.alarm(3)
        try:
            with self.assertRaises(transaction.TransactionError):
                candidate.commit(validation_receipt=receipt)
        finally:
            signal.alarm(0)
        self.assertTrue(snapshot_product.is_fifo())
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_required_validation_rejects_direct_commit(self):
        """A required transaction cannot publish without prepare and receipt."""
        candidate = self.candidate('required_direct', require_validation=True)
        with self.assertRaisesRegex(
            transaction.TransactionError, 'must prepare a snapshot'
        ):
            candidate.commit()
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_recovery_rejects_required_generation_without_receipt(self):
        """Recovery requires the semantic receipt declared by the context."""
        candidate = self.candidate('required_recovery', require_validation=True)
        self.fixture_semantic_dispatch(candidate)
        snapshot = candidate.prepare()
        receipt = self.validation_receipt(candidate, snapshot)
        with patch.dict(os.environ, {'CLOUD_BAL_FAIL_AT': 'after_generation_rename'}):
            with self.assertRaises(transaction.TransactionError):
                candidate.commit(validation_receipt=receipt)
        manifest_path = candidate.generation / 'MANIFEST.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.pop('validation')
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(
            transaction.TransactionError, 'required semantic validation receipt'
        ):
            candidate.recover()
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_prepared_snapshot_requires_explicit_validation_receipt(self):
        candidate = self.candidate('receipt_required')
        candidate.prepare()
        with self.assertRaisesRegex(
            transaction.TransactionError, 'requires validation receipt'
        ):
            candidate.commit()
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_cli_prepare_and_commit_validation_receipt(self):
        """The shell-facing prepare/receipt/commit protocol uses one snapshot."""
        import contextlib
        import io

        candidate = self.candidate('cli_validated', require_validation=True)
        self.fixture_semantic_dispatch(candidate)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = transaction.main(['prepare', str(self.root), candidate.transaction_id])
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), str(candidate.snapshot))
        receipt_path = self.root / 'validation_receipt.json'
        receipt_path.write_text(
            json.dumps(self.validation_receipt(candidate, candidate.snapshot)),
            encoding='utf-8',
        )
        with contextlib.redirect_stdout(io.StringIO()):
            result = transaction.main([
                'commit', str(self.root), candidate.transaction_id,
                '--validation-receipt', str(receipt_path),
            ])
        self.assertEqual(result, 0)
        self.assertEqual(transaction._current(self.root), candidate.generation)

    def test_fifo_source_swap_is_rejected_without_blocking(self):
        """A FIFO swapped after inventory cannot make snapshot open hang."""
        candidate = self.candidate('fifo_source')
        product = candidate.resolve_output('deep/nested/product')
        original_snapshot = transaction.OutputTransaction._snapshot_outputs

        def swap_to_fifo(item, context, context_sha256):
            product.unlink()
            os.mkfifo(product)
            return original_snapshot(item, context, context_sha256)

        with patch.object(
            transaction.OutputTransaction, '_snapshot_outputs', new=swap_to_fifo
        ):
            with self.assertRaises(transaction.TransactionError):
                candidate.commit()
        self.assertTrue(product.is_fifo())
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_source_path_swap_is_rejected_and_foreign_bytes_survive(self):
        """Snapshot writes never replace a producer pathname or foreign file."""
        candidate = self.candidate('source_path_swap')
        product = candidate.resolve_output('deep/nested/product')
        original_fsync = transaction.os.fsync
        swapped = False

        def swap_source_after_copy(descriptor):
            nonlocal swapped
            descriptor_path = os.readlink(f'/proc/self/fd/{descriptor}')
            if not swapped and descriptor_path == str(
                candidate.snapshot / 'deep/nested/product'
            ):
                product.unlink()
                product.write_bytes(b'foreign source replacement')
                swapped = True
            return original_fsync(descriptor)

        with patch.object(transaction.os, 'fsync', side_effect=swap_source_after_copy):
            with self.assertRaises(transaction.TransactionError):
                candidate.commit()
        self.assertTrue(swapped)
        self.assertEqual(product.read_bytes(), b'foreign source replacement')
        self.assertFalse(candidate.generation.exists())
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_source_swap_after_check_cannot_be_overwritten(self):
        """A source pathname swapped after its check remains foreign and harmless."""
        candidate = self.candidate('source_swap_after_check')
        product = candidate.resolve_output('deep/nested/product')
        original_stat = transaction.os.stat
        original_read = transaction.os.read
        foreign = b'foreign after source check'
        source_read_complete = False
        source_stat_count = 0
        swapped = False

        def mark_source_read(descriptor, count):
            nonlocal source_read_complete
            result = original_read(descriptor, count)
            descriptor_path = os.readlink(f'/proc/self/fd/{descriptor}')
            if descriptor_path == str(product) and not result:
                source_read_complete = True
            return result

        def swap_after_source_check(name, *args, **kwargs):
            nonlocal source_stat_count, swapped
            descriptor = kwargs.get('dir_fd')
            parent_path = (
                os.readlink(f'/proc/self/fd/{descriptor}')
                if descriptor is not None else ''
            )
            result = original_stat(name, *args, **kwargs)
            if source_read_complete and name == 'product' and parent_path == str(
                candidate.staging / 'deep/nested'
            ):
                source_stat_count += 1
            if source_stat_count >= 2 and not swapped:
                product.unlink()
                product.write_bytes(foreign)
                swapped = True
            return result

        with patch.object(transaction.os, 'read', side_effect=mark_source_read):
            with patch.object(transaction.os, 'stat', side_effect=swap_after_source_check):
                manifest = candidate.commit()
        self.assertTrue(swapped)
        self.assertEqual(product.read_bytes(), foreign)
        self.assertEqual(
            (candidate.generation / 'deep/nested/product').read_bytes(),
            b'source_swap_after_check',
        )
        self.assertEqual(
            manifest['products'][0]['sha256'],
            hashlib.sha256(b'source_swap_after_check').hexdigest(),
        )
        self.assertEqual(transaction._current(self.root), candidate.generation)

    def test_failed_snapshot_does_not_unlink_destination_replacement(self):
        """A failed copy leaves evidence; cleanup never unlinks a swapped path."""
        candidate = self.candidate('snapshot_failure')
        product = candidate.resolve_output('deep/nested/product')
        original_fsync = transaction.os.fsync
        failed = False

        def fail_destination_sync(descriptor):
            nonlocal failed
            descriptor_path = os.readlink(f'/proc/self/fd/{descriptor}')
            if not failed and descriptor_path == str(
                candidate.snapshot / 'deep/nested/product'
            ):
                failed = True
                raise OSError(errno.EIO, 'snapshot sync failure')
            return original_fsync(descriptor)

        with patch.object(transaction.os, 'fsync', side_effect=fail_destination_sync):
            with self.assertRaises((transaction.TransactionError, OSError)):
                candidate.commit()
        self.assertTrue(failed)
        self.assertEqual(product.read_bytes(), b'snapshot_failure')
        self.assertEqual(
            (candidate.snapshot / 'deep/nested/product').read_bytes(),
            b'snapshot_failure',
        )
        self.assertEqual(transaction._current(self.root), self.old.generation)

    def test_rejected_temporary_replacements_are_preserved(self):
        for replacement_kind in ('regular', 'symlink'):
            with self.subTest(replacement_kind=replacement_kind):
                candidate = self.candidate(f'replaced_{replacement_kind}')
                temporary = self.root / f'.current.{candidate.transaction_id}.tmp'

                def replace_temporary(point):
                    if point != 'before_current_swap':
                        return
                    temporary.unlink()
                    if replacement_kind == 'regular':
                        temporary.write_bytes(b'foreign temporary')
                    else:
                        temporary.symlink_to('generations/old')

                with patch.object(
                    transaction.OutputTransaction,
                    '_inject',
                    new=staticmethod(replace_temporary),
                ):
                    with self.assertRaisesRegex(
                        transaction.TransactionError,
                        'publication pointer is unsafe',
                    ):
                        candidate.commit()

                self.assertEqual(transaction._current(self.root), self.old.generation)
                if replacement_kind == 'regular':
                    self.assertTrue(temporary.is_file())
                    self.assertFalse(temporary.is_symlink())
                    self.assertEqual(temporary.read_bytes(), b'foreign temporary')
                else:
                    self.assertTrue(temporary.is_symlink())
                    self.assertEqual(os.readlink(temporary), 'generations/old')

                with self.assertRaisesRegex(
                    transaction.TransactionError,
                    'publication pointer is unsafe',
                ):
                    candidate.recover()
                self.assertTrue(os.path.lexists(temporary))

    def test_process_exit_before_current_swap(self):
        candidate = self.candidate('process_exit')
        child = os.fork()
        if child == 0:
            def exit_before_swap(point):
                if point == 'before_current_swap':
                    os._exit(77)
            transaction.OutputTransaction._inject = staticmethod(exit_before_swap)
            try:
                candidate.commit()
            except BaseException:
                os._exit(78)
            os._exit(79)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 77)
        self.assertEqual(transaction._current(self.root), self.old.generation)
        self.assertTrue((self.root / '.current.process_exit.tmp').is_symlink())
        candidate.recover()
        self.assertEqual(transaction._current(self.root), candidate.generation)

    def test_lock_release_failure_after_swap_is_uncertain(self):
        candidate = self.candidate('unlock')
        original = transaction.fcntl.flock
        def fail_unlock(fd, operation):
            if operation == transaction.fcntl.LOCK_UN:
                raise OSError(errno.EIO, 'unlock failed')
            return original(fd, operation)
        with patch.object(transaction.fcntl, 'flock', side_effect=fail_unlock):
            with self.assertRaises(transaction.PublicationUncertainError):
                candidate.commit()
        self.assertEqual(transaction._current(self.root), candidate.generation)
        candidate.recover()

    def test_cli_distinguishes_uncertain_publication(self):
        import contextlib
        import io
        error = transaction.PublicationUncertainError('run recover')
        stream = io.StringIO()
        with patch.object(transaction.OutputTransaction, 'commit', side_effect=error):
            with contextlib.redirect_stderr(stream):
                result = transaction.main(['commit', str(self.root), 'cli'])
        self.assertEqual(result, 3)
        self.assertIn('publication uncertain', stream.getvalue())
        self.assertNotIn('rejected', stream.getvalue())

    def test_recovery_fsync_failure_before_and_after_visibility(self):
        candidate = self.rename_without_publish('recover_sync')
        with patch.object(transaction.os, 'fsync', side_effect=OSError(errno.EIO, 'sync')):
            with self.assertRaises((OSError, transaction.TransactionError)) as caught:
                candidate.recover()
        self.assertNotIsInstance(caught.exception, transaction.PublicationUncertainError)
        self.assertEqual(transaction._current(self.root), self.old.generation)
        candidate.recover()
        with patch.object(transaction.os, 'fsync', side_effect=OSError(errno.EIO, 'sync')):
            with self.assertRaises(transaction.PublicationUncertainError):
                candidate.recover()
        self.assertEqual(transaction._current(self.root), candidate.generation)
        candidate.recover()

    def test_recovery_checks_inode_owner_and_old_valid_time(self):
        for attack in ('owner', 'inode', 'old_time'):
            with self.subTest(attack=attack):
                candidate = self.rename_without_publish(attack)
                if attack == 'owner':
                    candidate.owner.write_bytes(b'{}')
                elif attack == 'inode':
                    import shutil
                    original = candidate.generation.with_name(attack + '_original')
                    candidate.generation.rename(original)
                    shutil.copytree(original, candidate.generation)
                else:
                    # A legitimate older candidate is rejected, without forged metadata.
                    candidate = transaction.OutputTransaction(self.root, 'older')
                    candidate.begin(['product'], source_commit='0' * 40,
                                    configuration='older', valid_time=0)
                    candidate.resolve_output('product').write_bytes(b'older')
                    with patch.dict(os.environ, {'CLOUD_BAL_FAIL_AT': 'after_generation_rename'}):
                        with self.assertRaises(transaction.TransactionError):
                            candidate.commit()
                with self.assertRaises(transaction.TransactionError):
                    candidate.recover()
                self.assertEqual(transaction._current(self.root), self.old.generation)


if __name__ == '__main__':
    unittest.main(verbosity=2)
