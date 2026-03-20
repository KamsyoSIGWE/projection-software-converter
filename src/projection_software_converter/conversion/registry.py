from __future__ import annotations

import json
from importlib import resources
from typing import Iterable

from .base import ConversionPair, ConverterHandler


class RegistryValidationError(ValueError):
    pass


class ConversionRegistry:
    def __init__(self, formats: Iterable[str], conversions: Iterable[ConversionPair]) -> None:
        self._formats = sorted(dict.fromkeys(str(item).strip() for item in formats if str(item).strip()))
        self._conversions = list(conversions)
        self._handlers: dict[tuple[str, str], ConverterHandler] = {}
        self._config_pairs = {(pair.source, pair.target): pair for pair in self._conversions}

    @classmethod
    def from_resource(cls) -> "ConversionRegistry":
        raw_text = resources.files("projection_software_converter.resources").joinpath("conversions.json").read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        formats = payload.get("formats", [])
        conversions = [
            ConversionPair(source=item["from"], target=item["to"], handler_name=item["handler"])
            for item in payload.get("conversions", [])
        ]
        return cls(formats=formats, conversions=conversions)

    def register_converter(self, source: str, target: str, handler_function: ConverterHandler) -> None:
        key = (source, target)
        if key not in self._config_pairs:
            raise RegistryValidationError(f"Cannot register unsupported conversion: {source} -> {target}")
        self._handlers[key] = handler_function

    def query_available_sources(self) -> list[str]:
        return sorted({source for source, _target in self._config_pairs})

    def query_available_targets(self, source: str) -> list[str]:
        return sorted(target for src, target in self._config_pairs if src == source)

    def query_supported_formats(self) -> list[str]:
        return list(self._formats)

    def query_conversion_pairs(self) -> list[ConversionPair]:
        return list(self._conversions)

    def validate_conversion(self, source: str, target: str) -> bool:
        return (source, target) in self._config_pairs and (source, target) in self._handlers

    def require_handler(self, source: str, target: str) -> ConverterHandler:
        key = (source, target)
        if key not in self._config_pairs:
            raise RegistryValidationError(f"Unsupported conversion: {source} -> {target}")
        if key not in self._handlers:
            raise RegistryValidationError(f"Converter registered in config but no handler loaded: {source} -> {target}")
        return self._handlers[key]
