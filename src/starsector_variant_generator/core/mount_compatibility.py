from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

# Weapon-mount-type compatibility matrix. Previously both validation/legality.py
# and generation/candidate.py only did an exact string match (mount type ==
# weapon.mount_type), which is wrong for HYBRID/COMPOSITE/SYNERGY/UNIVERSAL
# mounts -- those accept documented *combinations* of basic types, not just
# their own name.
#
# Verified 2026-08-22 from three independent sources that all agree exactly:
#   1. https://starsector.wiki.gg/wiki/Weapon ("Hybrid weapons can fit in
#      Ballistic, Energy, Hybrid or Universal mounts. Composite weapons can
#      fit in Ballistic, Missile, Composite or Universal mounts. Synergy
#      weapons can fit in Energy, Missile, Synergy or Universal mounts.")
#   2. https://starsector.wiki.gg/wiki/Modding:Weapon_Slots (corroborates the
#      same combinations from the mount-slot-definition side)
#   3. Empirically, from every real BALLISTIC/ENERGY/MISSILE weapon assigned
#      to a HYBRID/COMPOSITE/SYNERGY/UNIVERSAL mount across all 431 core
#      (developer-authored) variants in a live installation -- e.g. 59
#      BALLISTIC-mount_type weapons and 56 ENERGY-mount_type weapons
#      installed in HYBRID-type mounts, 0 exceptions to this matrix.
#
# This is treated as a structural game-engine rule (like size compatibility,
# core/registry.py's _SIZE_ORDER), not per-mod data -- it applies uniformly
# regardless of which mod adds the hull or weapon.
MOUNT_TYPE_COMPATIBILITY: Mapping[str, frozenset[str]] = MappingProxyType({
    "BALLISTIC": frozenset({"BALLISTIC"}),
    "ENERGY": frozenset({"ENERGY"}),
    "MISSILE": frozenset({"MISSILE"}),
    "HYBRID": frozenset({"BALLISTIC", "ENERGY", "HYBRID"}),
    "COMPOSITE": frozenset({"BALLISTIC", "MISSILE", "COMPOSITE"}),
    "SYNERGY": frozenset({"ENERGY", "MISSILE", "SYNERGY"}),
    "UNIVERSAL": frozenset({"BALLISTIC", "ENERGY", "MISSILE", "HYBRID", "COMPOSITE", "SYNERGY", "UNIVERSAL"}),
})
