"""Spec-level validators for generated code."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from src.engine.spec_parser import ParsedService
from src.validators.base_validator import ValidationFailure


class SpecValidator(ABC):
    """Abstract base for all spec-level validators."""
    name: str

    @abstractmethod
    def validate(self, service: ParsedService, code_dir: Path) -> list[ValidationFailure]:
        ...
