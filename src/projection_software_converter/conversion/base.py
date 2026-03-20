from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ConversionPair:
    source: str
    target: str
    handler_name: str


@dataclass(frozen=True)
class ConversionRequest:
    input_path: Path
    output_path: Path
    source: str
    target: str
    debug_manifest_path: Path | None = None


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    item_count: int
    details: dict


ConverterHandler = Callable[[ConversionRequest], ConversionResult]
