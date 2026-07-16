"""Verify the SAVED level, in a fresh process. Separate from build_v7 on purpose."""
import unreal

MAP_PATH = "/Game/Maps/SvtPlayback"

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def emit(k, v):
    unreal.log("VERIFY: {} = {}".format(k, v))


emit("load_level_returned", les.load_level(MAP_PATH))
actors = eas.get_all_level_actors()
emit("actor_count", len(actors))

by_class = {}
for a in actors:
    cls = a.get_class().get_name()
    by_class[cls] = by_class.get(cls, 0) + 1
emit("light_actors", {k: v for k, v in by_class.items() if "Light" in k or "Sky" in k})
emit("volume_actors", by_class.get("HeterogeneousVolume", 0))

vol = next((a for a in actors if a.get_class().get_name() == "HeterogeneousVolume"), None)
if vol is None:
    emit("verdict", "NO_VOLUME")
else:
    emit("volume_label", vol.get_actor_label())
    comp = vol.get_component_by_class(unreal.HeterogeneousVolumeComponent)
    mat = comp.get_material(0)
    emit("material", mat.get_name() if mat else None)
    emit("playing", comp.get_editor_property("playing"))
    emit("frame_rate", comp.get_editor_property("frame_rate"))
    b = vol.get_actor_bounds(False)
    emit("bounds_origin_cm", b[0])
    emit("span_x_km", round(b[1].x * 2.0 / 100000.0, 2))
unreal.log("VERIFY: DONE")
