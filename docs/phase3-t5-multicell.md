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

---

## 8. RE-PRE-REGISTRATION of criterion 2 — organisation, not count

**Owner call, 2026-08-10: option (A).** This section is written and committed
BEFORE any candidate is scored, exactly as §§1–6 were. A, B and C are still
unread.

**The honesty caveat this section cannot escape, stated first.** §§1–6 were
written before *any* data existed. §8 is not: it is written after seeing the two
CONTROLS, because the ring is what retired the count. Candidates remain unread,
which is the property that matters — the discriminator cannot have been shaped by
the answer it will produce. Where §8 is weaker than §3, it says so.

### 8.1 What does NOT change

Criterion 1 (rotation), criterion 3 (sustained system), the mature window
(t ≥ 40 min), and **every one of the six field thresholds** — `DBZ_CELL` 40,
`DBZ_MIN_AREA_KM2` 10, `W_UPDRAFT` 10, `W_MIN_AREA_KM2` 4, `COLDPOOL_K` −2,
`MATURE_MIN` 40. The area minimum in particular is deliberately **left at 4 km²**:
§7.4 identified raising it as the tuning trap, and a re-pre-registration that
quietly took the trap would be worse than the original error. Criterion 1 keeps its
SC-relative calibration; it separated the controls 30.8× and nothing impeaches it.

### 8.2 The replacement: criterion 2′ — ORGANISED multiplicity

Multiplicity alone is not multicellularity; PC proved that. What distinguishes a
multicell system from a decaying cell's outflow ring is that its cells are
**organised** — they regenerate on a preferred flank, or they line up. Both are
statements about the *geometry of the component set*, and both are computable
frame-locally without identifying or tracking a single cell.

For each **qualifying frame** — mature, with ≥2 updraft components (w ≥ 10 m/s,
≥4 km²) and a ≥40 dBZ echo present — two shape statistics of the component
centroids:

**O1 — flank coherence `R` (first moment).** Let `c` be the echo centroid (the
≥40 dBZ mask centroid: an *independent* anchor — using the updraft components' own
mean would force `R ≡ 0` by construction). With `û_i` the unit vector from `c` to
component *i*'s centroid and `a_i` its area:

```
R = |Σ a_i û_i| / Σ a_i        R ∈ [0, 1]
```

This is the standard area-weighted circular resultant length. **R = 0 is exactly
the ring** — PC's four lobes at (±5,±5) with identical areas cancel to zero by
symmetry — and **R → 1 is all new convection on one flank**, which is what
cold-pool-driven regeneration in shear looks like. A component sitting exactly on
the anchor is skipped (its direction is undefined), not counted as zero.

**O2 — elongation `E` (second moment).** `E = √(λ₁/λ₂)`, the axis ratio of the
covariance of the **updraft mask's voxels** — every w ≥ 10 m/s voxel in the
surviving components, so *n* is in the thousands and the weighting is area by
construction. Frames with ≥3 components qualify (with 2 components an elongation
statement is not meaningful, and those frames are scored on `R` alone).

**Not the covariance of the component centroids, and that distinction is
measured, not stylistic.** `E` estimated from three centroid points is nearly
free: under an isotropic null of random triples the median `E` is **3.72**, and
**79.7 %** of triples clear 2.0 (n=4: 64 %; n=5: 52 %; n=12: 11 %). A floor of 2.0
on a 3-point ellipse would fire on unorganised convection roughly four times in
five — and **PC could never have caught it**, because its ring-symmetric 4/8/12
components give `E ≈ 1` either way. The voxel covariance has no such bias and
separates the shapes that matter: on synthetic blobs, ring-of-4 **1.00**,
ring-of-12 **1.00**, an unorganised compact triple **1.09**, a one-sided flank
cluster **1.85**, a five-cell line **8.37**.

**O2 exists because of candidate C, and without it C would be a false negative by
construction.** A squall line is the canonical multicell system, and its cells sit
symmetrically *about* the centroid — first-moment coherence `R ≈ 0`, the same
answer as the ring. The second moment separates them: a line is elongated
(`E ≫ 1`), a ring is isotropic (`E ≈ 1`).

**Criterion 2′ holds iff both:**

1. **Sustained multiplicity** — ≥ **5** qualifying frames (25 min at `tapfrq=300`).
   Not a new constant: 5 is the pre-registered `MIN_FRAMES_WITH_2_CELLS`, reused
   rather than reinvented.
