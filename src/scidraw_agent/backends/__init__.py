"""Asset backends behind the AssetBackend protocol."""

from .bioicons import BioiconsBackend
from .zenodo import ZenodoBackend

__all__ = ["BioiconsBackend", "ZenodoBackend"]
