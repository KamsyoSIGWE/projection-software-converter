from __future__ import annotations

from pathlib import Path

from .base import ConversionRequest, ConversionResult
from .registry import ConversionRegistry, RegistryValidationError


class ConverterService:
    def __init__(self, registry: ConversionRegistry) -> None:
        self._registry = registry

    def convert(self, request: ConversionRequest) -> ConversionResult:
        self._validate_request(request)
        handler = self._registry.require_handler(request.source, request.target)
        return handler(request)

    def _validate_request(self, request: ConversionRequest) -> None:
        if not request.input_path.exists():
            raise FileNotFoundError(f"Selected file does not exist: {request.input_path}")
        if not request.input_path.is_file():
            raise ValueError(f"Selected path is not a file: {request.input_path}")
        if not request.source:
            raise RegistryValidationError("Please choose a source format.")
        if not request.target:
            raise RegistryValidationError("Please choose a target format.")
        if request.source == request.target:
            raise RegistryValidationError("Choose two different formats for conversion.")
        if not self._registry.validate_conversion(request.source, request.target):
            raise RegistryValidationError(f"{request.source} cannot be converted to {request.target}.")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)


def default_output_path(input_path: Path, target: str) -> Path:
    return default_output_path_in_dir(input_path, target, input_path.parent)


def default_output_path_in_dir(input_path: Path, target: str, output_dir: Path) -> Path:
    suffix_map = {
        "FreeShow": ".project",
        "VideoPsalm": ".vpagd",
        "EasyWorship": ".ewsx",
    }
    return output_dir / input_path.with_suffix(suffix_map.get(target, input_path.suffix)).name
