"""Manual-selection template: no device auto-registration or feedback output."""


def create_instance(c_instance):
    from .surface import KroseGenericTemplate
    return KroseGenericTemplate(c_instance)


def get_capabilities():
    return {}