2. **Organisation** — over the qualifying frames, `median(R) ≥ 0.5` **or**
   `median(E) ≥ 2.0`.

**Why those two numbers are floors and not fits.** They are geometric statements
fixed a priori, readable without reference to any run: `R ≥ 0.5` means the
area-weighted mean direction of the convection is at least half-coherent (a
hemisphere-worth of preference rather than a ring); `E ≥ 2` means the cluster is at
least twice as long as it is wide. Neither was read off a control's distribution.

**This is deliberate, and it is what keeps PC a LIVE control.** The obvious move —
threshold at PC's 95th percentile — would have repeated §7.2's mistake one level
down: a run's median can never exceed its own p95, so PC would fail by arithmetic
and *both* controls would be tautologies, leaving the abort condition with nothing
live in it. With fixed floors, PC can genuinely come back MULTICELL again if its
ring turns out to be anisotropic. PC's measured `R`/`E` distributions are still
reported — as **evidence about the null, not as the threshold**.

### 8.3 Order matters: criterion 1 still runs first

A splitting supercell puts two movers on opposite flanks, so `R ≈ 0` and, with
two components, no `E` — a supercell would *fail* criterion 2′. It never gets
there: `crit1` is evaluated first and rotation outvotes everything, exactly as
§3.2 pre-registered. The ordering was load-bearing before and is more so now.

### 8.4 Labels, controls, abort condition — unchanged in form

`crit1` False → **SUPERCELL**. `crit1 ∧ crit2′ ∧ crit3` → **MULTICELL**.
`crit1 ∧ ¬crit2′` → **SINGLE CELL** — and this is where PC's ring must now land.
Anything else → **INDETERMINATE**.

**The abort condition stands and is re-armed:** SC must return SUPERCELL and PC
must return SINGLE CELL, or no candidate is scored. As §7.2 established, SC's half
is arithmetically forced and carries no information; **PC's half is live**, and
under §8.2's fixed floors it is live in the strong sense — PC has already failed
this abort once and nothing about the new rule guarantees it passes.

### 8.5 What is reported but does not gate

`R` and `E` per frame for all five runs; PC's null distribution; M4's peak-w
location series and M5's cold pool (descriptors from §3.1, unchanged); and the
§5 drift/void check, which voided neither control and is applied to candidates
unchanged.

### 8.6 What would falsify this section

Recorded so §8 is exposed the way §2.1's prediction was. **The uncertainty band is
two-sided, deliberately.** A statistic inside `R` **0.40–0.60** or `E`
**1.67–2.40** is uncertainty, not evidence, in *either* direction: a candidate
landing just over a floor is **not** a MULTICELL result to be banked, and one
landing just under is **not** a SINGLE CELL result either. Both are reported as
INDETERMINATE with the numbers. So the value that banks a MULTICELL is `R ≥ 0.60`
or `E ≥ 2.40`, and the value that banks a SINGLE CELL is `R < 0.40` **and**
`E < 1.67`.

**The band is per-statistic, and criterion 2′ is an OR.** A candidate whose `R` is
decisive (say 0.97) is not made uncertain by an `E` that happens to sit near its
own floor — only the statistic that *decides* the outcome has to be clear of its
band. This was caught by a fixture, not by reasoning: the one-sided flank cluster
(`R` 0.97, `E` 1.85) came back INDETERMINATE under the first draft of this
paragraph, which was wrong about a case the rule is supposed to be sure of.

The under-side is not symmetry for its own sake — it is aimed at a named risk.
**Candidate B is the weak-shear case (10 m/s), where cold-pool regeneration is only
weakly preferred downshear**, so B's plausible landing zone is `R ≈ 0.3–0.5`: right
at the floor. Without the under-band, `B → SINGLE CELL` would be ambiguous between
"B is not a multicell" and "the floor sits above weak-shear organisation", and
nothing on the page would let a reader tell which. A one-sided band is a thumb on
the scale toward the negative result.

And if PC returns MULTICELL a second time, criterion 2′ is wrong too, and the honest
conclusion is that this classifier cannot separate the regimes at 1 km — which
would be a real answer about the probe design, not a failure to be patched a
third time.

### 8.7 Measurements taken on the controls before §8 was committed

Three checks were run against SC and PC (and synthetic shapes) while §8 was being
drafted, before it was committed and with the candidates unread. All three are
listed whether or not they changed anything — a check that is only reported when
it fires is not a check.

1. **The `E`-from-3-points bias — CHANGED THE RULE.** Measured above; O2 moved
   from centroid points to the union mask because of it.
