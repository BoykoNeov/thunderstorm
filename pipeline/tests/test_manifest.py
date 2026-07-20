#!/usr/bin/env python3
"""Manifest gates (Phase 2 T1b + T2 + T3 + T4/T5 re-export torn down in T6).

    python3 pipeline/tests/test_manifest.py

`manifest.build()` is a PURE function of (Scenario, frames, provenance). That is what
lets the shipped 48 KB manifest be rebuilt from committed inputs alone -- no CM1, no
netCDF, no VDB, no re-export -- and compared byte-for-byte. T1b used the trick once to
prove the scenario-system refactor changed nothing; this file makes it a standing gate,
so a future edit to manifest.py that silently perturbs the shipped contract fails here
instead of in UE.

Reads only committed files (`scenarios/single_cell_500m/manifest.json` is tracked
precisely so this is possible -- scenarios/README.md).
"""
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import contract, manifest, scenario  # noqa: E402

PKG = os.path.join(REPO, "scenarios", "single_cell_500m")
SHIPPED = os.path.join(PKG, "manifest.json")

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def dumps(doc):
    """Exactly what manifest.write() produces."""
    buf = io.StringIO()
    json.dump(doc, buf, indent=1)
    return buf.getvalue()


def load_shipped():
    with open(SHIPPED) as f:
        text = f.read()
    return text, json.loads(text)


def rebuild(shipped):
    """Rebuild from the scenario config + the shipped frame/provenance records."""
    sc = scenario.load("single_cell_500m")
    return sc, manifest.build(sc, frames=shipped["frames"],
                              provenance=shipped["provenance"])


# --- T1b: the shipped manifest is reproducible from committed inputs --------

def gate_byte_identical(shipped_text, rebuilt):
    """The shipped manifest is byte-identical to a rebuild from committed inputs.

    Through T2/T3/T4/T5 this gate carried a revert block: the package was
    DELIBERATELY stale (the 301-frame re-export batched behind all three data/format
    tasks per plan §9), so the rebuild disagreed with the shipped bytes in exactly
    the ways T3-T5 intended, and the gate named those diffs, reverted them, and
    compared the remainder. **T6 ran the batched re-export (2026-07-20)**, so the
    scaffolding is gone: the shipped manifest now IS the T3-linear-Z / T4-`w` /
    T5-`cref` generation, and `manifest.build()` -- a pure function of (Scenario,
    frames, provenance) -- reproduces it to the byte with nothing to revert. If this
    ever fails again, manifest.py perturbed the shipped contract and it will surface
    here instead of in a consumer.
    """
    text = dumps(rebuilt)
    if text == shipped_text:
        return True, (f"rebuilt == shipped, {len(text)} chars byte-identical "
                      "(no revert -- the T3-T5 re-export has landed)")
    return False, (f"rebuild {len(text)} chars != shipped {len(shipped_text)}; "
                   "manifest.build() no longer reproduces the shipped contract")


def gate_grid_derived(sc, shipped):
    """The grid is DERIVED from the crop box -- not restated in the config."""
    want = [sc.nx, sc.ny, sc.nz]
    got = shipped["volume"]["dimensions"]
    return got == want, (f"{got} @ {sc.export_voxel_m:.0f} m, origin "
                         f"{shipped['volume']['origin_m']}")


# --- T2: the web block ------------------------------------------------------

def gate_format_version(shipped):
    """Still 1.1 -- and T3 must NOT have moved it.

    The rule is about FORMAT compatibility. T3 changed dbz VALUES, not the format: a
    1.0-era reader renders a linear-Z package correctly, and the method is recorded
    in `diagnostics.dbz.resampling` where a consumer actually looks. A version number
    that moves for data changes stops meaning "format" -- and a MAJOR would owe an SVT
    import re-test that cannot happen this phase (plan §7).
    """
    v = shipped["format_version"]
    ok = v == contract.FORMAT_VERSION == "1.1"
    return ok, (f"format_version {v} (contract says {contract.FORMAT_VERSION}) "
                "-- unmoved by T3, as a data-only change should be")


