# Phase 3 T5 — multicell initiation design

**Status: PRE-REGISTRATION. Written and committed BEFORE any probe run.**
Sections 1–6 are predictions and decision rules fixed in advance. Section 7 is
empty by design and is filled only after the runs exist. If a later section
contradicts an earlier one, the earlier one stays on the page with the
correction next to it — that is the whole point of committing this first.

---

## 1. The plan's §2.3 premise, checked against the source first

`docs/phase3-plan-2026-07-20.md` §2.3 framed multicell as "a different CLASS of
work", with initiation that "likely needs `init3d.F` Fortran". T4 has already
shown what happens when a plan premise about CM1's namelist reach goes
unchecked (§4.3 there was falsified in the *expensive* direction — stock CM1 has
no seed knob at all). So the source was read before any code was written again.

**The premise is falsified in the CHEAP direction.** CM1 exposes both the wind
profile and the initiation as namelist integers, and the set includes options
the author labels multicell:

| key | value | meaning (`README.namelist`) | reachable? |
|---|---|---|---|
| `iwnd` | 1 | RKW-type profile (Rotunno–Klemp–Weisman 1988) | namelist |
| `iwnd` | 3 | "multicell" — author's own source comment reads `Mulit-cell type profile (?)`, **no citation** | namelist |
| `iwnd` | 4 | "Weisman–Klemp multicell" — cites WK 1982, MWR 110, 504–520 | namelist |
| `iinit` | 3 | line of warm bubbles | namelist, but see §2 |
| `iinit` | 8 | line thermal with random perturbations | namelist |
| `iinit` | 9 | forced convergence (Loftus et al. 2008) | namelist |
| `iinit` | 12 | updraft nudging (Naylor & Gilmore 2012) | namelist |

**The caveat that keeps this honest:** `README.namelist` annotates both options
with *"[additional variables need to be set in base.F/init3d.F file]"*, and that
is exactly right. The **option selection** is namelist; every **parameter inside
the selected option** is a hardcoded Fortran local. `iwnd=4` is
`umax1=35.0`; `u0 = umax1*tanh(z/3000)` — the shear *magnitude* has no knob.
So the reachable design space is a handful of **fixed profiles**, not a
parameter sweep. §5 is where that bites.

So T5 is not automatically a Fortran task; whether it becomes one is an
empirical question, and §6 pre-commits what answer would force it.

## 2. Candidate shortlist, narrowed on provenance before spending runs

Charter core principle 1: every parameterization cites its paper. Applying that
*before* burning probe runs removes two options on the page rather than in the
data:

- **`iwnd=3` — RULED OUT, not probed.** The source comment is
  `Mulit-cell type profile (?)` — the author's own question mark — and there is
  no reference line, where `iwnd=1`/`4` both have one. Its profile is also odd
  on inspection (u from −12.7 to +52.7 m/s over 7.5 km with a constant
  v=+12.7). An uncited profile cannot ship under the charter, so probing it
  would be spending a run on something unusable even if it worked.
- **`iinit=3` — RULED OUT as "the obvious cheap one".** It *looks* like the
  natural multicell initiation (a line of 3 warm bubbles) but its positions are
  hardcoded `ric=30 km`, `rjc = 3 / 33 / 63 km` — absolute coordinates chosen
  for a small domain. On the 180 km centred (`iorigin=2`) domain those land
  off-centre and clustered in one corner. It cannot be used without a source
  edit, so it is *not* cheaper than the alternatives; it is the most expensive.

That leaves three probe candidates, all namelist-only, all cited:

| ID | `iwnd` | `iinit` | Character being tested |
|---|---|---|---|
| **A** | 4 (WK82) | 1 (single warm bubble) | CM1's own "multicell" label, taken at face value |
| **B** | 1 (RKW88) | 1 (single warm bubble) | Weak-shear cold-pool-driven multicell cluster |
| **C** | 1 (RKW88) | 8 (line thermal + noise) | Squall-line / MCS organisation |