2. **`R`'s area weighting near the anchor — CHECKED, NO CHANGE.** The concern: the
   parent updraft is usually both the largest component and the closest to the echo
   centroid, so its unstable heading would carry the largest weight. Recomputing
   `R` with components inside 2Δx of the anchor excluded moves **nothing on PC**
   (identical to three decimals in all 10 qualifying frames) and moves **one SC
   frame** (t=65: 0.598 → 0.631). Not material, so no exclusion is added — but the
   minimum component-to-anchor distance is reported per frame so the assumption
   stays visible.
3. **The floors were fixed before these numbers were seen, and did not move.**
   `R ≥ 0.5` and `E ≥ 2.0` were written into the §8.2 draft on geometric grounds;
   the control measurements below were taken afterwards and neither floor was
   adjusted to them.

**Measured null (controls, mature qualifying frames):**

| | `R` | `E` (mask) |
|---|---|---|
| **PC** (the ring) | 0.000–0.041, median **0.000** | **1.00 in every frame** |
| **SC** (supercell + flanking cells) | 0.191–0.943, median **≈0.49** | 1.29–2.12, median **≈1.83** |

PC's ring is annihilated by both statistics, which is the intended behaviour and
the reason for the pivot. The SC row is the more interesting one: a supercell's
scattered flanking convection sits at `R ≈ 0.49` and `E ≈ 1.83` — *just under both
floors*. So the floors are not generous thresholds that anything organised clears;
they are set at roughly "more organised than a supercell's flank scatter". SC's
label does not depend on this (criterion 1 catches it first, §8.3), which is what
makes the number usable as calibration rather than as a result.

---

## 9. Results — candidates scored under §8

### 9.1 The re-armed abort condition PASSED

| control | label | median `R` | median `E` | near a floor? |
|---|---|---|---|---|
| SC | **SUPERCELL** (crit 1, as forced) | 0.485 | 1.84 | both, but crit 1 decides first |
| PC | **SINGLE CELL** ✔ | **0.006** | **1.000 in every frame** | no |

PC — the run that produced the §7 abort — now lands SINGLE CELL and lands it
*decisively*, nowhere near the §8.6 band. Criterion 2′ did to the ring exactly what
it was designed to do, and only then were the candidates scored.

### 9.2 The candidates

All figures over mature frames (t ≥ 40 min). `uh` is CM1's standard **integrated
2–5 km AGL updraft helicity** — read from the file's own metadata, not assumed.

| run | median `max\|uh\|` | frac rotating | peak w | median cells | median updrafts | median `R` | median `E` | **label** |
|---|---|---|---|---|---|---|---|---|
| SC (control) | 678.7 | 1.00 | 60.7 | 1 | 4 | 0.485 | 1.84 | SUPERCELL |
| PC (control) | 22.0 | 0.00 | 61.6 | 1 | 4 | 0.005 | 1.00 | SINGLE CELL |
| **A** `iwnd=4` WK82 "multicell" | **1132.4** | 1.00 | 52.9 | 1 | 2 | 0.506 | 2.30 | **SUPERCELL** |
| **B** `iwnd=1` RKW88 | 349.9 | 1.00 | 56.2 | 1 | 2 | 0.192 | 3.14 | **SUPERCELL** |
| **C** `iinit=8` line thermal | 271.5 | 0.94 | 46.7 | 3 | **15** | 0.125 | **20.76** | **SUPERCELL — but VOID, §9.5** |

**No candidate returned MULTICELL.** That is §6's third row, whose consequence is
pre-committed. Before it is acted on, three things have to go on the page.

### 9.3 §2.1's prediction is CONFIRMED — by a bigger margin than predicted

§2.1 predicted, from shear arithmetic alone and before any run existed, that
*candidate A will not be multicellular despite CM1's label*. It is not. A is a
**supercell that out-rotates the supercell control** — median `max|uh|` **1132**
against SC's 679, peaking at 1605 — a single sustained cell whose echo centroid
tracks steadily southwest. `iwnd=4` carries 33.5 m/s of 0–6 km bulk shear against
`iwnd=2`'s 31.8, and the extra shear did what extra shear does. The label in
`README.namelist` is not a prediction about the storm; it is a name on a wind
profile. The cheap half of §2.2's argument is now empirical: both cited profiles
above 30 m/s make supercells.

### 9.4 B is a rotating cell, not a cluster

