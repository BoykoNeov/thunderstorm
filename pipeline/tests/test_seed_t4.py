#!/usr/bin/env python3
"""Gates for seed-driven variation (Phase 3 T4).

    python3 pipeline/tests/test_seed_t4.py

WHAT THIS FILE CAN AND CANNOT GATE
----------------------------------
The claims T4 actually rests on are RUN properties -- "the forked binary is bitwise
identical to stock at seed 0", "seed 1 produces a different storm", "the same seed
reproduces". Those were measured once, on real CM1, against both binaries
(docs/phase3-t4-seed.md). They cannot live here: they need a 346 MB source tree, two
compiled binaries and six CM1 runs, none of which are in git. Same shape as T3's
links A and B.

What IS gated permanently is the half that can silently rot: the SCENARIO -> DECK
contract. Specifically that a seed reaches CM1 as the value the scenario declared,
and that the three ways a seed can be silently ignored are all refused. Every one of
those three would otherwise produce a deck that generates, runs for hours, and comes
back as the wrong ensemble member -- no crash, no warning.

Reads only committed files -- no CM1 output, no WSL, no network.
"""
import copy
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import deck, scenario  # noqa: E402

SCENARIOS = ("single_cell_500m", "single_cell_333m", "supercell_333m")
PATCH = os.path.join(REPO, "sim", "cm1-patches", "0001-seed-via-var7.patch")

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def mutated(sc, **changes):
    """A copy of the scenario with sim.namelist changes applied (None deletes)."""
    nml = copy.deepcopy(dict(sc.namelist))
    for k, v in changes.items():
        nml.pop(k, None) if v is None else nml.__setitem__(k, v)
    return scenario.Scenario(
        name=sc.name, kind=sc.kind, phase=sc.phase, description=sc.description,
        run_dir=sc.run_dir, export_voxel_m=sc.export_voxel_m,
        crop_half_width_m=sc.crop_half_width_m, crop_z_top_m=sc.crop_z_top_m,
        provenance=sc.provenance, namelist=nml, source_path=sc.source_path)


def expect_error(fn, needle):
    try:
        fn()
    except deck.DeckError as e:
        if needle.lower() in str(e).lower():
            return True, f"refused: {str(e).splitlines()[0][-95:]}"
        return False, f"refused for the WRONG reason: {e}"
    return False, "generator ACCEPTED it -- the guard is dead"


def deck_value(text, key):
    return deck.parse(text).get(key)


# --- the single-source-of-truth check for binary hashes ---------------------
# sim/cm1-patches/README.md is the AUTHORITY. Every other tracked file that quotes
# a CM1 binary hash is checked against it rather than trusted, because a rebuild
# updates one file and silently staleness the rest.

PATCH_README = os.path.join(REPO, "sim", "cm1-patches", "README.md")
CHARTER = os.path.join(REPO, "CLAUDE.md")
TASK_DOC = os.path.join(REPO, "docs", "phase3-t4-seed.md")


def authoritative_hashes():
    """The full sha256s declared in the patches README's provenance table."""
    body = open(PATCH_README, encoding="utf-8").read()
    return set(re.findall(r"`([0-9a-f]{64})`", body))


def _slice(text, start_pat, end_pat):
    m = re.search(start_pat, text, re.M)
    if not m:
        return ""
    rest = text[m.start():]
    e = re.search(end_pat, rest[1:], re.M)
    return rest[:e.start() + 1] if e else rest


def dependent_regions():
    """(label, path, text) for each region that quotes hashes, scoped tightly.

    Scoped rather than whole-file: CLAUDE.md carries unrelated hex (a WSL distro
    GUID, openvdb versions), and a whole-file scan would either false-positive on
    those or have to be loosened until it caught nothing.
    """
    charter = open(CHARTER, encoding="utf-8").read()
    doc = open(TASK_DOC, encoding="utf-8").read()
    return [
        ("CLAUDE.md CM1 pin", CHARTER,
         _slice(charter, r"^- \*\*CM1:\*\*", r"^- \*\*")),
        ("phase3-t4-seed.md §2.1", TASK_DOC,
         _slice(doc, r"^\| Artifact \| sha256 \|", r"^\s*$\n^[A-Za-z]")),
    ]


