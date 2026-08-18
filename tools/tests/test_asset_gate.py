#!/usr/bin/env python3
"""Tests for the commercial-asset gate.

Each test builds a throwaway repository in a temp directory, so the real one
is never touched. The shape is deliberately symmetrical: one test proves a
correct tree passes, and the rest prove that each individual way of losing
the guarantee fails. A gate that only ever says "yes" is worse than no gate,
because it manufactures confidence.

Run:  python3 tools/tests/test_asset_gate.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asset_gate  # noqa: E402

GATE = Path(__file__).resolve().parent.parent / "asset_gate.py"

CLEARED_DEP = {
    "component": "Blender",
    "licence": "GPL-3.0-or-later (tool)",
    "commercial_use": True,
    "evidence_url": "https://www.blender.org/about/license/",
}

PRESET = """[preset.0]

name="Linux"
platform="Linux"
export_filter="all_resources"
include_filter=""
exclude_filter="{exclude}"
export_path="build/game.x86_64"
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GateFixture:
    """A minimal but complete repository that passes the gate."""

    def __init__(self, root: Path):
        self.root = root
        (root / "assets/models").mkdir(parents=True)
        (root / "art/character/ai_generated").mkdir(parents=True)
        (root / "scenes").mkdir()

        self.asset_bytes = b"glTF-pretend-binary"
        (root / "assets/models/barn.glb").write_bytes(self.asset_bytes)
        (root / "assets/models/barn.glb.import").write_text(
            'source_file="res://assets/models/barn.glb"\n'
        )
        (root / "scenes/world.tscn").write_text(
            '[gd_scene]\n[ext_resource path="res://assets/models/barn.glb"]\n'
        )

        (root / "art/character/ai_generated/.gdignore").write_text("")
        (root / "art/character/ai_generated/EVALUATION_ONLY.md").write_text("# evaluation only\n")
        (root / "art/character/ai_generated/candidate.glb").write_bytes(b"ai-generated-mesh")

        (root / "export_presets.cfg").write_text(
            PRESET.format(exclude="art/character/ai_generated/*")
        )

        self.manifest = {
            "schema_version": 1,
            "production_roots": ["assets"],
            "evaluation_roots": ["art/character/ai_generated"],
            "ignored_suffixes": [".import", ".uid"],
            "ignored_names": [".gdignore"],
            "reference_scan_roots": ["assets", "scenes"],
            "reference_scan_files": [],
            "export_preset_globs": ["export_presets.cfg"],
            "assets": {
                "assets/models/barn.glb": {
                    "source": "generated in-repo",
                    "generator": "tools/blender/gen_assets.py",
                    "dependency_licences": [dict(CLEARED_DEP)],
                    "evidence_urls": ["repo:tools/blender/gen_assets.py"],
                    "commercial_status": "cleared",
                    "sha256": sha256_bytes(self.asset_bytes),
                    "clearance": {
                        "cleared_by": "Thomas",
                        "cleared_on": "2026-08-18",
                        "evidence": "reviewed the generating script",
                        "method": "human-review",
                    },
                }
            },
        }
        self.write()

    @property
    def entry(self) -> dict:
        return self.manifest["assets"]["assets/models/barn.glb"]

    def write(self) -> None:
        (self.root / asset_gate.MANIFEST_NAME).write_text(json.dumps(self.manifest, indent=2))

    def check(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GATE), "--root", str(self.root), "check", *extra],
            capture_output=True,
            text=True,
        )

    def check_package(self, *paths: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GATE), "--root", str(self.root), "check-package", *paths],
            capture_output=True,
            text=True,
        )


class GateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="rv-asset-gate-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fx = GateFixture(Path(self.tmp))

    def assertPasses(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(
            result.returncode, 0, f"expected pass, got:\n{result.stdout}\n{result.stderr}"
        )

    def assertFailsWith(self, result: subprocess.CompletedProcess, fragment: str) -> None:
        self.assertNotEqual(result.returncode, 0, f"expected failure, got:\n{result.stdout}")
        self.assertIn(fragment, result.stdout + result.stderr)


class TestAllowed(GateTestCase):
    def test_complete_tree_passes(self):
        self.assertPasses(self.fx.check())

    def test_human_reviewed_clearance_passes_strict_baseline(self):
        self.assertPasses(self.fx.check("--strict-baseline"))

    def test_evaluation_asset_beside_markers_is_not_itself_a_failure(self):
        # Evaluation output may exist on disk; the gate's job is to keep it
        # out of production, not to forbid the pilot from producing anything.
        self.assertTrue((self.fx.root / "art/character/ai_generated/candidate.glb").exists())
        self.assertPasses(self.fx.check())

    def test_clean_package_passes(self):
        pack = Path(self.tmp) / "build" / "game.pck"
        pack.parent.mkdir()
        pack.write_bytes(b"res://assets/models/barn.glb" + b"\x00" * 32)
        self.assertPasses(self.fx.check_package(str(pack)))


class TestRejectedManifest(GateTestCase):
    def test_production_file_without_entry_fails(self):
        (self.fx.root / "assets/models/silo.glb").write_bytes(b"unknown-origin")
        self.assertFailsWith(self.fx.check(), "no provenance entry")

    def test_unknown_status_fails(self):
        self.fx.entry["commercial_status"] = "unknown"
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "production requires 'cleared'")

    def test_evaluation_only_status_fails(self):
        self.fx.entry["commercial_status"] = "evaluation_only"
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "production requires 'cleared'")

    def test_status_the_gate_has_never_heard_of_fails(self):
        self.fx.entry["commercial_status"] = "probably_fine"
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "unrecognised commercial_status")

    def test_missing_required_field_fails(self):
        del self.fx.entry["generator"]
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "missing required field 'generator'")

    def test_empty_source_fails(self):
        self.fx.entry["source"] = "   "
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "'source' is empty")

    def test_no_dependency_licences_fails(self):
        self.fx.entry["dependency_licences"] = []
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "must be a non-empty list")

    def test_non_commercial_dependency_fails(self):
        self.fx.entry["dependency_licences"] = [
            {
                "component": "nvdiffrast",
                "licence": "NVIDIA Source Code License (1-Way Commercial)",
                "commercial_use": False,
                "evidence_url": "https://github.com/NVlabs/nvdiffrast/blob/main/LICENSE.txt",
            }
        ]
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "cannot ship")

    def test_missing_evidence_urls_fails(self):
        self.fx.entry["evidence_urls"] = []
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "'evidence_urls' must be a non-empty list")

    def test_bare_evidence_url_fails(self):
        self.fx.entry["evidence_urls"] = ["ask Dave"]
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "must start with one of")

    def test_cleared_without_clearance_block_fails(self):
        del self.fx.entry["clearance"]
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "no 'clearance' block")

    def test_clearance_without_named_person_fails(self):
        self.fx.entry["clearance"]["cleared_by"] = ""
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "clearance is missing 'cleared_by'")

    def test_changed_bytes_invalidate_clearance(self):
        (self.fx.root / "assets/models/barn.glb").write_bytes(b"swapped-after-clearance")
        self.assertFailsWith(self.fx.check(), "needs re-clearance")

    def test_stale_entry_fails(self):
        (self.fx.root / "assets/models/barn.glb").unlink()
        self.assertFailsWith(self.fx.check(), "no matching file on disk")

    def test_baseline_clearance_fails_under_strict_baseline(self):
        self.fx.entry["clearance"]["method"] = "baseline"
        self.fx.write()
        self.assertPasses(self.fx.check())
        self.assertFailsWith(self.fx.check("--strict-baseline"), "not been confirmed by a human")

    def test_missing_manifest_fails(self):
        (self.fx.root / asset_gate.MANIFEST_NAME).unlink()
        self.assertFailsWith(self.fx.check(), "no provenance manifest")

    def test_overlapping_roots_fail(self):
        self.fx.manifest["evaluation_roots"].append("assets/models")
        self.fx.write()
        self.assertFailsWith(self.fx.check(), "overlap")