Candidate B — the one §2.1 called "the more likely multicell" — is a **single
rotating updraft** for its whole mature life: `n_cells` = 1 in 16 of 17 mature
frames, 1–4 updraft components, median `R` 0.192 (no flank preference). Its
rotation is real and sustained (`max|uh|` 236–562, never below the bar) but sits
**2.4× below** the SC control. It does elongate late (`E` 2.5–3.2 after t=105) —
organised multiplicity by criterion 2′ — but criterion 1 decides first (§8.3).

The honest reading: at 10 m/s of bulk shear with this WK sounding, one warm bubble
gives a **marginal rotating cell**, not the cold-pool-driven cluster the weak-shear
regime was supposed to produce. Whether "supercell" is the right word for it is
exactly what §9.6 is about.

### 9.5 C is VOID — structurally, not because a storm escaped

C trips **both** validity checks, and neither is about drift:

- §5 containment: clearance **0.00 km in every mature frame** → void.
- §6.2's boundary descriptor: **17 frames** with cells near a wall, against a
  predicted 0 at `irandp=0`.

The cause is `iinit=8` itself. Verified in the netCDF rather than inferred: C's
≥40 dBZ echo occupies **all 180 y rows, wall to wall, in every frame** (x extent
−5.5…+11.5 km at t=45). §2 chose `iinit=8` precisely *because* it is
domain-agnostic — "x-centred, no y term in its `beta`, so it spans the full y
extent" — and that same property makes it **structurally incapable of satisfying a
containment criterion written for a compact storm**. §6.2's prediction is not
falsified here; it is inapplicable to a domain-spanning line.

**So C is unevaluable as run** — and its numbers are the most interesting on the
page: 15 simultaneous updraft components, 3 cells, `E` = **20.8** against the 2.0
floor and PC's 1.00. Criterion 2′ says *organised multiplicity* as loudly as it can.
C is a squall line, by construction and by measurement. It is denied MULTICELL by
criterion 1 — not by criterion 2′, and not by its void.

### 9.6 The sensitivity that qualifies all of the above

Criterion 1's factor — 0.25 — was pre-registered before any data and is **not**
being changed. But its influence must be reported, because it is what decides B
and C. Fraction of mature frames at or above `k ×` SC's median:

| k → | 0.15 | **0.25** | 0.40 | 0.50 | 0.75 | 1.00 |
|---|---|---|---|---|---|---|
| SC | 1.00 | **1.00** | 1.00 | 1.00 | 1.00 | 0.53 |
| PC | 0.06 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 |
| A | 1.00 | **1.00** | 1.00 | 1.00 | 1.00 | 1.00 |
| B | 1.00 | **1.00** | 0.94 | 0.53 | 0.12 | 0.00 |
| C | 1.00 | **0.94** | 0.53 | 0.18 | 0.12 | 0.00 |

Three readings, in descending order of confidence:

1. **PC's separation is robust and A's label is unconditional.** PC never rotates
   at any bar the controls permit; A rotates at *every* bar, including k=1.0.
   Neither result depends on the factor.
2. **B's and C's labels turn entirely on it.** At k=0.5, C stops being a supercell
   (0.18) and B is on the knife edge (0.53); at k=0.75 both are comfortably
   not-supercells — which, with `E` 3.14 and 20.8, would make both **MULTICELL**.
3. **The controls place no ceiling on the bar — and the tautology is why.** An
   earlier draft of this paragraph claimed SC falls to 0.47 at k=1.0 and so
   "breaks the control", boxing the question into k ∈ [0.4, 0.75]. **Both halves
   were wrong.** The 0.47 was a rounding artifact: the analysis script hardcoded
   the printed median `678.7` while the exact median is `678.6939…`, so the median
   frame itself dropped out of its own comparison. Against the exact value SC reads
   **0.529**. And it could not have read otherwise: for odd *n* the fraction of
   frames at or above the median is always (n+1)/2n — here 9/17 — which **exceeds
   0.5 by definition**. SC cannot fail criterion 1 at any k ≤ 1.0.

   That is **§7.2's self-reference recurring one section later**, unnoticed until
   the number looked wrong. It means the honest range is **k ∈ [0.4, 1.0]**, over
   which PC stays flat at 0.00 and SC is arithmetically safe throughout — so
   nothing in the control design rules out a higher bar, and §9.8's option (iii)
   is *less* fenced off than the earlier draft implied.

That is a real limit of this probe design, found by running it. **Moving the factor
now, having seen this table, would still be the exact post-hoc move §7 and §8 exist
to prevent** — the point of correcting the arithmetic is to describe the option
honestly, not to take it.