def main():
    base = scenario.load(os.path.join(REPO, "sim", "scenarios", "single_cell_500m.json"))

    print("=== 1. the seed reaches CM1, under its own name ===")

    def seed_is_required():
        return expect_error(lambda: deck.generate(mutated(base, seed=None)),
                            "missing required key")

    check("a scenario with no `seed` is refused, not defaulted", seed_is_required)

    def seed_becomes_var7():
        # irandp must be on, or the (correct) irandp guard fires first.
        text, ov = deck.generate(mutated(base, irandp=1, seed=7))
        return (ov[deck.SEED_NAMELIST_KEY] == 7.0 and deck_value(text, "var7") == 7.0
                and deck_value(text, "irandp") == 1.0), (
            f"seed=7 -> overrides[{deck.SEED_NAMELIST_KEY}]={ov[deck.SEED_NAMELIST_KEY]}, "
            f"deck var7={deck_value(text, 'var7')}")

    check("seed=N lands in the deck as var7=N (the semantic mapping works)",
          seed_becomes_var7)

    def no_stray_seed_line():
        text, _ = deck.generate(mutated(base, irandp=1, seed=7))
        return "seed" not in deck.parse(text), (
            "the deck has no `seed =` line -- `seed` is the project's name for it, "
            "var7 is CM1's")

    check("`seed` is popped, never emitted as a bogus namelist key", no_stray_seed_line)

    def distinct_seeds_distinct_decks():
        a, _ = deck.generate(mutated(base, irandp=1, seed=1))
        b, _ = deck.generate(mutated(base, irandp=1, seed=2))
        return a != b and deck_value(a, "var7") != deck_value(b, "var7"), (
            f"var7 {deck_value(a, 'var7')} vs {deck_value(b, 'var7')}")

    check("two seeds produce two different decks", distinct_seeds_distinct_decks)

    def same_seed_same_deck():
        a, _ = deck.generate(mutated(base, irandp=1, seed=3))
        b, _ = deck.generate(mutated(base, irandp=1, seed=3))
        return a == b, ("byte-identical (deterministic text substitution -- this is "
                        "the WEAKEST of the reproducibility claims, not the one that "
                        "matters; the run-level one is in docs/phase3-t4-seed.md)")

    check("the same seed produces a byte-identical deck", same_seed_same_deck)

    print("\n=== 2. the three SILENT-ALIASING guards ===")
    print("      each of these would otherwise generate a valid deck that runs for")
    print("      hours and returns the wrong ensemble member")

    def negative_seed():
        return expect_error(lambda: deck.generate(mutated(base, irandp=1, seed=-5)),
                            "negative")

    check("a NEGATIVE seed is refused (nint(-5.0) is zero-trip -> aliases to seed 0)",
          negative_seed)

    def fractional_seed():
        return expect_error(lambda: deck.generate(mutated(base, irandp=1, seed=1.4)),
                            "not an integer")

    check("a FRACTIONAL seed is refused (nint() would alias 1.4 and 0.6 to seed 1)",
          fractional_seed)

    def seed_without_irandp():
        return expect_error(lambda: deck.generate(mutated(base, irandp=0, seed=4)),
                            "irandp=0")

    check("seed>0 with irandp=0 is refused (the advance is inside IF(irandp.eq.1))",
          seed_without_irandp)

    def seed_zero_with_irandp_zero_is_legal():
        text, _ = deck.generate(mutated(base, irandp=0, seed=0))
        return deck_value(text, "var7") == 0.0, (
            "seed=0 at irandp=0 is the honest way to declare an UNSEEDED scenario -- "
            "the guard must not fire here, or all three shipped scenarios break")

    check("seed=0 with irandp=0 is ACCEPTED (guard is targeted, not blanket)",
          seed_zero_with_irandp_zero_is_legal)

    def bool_seed():
        return expect_error(lambda: deck.generate(mutated(base, irandp=1, seed=True)),
                            "non-negative integer")

    check("a BOOLEAN seed is refused (bool is an int in Python -- True would pass a "
          "naive isinstance check and emit var7=1.0)", bool_seed)

    print("\n=== 3. the float trap: seed=0 must not rewrite the template line ===")

    def seed_zero_emits_float():
        # format_value(0) -> "0"; format_value(0.0) -> "0.0". The template line reads
        # `var7      =   0.0,`. An int here rewrites it and breaks byte-identity for
        # every existing scenario -- the same trap the OPTIONAL_KEYS cast avoids.
        text, ov = deck.generate(mutated(base, irandp=0, seed=0))
        emitted = deck.format_value(ov[deck.SEED_NAMELIST_KEY])
        line = [ln for ln in text.splitlines() if ln.strip().startswith("var7")]
        return emitted == "0.0" and len(line) == 1 and "0.0" in line[0], (
            f"emitted {emitted!r}, deck line: {line[0].rstrip() if line else 'MISSING'}")

    check("seed=0 is emitted as 0.0, not 0", seed_zero_emits_float)

    def int_would_break_it():
        # Demonstrate the trap rather than assert today's code is fine: show that the
        # int rendering really does differ, so this gate is not vacuous.
        return deck.format_value(0) == "0" and deck.format_value(0.0) == "0.0", (
            "format_value(0)='0' vs format_value(0.0)='0.0' -- the trap is real, "
            "which is why _seed_to_var7 returns float(s)")

    check("...and the int rendering genuinely differs (gate is not vacuous)",
          int_would_break_it)

    print("\n=== 4. the shipped scenarios are all explicitly unseeded ===")

    def all_shipped_declare_seed():
        rows = []
        for name in SCENARIOS:
            sc = scenario.load(os.path.join(REPO, "sim", "scenarios", f"{name}.json"))
            text, _ = deck.generate(sc)
            rows.append((name, sc.namelist.get("seed"), deck_value(text, "var7")))
        ok = all(s == 0 and v == 0.0 for _, s, v in rows)
        return ok, "; ".join(f"{n}: seed={s} var7={v}" for n, s, v in rows)

    check("every committed scenario declares seed=0 and emits var7=0.0",
          all_shipped_declare_seed)

    print("\n=== 5. the fork is vendored, and says what it does ===")

    def patch_committed():
        if not os.path.isfile(PATCH):
            return False, "sim/cm1-patches/0001-seed-via-var7.patch is MISSING"
        body = open(PATCH, encoding="utf-8").read()
        # The patch must ENABLE the loop: a '+' line carrying the live do-statement,
        # and the '-' side must be the commented-out original.
        adds = [ln for ln in body.splitlines() if ln.startswith("+")]
        dels = [ln for ln in body.splitlines() if ln.startswith("-")]
        enables = any("do n=1,nint(var7)" in ln and "!" not in ln.split("do")[0]
                      for ln in adds)
        removes_comment = any("!" in ln and "nint(var7)" in ln for ln in dels)
        return enables and removes_comment, (
            f"{len(adds)} added / {len(dels)} removed lines; enables the live "
            f"`do n=1,nint(var7)`: {enables}; removes the commented original: "
            f"{removes_comment}")

    check("the CM1 patch is committed and enables the var7 advance", patch_committed)

    def patch_targets_var7():
        body = open(PATCH, encoding="utf-8").read()
        return deck.SEED_NAMELIST_KEY in body, (
            f"deck.py emits {deck.SEED_NAMELIST_KEY!r} and the patch consumes it -- "
            "if someone repoints SEED_NAMELIST_KEY at another varN without "
            "re-patching CM1, the seed silently stops working")

    check("deck.py's SEED_NAMELIST_KEY and the patch agree on which key carries it",
          patch_targets_var7)

    print("\n=== 6. the binary hashes have ONE source of truth ===")
    print("      T2's lesson, one level over: a COPY needs a consistency check.")
    print("      The fork hash is quoted in three tracked files; rebuild CM1 (T5")
    print("      almost certainly will) and two of them go stale SILENTLY.")

    def hashes_agree():
        auth = authoritative_hashes()
        if len(auth) != 3:
            return False, (f"expected 3 hashes in the patches README table, "
                           f"found {len(auth)}: {sorted(auth)}")
        problems, seen_any = [], {}
        for label, path, region in dependent_regions():
            toks = set(re.findall(r"\b[0-9a-f]{8,64}\b", region))
            seen_any[label] = len(toks)
            for t in toks:
                if not any(h.startswith(t) for h in auth):
                    problems.append(f"{label}: {t[:12]}… matches no hash in the "
                                    f"patches README (stale copy?)")
            missing = {h[:8] for h in auth} - {t[:8] for t in toks}
            if missing:
                problems.append(f"{label}: does not mention {sorted(missing)}")
        if problems:
            return False, "; ".join(problems)
        return True, (f"all hashes in {', '.join(f'{k} ({v} tokens)' for k, v in seen_any.items())} "
                      f"agree with sim/cm1-patches/README.md, the single authority")

    check("CLAUDE.md and the task doc quote only hashes the patches README declares",
          hashes_agree)

    def gate_is_not_vacuous():
        # Prove the gate can fail: a plausible stale hash must be rejected.
        auth = authoritative_hashes()
        stale = "5fc93017"           # one hex digit off the real fork hash
        return not any(h.startswith(stale) for h in auth), (
            f"a one-digit-off hash ({stale}…) matches none of the {len(auth)} "
            "authoritative hashes -- so a stale copy really would be caught")

    check("...and a one-digit-off hash would be rejected (gate is not vacuous)",
          gate_is_not_vacuous)

    print("\n" + "=" * 62)
    ok, bad = _results.count(True), _results.count(False)
    print(f"{ok} passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
