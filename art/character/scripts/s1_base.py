"""Stage 1 -- MPFB base human shaped toward the Red Valley protagonist reference.

Adult female farmer, late 20s/early 30s, lean working build, oval face with
defined jaw and high cheekbones, straight nose, medium-full lips.

Targets must be LOADED (load_target) before their value can be set --
set_target_value alone is a silent no-op on a key that does not yet exist,
so every target here is verified and the run asserts on any miss.

Run:
  blender --background --python art/character/scripts/s1_base.py
Writes: art/character/Player_HiFi_v01.blend
"""
import bpy, addon_utils, os

addon_utils.enable("bl_ext.user_default.mpfb", default_set=True)
addon_utils.enable("rigify", default_set=True)

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.assetservice import AssetService
from bl_ext.user_default.mpfb.services.locationservice import LocationService

PROJ = "/home/thomas/Dev/red-valley/art/character"
OUT = os.path.join(PROJ, "Player_HiFi_v01.blend")

MACRO = {
    "gender": 0.0,
    "age": 0.58,          # ~ early 30s
    "muscle": 0.62,       # works the land
    "weight": 0.46,       # lean
    "proportions": 0.62,  # slightly idealised, still believable
    "height": 0.56,       # ~1.70 m
    "cupsize": 0.38,
    "firmness": 0.60,
    "race": {"asian": 0.06, "caucasian": 0.87, "african": 0.07},
}

# Symmetric pairs get expanded to l-/r- automatically via the "*" prefix.
DETAIL_TARGETS = [
    # --- head: oval with a defined, slightly square jaw
    ("head-oval", 0.55),
    ("head-square", 0.18),
    ("head-scale-depth-decr", 0.12),
    ("head-fat-decr", 0.30),
    ("head-angle-in", 0.10),

    # --- cheekbones: high and readable (key to the reference's look)
    ("*-cheek-bones-incr", 0.52),
    ("*-cheek-inner-decr", 0.28),
    ("*-cheek-volume-decr", 0.15),

    # --- chin / jaw: firm but feminine
    ("chin-bones-incr", 0.22),
    ("chin-height-decr", 0.10),
    ("chin-width-decr", 0.18),
    ("chin-prognathism-incr", 0.08),

    # --- nose: straight, narrow bridge, modest tip
    ("nose-scale-horiz-decr", 0.30),
    ("nose-nostrils-width-decr", 0.22),
    ("nose-hump-decr", 0.12),
    ("nose-point-width-decr", 0.18),
    ("nose-base-up", 0.10),
    ("nose-width1-decr", 0.15),

    # --- eyes: almond, slight upper-lid weight, calm gaze
    ("*-eye-scale-incr", 0.16),
    ("*-eye-height2-decr", 0.12),
    ("*-eye-corner1-down", 0.08),
    ("*-eye-epicanthus-out", 0.10),
    ("*-eye-eyefold-angle-up", 0.12),

    # --- mouth: medium-full, natural resting line
    ("mouth-scale-horiz-decr", 0.12),
    ("mouth-lowerlip-height-incr", 0.20),
    ("mouth-upperlip-height-incr", 0.14),
    ("mouth-cupidsbow-incr", 0.24),
    ("mouth-philtrum-volume-incr", 0.12),

    # --- forehead: smooth, slightly rounded
    ("forehead-scale-vert-decr", 0.14),
    ("forehead-nubian-decr", 0.10),
    ("forehead-temple-decr", 0.12),

    # --- neck: working build, not delicate
    ("neck-scale-horiz-incr", 0.12),

    # --- torso / limbs: field labour -- broader shoulders, lean waist
    ("torso-vshape-incr", 0.16),
    ("measure-shoulder-dist-incr", 0.18),
    ("measure-waist-circ-decr", 0.14),
    ("stomach-tone-incr", 0.30),
    ("*-upperarm-muscle-incr", 0.22),
    ("*-lowerarm-muscle-incr", 0.20),
    ("*-upperarm-shoulder-muscle-incr", 0.16),
    ("*-upperleg-muscle-incr", 0.18),
    ("*-lowerleg-muscle-incr", 0.16),
]

SKIN = "young_caucasian_female"   # CC0, 2K albedo; PBR detail added in stage 4
EYEBROWS = "Eyebrow010"
EYELASHES = "Eyelashes03"
EYES = "High-poly"


def log(*a):
    print("[S1]", *a, flush=True)


def expand(name):
    return [name.replace("*", "l"), name.replace("*", "r")] if "*" in name else [name]


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"

    log("creating base human")
    body = HumanService.create_human(
        mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
        feet_on_ground=True, scale=0.1, macro_detail_dict=MACRO,
    )
    body.name = "RV_Body"
    log("base:", body.name, "verts", len(body.data.vertices),
        "dims", tuple(round(d, 3) for d in body.dimensions))

    # ---- detail targets: load then weight, verifying each one lands
    loaded, failed = 0, []
    for raw, val in DETAIL_TARGETS:
        for name in expand(raw):
            path = TargetService.target_full_path(name)
            if not path or not os.path.exists(path):
                failed.append((name, "no such target file"))
                continue
            try:
                TargetService.load_target(body, path, weight=val, name=name)
                loaded += 1
            except Exception as exc:
                failed.append((name, str(exc)[:70]))
    log(f"detail targets loaded={loaded} failed={len(failed)}")
    for f in failed:
        log("   FAILED", f)

    # hard check: the detail keys must actually exist on the mesh now
    keys = {k.name for k in body.data.shape_keys.key_blocks}
    detail_keys = [k for k in keys if not k.startswith("$md") and k != "Basis"]
    log(f"shapekeys total={len(keys)} detail={len(detail_keys)}")
    assert len(detail_keys) >= loaded * 0.9, \
        f"targets did not materialise: {len(detail_keys)} keys for {loaded} loads"
    assert not failed, f"{len(failed)} targets failed to load"

    # ---- skin
    root = LocationService.get_user_data("skins")
    skin_path = os.path.join(root, SKIN, f"{SKIN}.mhmat")
    assert os.path.exists(skin_path), f"missing skin {skin_path}"
    HumanService.set_character_skin(skin_path, body, skin_type="ENHANCED_SSS")
    log("skin applied:", SKIN)

    # ---- eyes / brows / lashes
    for atype, aname in (("Eyes", EYES), ("Eyebrows", EYEBROWS), ("Eyelashes", EYELASHES)):
        lst = AssetService.get_asset_list(atype.lower())
        entry = lst.get(aname)
        assert entry, f"{atype} asset {aname!r} not found; have {list(lst)[:6]}"
        HumanService.add_mhclo_asset(entry["full_path"], body, asset_type=atype)
        log(f"{atype} added:", aname)

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    log("saved", OUT)
    for o in bpy.data.objects:
        if o.type == "MESH":
            log(f"  OBJ {o.name}: verts={len(o.data.vertices)}")


main()