### 9.7 What criterion 2′ earned

Independent of the labels, §8's replacement did its job on real data: it fired on
neither control, it annihilated the ring that caused the abort (`E` = 1.000 in
every PC frame, `R` = 0.006), and it separated that ring from a genuine line by a
factor of **20** on the same statistic. Validated in the field, not only on
fixtures.

### 9.8 The §6 branch that fires, and what the owner is asked

By the letter of §6, row 3 fires — all three candidates classify SUPERCELL → the
§2.2 shear gap is real → propose the `0002-` patch, priced, and do not write it
without a go. The price stands as §6 stated it: **a third binary hash, a new row in
`sim/cm1-patches/README.md`, and moving the charter's CM1 pin that `d427ff2` just
consolidated into one source of truth.**

But §9.5 and §9.6 mean that row is not the only live option, and presenting it as
the automatic next step would be dishonest. Three, priced rather than chosen:

| Option | What it buys | What it costs | Honest risk |
|---|---|---|---|
| **(i) `0002-` shear patch** — §6's pre-committed branch | Reaches the 10–31.8 m/s gap where the multicell regime is generally placed | Third binary hash; patches-README row; charter pin moves; a second fork to carry forever | The gap is *inferred* from three profiles, not measured. If B at k=0.75 is really a multicell, the gap may already be reachable and the patch unnecessary |
| **(ii) Re-run C contained** — same `iinit=8` line, in a form the domain can hold, so containment and §6.2 mean something | C is already the strongest organised-multiplicity signal on the page (`E` 20.8, 15 updrafts). Making it evaluable could answer T5 with no patch at all | One 13-min probe run, plus a source read on whether `iinit=8`'s y-extent is reachable without a patch | It may not be: §1's caveat is that parameters *inside* an option are hardcoded. If so this collapses into (i) — a patch, just a different one |
| **(iii) Re-pre-register criterion 1** | Criterion 1 is the real blocker for B and C, and §9.6's corrected reading shows the controls do not fence it off. The fix worth making is **a different discriminator, not a different k** — requiring rotation to *persist at a fixed storm-relative position*, which is what actually distinguishes a mesocyclone from an ordinarily tilted updraft. Settles both candidates with no new runs | A third pre-registration round, written against the controls with the candidates re-blinded | Doing this *after* §9.6's table is the post-hoc hazard in its purest form. It is only defensible for a discriminator justified on physical grounds independently of which way it moves B and C — and *tuning k* would not qualify |

**Owner call, 2026-08-10: option (ii).** Design and prediction in §10, written
before the run.

**Recommendation as given at the time: (ii) first, with (iii) close behind.** (ii) is one 13-minute run
against the candidate that already shows the multicell signature, and it needs
neither a moved threshold nor a second fork. (iii) is the principled fix — and it
is stronger than the first draft of §9.6 made it look, since the controls turn out
to permit the whole range — but it is also the one with the post-hoc hazard, so it
should follow (ii) rather than pre-empt it. (i) stays last: it is the most
expensive, and its premise weakens if (ii) or (iii) turns up a multicell in an
environment the namelist already reaches. None starts without an owner go.

---

## 10. PRE-REGISTRATION of the contained-C re-run (option ii)

Written before the run exists, like §§1–6 and §8.

### 10.1 The source read that came first — and changed the plan

§9.8's option (ii) was framed as "same `iinit=8` line, in a form the domain can
hold". **That form does not exist.** `init3d.F` at the `iinit=8` branch sets its
entire geometry as hardcoded locals — `ric = centerx`, `bhrad = 10000.0`,
`bvrad = 1500.0`, `bptpert = 2.0`, `amplitude = 0.20` — and its `beta` is

```
beta = sqrt( ((xh(i)-ric)/bhrad)**2 + ((zh(i,j,k)-zc)/bvrad)**2 )
```

with **no y term at all**. The line is not "long"; it is *infinite in y* by
construction, and there is no parameter — namelist or otherwise — that shortens
it. §1's caveat lands exactly as written: the option selection is namelist, the
parameters inside it are Fortran.

**So the fix is not the line. It is the boundary.** A domain-spanning line with
**periodic** y walls is the standard along-line configuration for squall-line
simulations, and CM1 exposes it as a namelist integer: `sbc`/`nbc` = 1 (`1 =
periodic`, `2 = open-radiative`, `README.namelist` line 569). The template runs 2
on all four sides, which is right for a compact storm and wrong for a line. Under
periodic y the same line stops being a containment failure and becomes the
intended setup — **no patch, no third binary hash, and the CM1 pin does not move.**

