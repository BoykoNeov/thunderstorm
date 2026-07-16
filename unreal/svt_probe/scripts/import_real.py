"""Task 5 -> SVT link: import the REAL CM1-derived VDB sequence headless.

Task 3 proved the SVT path using synthetic frames whose transform translation was
(0,0,0). The real pipeline emits CM1-native world coordinates, so the shared
transform now carries a NONZERO translation (-25875, -25875, 125). That path is
untested: if UE dropped or mangled the translation, the volume would render in the
wrong place and the "VDB carries SI metres, UE converts at actor placement"
contract would be broken.

Checks: frame count (301), grid->channel identity, resolution (208x208x72), and the
shared transform's translation/scale.
"""
import os
import time
import unreal

SEQ_DIR = r"M:\claud_projects\temp\task5\vdb"
FIRST_FRAME = os.path.join(SEQ_DIR, "frame_00000.vdb")
DEST_PATH = "/Game/SVT_REAL"

# RESULT (2026-07-15): UE does NOT import the padded box as authored. It unions the
# active voxels across the WHOLE sequence and tightens the volume to that, re-basing
# the translation by exactly trimmed_voxels * voxel_size. The padded 208x208x72 box
# @ origin -25875 arrives as 186x186x65 @ -23125: 11 empty voxels trimmed per side in
# x/y (11*250 = 2750 m) and 7 off the top. -23125 is the centre of voxel 11, whose
# outer face is -23250 m -- the exact union half-width the bbox sweep measured. So the
# index->world mapping is preserved exactly; only empty pad was dropped.
# Expectations below are UE's derived values, so a re-run passes and documents this.
EXPECTED_FRAMES = 301
EXPECTED_RES = (186, 186, 65)
EXPECTED_TRANSLATION = (-23125.0, -23125.0, 125.0)
EXPECTED_SCALE = 250.0


def emit(k, v):
    unreal.log("REAL: {} = {}".format(k, v))


emit("source_frames_on_disk", len([f for f in os.listdir(SEQ_DIR) if f.endswith(".vdb")]))

task = unreal.AssetImportTask()
task.set_editor_property("filename", FIRST_FRAME)
task.set_editor_property("destination_path", DEST_PATH)
task.set_editor_property("automated", True)
task.set_editor_property("replace_existing", True)
task.set_editor_property("save", True)
task.set_editor_property("factory", unreal.SparseVolumeTextureFactory())

at = unreal.AssetToolsHelpers.get_asset_tools()
t0 = time.time()
at.import_asset_tasks([task])
emit("import_wall_seconds", round(time.time() - t0, 1))

imported = list(task.get_editor_property("imported_object_paths") or [])
emit("imported_object_count", len(imported))

checks = {}
for p in imported:
    emit("imported_object_path", p)
    asset = unreal.load_asset(p)
    if asset is None:
        continue
    cls = asset.get_class().get_name()
    emit("asset_class", cls)

    # NOTE: the API is get_num_frames(); there is NO get_frame_count on the
    # animated asset (task 3 footnote -- a wrong name silently reads None).
    n = asset.get_num_frames()
    emit("num_frames", n)
    checks["frame_count"] = (n == EXPECTED_FRAMES)

    res = asset.get_editor_property("volume_resolution")
    emit("volume_resolution", res)
    checks["resolution"] = (int(res.x), int(res.y), int(res.z)) == EXPECTED_RES

    t = asset.get_frame_transform()
    emit("shared_transform_translation", t.translation)
    emit("shared_transform_scale3d", t.scale3d)
    tr = t.translation
    checks["translation_preserved"] = all(
        abs(a - b) < 1.0 for a, b in
        [(tr.x, EXPECTED_TRANSLATION[0]), (tr.y, EXPECTED_TRANSLATION[1]),
         (tr.z, EXPECTED_TRANSLATION[2])]
    )
    checks["scale"] = abs(t.scale3d.x - EXPECTED_SCALE) < 1e-3

    for fmt_prop in ("format_a", "format_b"):
        try:
            emit(fmt_prop, asset.get_editor_property(fmt_prop))
        except Exception:  # noqa: BLE001
            pass

    try:
        pkg = asset.get_outermost().get_name()
        rel = pkg.replace("/Game/", "Content/") + ".uasset"
        full = os.path.join(unreal.Paths.project_dir(), rel)
        if os.path.isfile(full):
            emit("uasset_MB", round(os.path.getsize(full) / (1024 * 1024), 2))
    except Exception as e:  # noqa: BLE001
        emit("uasset_size_error", str(e))

for k, v in checks.items():
    emit("check_" + k, "PASS" if v else "FAIL")
emit("verdict", "PASS" if checks and all(checks.values()) else "FAIL")
unreal.log("REAL: DONE")
