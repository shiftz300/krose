"""Krose integration for KeyLab Essential mk3, Live 11.3.3+."""


def create_instance(c_instance):
    from .surface import KroseKeyLabEssential
    return KroseKeyLabEssential(c_instance=c_instance)


def get_capabilities():
    from KeyLab_Essential_mk3 import get_capabilities as arturia_capabilities
    from ableton.v3.control_surface.capabilities import AUTO_LOAD_KEY
    capabilities = arturia_capabilities()
    # Keep the official port/model descriptors. The user selects this surface
    # once; do not create a second owner alongside an existing Arturia surface.
    capabilities[AUTO_LOAD_KEY] = False
    return capabilities