### 10.2 The criterion change this forces, and why it is not a loophole

§5's containment check and §6.2's descriptor both ask *"is the storm leaving the
window?"* **A periodic boundary is not a window.** Measuring clearance to it is
the §9.5 error stated positively rather than negatively: not "C failed
containment" but "containment was the wrong question in that direction".

Both are therefore now measured **against open boundaries only**, read from the
run's own `sbc`/`nbc`/`wbc`/`ebc` rather than assumed. Three guards against this
becoming a way to make an inconvenient void disappear:

1. **The x direction is still checked, and it is the one that matters** — a squall
   line propagates across-line, so the direction it can actually escape through
   stays open and stays measured. A test asserts a wall-touch in x still fires
   under periodic y.
2. **Absent keys default to open**, so every run made before this change scores
   exactly as it did. Verified, not asserted: re-scoring SC, PC and C reproduces
   0.4854/1.84, 0.0055/1.00 and 0.1247/20.757 to the digit, and **C stays VOID**.
3. **A fully periodic domain reports no clearance at all** rather than a
   reassuring number.

### 10.3 The run

`t5probe_c2`: candidate C's deck with `sbc = nbc = 1`, everything else byte-identical
(`iwnd=1`, `iinit=8`, `irandp=0`, `seed=0`, `umove=8`, 180² @ 999 m, `tapfrq=300`,
2 h, fork binary `5fc93016…`). One 13-minute run at 4 ranks. Scored by the
**unchanged** §8 rule — no threshold, floor, band or factor moves.

### 10.4 A prediction, recorded so the run can falsify it

**I predict C2 will still classify SUPERCELL, and that option (ii) will therefore
hand back "the blocker is criterion 1, not containment".**

The reasoning is on the page already: C was denied MULTICELL by criterion 1
(`frac_rot` 0.94), not by criterion 2′ (`E` 20.8, far past its floor) and not by
its void. Making the run evaluable removes the void, but nothing about periodic y
obviously removes 2–5 km rotation from a line of vigorous 1 km updrafts. Periodic
walls will change the flow near the old y edges and may lower `max|uh|` somewhat —
if that drop is large enough to push `frac_rot` below 0.5, C2 is a MULTICELL and
this paragraph is wrong on the page.

Two consequences fixed in advance, so neither is a judgement call made after
seeing the number:

- **If C2 → MULTICELL:** T5 is answered namelist-only. The multicell scenario is
  `iwnd=1` + `iinit=8` + periodic y, §2.3's premise is corrected in the cheap
  direction, no fork, and T5 becomes a T1-shaped task (config, run, measured box).
- **If C2 → SUPERCELL:** option (ii) is spent and the answer is §9.8's (iii) — the
  criterion-1 discriminator — *not* (i). Rotation, not shear reach, is then the
  demonstrated blocker, and buying a second CM1 fork to widen the shear range
  would be paying for the wrong thing.

---

## 11. Results — C2, and what option (ii) actually bought

The run is on disk (`~/thunderstorm/runs/t5probe_c2`, `PROBE_OK`, 32.5 min at 4
ranks, 25 frames). Provenance from its own log rather than re-asserted here:
`cm1_binary_sha256 5fc9301623fb…` (the fork), `irandp = 0` in the override dump,
`sbc`/`nbc` = 1 among 31 overrides, and the classifier's own header line reads
**`open sides x`** — the run is being scored against the boundary type it was
given.

### 11.1 The containment fix worked, and the diagnosis holds

| | C (§9.5) | C2 |
|---|---|---|
| open sides | x **and y** | x only |
| §6.2 boundary-cell frames | **17** | **0** |
| min cell clearance | **0.00 km** | **69.93 km** |
| min w clearance | **0.00 km** | **68.93 km** |
| §5 verdict | **VOID** | valid |
| implied `umove`/`vmove` from drift | 9.23 / −1.24 | 9.16 / −0.30 |

C's void was `iinit=8`'s geometry, exactly as §10.1 read it off the source — not a
storm escaping. Changing the boundary type and nothing else (the deck differs in
**2 of 413 lines**, both boundary keys) turns a run that touched the wall in every
frame into one with ~69 km of clearance. **Namelist-only: no patch, no third binary
hash, the CM1 pin did not move.**

### 11.2 The score, under the unchanged §8 rule

