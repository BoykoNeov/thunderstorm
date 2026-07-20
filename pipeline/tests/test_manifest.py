#!/usr/bin/env python3
"""Manifest gates (Phase 2 T1b + T2).

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
    text = dumps(rebuilt)
    if text == shipped_text:
        return True, f"rebuilt == shipped, {len(text)} chars byte-identical"
    return False, (f"rebuilt {len(text)} chars != shipped {len(shipped_text)}; "
                   "manifest.build() no longer reproduces the shipped contract")


def gate_grid_derived(sc, shipped):
    """The grid is DERIVED from the crop box -- not restated in the config."""
    want = [sc.nx, sc.ny, sc.nz]
    got = shipped["volume"]["dimensions"]
    return got == want, (f"{got} @ {sc.export_voxel_m:.0f} m, origin "
                         f"{shipped['volume']['origin_m']}")


# --- T2: the web block ------------------------------------------------------

def gate_format_version(shipped):
    v = shipped["format_version"]
    ok = v == contract.FORMAT_VERSION == "1.1"
    return ok, f"format_version {v} (contract says {contract.FORMAT_VERSION})"


def gate_web_block_present(shipped):
    w = shipped.get("web")
    if not isinstance(w, dict):
        return False, "no `web` block -- carried item #2 is not closed"
    ok = (w["dir"] == contract.WEB_DIR
          and w["manifest"] == contract.WEB_MANIFEST
          and w["web_format_version"] == contract.WEB_FORMAT_VERSION)
    return ok, (f"dir={w['dir']} manifest={w['manifest']} "
                f"web_format_version={w['web_format_version']}")


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


def gate_web_version_not_bumped(shipped):
    """Package 1.0 -> 1.1 must NOT have moved the brick format version.

    diorama/src/volume.ts refuses a newer MAJOR web_format_version; the brick
    layout, quantization and reader contract were untouched by T2.
    """
    v = shipped["web"]["web_format_version"]
    return v == "1.0", f"web_format_version {v} (brick format unchanged by T2)"


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
    check("format_version is 1.1 and matches contract.py",
          lambda: gate_format_version(shipped))
    check("web block present and agrees with contract constants",
          lambda: gate_web_block_present(shipped))
    check("web block is a POINTER, not a census",
          lambda: gate_web_is_pointer(shipped))
    check("web block restates no per-frame layout in PROSE either",
          lambda: gate_web_no_prose_census(shipped))
    check("web_format_version NOT bumped (brick format unchanged)",
          lambda: gate_web_version_not_bumped(shipped))
    check("the 1.1 bump is purely ADDITIVE (1.0 readers still work)",
          lambda: gate_minor_bump_is_additive(shipped))

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
