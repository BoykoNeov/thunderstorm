# scenarios/

Finished scenario packages. A package is a **versioned contract**:

- VDB volume sequence (cloud/ice/rain/graupel-hail/dBZ channels, matched transforms,
  fixed padded bounding box across all frames)
- surface-layer textures (qr/qg near-surface stack driving Niagara particles)
- skew-T / hodograph plot images (rendered in the pipeline with MetPy/matplotlib)
- lightning event list (positions / times / polarity)
- `manifest.json` carrying `format_version` (UE refuses newer major versions)

Packages are multi-GB and **do not** live in plain git — they go to LFS or out-of-repo
storage (decided before the first package ships). Only `manifest.json` and small docs
are tracked here.

_Empty until scenarios are produced. Do not start a phase without explicit go from the
owner._