def gate_web_block_present(shipped):
    """The web block agrees with the contract -- paths AND version.

    Through T4/T5 this gate deliberately asserted the shipped web version LAGGED the
    contract: `contract` moved to 1.1 then 1.2 while the package stayed 1.0, because
    the 301-frame re-export was batched behind all three tasks (plan §9) and a
    manifest regenerated early would have advertised a format the bricks did not yet
    have. **T6 ran that re-export**, so shipped == contract on every field now; a
    lag here would mean the package is stale again.
    """
    w = shipped.get("web")
    if not isinstance(w, dict):
        return False, "no `web` block -- carried item #2 is not closed"
    ok = (w["dir"] == contract.WEB_DIR
          and w["manifest"] == contract.WEB_MANIFEST
          and w["web_format_version"] == contract.WEB_FORMAT_VERSION == "1.2")
    return ok, (f"dir={w['dir']} manifest={w['manifest']} "
                f"web_format_version={w['web_format_version']} "
                f"== contract {contract.WEB_FORMAT_VERSION}")


def gate_web_is_pointer(shipped):
    """A POINTER, not a census.

    web/ is gitignored and regenerable, so it is absent from a fresh clone. Any
    grid/frame/byte figures copied into the tracked manifest would go stale on the
    next re-export and could not be trusted; web_manifest.json is authoritative.
    Nothing duplicated => nothing to drift.
    """
    w = shipped.get("web", {})
    census = [k for k in ("frames", "frame_count", "grid", "channels", "bytes",
                          "qmax", "voxel_m", "dimensions") if k in w]
    return not census, (f"keys {sorted(w)} -- "
                        + ("no census data copied" if not census
                           else f"CENSUS LEAK: {census}"))


def gate_web_no_prose_census(shipped):
    """A census in PROSE is still a census -- and the key check above is blind to it.

    An earlier draft of `content` enumerated "two files per frame (fNNNN.rgba.gz =
    cloud/ice/rain/graupelhail; fNNNN.dbz.gz ...)". That is exactly the duplication
    the pointer design exists to avoid, and it goes stale at T4/T5: `w` is signed and
    web-export-only, so it cannot ride in the 4-channel rgba plane and the file list
    grows. The prose must point at web_manifest.json, never restate it.
    """
    import re
    pat = re.compile(r"\.rgba\.gz|\.dbz\.gz|f\s*N{2,}|fNNNN|two files per frame",
                     re.IGNORECASE)
    hits = [f"{k}: {m.group(0)!r}"
            for k, v in shipped.get("web", {}).items()
            if isinstance(v, str) and (m := pat.search(v))]
    return not hits, ("no per-frame file layout restated in prose" if not hits
                      else f"PROSE CENSUS: {hits}")


def gate_web_version_bumped(shipped):
    """T4 and T5 each grow the WEB format, so it bumps MINOR -- same major, twice.

    The distinction that decides every version question in this project:
      T3 changed dbz VALUES inside existing files  -> DATA  -> no bump.
      T4 adds a per-frame file, a manifest block and a new encoding
                                                   -> FORMAT -> MINOR bump (1.1).
      T5 adds another per-frame file and block      -> FORMAT -> MINOR bump (1.2).
    Not bumping would assert that "1.0" and "1.0-with-an-updraft-field" are the same
    format, which is false. Bumping the MAJOR would be worse: diorama/src/volume.ts
    refuses a newer major, so it would lock out the very viewer T8 is about to
    extend -- and a 1.0-era viewer genuinely still renders a T4/T5 package correctly,
    because it simply never fetches the files it does not know about.

    T5 is worth stating separately because it is the case where MAJOR is most
    tempting: the file it adds has a different RANK (2D, not 3D). It is still MINOR,
    because rank is a property of the NEW block, which an older reader never fetches;
    nothing that already existed changed shape.

    The bumps are NOT redundant with the `w`/`cref` keys (the trap T3's bump fell
    into): the version declares the GENERATION, the key declares the CAPABILITY, and
    T8/T9 must feature-detect on the key.

    "major stays 1 so volume.ts still accepts it" is CHECKED, not reasoned:
    diorama/src/volume.ts:40 does `parseInt(version.split(".")[0], 10)` and rejects
    only `major > SUPPORTED_MAJOR (1)`. It splits on the dot before parsing, so "1.2"
    yields 1 and is accepted -- a parseFloat there would also have passed `> 1` today
    but would break at "1.10". The split is what makes MINOR bumps safe indefinitely.
    """
    v = contract.WEB_FORMAT_VERSION
    major, _, minor = v.partition(".")
    ok = v == "1.2" and major == "1" and minor == "2"
    return ok, (f"contract web_format_version {v} -- MINOR bump for additive format "
                f"growth (T4 -> 1.1, T5 -> 1.2), major stays {major} so volume.ts "
                "still accepts it")


