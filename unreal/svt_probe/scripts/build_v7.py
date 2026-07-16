"""v7: save the level in a way that is CONFIRMED to hit disk.

v5/v6 called LevelEditorSubsystem.save_current_level() and never checked its return
value. It was silently failing: SvtPlayback.umap on disk stayed at its 18:44 timestamp
while the build reported "verdict = READY, all checks PASS". Every one of those checks
inspected in-memory objects that were never persisted, so the map the owner would have
opened was a stale volume with no material, no placement and no lights -- a black
viewport, exactly the outcome the checks claimed to rule out.

Rule this file follows: log every save's return value, and verify by re-loading the
level from disk in a SEPARATE process (verify_v7.py), not in the process that built it --
an in-process reload can hand back the still-resident package and tell you nothing.
"""
import unreal

SVT_PATH = "/Game/SVT_REAL/frame"
MAP_PATH = "/Game/Maps/SvtPlayback"
MI_PATH = "/Game/SVT_REAL/MI_SvtPlayback"
FRAME_RATE = 25.0
M_TO_CM = 100.0

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def emit(k, v):
    unreal.log("BUILD7: {} = {}".format(k, v))


svt = unreal.load_asset(SVT_PATH)
mi = unreal.load_asset(MI_PATH)
emit("svt_frames", svt.get_num_frames())

emit("new_level_returned", les.new_level(MAP_PATH))

sun = eas.spawn_actor_from_class(unreal.DirectionalLight,
                                 unreal.Vector(0, 0, 500000), unreal.Rotator(-35, 45, 0))
sun.set_actor_label("Sun")
sun.light_component.set_intensity(8.0)

sky_light = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500000),
                                       unreal.Rotator(0, 0, 0))
sky_light.set_actor_label("SkyLight")
sky_light.light_component.set_editor_property("real_time_capture", True)
sky_light.light_component.set_intensity(1.0)

sky_atmo = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0),
                                      unreal.Rotator(0, 0, 0))
sky_atmo.set_actor_label("SkyAtmosphere")

actor = eas.spawn_actor_from_class(unreal.HeterogeneousVolume,
                                   unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
comp = actor.get_component_by_class(unreal.HeterogeneousVolumeComponent)
comp.set_material(0, mi)

ft = svt.get_frame_transform()
actor.set_actor_scale3d(unreal.Vector(ft.scale3d.x * M_TO_CM,
                                      ft.scale3d.y * M_TO_CM,
                                      ft.scale3d.z * M_TO_CM))
actor.set_actor_location(unreal.Vector(ft.translation.x * M_TO_CM,
                                       -ft.translation.y * M_TO_CM,
                                       ft.translation.z * M_TO_CM), False, False)
for prop, val in (("frame_rate", FRAME_RATE), ("playing", True), ("looping", True)):
    comp.set_editor_property(prop, val)
actor.set_actor_label("StormVolume")

emit("in_memory_actor_count", len(eas.get_all_level_actors()))

# --- saving: try the subsystem, then fall back and REPORT which one worked ----------
r1 = les.save_current_level()
emit("save_current_level_returned", r1)

world = unreal.EditorLevelLibrary.get_editor_world()
emit("world_name", world.get_name())
emit("world_package", world.get_outermost().get_name())

try:
    r2 = unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_PATH)
    emit("save_map_returned", r2)
except Exception as e:  # noqa: BLE001
    emit("save_map_error", str(e))

try:
    r3 = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    emit("save_dirty_packages_returned", r3)
except Exception as e:  # noqa: BLE001
    emit("save_dirty_packages_error", str(e))

emit("asset_exists_after_save", unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH))
unreal.log("BUILD7: DONE")
