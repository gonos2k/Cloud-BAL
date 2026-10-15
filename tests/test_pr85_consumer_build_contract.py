import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr85_consumer_build_contract as contract
from archive_member_hashes import archive_member_hashes


def write_archive(path, members):
    data = bytearray(b"!<arch>\n")
    for name, body in members:
        header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'644':<8}{len(body):<10}`\n"
        data.extend(header.encode() + body + (b"\n" if len(body) % 2 else b""))
    path.write_bytes(data)


class ConsumerBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        base_dir = self.root / "parent/link/main"
        base_dir.mkdir(parents=True)
        self.parent_exe = self.root / "parent/wrf.exe"
        self.parent_exe.write_bytes(b"parent executable")
        self.parent_archive = base_dir / "libwrf.a"
        write_archive(self.parent_archive, [("solve_em.o", b"old"), ("kdm6.o", b"fixed")])
        self.wrf = base_dir / "wrf.o"
        self.top = base_dir / "module_wrf_top.o"
        self.wrf.write_bytes(b"parent wrf")
        self.top.write_bytes(b"parent top")
        self.tool = self.root / "mpiifx"
        self.tool.write_bytes(b"pinned link driver")
        self.external = self.root / "libexternal.a"
        self.external.write_bytes(b"external library")

        self.build = self.root / "candidate"
        link_dir = self.build / "link/main"
        compile_dir = self.build / "compile"
        link_dir.mkdir(parents=True)
        compile_dir.mkdir()
        self.exe = self.build / "wrf_pr85.exe"
        self.exe.write_bytes(b"candidate executable")
        self.archive = link_dir / "libwrf_pr85.a"
        write_archive(self.archive, [("solve_em.o", b"new"), ("kdm6.o", b"fixed")])
        self.copied_wrf = link_dir / "wrf.o"
        self.copied_top = link_dir / "module_wrf_top.o"
        self.copied_wrf.write_bytes(self.wrf.read_bytes())
        self.copied_top.write_bytes(self.top.read_bytes())
        self.observer_source = self.root / "observer.f90"
        self.observer_source.write_bytes(b"observer source")
        self.observer = compile_dir / "observer.o"
        self.observer.write_bytes(b"observer object")
        self.source = self.root / "solve_em.F"
        self.source.write_bytes(b"source")
        self.patched = self.root / "solve_em.patched.F"
        self.patched.write_bytes(b"patched source")
        self.generated = self.root / "solve_em.f90"
        self.generated.write_bytes(b"generated source")
        self.obj = self.root / "solve_em.o"
        self.obj.write_bytes(b"new")

        self.base_argv = [str(self.tool), "-o", str(self.parent_exe), "-O3", "-ip",
                          str(self.wrf), str(self.top), str(self.parent_archive),
                          str(self.external), "-qopenmp"]
        self.base = {
            "production_link_argv": self.base_argv,
            "production_link_dependencies_sha256": {
                str(self.tool): contract.sha256(self.tool),
                str(self.wrf): contract.sha256(self.wrf),
                str(self.top): contract.sha256(self.top),
                str(self.parent_archive): contract.sha256(self.parent_archive),
                str(self.external): contract.sha256(self.external),
            },
        }
        self.base_receipt = self.root / "base.json"
        self.base_receipt.write_text(json.dumps(self.base))
        self.receipt = self.root / "build.json"
        link_argv = [str(self.tool), "-o", str(self.exe), "-O3", "-ip",
                     str(self.copied_wrf), str(self.copied_top), str(self.archive),
                     str(self.observer), str(self.external), "-qopenmp"]
        row = {
            "member": "solve_em.o",
            "source_path": str(self.source), "source_sha256": contract.sha256(self.source),
            "patched_source_path": str(self.patched), "patched_source_sha256": contract.sha256(self.patched),
            "generated_source_path": str(self.generated), "generated_source_sha256": contract.sha256(self.generated),
            "object_path": str(self.obj), "object_sha256": contract.sha256(self.obj),
            "compile_argv": [str(contract.IFX), "-c", str(self.generated), "-o", str(self.obj)],
        }
        self.record = {
            "schema": "pr85_joint_moment_native_build_v1", "status": "PASS_SCOPED_BUILD",
            "parent_executable_path": str(self.parent_exe), "parent_executable_sha256": contract.sha256(self.parent_exe),
            "parent_archive_path": str(self.parent_archive), "parent_archive_sha256": contract.sha256(self.parent_archive),
            "candidate_executable_path": str(self.exe), "candidate_executable_sha256": contract.sha256(self.exe),
            "candidate_archive_path": str(self.archive), "candidate_archive_sha256": contract.sha256(self.archive),
            "replaced_members": ["solve_em.o"],
            "compiler_profile_sha256": contract.PROFILE_SHA256,
            "compiler_path": str(contract.IFX), "compiler_sha256": contract.IFX_SHA256,
            "compiler_version": contract.IFX_VERSION,
            "observer_source_path": str(self.observer_source), "observer_source_sha256": contract.sha256(self.observer_source),
            "observer_object_path": str(self.observer), "observer_object_sha256": contract.sha256(self.observer),
            "observer_compile_argv": [str(contract.IFX), "-O0", "-c", str(self.observer_source), "-o", str(self.observer)],
            "compiled_objects": [row], "supplemental_replacements": [], "compiled_member_provenance": [row],
            "ordered_parent_members": [list(item) for item in archive_member_hashes(self.parent_archive)],
            "ordered_candidate_members": [list(item) for item in archive_member_hashes(self.archive)],
            "link_argv": link_argv, "link_argv_nul_sha256": contract.sha256_argv(link_argv),
            "link_inputs_sha256": {str(path): contract.sha256(path) for path in
                                   (self.tool, self.copied_wrf, self.copied_top, self.archive, self.observer, self.external)},
            "link_cwd": str(self.build), "model_run": False,
        }
        self.patches = patch.multiple(contract, BASE_RECEIPT=self.base_receipt,
                                      BASE_RECEIPT_SHA256=contract.sha256(self.base_receipt),
                                      PARENT_EXE_SHA256=contract.sha256(self.parent_exe),
                                      PARENT_ARCHIVE_SHA256=contract.sha256(self.parent_archive))
        self.patches.start()
        self.addCleanup(self.patches.stop)

    def validate(self):
        self.receipt.write_text(json.dumps(self.record))
        return contract.validate_consumer_build(self.receipt, self.exe,
                                                contract.sha256(self.parent_exe))

    def test_valid_recipe_is_scoped_and_does_not_claim_physics(self):
        result = self.validate()
        self.assertEqual(result["status"], "PASS_SCOPED_BUILD")
        self.assertEqual(result["physical_acceptance"], "UNASSESSED")
        self.assertIn("transitive libraries", result["scope"])

    def test_wrong_output_rejected(self):
        self.record["link_argv"][2] = str(self.root / "other.exe")
        self.record["link_argv_nul_sha256"] = contract.sha256_argv(self.record["link_argv"])
        with self.assertRaisesRegex(ValueError, "-o does not name"):
            self.validate()

    def test_missing_or_duplicate_candidate_archive_rejected(self):
        original = list(self.record["link_argv"])
        for altered in (original[:original.index(str(self.archive))] +
                        original[original.index(str(self.archive)) + 1:],
                        original[:original.index(str(self.archive)) + 1] +
                        [str(self.archive)] + original[original.index(str(self.archive)) + 1:]):
            with self.subTest(archive_occurrences=altered.count(str(self.archive))):
                self.record["link_argv"] = altered
                self.record["link_argv_nul_sha256"] = contract.sha256_argv(altered)
                with self.assertRaisesRegex(ValueError, "candidate archive exactly once"):
                    self.validate()
        self.record["link_argv"] = original
        self.record["link_argv_nul_sha256"] = contract.sha256_argv(original)

    def test_inherited_flag_change_rejected(self):
        self.record["link_argv"][3] = "-O2"
        self.record["link_argv_nul_sha256"] = contract.sha256_argv(self.record["link_argv"])
        with self.assertRaisesRegex(ValueError, "differs from pinned PR84"):
            self.validate()

    def test_parent_link_objects_must_be_byte_preserved(self):
        self.copied_wrf.write_bytes(b"changed parent object")
        self.record["link_inputs_sha256"][str(self.copied_wrf)] = contract.sha256(self.copied_wrf)
        with self.assertRaisesRegex(ValueError, "copied parent wrf.o identity"):
            self.validate()

    def test_observer_compile_binding_required(self):
        self.record["observer_compile_argv"][-1] = str(self.root / "other.o")
        with self.assertRaisesRegex(ValueError, "observer compile argv"):
            self.validate()

    def test_replacement_compile_cannot_claim_another_compiler_or_source(self):
        row = self.record["compiled_member_provenance"][0]
        original = list(row["compile_argv"])
        for position, replacement in ((0, "/unapproved/compiler"),
                                       (2, str(self.source))):
            with self.subTest(position=position):
                row["compile_argv"] = original.copy()
                row["compile_argv"][position] = replacement
                with self.assertRaisesRegex(ValueError, "compile argv is not bound"):
                    self.validate()

    def test_patched_source_hash_is_checked(self):
        self.patched.write_bytes(b"post-build change")
        with self.assertRaisesRegex(ValueError, "patched source identity"):
            self.validate()

    def test_candidate_archive_change_outside_manifest_rejected(self):
        write_archive(self.archive, [("solve_em.o", b"new"), ("kdm6.o", b"changed")])
        self.record["candidate_archive_sha256"] = contract.sha256(self.archive)
        self.record["link_inputs_sha256"][str(self.archive)] = contract.sha256(self.archive)
        self.record["ordered_candidate_members"] = [list(item) for item in archive_member_hashes(self.archive)]
        with self.assertRaisesRegex(ValueError, "archive changes differ"):
            self.validate()

    def test_kdm6_replacement_requires_explicit_patch_receipt(self):
        parent_rows = [(contract.KDM6_MEMBER, contract.KDM6_MEMBER_SHA256)]
        with self.assertRaisesRegex(ValueError, "explicit sedimentation patch receipt"):
            contract.validate_kdm6_replacement(
                {}, [], [contract.KDM6_MEMBER], parent_rows)

    def test_existing_replacement_set_does_not_require_kdm6_receipt(self):
        contract.validate_kdm6_replacement(
            {}, [], ["solve_em.o"], [(contract.KDM6_MEMBER,
                                      contract.KDM6_MEMBER_SHA256)])

    def test_kdm6_replacement_accepts_only_pinned_recipe_and_source_provenance(self):
        source = self.root / "module_mp_kdm6.F"
        source.write_text("module source\n")
        patched = self.root / "phys/module_mp_kdm6.F"
        patched.parent.mkdir()
        patched.write_text("patched module source\n")
        generated = self.root / "module_mp_kdm6.f90"
        generated.write_text("preprocessed module source\n")
        obj = self.root / "module_mp_kdm6.o"
        obj.write_bytes(b"new KDM6 object")
        patch_file = self.root / "kdm6.patch"
        patch_file.write_text("pinned sedimentation patch\n")
        parent_obj = self.root / "parent/module_mp_kdm6.o"
        parent_obj.parent.mkdir(exist_ok=True)
        parent_obj.write_bytes(b"parent KDM6 object")
        parent_source_hash = contract.sha256(source)
        parent_object_hash = "pinned parent archive member"
        original_argv = [str(contract.IFX), "-stand", "f08", "-fpp", "-Iparent-modules",
                         "-free", "-c", str(source), "-o", str(parent_obj)]
        source_receipt = self.root / "pr84.json"
        source_receipt.write_text(json.dumps({
            "production_source_sha256": parent_source_hash,
            "production_object_sha256": parent_object_hash,
            "production_compile_argv": original_argv,
        }))
        preprocess_argv = [str(contract.IFX), "-stand", "f08", "-fpp", "-Iparent-modules",
                           "-free", str(patched), "-EP"]
        compile_argv = [str(contract.IFX), "-stand", "f08", "-Iparent-modules", "-free",
                        "-c", str(generated), "-o", str(obj)]
        row = {
            "member": contract.KDM6_MEMBER,
            "source_path": str(source), "source_sha256": parent_source_hash,
            "patched_source_path": str(patched), "patched_source_sha256": contract.sha256(patched),
            "generated_source_path": str(generated), "generated_source_sha256": contract.sha256(generated),
            "object_path": str(obj), "object_sha256": contract.sha256(obj),
            "compile_argv": compile_argv, "preprocess_argv": preprocess_argv,
            "preprocessor_defines": [],
            "source_receipt_path": str(source_receipt),
            "source_receipt_sha256": contract.sha256(source_receipt),
            "compile_recipe_source_path": str(source_receipt),
            "compile_recipe_source_sha256": contract.sha256(source_receipt),
            "patches": {"kdm6_sedimentation": {
                "path": str(patch_file), "sha256": contract.sha256(patch_file)}},
        }
        record = {"kdm6_sedimentation_patch_path": str(patch_file),
                  "kdm6_sedimentation_patch_sha256": contract.sha256(patch_file)}
        with patch.multiple(contract,
                            BASE_RECEIPT=source_receipt,
                            BASE_RECEIPT_SHA256=contract.sha256(source_receipt),
                            KDM6_SOURCE_SHA256=parent_source_hash,
                            KDM6_MEMBER_SHA256=parent_object_hash):
            contract.validate_kdm6_replacement(
                record, [row], [contract.KDM6_MEMBER],
                [(contract.KDM6_MEMBER, parent_object_hash)])


if __name__ == "__main__":
    unittest.main()
