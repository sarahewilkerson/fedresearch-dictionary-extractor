from .army import ArmyProfile
from .base import ReferenceProfile

PROFILES: dict[str, type[ReferenceProfile]] = {
    "army": ArmyProfile,
}


def get_profile(name: str) -> ReferenceProfile:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name!r}. Available: {sorted(PROFILES)}")
    return PROFILES[name]()
