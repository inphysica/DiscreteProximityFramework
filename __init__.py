"""DiscreteProximityFramework plugin package init
"""
def classFactory(iface):
    """Load DiscreteProximityFramework plugin."""
    from .discrete_proximity_framework import DiscreteProximityFramework
    return DiscreteProximityFramework(iface)
