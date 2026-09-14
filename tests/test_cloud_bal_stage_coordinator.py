from pathlib import Path
import tempfile
import os
import signal
import time
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cloud_bal_stage_coordinator as launch

class SnapshotBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        (self.source / 'a').write_bytes(b'owned actual input')
        self.expected = {'a': launch.digest(self.source / 'a')}
    def tearDown(self):
        self.temp.cleanup()
    def test_detached_retained_writer(self):
        with (self.source / 'a').open('r+b') as writer:
            launch.detach_inputs(self.source, self.root / 'copy', self.expected)
            writer.write(b'changed afterwards')
        self.assertEqual((self.root / 'copy/a').read_bytes(), b'owned actual input')
    def test_wrong_expected_hash(self):
        with self.assertRaises(ValueError):
            launch.detach_inputs(self.source, self.root / 'copy', {'a': '0' * 64})
    def test_symlink_rejected(self):
        (self.source / 'link').symlink_to('a')
        with self.assertRaises(Exception):
            launch.detach_inputs(self.source, self.root / 'copy', {'link': self.expected['a']})
    def test_hardlink_rejected(self):
        (self.source / 'link').hardlink_to(self.source / 'a')
        with self.assertRaises(Exception):
            launch.detach_inputs(self.source, self.root / 'copy', self.expected)
    def test_traversal_rejected(self):
        with self.assertRaises(Exception):
            launch.detach_inputs(self.source, self.root / 'copy', {'../source/a': self.expected['a']})
    def test_manifest_replacement_after_read_uses_verified_bytes(self):
        manifest = self.root / 'inputs.sha256'
        manifest.write_text(self.expected['a'] + '  ' + str(self.source / 'a') + '\n')
        runtime = self.root / 'runtime.sha256'; runtime.write_text('runtime identity\n')
        build = {'inputs_manifest': str(manifest), 'inputs_sha256': launch.digest(manifest),
                 'runtime_manifest': str(runtime), 'runtime_sha256': launch.digest(runtime),
                 'executable': str(self.source / 'a'), 'executable_sha256': self.expected['a']}
        real_read = launch.read_verified_file
        def replace_after_read(path, expected):
            data = real_read(path, expected)
            if path == manifest:
                path.write_text('unverified replacement must not be parsed\n')
            return data
        with patch.object(launch, 'read_verified_file', side_effect=replace_after_read):
            self.assertEqual(launch.verify_build(build), {str(self.source / 'a'): self.expected['a']})

    def test_manifest_text_hash_does_not_replace_file_verification(self):
        manifest = self.root / 'inputs.sha256'
        manifest.write_text(self.expected['a'] + '  ' + str(self.source / 'a') + '\n')
        runtime = self.root / 'runtime.sha256'; runtime.write_text('runtime identity\n')
        build = {'inputs_manifest': str(manifest), 'inputs_sha256': launch.digest(manifest),
                 'runtime_manifest': str(runtime), 'runtime_sha256': launch.digest(runtime)}
        (self.source / 'a').write_bytes(b'changed before validation')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            launch.verify_build(build)

class SupervisorTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_double_fork_setsid_retained_writer(self):
        target=self.root/'retained.txt'
        def job():
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,b'before')
            readfd,writefd=os.pipe()
            child=os.fork()
            if child==0:
                grandchild=os.fork()
                if grandchild==0:
                    os.setsid();os.write(writefd,b'R');time.sleep(2);os.write(fd,b'after');os._exit(0)
                os._exit(0)
            os.read(readfd,1)
        receipt=launch._supervise_launch(self.root,job,3)
        self.assertEqual(receipt['exit_code'],0);self.assertEqual(receipt['leader_exit_code'],0)
        self.assertEqual(receipt['closure']['status'],'ECHILD')
        self.assertTrue(receipt['closure']['signaled'])
        self.assertEqual(target.read_bytes(),b'before')
    def test_foreign_child_is_not_reaped(self):
        foreign=os.fork()
        if foreign==0:time.sleep(0.1);os._exit(7)
        receipt=launch._supervise_launch(self.root,lambda:None,2)
        self.assertEqual(receipt['exit_code'],0)
        pid,status=os.waitpid(foreign,0)
        self.assertEqual(pid,foreign);self.assertEqual(os.waitstatus_to_exitcode(status),7)
    def test_leader_timeout(self):
        receipt=launch._supervise_launch(self.root,lambda:time.sleep(3),0.05)
        self.assertEqual(receipt['exit_code'],124)
        self.assertEqual(receipt['leader_exit_code'],-signal.SIGKILL)
        self.assertEqual(receipt['closure']['status'],'ECHILD')
    def test_closure_timeout_rejects_leader_zero(self):
        with patch.object(launch,'_reap_descendants',return_value={'status':'TIMEOUT','reaped':[],'signaled':[]}):
            receipt=launch._supervise_launch(self.root,lambda:None,2)
        self.assertEqual(receipt['leader_exit_code'],0);self.assertEqual(receipt['exit_code'],126)
        self.assertEqual(receipt['closure']['status'],'TIMEOUT')


if __name__ == '__main__':
    unittest.main()
