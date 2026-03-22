from __future__ import annotations

from .easyworship_freeshow import convert_easyworship_request, convert_freeshow_to_easyworship_request
from .registry import ConversionRegistry
from .videosalm_freeshow import convert_freeshow_request, convert_videosalm_request


def build_registry() -> ConversionRegistry:
    registry = ConversionRegistry.from_resource()
    registry.register_converter("VideoPsalm", "FreeShow", convert_videosalm_request)
    registry.register_converter("FreeShow", "VideoPsalm", convert_freeshow_request)
    registry.register_converter("EasyWorship", "FreeShow", convert_easyworship_request)
    registry.register_converter("FreeShow", "EasyWorship", convert_freeshow_to_easyworship_request)
    return registry
