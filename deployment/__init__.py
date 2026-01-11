"""
Milton deployment package.

Provides edge bundle packaging and deployment management.
"""

from .edge_packager import EdgePackager, BundleManifest
from .deployment_manager import DeploymentManager, DeploymentRecord

__all__ = [
    "EdgePackager",
    "BundleManifest",
    "DeploymentManager",
    "DeploymentRecord",
]
