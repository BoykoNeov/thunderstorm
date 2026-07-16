"""Build a ready-to-look-at playback level for the OWNER's visual streaming check.

The owner's job is to judge whether 301 real frames stream smoothly and look right --
not to wire UE up. This does the wiring headless and saves a level, so the check reduces
to: open the level, look, fly around.

Creates /Game/Maps/SvtPlayback with a HeterogeneousVolume actor whose material is a
MaterialInstance of /Engine/EngineMaterials/SparseVolumeMaterial bound to
/Game/SVT_REAL/frame, looping at 25 fps (301 frames -> ~12 s per simulated hour).

Note on approach: spawn_actor_from_object() (the content-browser-drag actor factory)
refuses an SVT from Python, with and without -nullrhi -- hence the explicit material
instance. Parameter names were read out of the engine material's own package:
  SparseVolumeTexture        - MaterialExpressionSparseVolumeTextureSampleParameter
  StaticSparseVolumeTexture  - static switch; must be FALSE or the animated frames are
                               sampled through the static path and never advance.
Every binding is read back and asserted rather than assumed: an unbound volume renders
empty, which would read to the owner as "streaming is broken" when nothing is wrong.
"""
import unreal

SVT_PATH = "/Game/SVT_REAL/frame"
MAP_PATH = "/Game/Maps/SvtPlayback"
MI_PKG = "/Game/SVT_REAL"
MI_NAME = "MI_SvtPlayback"
BASE_MAT = "/Engine/EngineMaterials/SparseVolumeMaterial"
SVT_PARAM = "SparseVolumeTexture"
STATIC_SWITCH = "StaticSparseVolumeTexture"
TEMPLATE_MAP = "/Engine/Maps/Templates/TimeOfDay_Default"
FRAME_RATE = 25.0
# 186 voxels * 250 m = 46.5 km across. If the bounds come back anywhere near 186 cm,
# the units conversion silently did not take.
EXPECTED_SPAN_CM = 186 * 250 * 100
# See the extinction reasoning at the material block below. Owner-tunable knob.
DENSITY_SCALE = 2e-4

MEL = unreal.MaterialEditingLibrary


def emit(k, v):
    unreal.log("PLAYBACK: {} = {}".format(k, v))


checks = {}

svt = unreal.load_asset(SVT_PATH)
if svt is None:
    raise RuntimeError("SVT missing: " + SVT_PATH)
emit("svt_class", svt.get_class().get_name())
emit("svt_num_frames", svt.get_num_frames())
checks["frames_301"] = svt.get_num_frames() == 301

base = unreal.load_asset(BASE_MAT)
emit("base_material", base.get_name() if base else None)

# --- material instance -------------------------------------------------------------
mi_path = MI_PKG + "/" + MI_NAME
if unreal.EditorAssetLibrary.does_asset_exist(mi_path):
    unreal.EditorAssetLibrary.delete_asset(mi_path)
at = unreal.AssetToolsHelpers.get_asset_tools()
mi = at.create_asset(MI_NAME, MI_PKG, unreal.MaterialInstanceConstant,
                     unreal.MaterialInstanceConstantFactoryNew())
MEL.set_material_instance_parent(mi, base)

MEL.set_material_instance_sparse_volume_texture_parameter_value(mi, SVT_PARAM, svt)

# --- make it VISIBLE, not just bound -----------------------------------------------
# The stock material is tuned for density grids ~0-1 (Niagara/Embergen). Our channels
# are physical mixing ratios ~1e-3 kg/kg, and the material does not know that. With the
# default Density Scale = 1.0 the optical depth across the storm is
#     tau ~ 1.0 * 5e-3 (peak cloud) * 1e6 cm (10 km path) ~ 5000
# i.e. a solid opaque block -- NOT invisible, but just as useless a verdict. Scaling for
# tau ~ 1 gives 1 / (5e-3 * 1e6) ~ 2e-4. This is a VIEWING knob for the owner's check,
# not science: it never touches the data, and the real material is Phase 4.
for sw, val in ((STATIC_SWITCH, False),          # animated path, not static
                ("Density (Attributes A)", True),  # density <- Tex A (R = cloud)
                ("Clamp SVT Density", False),      # clamp max 1.0 is meaningless at 1e-3
                ("Use Blackbody Temperature", False)):  # Tex B is dbz, not temperature
    try:
        MEL.set_material_instance_static_switch_parameter_value(mi, sw, val)
        emit("switch." + sw, val)
    except Exception as e:  # noqa: BLE001
        emit("switch_error." + sw, str(e))

