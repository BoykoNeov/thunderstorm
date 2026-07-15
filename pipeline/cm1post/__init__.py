"""cm1post -- CM1 netCDF -> scenario-package post-processor.

Phase 1 scope: the volume half of the package (VDB sequence + manifest). Surface
-layer textures, skew-T/hodograph plots and lightning event lists are later phases;
they attach to the same manifest.

Charter rule this package exists to honour: UE is a dumb player. Everything derived
happens here, and the channel->texture mapping is published in the manifest so UE
reads it rather than hardcoding it.
"""
