#!/usr/bin/env python3
"""Report-only repository hygiene audit. NEVER deletes anything.

Context: this repository once carried 346 MB of regenerable binaries against
26 MB of source, which required a history rewrite to undo. This tool exists so
that never silently recurs. It reports; a human decides.

Protected and never proposed for removal:
  * anything tracked by Git
  * anything recorded in the private asset manifest (~/RedValleyAssets)
  * paid ARDY .npz clips and the explicit production allowlist

  python3 tools/repo_hygiene.py            # report
  python3 tools/repo_hygiene.py --trash-script  # also emit an approval script
"""
import hashlib, json, os, subprocess, sys

ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
STORE = os.path.expanduser("~/RedValleyAssets")
MANIFEST = os.path.join(STORE, "MANIFEST.sha256")
ALLOWLIST = os.path.join(ROOT, "tools", "hygiene_allowlist.txt")
AUDIT_DIRS = ["art"]
DISPOSABLE = {".png", ".jpg", ".jpeg", ".mp4", ".webm", ".mov",
              ".blend", ".blend1", ".fbx", ".log", ".out", ".glb"}
# which script regenerates what, for the provenance column
PROVENANCE = [
    ("art/animation/rigify/", "tools/ardy/align_metarig.py + generate_rigify.py + bind_rigify.py"),
    ("art/animation/ardy_pilot/pose_ref/", "tools/ardy/pose_reference.py + render_poses.py"),
    ("art/animation/ardy_pilot/handcheck/", "tools/ardy/render_hand.py"),
    ("art/animation/ardy_pilot/retargeted", "tools/ardy/retarget.py"),
    ("art/animation/mixamo_bench/", "tools/ardy/bake_for_autorig.py (upload); rigged = Mixamo download"),
    ("art/character/renders/", "art/character/scripts/"),
]


def sh(*a):
    return subprocess.check_output(list(a), cwd=ROOT).decode()


def tracked():
    return set(sh("git", "ls-files").splitlines())


def manifest_names():
    """Basenames recorded in the private store, so a local copy of a preserved
    master is never proposed for removal."""
    names = set()
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST):
            parts = line.split(None, 1)
            if len(parts) == 2:
                names.add(os.path.basename(parts[1].strip()))
    return names


def allowlist():
    out = set()
    if os.path.exists(ALLOWLIST):
        for line in open(ALLOWLIST):
            line = line.split("#", 1)[0].strip()
            if line: out.add(line)
    return out


def provenance_for(path):
    for prefix, tool in PROVENANCE:
        if path.startswith(prefix):
            return tool
    return "unknown"


def main():
    TRACKED, NAMES, ALLOW = tracked(), manifest_names(), allowlist()
    rows, total = [], 0
    for d in AUDIT_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base): continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != ".git"]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                ext = os.path.splitext(fn)[1].lower()
                if rel in TRACKED or rel in ALLOW: continue     # protected
                if ext == ".npz": continue                      # paid output
                if fn in NAMES: continue                        # in private store
                if ext not in DISPOSABLE: continue
                try: sz = os.path.getsize(full)
                except OSError: continue
                rows.append((sz, rel, provenance_for(rel)))
                total += sz
    rows.sort(reverse=True)
    print("REPO HYGIENE — report only, nothing is deleted")
    print("  repository : %s" % ROOT)
    print("  protected  : %d tracked files, %d private-store entries, %d allowlisted"
          % (len(TRACKED), len(NAMES), len(ALLOW)))
    if not rows:
        print("\n  No disposable generated output found under %s. Nothing to propose."
              % ", ".join(AUDIT_DIRS))
        return 0
    print("\n  %d disposable files, %.1f MB total\n" % (len(rows), total / 1048576))
    print("  %10s  %-58s %s" % ("SIZE", "PATH", "REGENERATE WITH"))
    for sz, rel, prov in rows[:40]:
        print("  %7.2f MB  %-58s %s" % (sz / 1048576, rel[:58], prov))
    if len(rows) > 40:
        rest = sum(r[0] for r in rows[40:])
        print("  ... and %d more totalling %.1f MB" % (len(rows) - 40, rest / 1048576))
    print("\n  PROPOSED (requires your explicit approval — this tool will not do it):")
    print("    python3 tools/repo_hygiene.py --trash-script > /tmp/hygiene_trash.sh")
    print("    less /tmp/hygiene_trash.sh     # read it")
    print("    bash /tmp/hygiene_trash.sh     # only if you agree")
    if "--trash-script" in sys.argv:
        p = os.path.join(ROOT, ".hygiene_trash.sh")
        with open(p, "w") as f:
            f.write("#!/usr/bin/env bash\n# Review before running. Moves to trash, not rm.\nset -e\n")
            for sz, rel, _ in rows:
                f.write('/usr/bin/gio trash %s\n' % json.dumps(os.path.join(ROOT, rel)))
        os.chmod(p, 0o755)
        print("\n  wrote %s (%d entries) — review it before running" % (p, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
