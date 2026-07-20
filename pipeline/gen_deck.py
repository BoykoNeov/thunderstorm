#!/usr/bin/env python3
"""Generate a CM1 namelist.input from a scenario config.

    python3 pipeline/gen_deck.py --scenario single_cell_500m -o namelist.input
    python3 pipeline/gen_deck.py --scenario single_cell_500m \
        --verify sim/single_cell/namelist.input

`--verify` is the T1c regression gate: it compares the GENERATED deck against a
committed hand-written one by PARSED VALUE, modulo comments and key ordering
(docs/phase2-plan-2026-07-20.md §4). Text comparison is deliberately not used --
the hand-written decks are not column-consistent (` ptype     =  5,` vs
` ptype     =  27,`), so a byte gate would fail on whitespace and prove nothing
about the physics.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm1post import deck, scenario  # noqa: E402


def cmd_generate(args):
    sc = scenario.load(args.scenario)
    text, overrides = deck.generate(sc, template_path=args.template)

    print(f"scenario : {sc.name} ({sc.kind}, {sc.phase})")
    print(f"config   : {sc.source_path}")
    print(f"template : {args.template or deck.DEFAULT_TEMPLATE}")
    print(f"overrides: {len(overrides)} key(s)")
    for k in sorted(overrides):
        print(f"    {k:<14} = {deck.format_value(overrides[k])}")
    print(f"output flags checked: {', '.join(deck.check_output_flags(text))}")
    print(f"export reads: {', '.join(deck.describe_sources())}")

    # The SIM grid is not the EXPORT grid -- print both so they are never confused.
    nml = sc.namelist
    print(f"sim grid : {nml['nx']}x{nml['ny']}x{nml['nz']} @ {nml['dx']:.0f} m "
          f"-> {nml['nx'] * nml['dx'] / 1000:.0f} km domain")
    print(f"export   : {sc.describe_grid()}")

    if args.verify:
        return verify(text, args.verify)

    if args.out:
        with open(args.out, "w", newline="\n") as f:
            f.write(text)
        print(f"\nwrote {args.out} ({len(text)} bytes)")
    else:
        print()
        sys.stdout.write(text)
    return 0


def verify(text, reference_path):
    """Compare generated vs committed deck by parsed value."""
    with open(reference_path) as f:
        want = deck.parse(f.read())
    got = deck.parse(text)

    print(f"\n=== verify against {reference_path} ===")
    print(f"  reference keys: {len(want)}   generated keys: {len(got)}")

    problems = []
    for key in sorted(set(want) | set(got)):
        if key not in got:
            problems.append(f"  MISSING  {key} (reference has {want[key]!r})")
        elif key not in want:
            problems.append(f"  EXTRA    {key} = {got[key]!r}")
        elif not deck.values_equal(want[key], got[key]):
            problems.append(f"  DIFFERS  {key}: reference {want[key]!r} "
                            f"-> generated {got[key]!r}")

    if problems:
        print("\n".join(problems))
        print(f"\nFAIL -- {len(problems)} key(s) differ")
        return 1

    print(f"\nPASS -- all {len(want)} keys match the committed deck "
          "(modulo comments and key ordering)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", required=True,
                   help="scenario name (looked up in sim/scenarios/) or a JSON path")
    p.add_argument("-o", "--out", help="write the deck here (default: stdout)")
    p.add_argument("--template", help=f"base deck (default: {deck.DEFAULT_TEMPLATE})")
    p.add_argument("--verify", metavar="NAMELIST",
                   help="compare against a committed deck instead of writing")
    args = p.parse_args()

    try:
        return cmd_generate(args)
    except (deck.DeckError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
