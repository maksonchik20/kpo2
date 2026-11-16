"""Выгрузка вычисленных итогов в CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from ..domain import Total
from ..ports import ExportError
from .utils import atomic_text, format_score


class CsvTotalExporter:
    def export(self, totals: tuple[Total, ...], destination: str) -> None:
        path = Path(destination)
        if path.suffix.lower() != ".csv":
            raise ExportError("Для экспорта нужен файл с расширением .csv.")
        try:
            with atomic_text(path, encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(("id", "name", "score", "graded_count", "criteria_count", "mode"))
                for total in totals:
                    writer.writerow((
                        total.student.id, total.student.name,
                        "" if total.score is None else format_score(total.score),
                        total.graded_count, total.criteria_count, total.mode,
                    ))
        except (OSError, ValueError, csv.Error) as error:
            raise ExportError(f"Не удалось выгрузить итоги: {error}") from error