| run | label | `frac_rot` | crit1 ¬SC | median `R` | median `E` | qual. frames | crit2′ | crit3 |
|---|---|---|---|---|---|---|---|---|
| SC (control) | SUPERCELL | 1.000 | ✗ | 0.485 | 1.84 | 13 | ✗ | ✓ |
| PC (control) | SINGLE CELL | 0.000 | ✓ | 0.006 | 1.00 | 10 | ✗ | ✓ |
| A | SUPERCELL | 1.000 | ✗ | — | — | — | — | ✓ |
| B | SUPERCELL | 1.000 | ✗ | — | — | — | — | ✓ |
| C | SUPERCELL **[VOID]** | 0.941 | ✗ | 0.125 | 20.76 | 17 | ✓ | ✓ |
| **C2** | **SUPERCELL** | **0.765** | **✗** | **0.129** | **19.04** | **17** | **✓** | **✓** |

No threshold, floor, band or factor moved, as §10.3 fixed in advance. Both
controls re-scored identically to §9.1.

### 11.3 §10.4's prediction is CONFIRMED, and the §10.4 branch fires

C2 classifies SUPERCELL. The second branch was pre-committed: **option (ii) is
spent, and the answer is §9.8's (iii) — the criterion-1 discriminator — not (i).**

What (ii) bought is worth stating precisely, because it is more than "no change".
**C2 is the first non-void run with crit2′ ∧ crit3 ∧ ¬crit1.** C had the same
signature and was voided, so its isolation was confounded; SC, PC and B all fail
crit2′; A fails crit1 at every k in the sweep below. On C2 the organisation
criterion says multicell **decisively** — median `E` 19.04 is 7.9× the banded floor
of 2.40 — the sustained-system criterion passes, containment is clean, and the sole
dissenting voice is criterion 1. That is a measurement of where the blocker is, not
a reading of one.

### 11.4 The finding: criterion 1 is a median comparison, and supplies no temporal robustness

The k-sweep produced a column it was not built to produce. Every run's flip point
— the k above which `frac_rot` drops below 0.5 — is **exactly** its own
`median(mature max|uh|) ÷ SC's median`:

| run | median mature `max\|uh\|` | ÷ SC median | k_flip measured |
|---|---|---|---|
| A | 1132.4072 | 1.668509 | 1.668509 |
| SC | 678.6939 | 1.000000 | 1.000000 |
| B | 349.8639 | 0.515496 | 0.515496 |
| C | 271.5086 | 0.400046 | 0.400046 |
| **C2** | **197.3048** | **0.290713** | **0.290713** |
| PC | 22.0080 | 0.032427 | 0.032427 |

Match to 1e-12 in all six. It is not a coincidence: with `UH_FRAC_FRAMES` = 0.5 and
an odd frame count (every probe has exactly 17 mature frames), `frac_rot < 0.5` ⟺
the threshold exceeds the **median**. So criterion 1 reduces to a single scalar
magnitude ratio:

> **median(candidate mature max|uh|) ≥ 0.25 × median(SC mature max|uh|)** ⇒ SUPERCELL

Tested rather than argued (`check_median_collapse.py`): **12 000 comparisons across
the six real runs on a dense k grid produced 0 disagreements** between the fraction
rule and the median rule, as did five adversarial synthetic series built to break
it. The clinching pair, at the pre-registered k:

- 8 frames at `max|uh|` = 2000 and 9 frames at 1 → **not a supercell** (`frac` 0.471)
- 9 frames at 2000 and 8 frames at 1 → **supercell** (`frac` 0.529)
- one frame at 10⁶ and 16 at 1 → **not a supercell**; 17 flat frames at 200 → **supercell**

The pre-registration's phrase *"rotating for less than half its mature life"* reads
as a persistence requirement and arithmetically is one only in the degenerate sense
that a median is the middle order statistic. A storm with one monstrous mesocyclone
frame is not a supercell by this rule; a storm with uniformly mild rotation is.
**This is the same root cause as §7.2 and §9.6, stated once instead of twice:**
criterion 1 is a median-magnitude test, and SC is scored against a fraction of its
own median — which is why SC's label is forced and why the "SC caps k at 0.75"
claim was arithmetically impossible.

This finding is *earned from data already collected* and is the most useful thing
§11 hands to (iii).

### 11.5 Stability, not margin, is the argument for (iii)

