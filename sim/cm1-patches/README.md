# CM1 source patches

The project's CM1 is **forked**, as of Phase 3 T4. This directory is the fork:
patches only, applied to a pinned upstream tarball. The full CM1 tree is 346 MB
and is never committed (charter data/git policy: nothing >10 MB in plain git, no
LFS anywhere in this repo).

## Why a fork exists at all

Phase 3 T4 needed **seed-driven outcome variation**. The Phase 3 plan (§4.3)
assumed this was a namelist job — "wires `irandp=1` + the CM1 seed/amplitude
keys". **Those keys do not exist.** Measured in cm1r21.1 before any code was
written:

- `use_truly_random_pert` is a `logical, parameter = .false.` (`init3d.F:168`) —
  a *compile-time constant*, not a namelist value. So the `irandp=1` path always
  takes the "generate same set of pseudorandom numbers every time" branch, which
  seeds from a hardcoded ramp (`sand(n) = nint(2.0e9*(2*(n-1)/(k-1)-1))`).
- Consequence: on stock CM1, `irandp=1` produces the **identical** perturbation
  field on every run. Reproducible, but with **zero** outcome variation.
- No `namelist /paramN/` statement in `input.F` contains a seed or an amplitude
  key. The perturbation amplitude (0.25 K) and the warm-bubble geometry are
  likewise hardcoded in `init3d.F`. `centerx`/`centery` are module variables set
  from domain geometry in `param.F`, not namelist keys.

So a seed variant is not reachable from the namelist, and the fork is unavoidable.

## The reproducibility consequence, handled deliberately

Phase 2 §10.2 earns the claim *"the generated deck reproduces the **run**, not
just the deck"* from the fact that with `isnd=5` the namelist is CM1's **sole**
scenario input, so deck + same binary ⇒ bitwise-identical run. The Phase 3 plan
§2.3 flagged that a source edit breaks half of that.

The two halves are separable, and only one moves:

- **"The namelist is the sole scenario input"** — still true. The patch drives the
  seed from `var7`, an **existing** CM1 namelist key in `&param8`, already present
  in the template and already MPI-broadcast. Nothing new enters the binary as a
  hardcoded scenario value.
- **"The binary is the Phase 0 binary"** — no longer true. Hence this directory,
  the recorded hashes below, and the charter's `Pinned versions → CM1` entry
  naming the fork.

## Provenance chain

| Artifact | sha256 |
|---|---|
| Upstream tarball `cm1r21.1.tar.gz` | `dc49fe84531056d1ae6249b37a5e3ee453fd96861c3b6bafd63828d92e64edf7` |
| Stock binary `run/cm1.exe` (Phase 0, pre-fork) | `5da2c2aa49b9f226cedb5c833219d915dca71c4f328923e47cdbf596bab016bd` |
| Forked binary `run/cm1.exe` (T4, `0001` applied) | `5fc9301623fb2f8b00ebf476cef39b7046e50a2ce0bacfdad560941ae80eb59d` |

The stock hash matches `docs/phase0-cm1-build.md:45` — verified *before* the
patch was applied, so any later difference is attributable to the patch and not
to a binary that had already drifted.

Build configuration is unchanged from `docs/phase0-cm1-build.md` (same Makefile,
same gfortran 13 / OpenMPI 4.1.6 / netCDF). The stock binary is preserved
in-place at `run/cm1.exe.phase0-stock` so the two can be A/B'd.

## Patches

### `0001-seed-via-var7.patch`

**Uncomments CM1's own hook.** The upstream author shipped exactly this loop,
commented out, immediately inside `IF( irandp.eq.1 )THEN`. The patch enables it
and documents the semantics in-source; it adds no new logic.

`var7` (namelist `&param8`) advances the PRNG stream by
`nint(var7)*nk*(ny+2)*(nx+2)` draws before the perturbations are drawn.

**It is a stream OFFSET, not a re-seed** — this is stated plainly because it
bounds the claim. Different seeds get a *shifted reuse of one stream*:
decorrelated at every grid point, but not independently drawn. That is enough
for "same environment, divergent trajectory", which is what the teaching
scenario needs. If independence is ever required, a true `random_seed(put=)`
is a small further edit on this already-forked binary.

Two properties worth banking:

- **`var7 = 0` is a zero-trip loop**, so the fork is bitwise identical to stock
  CM1 at seed 0. Gated — see `docs/phase3-t4-seed.md`.
- **`nint()` makes a negative `var7` zero-trip too**, which would silently alias
  a negative seed to seed 0. `pipeline/cm1post/deck.py` rejects negative and
  non-integer seeds so that collision can never reach a deck.

The perturbation loop iterates the *global* domain on every rank and each rank
applies only the points it owns, so the perturbation field is
**decomposition-independent** — the same seed gives the same field at any rank
count. (This does *not* make a whole run rank-independent: floating-point
summation order still differs, so "same seed ⇒ bitwise identical" holds at a
fixed rank count, which is what the charter's reproducibility contract records.)

## Rebuilding the fork from scratch

```sh
tar xzf cm1r21.1.tar.gz                  # verify the tarball sha256 above first
cd cm1r21.1
patch -p1 < /path/to/sim/cm1-patches/0001-seed-via-var7.patch
cd src && make                           # Makefile per docs/phase0-cm1-build.md
sha256sum ../run/cm1.exe                 # must equal the forked hash above
```

`make`'s `.F.o` rule regenerates `$*.f90` from `$*.F` on every build, so the cpp
artifact cannot go stale against the patched source. Do not edit `init3d.f90`
directly — it is a build product and is overwritten.