def gate_minor_bump_is_additive(shipped):
    """1.1 must be readable by a 1.0-era reader: only the `web` key is new.

    This is what makes the bump UE-safe while the UE app is deferred and the SVT
    import contract cannot be re-tested (docs/phase2-plan-2026-07-20.md §7).
    """
    v1_0_keys = {"format_version", "scenario", "kind", "phase", "units", "volume",
                 "channels", "diagnostics", "provenance", "source_run",
                 "frame_count", "frames"}
    added = set(shipped) - v1_0_keys
    removed = v1_0_keys - set(shipped)
    ok = added == {"web"} and not removed
    return ok, (f"added {sorted(added) or 'nothing'}, "
                f"removed {sorted(removed) or 'nothing'} vs the 1.0 key set")


# --- negative controls ------------------------------------------------------

def negative_controls(shipped_text, rebuilt):
    """The byte-identity gate must FAIL on any perturbation of the rebuild.

    A pure `==` is obviously byte-sensitive, but these controls still earn their keep:
    they prove the gate is comparing the WHOLE document (not a length, a hash of a
    subset, or a stale copy), and each perturbs a different structural layer -- a
    version string, an inserted diagnostic key, a prose field, a frame record. If any
    were ACCEPTED, the gate would be silently comparing less than it claims. The
    old-dB-caveat control is the one that would have caught the T3 regression
    slipping back in: it restores the wrong (dB-interpolated) caveat text.
    """
    print("\nnegative controls -- byte-identity must reject every perturbation")

    OLD_DB_CAVEAT = ("dBZ is interpolated in dB space (Phase 1); a known bias that "
                     "hollows echo cores, acceptable for the cloud view.")

    def control(name, mutate):
        doc = json.loads(json.dumps(rebuilt))
        mutate(doc)
        ok, detail = gate_byte_identical(shipped_text, doc)
        _results.append(not ok)
        print(f"  {'PASS' if not ok else 'FAIL'}  fires on: {name}\n"
              f"          {'rejected' if not ok else 'ACCEPTED -- gate is blind'}"
              f": {detail[:96]}")

    def set_dbz(doc, **kw):
        doc["diagnostics"]["dbz"].update(kw)

    control("format_version bumped MINOR",
            lambda d: d.__setitem__("format_version", "1.2"))
    control("format_version bumped MAJOR",
            lambda d: d.__setitem__("format_version", "2.0"))
    control("the T3 `resampling` key was removed",
            lambda d: d["diagnostics"]["dbz"].pop("resampling"))
    control("caveat reverted to the old dB-interpolation text (T3 regression)",
            lambda d: set_dbz(d, caveat=OLD_DB_CAVEAT))
    control("an UNRELATED numeric field changed",
            lambda d: d["volume"].__setitem__("voxel_size_m", 999.0))
    control("an unrelated PROSE field changed",
            lambda d: set_dbz(d, feedback="none at all"))
    control("a frame record was dropped",
            lambda d: d["frames"].pop())
    control("the web format version was reverted to 1.0",
            lambda d: d["web"].__setitem__("web_format_version", "1.0"))
    control("the web format version was bumped MAJOR (locks out volume.ts)",
            lambda d: d["web"].__setitem__("web_format_version", "2.0"))


def main():
    print(f"manifest gates -- {SHIPPED}")
    shipped_text, shipped = load_shipped()
    sc, rebuilt = rebuild(shipped)
    print(f"  scenario {sc.name}: {sc.describe_grid()}, "
          f"{shipped['frame_count']} frames\n")

    print("T1b -- shipped manifest reproducible from committed inputs")
    check("rebuild is byte-identical to the shipped manifest",
          lambda: gate_byte_identical(shipped_text, rebuilt))
    check("export grid derives from the scenario crop box",
          lambda: gate_grid_derived(sc, shipped))

    print("\nT2 -- web block + format_version 1.1")
    check("format_version 1.1, UNMOVED by T3 (data-only change)",
          lambda: gate_format_version(shipped))
    check("web block present and agrees with contract constants",
          lambda: gate_web_block_present(shipped))
    check("web block is a POINTER, not a census",
          lambda: gate_web_is_pointer(shipped))
    check("web block restates no per-frame layout in PROSE either",
          lambda: gate_web_no_prose_census(shipped))
    check("web_format_version bumped MINOR for T4's additive format growth",
          lambda: gate_web_version_bumped(shipped))
    check("the 1.1 bump is purely ADDITIVE (1.0 readers still work)",
          lambda: gate_minor_bump_is_additive(shipped))

    negative_controls(shipped_text, rebuilt)

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
