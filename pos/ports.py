"""Контракты внешнего хранения и экспорта; реализации находятся в adapters."""

from typing import Protocol

from .domain import Gradebook, Total


class StorageError(RuntimeError):
    pass


class ExportError(RuntimeError):
    pass


class GradebookRepository(Protocol):
    def load(self) -> Gradebook: ...

    def save(self, gradebook: Gradebook) -> None: ...


class TotalExporter(Protocol):
    def export(self, totals: tuple[Total, ...], destination: str) -> None: ...
