#!/usr/bin/env python3
"""Fail-closed commercial-asset gate.

Nothing reaches a production build unless the provenance manifest says, in
machine-readable terms, where it came from and that someone cleared it for
commercial use. Absence of information is treated as *not cleared* — a file
with no manifest entry, an unrecognised status, or a manifest entry whose
recorded hash no longer matches the bytes on disk all fail the gate.

The concrete risk this exists for: the AI asset-generation pilot under
`art/character/ai_generated/` produces output whose rendering dependencies
(NVIDIA nvdiffrast/nvdiffrec) are licensed for research/evaluation only. That
output must never be imported by Godot, referenced by a scene, or land in an
exported package. See `art/character/ai_generated/EVALUATION_ONLY.md`.

Commands
--------
  check                 gate the working tree (manifest, markers, references,
                        export presets)
  check-package PATH..  gate a built artifact: no evaluation-only path may
                        appear anywhere in its bytes
  sync-presets          write the required exclusions into export presets
  promote SRC DST       copy an evaluated asset into production — refuses
                        unless a human supplies clearance evidence at a TTY

Exit status is 0 only when every check passes. Anything else is a failure.
Stdlib only, so CI needs no install step.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "asset_provenance.json"
SCHEMA_VERSION = 1

# The only status that may ship. Every other value — including a value this
# gate has never heard of — is a failure, which is what makes it fail-closed.
STATUS_CLEARED = "cleared"
KNOWN_STATUSES = {STATUS_CLEARED, "evaluation_only", "unknown"}

# A clearance recorded by `promote` after a human reviewed it, versus one
# seeded when the gate was introduced. Both ship; baseline ones are reported
# so the backlog of un-reviewed inherited assets stays visible.
METHOD_HUMAN = "human-review"
METHOD_BASELINE = "baseline"
KNOWN_METHODS = {METHOD_HUMAN, METHOD_BASELINE}

REQUIRED_ENTRY_FIELDS = (
    "source",
    "generator",
    "dependency_licences",
    "evidence_urls",
    "commercial_status",
    "sha256",
)
REQUIRED_CLEARANCE_FIELDS = ("cleared_by", "cleared_on", "evidence", "method")

# Where an evidence URL may point. `repo:` covers in-tree evidence (a script,
# a licence record) that has no external URL.
EVIDENCE_SCHEMES = ("https://", "http://", "repo:", "file:")

# File types that carry a reference to another resource, and so could smuggle
# an evaluation-only path into the game data.
REFERENCE_SUFFIXES = (".gd", ".tscn", ".tres", ".scn", ".res", ".import", ".gdshader", ".godot", ".cfg")


class GateError(Exception):
    """Configuration or usage problem — distinct from a gate failure."""


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    baseline: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def ok(self) -> bool:
        return not self.failures


# --------------------------------------------------------------------------
# manifest


def manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def load_manifest(root: Path) -> dict:
    path = manifest_path(root)
    if not path.is_file():
        raise GateError(
            f"no provenance manifest at {path}\n"
            "The gate cannot certify a build without one; create it or run "
            "the gate against a tree that has one."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"{MANIFEST_NAME} is not valid JSON: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise GateError(
            f"{MANIFEST_NAME} schema_version is {data.get('schema_version')!r}, "
            f"this gate understands {SCHEMA_VERSION}"
        )
    for key in ("production_roots", "evaluation_roots", "assets"):
        if key not in data:
            raise GateError(f"{MANIFEST_NAME} is missing required key {key!r}")
    return data


def save_manifest(root: Path, data: dict) -> None:
    path = manifest_path(root)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def production_files(root: Path, manifest: dict) -> list[str]:
    """Every file under a production root that needs a provenance entry."""
    ignored_suffixes = tuple(manifest.get("ignored_suffixes", []))
    ignored_names = set(manifest.get("ignored_names", []))
    found: list[str] = []
    for rel_root in manifest["production_roots"]:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.name in ignored_names or path.name.startswith("."):
                continue
            if path.suffix in ignored_suffixes:
                continue
            found.append(path.relative_to(root).as_posix())
    return found


# --------------------------------------------------------------------------
# checks


def check_evaluation_markers(root: Path, manifest: dict, report: Report) -> None:
    """Every evaluation root must be walled off from Godot and self-documenting.

    `.gdignore` keeps the engine from importing the directory at all;
    EVALUATION_ONLY.md states why the contents cannot ship. Losing either one
    silently is exactly how evaluation output ends up in a build, so their
    absence is a gate failure rather than a warning.
    """
    for rel_root in manifest["evaluation_roots"]:
        base = root / rel_root
        if not base.is_dir():
            report.note(f"evaluation root {rel_root} does not exist (nothing to wall off)")
            continue
        if not (base / ".gdignore").is_file():
            report.fail(f"{rel_root}/.gdignore is missing — Godot would import evaluation output")
        if not (base / "EVALUATION_ONLY.md").is_file():
            report.fail(f"{rel_root}/EVALUATION_ONLY.md is missing — the licence restriction is undocumented")


def check_roots_disjoint(manifest: dict, report: Report) -> None:
    for prod in manifest["production_roots"]:
        for evaluation in manifest["evaluation_roots"]:
            prod_p = Path(prod)
            eval_p = Path(evaluation)
            if prod_p == eval_p or eval_p in prod_p.parents or prod_p in eval_p.parents:
                report.fail(
                    f"production root {prod} and evaluation root {evaluation} overlap — "
                    "evaluation output would be shippable by construction"
                )


def check_entry(rel: str, entry: object, root: Path, report: Report, strict_baseline: bool) -> None:
    if not isinstance(entry, dict):
        report.fail(f"{rel}: manifest entry is not an object")
        return

    for key in REQUIRED_ENTRY_FIELDS:
        if key not in entry:
            report.fail(f"{rel}: missing required field {key!r}")
            return

    for key in ("source", "generator"):
        if not str(entry[key]).strip():
            report.fail(f"{rel}: {key!r} is empty")

    urls = entry["evidence_urls"]
    if not isinstance(urls, list) or not urls:
        report.fail(f"{rel}: 'evidence_urls' must be a non-empty list")
    else:
        for url in urls:
            if not isinstance(url, str) or not url.startswith(EVIDENCE_SCHEMES):
                report.fail(
                    f"{rel}: evidence url {url!r} must start with one of {', '.join(EVIDENCE_SCHEMES)}"
                )

    deps = entry["dependency_licences"]
    if not isinstance(deps, list) or not deps:
        report.fail(
            f"{rel}: 'dependency_licences' must be a non-empty list — "
            "state 'none' explicitly rather than leaving it blank"
        )
    else:
        for dep in deps:
            if not isinstance(dep, dict):
                report.fail(f"{rel}: dependency licence entry is not an object")
                continue
            for key in ("component", "licence", "commercial_use", "evidence_url"):
                if key not in dep:
                    report.fail(f"{rel}: dependency licence missing {key!r}")
            if dep.get("commercial_use") is not True:
                report.fail(
                    f"{rel}: dependency {dep.get('component')!r} is licensed "
                    f"{dep.get('licence')!r} with commercial_use="
                    f"{dep.get('commercial_use')!r} — cannot ship"
                )

    status = entry["commercial_status"]
    if status not in KNOWN_STATUSES:
        report.fail(f"{rel}: unrecognised commercial_status {status!r} — treated as not cleared")
        return
    if status != STATUS_CLEARED:
        report.fail(f"{rel}: commercial_status is {status!r}, production requires {STATUS_CLEARED!r}")
        return

    clearance = entry.get("clearance")
    if not isinstance(clearance, dict):
        report.fail(f"{rel}: status is 'cleared' but there is no 'clearance' block")
        return
    for key in REQUIRED_CLEARANCE_FIELDS:
        if not str(clearance.get(key, "")).strip():
            report.fail(f"{rel}: clearance is missing {key!r}")
    method = clearance.get("method")
    if method not in KNOWN_METHODS:
        report.fail(f"{rel}: unrecognised clearance method {method!r}")
    elif method == METHOD_BASELINE:
        if strict_baseline:
            report.fail(f"{rel}: baseline clearance has not been confirmed by a human review")
        else:
            report.baseline.append(rel)

    # A clearance covers the bytes that were reviewed, not the path. If the
    # file changed, the clearance no longer applies to what is on disk.
    path = root / rel
    if path.is_file():
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            report.fail(
                f"{rel}: content changed since it was cleared "
                f"(manifest {entry['sha256'][:16]}…, on disk {actual[:16]}…) — needs re-clearance"
            )


def check_manifest_coverage(root: Path, manifest: dict, report: Report, strict_baseline: bool) -> None:
    assets = manifest["assets"]
    on_disk = production_files(root, manifest)

    for rel in on_disk:
        report.checked += 1
        if rel not in assets:
            report.fail(f"{rel}: no provenance entry — unknown provenance is not shippable")
            continue
        check_entry(rel, assets[rel], root, report, strict_baseline)

    for rel in assets:
        if rel not in on_disk:
            report.fail(f"{rel}: manifest entry has no matching file on disk (stale entry)")


def evaluation_tokens(manifest: dict) -> list[str]:
    """Path fragments that must never appear in game data or a build."""
    tokens = {Path(r).as_posix() for r in manifest["evaluation_roots"]}
    tokens.update(manifest.get("extra_forbidden_tokens", []))
    return sorted(tokens)


def check_references(root: Path, manifest: dict, report: Report) -> None:
    """No script, scene, resource or import file may name an evaluation path."""
    tokens = evaluation_tokens(manifest)
    candidates: list[Path] = []

    for rel_root in manifest.get("reference_scan_roots", []):
        base = root / rel_root
        if not base.is_dir():
            continue
        candidates.extend(
            path
            for path in sorted(base.rglob("*"))
            if path.is_file() and path.suffix in REFERENCE_SUFFIXES
        )
    for rel_file in manifest.get("reference_scan_files", []):
        path = root / rel_file
        if path.is_file():
            candidates.append(path)

    for path in dict.fromkeys(candidates):
        rel = path.relative_to(root).as_posix()
        report.checked += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            report.fail(f"{rel}: unreadable ({exc})")
            continue
        for token in tokens:
            if token in text:
                report.fail(f"{rel}: references evaluation-only path {token!r}")


# --------------------------------------------------------------------------
# export presets


PRESET_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
PRESET_KV_RE = re.compile(r"^(?P<key>[A-Za-z0-9_/.]+)\s*=\s*(?P<value>.*)$")


def parse_presets(text: str) -> dict[str, dict[str, str]]:
    """Minimal reader for Godot's export_presets.cfg.

    Deliberately not configparser: Godot writes values (PackedStringArray(...),
    Object(...)) that configparser is happy to read but unhappy to write back,
    and this gate must be able to rewrite the file without corrupting it.
    """
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = PRESET_SECTION_RE.match(line)
        if match:
            current = match.group("name")
            sections.setdefault(current, {})
            continue
        if current is None:
            continue
        kv = PRESET_KV_RE.match(line)
        if kv:
            sections[current][kv.group("key")] = kv.group("value").strip()
    return sections


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def split_filters(value: str) -> list[str]:
    return [part.strip() for part in unquote(value).split(",") if part.strip()]


def pattern_covers_root(patterns: list[str], rel_root: str) -> bool:
    """True if some exclude pattern hides everything under rel_root."""
    probes = [f"{rel_root}/file.glb", f"{rel_root}/nested/dir/file.png"]
    for pattern in patterns:
        if all(fnmatch.fnmatch(probe, pattern) for probe in probes):
            return True
    return False


def preset_files(root: Path, manifest: dict) -> list[Path]:
    found: list[Path] = []
    for pattern in manifest.get("export_preset_globs", ["export_presets.cfg"]):
        found.extend(sorted(root.glob(pattern)))
    return found


def check_export_presets(root: Path, manifest: dict, report: Report) -> None:
    """Every preset must exclude every evaluation root.

    A preset file that does not exist is not a pass by omission: the release
    workflow supplies the committed preset, and a local export without one
    cannot happen either. Absence is reported, and a preset that exists but
    omits an exclusion fails.
    """
    files = preset_files(root, manifest)
    if not files:
        report.note("no export presets found — nothing to check (a release export supplies its own)")
        return
    for path in files:
        sections = parse_presets(path.read_text(encoding="utf-8"))
        preset_sections = [n for n in sections if re.fullmatch(r"preset\.\d+", n)]
        if not preset_sections:
            report.fail(f"{path.relative_to(root)}: contains no export presets")
            continue
        for name in preset_sections:
            patterns = split_filters(sections[name].get("exclude_filter", ""))
            label = f"{path.relative_to(root)} [{name}] ({unquote(sections[name].get('name', '?'))})"
            for rel_root in manifest["evaluation_roots"]:
                if not pattern_covers_root(patterns, rel_root):
                    report.fail(f"{label}: exclude_filter does not exclude {rel_root}")


def sync_presets(root: Path, manifest: dict) -> list[str]:
    """Add the required exclusions to every preset. Returns changed files."""
    changed: list[str] = []
    for path in preset_files(root, manifest):
        text = path.read_text(encoding="utf-8")
        sections = parse_presets(text)
        lines = text.splitlines()
        current: str | None = None
        out: list[str] = []
        touched = False
        for line in lines:
            match = PRESET_SECTION_RE.match(line)
            if match:
                current = match.group("name")
            kv = PRESET_KV_RE.match(line)
            if (
                current
                and re.fullmatch(r"preset\.\d+", current)
                and kv
                and kv.group("key") == "exclude_filter"
            ):
                patterns = split_filters(kv.group("value"))
                missing = [
                    f"{rel_root}/*"
                    for rel_root in manifest["evaluation_roots"]
                    if not pattern_covers_root(patterns, rel_root)
                ]
                if missing:
                    patterns.extend(missing)
                    line = 'exclude_filter="{}"'.format(", ".join(patterns))
                    touched = True
            out.append(line)
        # A preset with no exclude_filter line at all still has to be fixed.
        for name in [n for n in sections if re.fullmatch(r"preset\.\d+", n)]:
            if "exclude_filter" not in sections[name]:
                raise GateError(
                    f"{path.relative_to(root)} [{name}] has no exclude_filter line; "
                    "add one (it may be empty) and re-run"
                )
        if touched:
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            changed.append(path.relative_to(root).as_posix())
    return changed


# --------------------------------------------------------------------------
# built package


def iter_package_members(path: Path):
    """Yield (label, bytes) for everything inside a built artifact."""
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                yield child.as_posix(), child.read_bytes()
        return
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                yield f"{path.as_posix()}!{name}", name.encode("utf-8")
                if not name.endswith("/"):
                    yield f"{path.as_posix()}!{name}", archive.read(name)
        return
    # A .pck — or a binary with the pck embedded — stores res:// paths as
    # plain strings, so scanning the raw bytes finds them without needing a
    # pck parser.
    yield path.as_posix(), path.read_bytes()


def check_package(root: Path, manifest: dict, targets: list[Path], report: Report) -> None:
    tokens = [token.encode("utf-8") for token in evaluation_tokens(manifest)]
    if not targets:
        report.fail("no package paths given — refusing to certify an unspecified build")
        return
    for target in targets:
        if not target.exists():
            report.fail(f"{target}: package does not exist — nothing was verified")
            continue
        report.checked += 1
        for label, blob in iter_package_members(target):
            for token in tokens:
                if token in blob:
                    report.fail(
                        f"{label}: contains evaluation-only path "
                        f"{token.decode('utf-8')!r} — this build cannot ship"
                    )


# --------------------------------------------------------------------------
# promotion


def parse_dep(spec: str) -> dict:
    """`component|licence|commercial_use|evidence_url`"""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 4:
        raise GateError(
            f"--dep {spec!r} must have 4 fields: "
            "'component|licence|commercial_use|evidence_url'"
        )
    commercial = parts[2].lower()
    if commercial not in ("true", "false"):
        raise GateError(f"--dep {spec!r}: commercial_use must be 'true' or 'false'")
    return {
        "component": parts[0],
        "licence": parts[1],
        "commercial_use": commercial == "true",
        "evidence_url": parts[3],
    }


def tty_confirm(prompt: str, phrase: str) -> bool:
    """Ask for a typed phrase on the controlling terminal.

    Reading /dev/tty rather than stdin is the point: an automated session with
    a pipe for stdin cannot answer this, so a script or an agent cannot drive
    a promotion to 'cleared' without a person at a keyboard.
    """
    try:
        with open("/dev/tty", "r+") as tty:
            tty.write(prompt)
            tty.write(f"\nType exactly: {phrase}\n> ")
            tty.flush()
            answer = tty.readline().strip()
    except OSError:
        return False
    return answer == phrase


def promote(
    root: Path,
    manifest: dict,
    src: Path,
    dst_rel: str,
    *,
    source: str,
    generator: str,
    deps: list[dict],
    evidence_urls: list[str],
    cleared_by: str,
    evidence: str,
    cleared_on: str,
    confirm=None,
) -> str:
    """Copy an evaluated asset into production with a human clearance recorded.

    Every refusal below is deliberate: the promotion path is the one place
    where something moves from 'evaluation only' to 'shippable', so it demands
    the evidence up front rather than accepting a status change on trust.
    """
    if not src.is_file():
        raise GateError(f"source {src} does not exist")
    if not deps:
        raise GateError("at least one --dep is required (use 'none|n/a|true|repo:...' if there are none)")
    for dep in deps:
        if dep["commercial_use"] is not True:
            raise GateError(
                f"dependency {dep['component']!r} is licensed {dep['licence']!r} with "
                "commercial_use=false — it cannot be promoted, whatever the evidence says"
            )
    if not cleared_by.strip():
        raise GateError("--cleared-by is required: name the person accepting responsibility")
    if not evidence.strip():
        raise GateError("--evidence is required: state what was reviewed and how")
    if not evidence_urls:
        raise GateError("at least one --evidence-url is required")
    for url in evidence_urls:
        if not url.startswith(EVIDENCE_SCHEMES):
            raise GateError(f"evidence url {url!r} must start with one of {', '.join(EVIDENCE_SCHEMES)}")

    if not any(dst_rel == r or dst_rel.startswith(r.rstrip("/") + "/") for r in manifest["production_roots"]):
        raise GateError(f"destination {dst_rel} is not inside a production root")
    for rel_root in manifest["evaluation_roots"]:
        if dst_rel.startswith(rel_root.rstrip("/") + "/"):
            raise GateError(f"destination {dst_rel} is inside evaluation root {rel_root}")

    phrase = f"clear {Path(dst_rel).name} for commercial use"
    prompt = (
        f"\nPromoting to production:\n"
        f"  from      {src}\n"
        f"  to        {dst_rel}\n"
        f"  cleared by {cleared_by}\n"
        f"  evidence   {evidence}\n"
        f"This records a commercial-use clearance in your name."
    )
    confirm = confirm or (lambda: tty_confirm(prompt, phrase))
    if not confirm():
        raise GateError("promotion not confirmed — nothing was copied or recorded")

    dst = root / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    manifest["assets"][dst_rel] = {
        "source": source,
        "generator": generator,
        "dependency_licences": deps,
        "evidence_urls": evidence_urls,
        "commercial_status": STATUS_CLEARED,
        "sha256": sha256_of(dst),
        "clearance": {
            "cleared_by": cleared_by,
            "cleared_on": cleared_on,
            "evidence": evidence,
            "method": METHOD_HUMAN,
        },
    }
    save_manifest(root, manifest)
    return dst_rel


# --------------------------------------------------------------------------
# cli


def print_report(report: Report, title: str) -> int:
    for note in report.notes:
        print(f"  note: {note}")
    if report.baseline:
        print(
            f"  note: {len(report.baseline)} asset(s) carry a baseline clearance rather than "
            "an individual human review; run 'check --strict-baseline' to list them as failures"
        )
    if report.ok:
        print(f"asset-gate: PASS — {title} ({report.checked} checked)")
        return 0
    print(f"asset-gate: FAIL — {title}", file=sys.stderr)
    for failure in report.failures:
        print(f"  ✗ {failure}", file=sys.stderr)
    print(
        f"\n{len(report.failures)} problem(s). Nothing here is auto-fixable by an agent: "
        "provenance and clearance are human decisions.",
        file=sys.stderr,
    )
    return 1


def cmd_check(args, root: Path) -> int:
    manifest = load_manifest(root)
    report = Report()
    check_roots_disjoint(manifest, report)
    check_evaluation_markers(root, manifest, report)
    check_manifest_coverage(root, manifest, report, args.strict_baseline)
    check_references(root, manifest, report)
    check_export_presets(root, manifest, report)
    return print_report(report, "working tree")


def cmd_check_package(args, root: Path) -> int:
    manifest = load_manifest(root)
    report = Report()
    check_package(root, manifest, [Path(p) for p in args.paths], report)
    return print_report(report, "built package")


def cmd_sync_presets(args, root: Path) -> int:
    manifest = load_manifest(root)
    changed = sync_presets(root, manifest)
    if changed:
        for rel in changed:
            print(f"asset-gate: updated exclusions in {rel}")
    else:
        print("asset-gate: export presets already exclude every evaluation root")
    return 0


def cmd_promote(args, root: Path) -> int:
    manifest = load_manifest(root)
    deps = [parse_dep(spec) for spec in args.dep]
    rel = promote(
        root,
        manifest,
        Path(args.src),
        args.dst,
        source=args.source,
        generator=args.generator,
        deps=deps,
        evidence_urls=args.evidence_url,
        cleared_by=args.cleared_by,
        evidence=args.evidence,
        cleared_on=args.cleared_on,
    )
    print(f"asset-gate: promoted {args.src} -> {rel} and recorded a human clearance")
    print("Re-run 'tools/asset_gate.py check' and commit the manifest with the asset.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asset_gate.py",
        description="Fail-closed commercial-asset gate for Red Valley.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (default: the repository containing this script)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="gate the working tree")
    check.add_argument(
        "--strict-baseline",
        action="store_true",
        help="also fail on clearances that were seeded rather than human-reviewed",
    )
    check.set_defaults(func=cmd_check)

    package = sub.add_parser("check-package", help="gate a built artifact")
    package.add_argument("paths", nargs="*", help="exported file(s) or directory(ies)")
    package.set_defaults(func=cmd_check_package)

    presets = sub.add_parser("sync-presets", help="write required exclusions into export presets")
    presets.set_defaults(func=cmd_sync_presets)

    prom = sub.add_parser("promote", help="copy an evaluated asset into production (human only)")
    prom.add_argument("src")
    prom.add_argument("dst", help="destination path relative to the repository root")
    prom.add_argument("--source", required=True, help="where the asset came from")
    prom.add_argument("--generator", required=True, help="what produced it")
    prom.add_argument(
        "--dep",
        action="append",
        default=[],
        metavar="component|licence|commercial_use|evidence_url",
        help="dependency licence (repeatable, at least one required)",
    )
    prom.add_argument("--evidence-url", action="append", default=[], help="repeatable")
    prom.add_argument("--cleared-by", required=True, help="the person accepting responsibility")
    prom.add_argument("--evidence", required=True, help="what was reviewed and how")
    prom.add_argument("--cleared-on", required=True, help="ISO date of the clearance")
    prom.set_defaults(func=cmd_promote)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    try:
        return args.func(args, root)
    except GateError as exc:
        print(f"asset-gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