try:
    MEL.set_material_instance_scalar_parameter_value(mi, "Density Scale", DENSITY_SCALE)
    emit("density_scale", DENSITY_SCALE)
except Exception as e:  # noqa: BLE001
    emit("density_scale_error", str(e))

MEL.update_material_instance(mi)

# Read back -- do not trust the setter.
got = MEL.get_material_instance_sparse_volume_texture_parameter_value(mi, SVT_PARAM)
emit("readback_svt", got.get_name() if got else None)
checks["svt_bound"] = (got == svt)
try:
    sw = MEL.get_material_instance_static_switch_parameter_value(mi, STATIC_SWITCH)
    emit("readback_static_switch", sw)
    checks["animated_path"] = (sw is False)
except Exception as e:  # noqa: BLE001
    emit("static_switch_readback_error", str(e))
try:
    ds = MEL.get_material_instance_scalar_parameter_value(mi, "Density Scale")
    emit("readback_density_scale", ds)
    checks["density_scaled"] = abs(ds - DENSITY_SCALE) < 1e-9
except Exception as e:  # noqa: BLE001
    emit("density_readback_error", str(e))

unreal.EditorAssetLibrary.save_asset(mi_path)

# --- level -------------------------------------------------------------------------
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
# From a template, not new_level(): an empty level has no light, and a volumetric with
# nothing lighting it renders as nothing -- indistinguishable from a streaming failure.
les.new_level_from_template(MAP_PATH, TEMPLATE_MAP)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor = eas.spawn_actor_from_class(unreal.HeterogeneousVolume,
                                   unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
actor.set_actor_label("StormVolume")
comp = actor.get_component_by_class(unreal.HeterogeneousVolumeComponent)
comp.set_material(0, mi)

# --- placement: the single conversion site -----------------------------------------
# The component does NOT apply the SVT's frame transform -- it lays the volume out at
# 1 voxel = 1 UE unit (bounds came back 186x186x65 cm, a 1.9 m storm). So the actor
# carries the whole CM1->UE mapping, which is the charter's single-conversion-site rule
# in action: frame transform (metres) x 100 cm/m, with Y negated for UE's left-handed
# space. Nothing here re-derives placement from the manifest's origin_m -- that is the
# double-apply trap (volume.ue_placement_rule).
ft = svt.get_frame_transform()
emit("svt_frame_translation_m", ft.translation)
emit("svt_frame_scale_m_per_voxel", ft.scale3d)

M_TO_CM = 100.0
actor.set_actor_scale3d(unreal.Vector(ft.scale3d.x * M_TO_CM,
                                      ft.scale3d.y * M_TO_CM,
                                      ft.scale3d.z * M_TO_CM))
actor.set_actor_location(
    unreal.Vector(ft.translation.x * M_TO_CM,
                  -ft.translation.y * M_TO_CM,   # Y flip: CM1 right-handed -> UE left-handed
                  ft.translation.z * M_TO_CM),
    False, False)

for prop, val in (("frame_rate", FRAME_RATE), ("playing", True), ("looping", True)):
    try:
        comp.set_editor_property(prop, val)
        emit("set_" + prop, val)
    except Exception as e:  # noqa: BLE001
        emit("set_error_" + prop, str(e))

mat_ok = comp.get_material(0)
emit("component_material", mat_ok.get_name() if mat_ok else None)
checks["material_on_component"] = mat_ok is not None

# The component drives its own resolution from the bound SVT; report it so the owner
# can tell at a glance whether the real volume (186x186x65) actually arrived.
try:
    emit("component_volume_resolution", comp.get_editor_property("volume_resolution"))
except Exception as e:  # noqa: BLE001
    emit("volume_resolution_error", str(e))

b = actor.get_actor_bounds(False)
emit("bounds_origin_cm", b[0])
emit("bounds_extent_cm", b[1])
span_x = b[1].x * 2.0
emit("span_x_km", round(span_x / 100000.0, 2))
checks["units_applied"] = abs(span_x - EXPECTED_SPAN_CM) < (EXPECTED_SPAN_CM * 0.02)

les.save_current_level()
emit("map_saved", MAP_PATH)

for k, v in checks.items():
    emit("check_" + k, "PASS" if v else "FAIL")
emit("verdict", "READY" if checks and all(checks.values()) else "INCOMPLETE")
unreal.log("PLAYBACK: DONE")
