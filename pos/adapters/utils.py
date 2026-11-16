"""Общие операции адаптеров: запись текстового файла и форматирование балла."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator, TextIO


@contextmanager
def atomic_text(path: Path, encoding: str = "utf-8") -> Iterator[TextIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding=encoding, newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def format_score(score: Decimal | None) -> str:
    return "-" if score is None else str(score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