class TestRejectedIsolation(GateTestCase):
    def test_missing_gdignore_fails(self):
        (self.fx.root / "art/character/ai_generated/.gdignore").unlink()
        self.assertFailsWith(self.fx.check(), ".gdignore is missing")

    def test_missing_evaluation_only_doc_fails(self):
        (self.fx.root / "art/character/ai_generated/EVALUATION_ONLY.md").unlink()
        self.assertFailsWith(self.fx.check(), "EVALUATION_ONLY.md is missing")

    def test_scene_referencing_evaluation_path_fails(self):
        (self.fx.root / "scenes/world.tscn").write_text(
            '[ext_resource path="res://art/character/ai_generated/candidate.glb"]\n'
        )
        self.assertFailsWith(self.fx.check(), "references evaluation-only path")

    def test_import_file_referencing_evaluation_path_fails(self):
        (self.fx.root / "assets/models/barn.glb.import").write_text(
            'source_file="res://art/character/ai_generated/candidate.glb"\n'
        )
        self.assertFailsWith(self.fx.check(), "references evaluation-only path")

    def test_preset_without_exclusion_fails(self):
        (self.fx.root / "export_presets.cfg").write_text(PRESET.format(exclude="build/*"))
        self.assertFailsWith(self.fx.check(), "does not exclude art/character/ai_generated")

    def test_sync_presets_repairs_a_preset(self):
        (self.fx.root / "export_presets.cfg").write_text(PRESET.format(exclude="build/*"))
        self.assertFailsWith(self.fx.check(), "does not exclude")
        subprocess.run(
            [sys.executable, str(GATE), "--root", str(self.fx.root), "sync-presets"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertPasses(self.fx.check())

    def test_wildcard_parent_exclusion_is_accepted(self):
        (self.fx.root / "export_presets.cfg").write_text(PRESET.format(exclude="art/*"))
        self.assertPasses(self.fx.check())


class TestRejectedPackage(GateTestCase):
    def test_package_containing_evaluation_path_fails(self):
        pack = Path(self.tmp) / "build" / "game.pck"
        pack.parent.mkdir()
        pack.write_bytes(b"\x00res://art/character/ai_generated/candidate.glb\x00")
        self.assertFailsWith(self.fx.check_package(str(pack)), "cannot ship")

    def test_zip_containing_evaluation_path_fails(self):
        archive = Path(self.tmp) / "game.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("art/character/ai_generated/candidate.glb", "mesh")
        self.assertFailsWith(self.fx.check_package(str(archive)), "cannot ship")

    def test_exported_directory_is_walked(self):
        out = Path(self.tmp) / "build" / "linux"
        out.mkdir(parents=True)
        (out / "game.x86_64").write_bytes(b"res://art/character/ai_generated/candidate.glb")
        self.assertFailsWith(self.fx.check_package(str(out)), "cannot ship")

    def test_missing_package_fails_rather_than_passing_vacuously(self):
        self.assertFailsWith(self.fx.check_package(str(Path(self.tmp) / "nope.pck")), "does not exist")

    def test_no_package_argument_fails(self):
        self.assertFailsWith(self.fx.check_package(), "refusing to certify")


class TestPromotion(GateTestCase):
    """The one path that turns evaluation output into a shippable asset."""

    def promote(self, **overrides):
        manifest = json.loads((self.fx.root / asset_gate.MANIFEST_NAME).read_text())
        kwargs = dict(
            source="TRELLIS.2 evaluation run 2026-08-18",
            generator="Pixal3D -> TRELLIS.2",
            deps=[dict(CLEARED_DEP)],
            evidence_urls=["https://example.invalid/legal-review-42"],
            cleared_by="Thomas",
            evidence="legal review 42 confirmed nvdiffrast is absent from this path",
            cleared_on="2026-08-18",
            confirm=lambda: True,
        )
        kwargs.update(overrides)
        return asset_gate.promote(
            self.fx.root,
            manifest,
            self.fx.root / "art/character/ai_generated/candidate.glb",
            "assets/models/candidate.glb",
            **kwargs,
        )

    def test_promotion_with_full_evidence_produces_a_passing_tree(self):
        self.promote()
        self.assertTrue((self.fx.root / "assets/models/candidate.glb").exists())
        self.assertPasses(self.fx.check("--strict-baseline"))

    def test_promotion_records_human_review_not_baseline(self):
        self.promote()
        manifest = json.loads((self.fx.root / asset_gate.MANIFEST_NAME).read_text())
        entry = manifest["assets"]["assets/models/candidate.glb"]
        self.assertEqual(entry["commercial_status"], "cleared")
        self.assertEqual(entry["clearance"]["method"], "human-review")
        self.assertEqual(entry["clearance"]["cleared_by"], "Thomas")

    def test_declining_the_confirmation_copies_nothing(self):
        with self.assertRaises(asset_gate.GateError):
            self.promote(confirm=lambda: False)
        self.assertFalse((self.fx.root / "assets/models/candidate.glb").exists())

    def test_promotion_without_a_named_person_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            self.promote(cleared_by="  ")

    def test_promotion_without_evidence_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            self.promote(evidence="")

    def test_promotion_without_evidence_url_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            self.promote(evidence_urls=[])

    def test_promotion_of_non_commercial_dependency_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            self.promote(
                deps=[
                    {
                        "component": "nvdiffrast",
                        "licence": "NVIDIA 1-Way Commercial",
                        "commercial_use": False,
                        "evidence_url": "https://example.invalid/licence",
                    }
                ]
            )

    def test_promotion_outside_a_production_root_is_refused(self):
        manifest = json.loads((self.fx.root / asset_gate.MANIFEST_NAME).read_text())
        with self.assertRaises(asset_gate.GateError):
            asset_gate.promote(
                self.fx.root,
                manifest,
                self.fx.root / "art/character/ai_generated/candidate.glb",
                "art/character/ai_generated/promoted.glb",
                source="x",
                generator="y",
                deps=[dict(CLEARED_DEP)],
                evidence_urls=["https://example.invalid/e"],
                cleared_by="Thomas",
                evidence="e",
                cleared_on="2026-08-18",
                confirm=lambda: True,
            )

    def test_cli_promotion_is_refused_without_a_terminal(self):
        # The CLI confirmation reads /dev/tty, so a piped/automated caller --
        # a script, a CI job, an agent -- cannot answer it. This is the
        # mechanical part of "agents must not clear assets".
        result = subprocess.run(
            [
                sys.executable, str(GATE), "--root", str(self.fx.root), "promote",
                str(self.fx.root / "art/character/ai_generated/candidate.glb"),
                "assets/models/candidate.glb",
                "--source", "evaluation run",
                "--generator", "TRELLIS.2",
                "--dep", "Blender|GPL|true|https://example.invalid/l",
                "--evidence-url", "https://example.invalid/review",
                "--cleared-by", "An Agent",
                "--evidence", "trust me",
                "--cleared-on", "2026-08-18",
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach from any inherited terminal
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not confirmed", result.stdout + result.stderr)
        self.assertFalse((self.fx.root / "assets/models/candidate.glb").exists())


class TestDependencySpec(unittest.TestCase):
    def test_parses_four_fields(self):
        dep = asset_gate.parse_dep("Blender|GPL-3.0|true|https://example.invalid/l")
        self.assertEqual(dep["component"], "Blender")
        self.assertIs(dep["commercial_use"], True)

    def test_wrong_field_count_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            asset_gate.parse_dep("Blender|GPL-3.0|true")

    def test_non_boolean_commercial_use_is_refused(self):
        with self.assertRaises(asset_gate.GateError):
            asset_gate.parse_dep("Blender|GPL-3.0|probably|https://example.invalid/l")


if __name__ == "__main__":
    unittest.main(verbosity=2)