`iinit=8` is the domain-agnostic line thermal (x-centred, no y term in its
`beta`, so it spans the full y extent) — unlike `iinit=3` it needs no source
edit at any domain size.

### 2.1 A prediction, recorded so the probe can falsify it

**I predict candidate A will NOT be multicellular, despite CM1's label.** The
reasoning is arithmetic on the profiles, not recall:

| profile | wind at 6 km | 0–6 km bulk shear |
|---|---|---|
| `iwnd=2` (the project's validated **supercell**) | (31, 7) m/s | **31.8 m/s** |
| `iwnd=4` ("multicell") | (33.5, 0) m/s | **33.5 m/s** |
| `iwnd=1` (RKW88) | (10, 0) m/s | **10.0 m/s** |

`iwnd=4` carries *more* bulk shear than the profile this project has already
verified produces a splitting supercell — it differs mainly in being straight
rather than curved, which should give a *symmetric* split (mirror-image left and
right movers) instead of a right-favoured one. On that ground candidate B is
the more likely multicell, and A is likely a second supercell flavour.

Recording the prediction is the point: if A comes back multicellular, this
paragraph is wrong on the page and the shear arithmetic is not the whole story.

### 2.2 The shear gap this exposes

The reachable profiles are **10, 31.8, 33.5 m/s** of 0–6 km bulk shear. The
multicell↔supercell transition is generally placed *between* those first two
values, and nothing in the namelist reaches it. If the probe finds B too weak
(a single pulse cell, no organisation) and A a supercell, then the multicell
regime sits in a gap that **only a source edit can reach**, and a `0002-` patch
exposing shear magnitude becomes the answer rather than a preference. §6 makes
that a pre-committed branch rather than a judgement call made after seeing the
data.

## 3. The classifier, pre-registered

"Is this a multicell?" is a **classification**, and this project has been burned
twice by criteria written after the fact: T3's "both cores must move" reported
FAIL on correct data, and T4 §5.2's per-mover tracker was found untrustworthy
mid-analysis and its separation column had to be discarded. So the
discriminators and the decision rule are fixed here, before the runs.

### 3.1 Metrics (all frame-local — none requires cell identification)

**M1 — sustained mid-level rotation.** Per-frame `max|uh|` (updraft helicity,
already written by the template's `&param9` block, as is `vort`). This is the
sharpest supercell-vs-multicell discriminator: a supercell has a *sustained,
storm-following* rotating updraft; a multicell does not. `max|·|` rather than
`max` because a straight hodograph gives a cyclonic **and** an anticyclonic
mover, and the anticyclonic one has negative UH.

*UH is frame-invariant* — it integrates `w·ζ`, and vertical vorticity
`ζ = ∂v/∂x − ∂u/∂y` is Galilean-invariant — so a run with `imove=1` and a run
with `imove=0` may be compared on it directly. That is what licenses §5's
different domain-motion settings between candidates and controls.

**M2 — simultaneous cell count.** Connected components of composite
reflectivity ≥ 40 dBZ (`scipy.ndimage.label`, 8-connectivity, minimum area
10 km² to reject specks), per frame. Deliberately `ndimage.label` and **not** an
argmax tracker — the argmax tracker is the exact tool that failed in §5.2.

**M3 — simultaneous updraft count.** Same labelling on column-max
`w ≥ 10 m/s`, minimum area 4 km², per frame, plus each component's peak w. An
*updraft* count is the more direct read of cell multiplicity than an echo count,
since a decaying cell keeps its echo long after its updraft has gone.

**M4 — peak-w location series.** Per frame, `max w` and its horizontal
position. Multicell: pulsing magnitude with the location stepping discretely as
new cells take over. Supercell: quasi-steady magnitude at a near-fixed
storm-relative position. **Read as a descriptor, not a gate** — the location can
also flip between the two movers of a split, which is why it does not appear in
the decision rule below.

**M5 — cold pool (descriptor).** Surface `thpert ≤ −2 K` area and minimum
`thpert`, per frame. Multicell redevelopment is cold-pool-driven, so this is the
*mechanism* behind M3; it is reported, not gated.

**M6 — containment (validity check, not a classification).** Per-frame
clearance from the ≥40 dBZ core and the ≥10 m/s updraft body to each open
boundary, in the style of T1's `probe_edge.py`. See §5.

### 3.2 The decision rule

Absolute thresholds on UH would be a guess (UH is strongly resolution- and
profile-dependent). The **controls set the scale** — that is their job. Let
`SC` = the supercell control and `PC` = the pulse-cell control (§4), and
consider only frames after t = 40 min (before that every candidate is still a
bubble).

A candidate X is classified **MULTICELL** iff all three hold:

1. **Not a supercell.** `frac_frames( max|uh| ≥ 0.25 × median_frames(SC max|uh|) ) < 0.5`.
   *In words:* X spends less than half its mature life with rotation even a
   quarter as strong as the known supercell's typical value.
2. **Not a single cell.** X reaches **≥ 3 simultaneous** updraft components
   (M3) in at least one frame, **or** ≥ 2 simultaneous ≥40 dBZ components (M2)
   in ≥ 5 frames — against PC, which should show 1 and 0 respectively.
3. **A sustained system.** Total ≥40 dBZ area is non-zero across ≥ 60 min, i.e.
   the *system* outlives its individual cells.

X is classified **SUPERCELL** if criterion 1 fails, **regardless of cell
count** — a splitting supercell legitimately shows two components, so count
alone must never outvote sustained rotation. X is classified **SINGLE CELL** if
criterion 1 holds but 2 fails. Anything else is **INDETERMINATE** and is
reported as such rather than rounded to the nearest label.

### 3.3 Why the controls are not optional

Without a known-supercell and a known-single-cell passing through the *identical*
classifier at the *identical* probe settings, "the classifier says multicell" is
unfalsifiable. This is the project's standing rule — *a gate that has only ever
passed is not known to work* — applied to a classifier instead of a test. The
controls are also what turn criterion 1's `0.25 ×` factor from a magic number
into a measured ratio.

## 4. Controls

| ID | Config | Purpose | Expected classification |
|---|---|---|---|
| **SC** | `supercell_333m`'s storm keys (`iwnd=2`, `iinit=1`, `imove=1`, `umove/vmove` 12.5/3.0) | Calibrates the UH scale; the known positive | SUPERCELL |
| **PC** | `single_cell_333m`'s storm keys (`iwnd=0`, `iinit=1`, `imove=0`) | The known negative at the other end | SINGLE CELL |

**If either control does not come back with its expected label, the classifier
is wrong and no candidate result may be reported.** That is the pre-registered
abort condition.

Both controls are re-run at the probe settings rather than reusing T4's
`t4gate_sc` runs, which were written at `tapfrq=600` (10 min). A multicell
cycles new cells on a ~15 min timescale, so a 10 min cadence samples 1–2 frames
per cell and would bias M2/M3 *toward* undercounting — i.e. toward "not
multicell", the answer being tested. The probe therefore uses **`tapfrq=300`**
throughout, and comparability requires the controls share it.

## 5. Domain motion — decided explicitly, and measured

`imove` motion in CM1 is **constant and set a priori**, and the template's
`umove/vmove` are a **Bunkers** estimate — which is a *supercell* motion
formula. A cold-pool-driven cluster or a squall line does not move with a
Bunkers vector. Getting this wrong has already cost this phase one full re-run
(T1's domain enlargement), so it is settled before the probe rather than after.

**Decision:** candidates run `imove=1` with an a-priori **mean 0–6 km wind**,
not Bunkers, stated as such:

| candidate | profile | mean 0–6 km u | `umove` / `vmove` |
|---|---|---|---|
| A | `35·tanh(z/3000)` → `(35·3000·ln cosh 2)/6000` | 23.2 m/s | 23.0 / 0.0 |
| B, C | `10·z/2500` capped at 10 | 7.9 m/s | 8.0 / 0.0 |

Controls keep their own validated settings (SC: Bunkers 12.5/3.0; PC: `imove=0`,
a zero-shear cell that does not translate).

**M6 makes the guess falsifiable inside 13 minutes instead of 4.5 hours.** If a
candidate's system drifts steadily toward a wall, the probe reports the drift
rate and the implied correct motion, and **that candidate's classification is
declared void and re-run** — a storm leaving the window would depress every one
of M1–M3 and could masquerade as "not a supercell". Pre-registered so that a
wall-hitting run cannot be quietly read as a negative result.

## 6. Pre-committed branches on the outcome

| Probe outcome | T5 proceeds as |
|---|---|
| B (or C) classifies MULTICELL | **Namelist-only.** Plan §2.3's premise corrected in the cheap direction; no second fork patch; T5 becomes a T1-shaped task (config + run + measured box). The multicell scenario's identity is then a *wind-profile* change, exactly as the supercell's was a near-empty override set. |
| A classifies MULTICELL | Same, with §2.1's prediction recorded as falsified and the shear arithmetic re-examined on the page. |
| All three classify SUPERCELL or SINGLE CELL | **The §2.2 shear gap is real.** Propose a `0002-` patch exposing the shear magnitude of one cited profile, priced honestly to the owner *before* writing it: a third binary hash, a new row in `sim/cm1-patches/README.md`, and moving the charter CM1 pin that d427ff2 just consolidated into one source of truth. Not undertaken without that go-ahead. |
| INDETERMINATE | Reported as indeterminate with the numbers, not rounded to a label. Next step decided with the owner. |

## 6.1 Two caveats stated up front

**The 1 km caveat.** These probes run at 1 km — the resolution T4 §5.2 used, and
the class WK82 itself ran in — chosen because it costs ~13 min per run instead
of ~4.5 h. 1 km **under-resolves individual cell cores**, so M2/M3 component
counts may bias low and small daughter cells may not appear at all. What
survives at this resolution is the **regime** call — sustained rotating updraft
vs. sequential pulses — and that is what the decision rule in §3.2 rests on. A
namelist-only outcome would still be confirmed at 333 m before shipping.

**A correction to an advisor flag, from the source.** It was flagged that with
`iinit=8`, T4's `var7` seed would also perturb the line-thermal noise — the same
key with different semantics than T4 documented. **Reading `init3d.F` shows the
opposite.** The order is: `random_seed(put=…)` (line ~436, inside
`IF(irandp.eq.1)`) → the `iinit` block (~450–1416, where `iinit=8` draws its own
`random_number`) → the `var7` advance and the `irandp` perturbations (~1446).
The seed advance happens **after** `iinit=8` has drawn, so `seed` does **not**
vary the line-thermal noise; it varies only the separate ±0.25 K `irandp` field.
What `iinit=8` *is* sensitive to is whether `irandp=1` at all, since that is
what seeds the generator in the first place. Recorded because it is the kind of
thing that would otherwise be assumed in either direction.

## 6.2 One correction made BEFORE the probes ran, and why it is not tuning

Recorded here, between the pre-registration and the results, because the
distinction matters: this changed a **candidate's configuration** in response to
a confound found in *T4's* existing run, before any T5 probe had produced data.
It did not change a metric, a threshold, or the decision rule — those are still
exactly as committed in de40eb1.

The classifier was smoke-tested on `t4gate_sc/seed0` (a T4 supercell run) purely
to check its code paths before an hour of runs. That test showed something
unrelated to plumbing:

| t (min) | ≥40 dBZ cells | of which >40 km from the storm | where |
|---|---|---|---|
| 60 | 1 | 0 | (−0.5, 10.5) — the storm |
| 90 | 5 | 4 | x ≈ +77…+81 km |
| 120 | 6 | 4 | x ≈ +75…+79 km |

Those far cells sit **4–14 km from the east wall** on a domain of half-width
90 km, appear only after t≈70 min, and multiply. `irandp` perturbations are
**initial conditions** — ±0.25 K over the *entire* domain at t=0 — and the WK
analytic sounding carries little CIN (the charter already flags CIN as an
unsolved design task), so that noise eventually grows secondary convection
domain-wide, preferentially away from the storm's own subsidence.

**Consequence for candidate C.** C was drafted with `irandp=1`, on the reasoning
that `random_seed(put=…)` sits inside `IF(irandp.eq.1)` and is therefore what
seeds the generator `iinit=8` draws from. That reasoning is true and
**irrelevant**: gfortran's `random_number` is deterministically seeded without
that call, so `iinit=8` gets its noise either way — while `irandp=1` *also* buys
the domain-wide field above. C would then have shown many simultaneous cells and
could have been classified MULTICELL, with the classifier **right about the
count and wrong about the storm**. C now runs `irandp=0`, matching every other
probe; its deck differs from the SC control's in exactly 4 keys
(`iinit`, `iwnd`, `umove`, `vmove`). Charter principle 1 is the real argument:
multicellularity has to come from the initiation and the environment, never from
noise triggering convection everywhere.

**Consequence for the classifier.** A per-frame **descriptor** was added —
count of ≥40 dBZ components whose centroid lies within 15 km of any open wall.
It feeds nothing in §3.2. All five probes run `irandp=0`, so it should read 0
throughout; printing it is what makes that an observation rather than an
assumption.

**Consequence for T4 §5.2, stated because it is unflattering.** Those spread
metrics (pattern correlation, IoU, ≥40 dBZ centroid offset, storm area) were
computed over the *echo union* of `irandp=1` runs, so they included these
boundary cells. The qualitative conclusion — intensity robust, structure
divergent — is unaffected and if anything overdetermined, but the specific
numbers are contaminated: part of the measured "divergence" is two different
noise fields growing different boundary junk, not two storms evolving
differently. The shipped scenarios all run `irandp=0` and are unaffected. §5.2's
numbers should be read with this caveat; they are not re-measured here because
T4's package decision (ship nothing) does not turn on them.

## 7. Results — THE ABORT CONDITION FIRED

**§4's pre-registered abort condition is met: the PC control classified
MULTICELL, not SINGLE CELL. No candidate result may be reported, and none was
read — A, B and C have not been through the classifier at all.** That is the
pre-registration doing its job, and it is worth saying plainly that the order it
forced is what makes the result usable: the classifier was promoted into the repo
and committed (`sim/probes/classify_t5.py`, `pipeline/tests/test_classifier_t5.py`
20/20, commit `3692e9a`) *before* it was pointed at a single probe frame, and the
controls were run and adjudicated on their own, before the candidates.

**This constraint is still live: no candidate may be scored until the replacement
for criterion 2 is agreed (§7.6).** Running the classifier over A, B or C now would
spend the pre-registration for nothing — the abort's whole value is that the rule
was fixed, then found unfit, before anyone saw the answers.

### 7.1 What the controls actually returned

Both control runs are clean as runs. All five probes completed (25 frames each).
Their configs were read back from all five run dirs rather than assumed from one:
**every probe ran `irandp=0`, `seed=0`, `tapfrq=300`, 180² @ 999 m, fork binary
`5fc93016…`** — including candidate C, which is where it mattered, since §6.2's
whole correction was C-specific. (Reading a deck is not reading a result; the
candidates' *output* remains unscored.)

| | SC (`iwnd=2`, Bunkers 12.5/3.0) | PC (`iwnd=0`, `imove=0`) |
|---|---|---|
| median mature `max\|uh\|` | **678.7** m²/s² | **22.0** m²/s² |
| `frac_frames_rotating` (crit 1) | 1.000 | 0.000 |
| max simultaneous updrafts (M3) | 12 | **12** |
| frames with ≥2 cells (M2) | 1 | **4** |
| echo span, mature (crit 3) | 80.0 min | 80.0 min |
| §6.2 boundary-cell frames | 0 | 0 |
| §5 drift (u, v) | −0.31 / +2.13 m/s → implied `umove/vmove` 12.19 / 5.13 | 0.00 / 0.00 |
| min mature clearance (cell / w) | 47.95 / 44.96 km | 77.92 / 77.92 km |
| **label** | SUPERCELL | **MULTICELL** ← abort |

Three pre-registered expectations *held*, and they are the reason the failure can
be localised so precisely:

- **M1 separates the controls by a factor of 30.8.** The rotation discriminator is
  not the problem; §3.1's claim for it is vindicated.
- **§6.2's prediction that the boundary-cell descriptor reads 0 at `irandp=0`
  held**, in all 50 control frames. The domain-wide spurious convection seen in
  T4's `irandp=1` run is absent, as predicted.
- **§5's containment/drift check passes both controls** and voids neither. SC's
  measured drift implies `vmove` ≈ 5.1 against the 3.0 it was given — a 2 m/s
  Bunkers error over 2 h, far inside the 45 km clearance.

### 7.2 SC could not have failed — recording it rather than fixing it

Criterion 1's threshold is `0.25 × median(SC mature max|uh|)` and **SC is scored
against it too**. At least half of SC's frames sit at or above their own median,
which is four times the threshold, so `frac_rot ≥ 0.5` always and SC classifies
SUPERCELL *by arithmetic* — on any data, including an empty domain. `frac_rot`
came back exactly 1.000, which is what that looks like from the outside.

The rule is **not** being changed for this; changing it now would be post-hoc.
What it means is that §4's abort condition was only ever half-live: **SC's job is
to set the scale, not to be an independent check, and PC was the whole test.**
Three gates in `test_classifier_t5.py` feed absurd SC inputs (flat, tiny, wildly
growing) and confirm SUPERCELL comes back every time, so the fact stays visible in
test output instead of being rediscovered while reading results. This is the same
family as T3's symmetric fixture and the standing rule *a gate that has only ever
passed is not known to work* — here, reproduced inside §3.2's self-reference.

### 7.3 Why PC classified MULTICELL: one axisymmetric ring, counted as four cells

PC's pulse cell peaks at **61.6 m/s at t=25** and decays to `max w` 10.6 by t=70.
What trips criterion 2 comes *after* that, and it has an unmistakable signature:

| t (min) | ≥40 dBZ components | w≥10 m/s components |
|---|---|---|
| 60 | 1 × 96 km², pk 63 dBZ @ (0,0) | 1 × 12 km², pk 28 @ (0,0) |
| 85 | 4 × **41 km², pk 52 dBZ** @ (±5,±5) + 1 × 20 km² @ (0,0) | 4 × **25 km², pk 21** @ (±5,±5) |
| 90 | 4 × **52 km², pk 53 dBZ** @ (±5,±5) | 4 × **26 km², pk 19** @ (±5,±5) |
| 105 | 1 × 295 km² @ (0,0) | 12: 4 × 11 km² pk 20 @ (±6,±6), 4 × 10 km² pk 18 @ (0,±6)/(±6,0), 4 × 8 km² pk 15 @ (±9,±9) |

**The four lobes have identical areas and identical peak values, to the digit,
in every frame.** That is not four cells; it is one axisymmetric structure — the
gust-front ring of a zero-shear pulse cell — quantised by a square grid, first
into 4 lobes and then, as the ring expands, into 4 corner + 4 edge + 4 outer
lobes. Connected-component labelling cannot tell "N cells" from "one ring in N
lobes", and §3.1 chose `ndimage.label` precisely *because* it avoids the tracker
that failed in T4 §5.2. It avoided that failure mode and walked into another one.

For contrast, SC's simultaneous components are 100–300 km², separated by 20–58 km,
with different peaks — genuinely distinct updrafts.

### 7.4 Two obvious repairs, both refuted with numbers — and one trap named

Measured on the controls only (`diag_ring.py`, PC frames 75–120):

- **Morphological closing** (merge lobes separated by a grid-scale gap). It works
  late — t=105/110 collapse from 12/8 to 1 at a 2–3 km radius — and **fails
  early**: at **t=75 and t=80 PC still has 4 simultaneous w≥10 components at every
  radius 1, 2, 3, 4 and 5 km.** Criterion 2 arm A needs 3 in *one* frame, so the
  label does not move.
- **Lowering the w threshold** (a ring becomes one annulus). Same shape of
  failure: t=75 gives 4 components at w≥5 and 5 at w≥3; t=105/110 give 8 at w≥5.
- **The trap, named so it is not stumbled into later:** PC's lobes top out at
  26 km², so raising `W_MIN_AREA_KM2` from 4 to ~30 would rescue the control
  immediately. That is exactly *picking the number just above what the control
  did*, and it would also suppress genuine small cells at 1 km in candidate B —
  the candidate the whole probe exists to test. Not done.

### 7.5 The diagnosis: §3.2's PC expectation was naive, not merely mis-implemented

§4 pre-committed the reading "the classifier is wrong" for a control failure. The
evidence supports a sharper statement, which is recorded here rather than
smoothed over: **the classifier miscounts a ring, *and* the expectation that PC
shows "1 and 0" was itself untested.** Those lobes carry peak w 15–32 m/s and
49–56 dBZ — that is convection, not speckle. A zero-shear pulse cell at t = 2 h
has a cold pool and a gust-front ring of daughter cells; "one bubble ⇒ one cell
for 120 minutes" was an assumption nobody had measured, and it is false at 1 km
over this window.

That makes this a **pivot, not a patch**, for three compounding reasons:

1. Component counting cannot separate multiplicity from geometry *at all* — the
   ring proves the metric is unfit, not mis-tuned.
2. Criterion 2 cannot be calibrated against PC the way criterion 1 is calibrated
   against SC. PC's maximum count is **12**, higher than any threshold one would
   set for a multicell, so the symmetric-calibration move that legitimises the
   `0.25 ×` factor is simply unavailable on this axis.
3. The false-positive mode points **straight at candidates B and C** — the
   weak-shear and line-forcing configurations, the two most likely to produce an
   outflow ring. A patched count could return MULTICELL for exactly the wrong
   reason, which is the one outcome worse than no answer.

### 7.6 State, and what the owner is being asked

**Committed:** the classifier, its 20 wiring gates, and this abort. **Not done and
deliberately not done:** any candidate label; any edit to §§1–6; any change to a
metric or threshold. The five probe runs are on disk and cost nothing to re-score
once a discriminator is agreed — this is a *design* decision, not a compute one.

The principled replacement for a count is **organisation**: preferred-flank
regeneration (do daughter cells appear on one side, as with shear, or on all
sides, as in PC's ring?) and system propagation while individual cells cycle. A
symmetric ring fails an organisation test by construction, which is precisely why
it is the right axis. Options, priced rather than chosen:

| Option | What it costs | Risk |
|---|---|---|
| **(A) Re-pre-register criterion 2 as an organisation test**, controls-only, candidates still unread | Metric design + a new pre-registration section; **no new runs** (re-scoring 5 × 25 frames is minutes) | The metric is designed after seeing PC's ring. Mitigation: it is fixed against the controls and committed before any candidate is read — the same discipline that produced this abort |
| **(B) Replace or re-window the PC control** so it is genuinely a single cell | Cheap if it means scoring a shorter window; **expensive** if it means a sounding with real CIN to suppress secondary triggering — that is the charter's open CIN design task | A re-window is close to tuning, and shortening the mature window also amputates the multicell development the probe is looking for |
| **(C) Accept the ring as real multicellularity** and drop criterion 2, classifying on rotation + organisation only | Cheapest | Makes "multicell" mean "not a supercell", which would label PC's decaying pulse cell a multicell — a teaching-grade scenario would then be wrong in the way that matters most |

Recommendation: **(A)**, with (C)'s honesty about criterion 2 folded in — the ring
result stays on the page as the reason the count was retired. §2.2's shear-gap
branch and §6's outcome table are untouched and still pending, because they turn
on candidate results that have not been read.