C2's median rotation is **1.16× criterion 1's threshold — 16 % above it** (197.30
vs 169.67). Stated as a ratio deliberately: the same fact reads as "0.04 in k",
which sounds like a rounding error and is a thumb on the scale toward moving k.
Nobody has to accept that 0.29 is "close to" 0.25 for the real argument to work:

**A boundary-condition-only change moved this candidate's flip point from 0.4000 to
0.2907 — 0.11 in k, which is 2.7× the distance from the pre-registered 0.25 to the
flip point.** Criterion 1's verdict on this candidate family is *less stable* than a
namelist edit that was supposed to be pure containment bookkeeping. A discriminator
whose answer swings that far on `sbc`/`nbc` is not measuring the thing the label
claims.

Full sweep, for the record (`*` = void):

```
  k=0.20   sc=SUPE  pc=SING  a=SUPE  b=SUPE  c=SUPE*  c2=SUPE
  k=0.25   sc=SUPE  pc=SING  a=SUPE  b=SUPE  c=SUPE*  c2=SUPE      <- pre-registered
  k=0.30   sc=SUPE  pc=SING  a=SUPE  b=SUPE  c=SUPE*  c2=MULT
  k=0.40   sc=SUPE  pc=SING  a=SUPE  b=SUPE  c=SUPE*  c2=MULT
  k=0.50   sc=SUPE  pc=SING  a=SUPE  b=SUPE  c=MULT*  c2=MULT
  k=0.60   sc=SUPE  pc=SING  a=SUPE  b=MULT  c=MULT*  c2=MULT
  k=1.00   sc=SUPE  pc=SING  a=SUPE  b=MULT  c=MULT*  c2=MULT
```

PC is SINGLE CELL at every k and A is SUPERCELL at every k — the controls and the
CM1-labelled "multicell" profile are unaffected by the whole question. **k is not
being moved.** §7.4 named picking a number just above what a control did as the
tuning trap; picking one just above what a *candidate* did is the same trap with a
different victim.

### 11.6 What (iii) must satisfy — constraints only, not its conclusion

C2 is consistent with a line carrying embedded rotation. **Whether that rotation
persists at a fixed storm-relative position is unmeasured** — this probe has
measured `|uh|` *magnitude*, updraft count, elongation and cold pool, and nothing
at all about rotation *position or persistence*. Asserting the answer here would
bank (iii)'s conclusion before its metric exists, which is precisely the discipline
§8 was written to enforce. Three constraints, fixed now:

1. **A different discriminator, not a different k** (§9.8's wording, unchanged).
2. **Scale-free, with no control normalisation.** Any statistic of the form
   *candidate magnitude ÷ control magnitude* reinstates §7.2's self-reference,
   which has now bitten twice. A position-persistence statistic — *does the
   strongest rotation centre stay within X km of itself for ≥ T minutes in the
   storm-relative frame* — needs no cross-run normalisation, so both controls can
   calibrate it without either becoming a tautology.
3. **Thresholds fixed a priori from geometry and duration, validated on SC and PC
   only, committed, and only then re-scored against A/B/C/C2.** That is the §8
   sequence, which worked.

Re-scoring costs minutes: all six runs are on disk and `uh` is already read
per-frame. This remains a design decision, not a compute one.

### 11.7 One consequence of the containment fix, named and not acted on

If C2 ever becomes the T6 multicell asset, **a periodic-y domain has no finite
condensate extent in y** — so the crop-box measurement and `require_measured_box`
would inherit §9.5's error one level up: a compact-storm criterion applied to a
periodic direction, this time in the export path rather than the classifier.
Flagged here so it is not rediscovered later; it has no bearing on the T5 verdict.

### 11.8 State

- **All four candidates (A, B, C, C2) classify SUPERCELL. T5 still has no
  multicell.**
- Option (ii) is **spent and it delivered**: the void is gone, the diagnosis held,
  and the blocker is isolated to criterion 1 with no confounds.
- The pre-committed next step is **(iii)**, and §11.4 gives it a concrete defect to
  fix rather than a threshold to argue about. **Not started — it needs an owner
  go**, and per §9.8 its post-hoc hazard is real: it is defensible only for a
  discriminator justified independently of which way it moves B, C and C2.
- **(i), the `0002-` shear patch, is now the weakest of the three.** Its premise is
  that the multicell regime is out of namelist reach; C2 shows a namelist-reachable
  candidate that passes organisation and sustained-system and is denied only by a
  rotation test whose defect is now measured. Buying a second CM1 fork to widen the
  shear range would be paying for the wrong thing — §10.4 pre-committed that
  reading before the run, and the run did not change it.
