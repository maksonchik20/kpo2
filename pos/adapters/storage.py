"""Репозитории ведомости: память для тестов и JSON для обычного запуска."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ..domain import Criterion, DomainError, Gradebook, Student
from ..ports import StorageError
from .utils import atomic_text


class MemoryGradebookRepository:
    def __init__(self) -> None:
        self._gradebook = Gradebook()

    def load(self) -> Gradebook:
        return deepcopy(self._gradebook)

    def save(self, gradebook: Gradebook) -> None:
        self._gradebook = deepcopy(gradebook)


class JsonGradebookRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.suffix.lower() != ".json":
            raise StorageError("Для ведомости нужен файл с расширением .json.")

    def load(self) -> Gradebook:
        try:
            with self.path.open(encoding="utf-8") as stream:
                fieldToValue = json.load(stream)
        except FileNotFoundError:
            return Gradebook()
        except (OSError, ValueError) as error:
            raise StorageError(f"Не удалось прочитать ведомость: {error}") from error
        try:
            if (
                not isinstance(fieldToValue, dict)
                or set(fieldToValue) != {"version", "students", "criteria", "evaluations"}
                or type(fieldToValue["version"]) is not int
                or fieldToValue["version"] != 1
                or any(not isinstance(fieldToValue[key], list) for key in ("students", "criteria", "evaluations"))
            ):
                raise ValueError("Ожидалась ведомость формата version=1.")
            gradebook = Gradebook()
            for studentFieldToValue in fieldToValue["students"]:
                gradebook.add_student(Student(**studentFieldToValue))
            for criterionFieldToValue in fieldToValue["criteria"]:
                gradebook.add_criterion(Criterion(**criterionFieldToValue))
            seen_evaluations = set()
            for evaluationFieldToValue in fieldToValue["evaluations"]:
                key = (evaluationFieldToValue["student_id"], evaluationFieldToValue["criterion_id"])
                if key in seen_evaluations:
                    raise ValueError("Одна оценка встречается в файле несколько раз.")
                seen_evaluations.add(key)
                if set(evaluationFieldToValue) != {"student_id", "criterion_id", "score", "comment"}:
                    raise ValueError("Неверные поля оценки.")
                gradebook.evaluate(*key, evaluationFieldToValue["score"], evaluationFieldToValue["comment"])
            return gradebook
        except (DomainError, KeyError, TypeError, ValueError) as error:
            raise StorageError(f"Некорректная ведомость: {error}") from error

    def save(self, gradebook: Gradebook) -> None:
        fieldToValue = {
            "version": 1,
            "students": [{"id": student.id, "name": student.name} for student in gradebook.students],
            "criteria": [
                {"id": criterion.id, "name": criterion.name,
                 "max_score": str(criterion.max_score), "weight": str(criterion.weight)}
                for criterion in gradebook.criteria
            ],
            "evaluations": [
                {"student_id": evaluation.student.id, "criterion_id": evaluation.criterion.id,
                 "score": str(evaluation.score.value), "comment": evaluation.comment}
                for evaluation in gradebook.evaluations
            ],
        }
        try:
            with atomic_text(self.path) as stream:
                json.dump(fieldToValue, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except (OSError, ValueError) as error:
            raise StorageError(f"Не удалось сохранить ведомость: {error}") from error
