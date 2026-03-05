"""Custom exceptions for jmespath-mapper."""

from __future__ import annotations


class SpaghettimapMapperError(Exception):
    """Base exception for all jmespath-mapper errors."""


class ConfigurationError(SpaghettimapMapperError):
    """Raised when a MappingConfig is invalid."""


class MappingError(SpaghettimapMapperError):
    """Raised when a mapping operation fails at runtime."""


class FieldMappingError(MappingError):
    """Raised when mapping a specific field fails."""

    def __init__(
        self, field: str, reason: str, source_exception: BaseException | None = None
    ) -> None:
        self.field = field
        self.reason = reason
        message = f"Failed to map field '{field}': {reason}"
        super().__init__(message)
        if source_exception is not None:
            self.__cause__ = source_exception
