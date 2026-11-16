"""Модель одной ведомости и правила расчёта. Без файлов, консоли и DI."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol


class DomainError(ValueError):
    """Нарушено правило предметной области."""


def required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} не может быть пустым.")
    return value.strip()


def decimal_number(value: object) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        raise DomainError("Введите число.") from None
    if not number.is_finite():
        raise DomainError("Число должно быть конечным.")
    return number


@dataclass(frozen=True)
class Student:
    id: str
    name: str = field(compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", required_text(self.id, "ID студента"))
        object.__setattr__(self, "name", required_text(self.name, "Имя студента"))


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str = field(compare=False)
    max_score: Decimal = field(compare=False)
    weight: Decimal = field(compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", required_text(self.id, "ID критерия"))
        object.__setattr__(self, "name", required_text(self.name, "Название критерия"))
        for attribute in ("max_score", "weight"):
            value = decimal_number(getattr(self, attribute))
            if value <= 0:
                raise DomainError("Максимальный балл и вес должны быть больше нуля.")
            object.__setattr__(self, attribute, value)


@dataclass(frozen=True)
class Score:
    value: Decimal

    def __post_init__(self) -> None:
        value = decimal_number(self.value)
        if value < 0:
            raise DomainError("Балл не может быть отрицательным.")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class Evaluation:
    student: Student
    criterion: Criterion
    score: Score
    comment: str = ""

    def __post_init__(self) -> None:
        if self.score.value > self.criterion.max_score:
            raise DomainError(f"Балл должен быть от 0 до {self.criterion.max_score}.")
        if not isinstance(self.comment, str):
            raise DomainError("Комментарий должен быть текстом.")


class EvaluationFactory:
    @staticmethod
    def create(
        gradebook: Gradebook, student_id: str, criterion_id: str,
        value: object, comment: str = "",
    ) -> Evaluation:
        return Evaluation(
            gradebook.student(student_id), gradebook.criterion(criterion_id),
            Score(value), comment,
        )


class Gradebook:
    """Корень агрегата: все изменения ведомости проходят через его методы."""

    def __init__(self) -> None:
        self._studentIdToStudent: dict[str, Student] = {}
        self._criterionIdToCriterion: dict[str, Criterion] = {}
        self._studentAndCriterionToEvaluation: dict[tuple[str, str], Evaluation] = {}

    @property
    def students(self) -> tuple[Student, ...]:
        return tuple(self._studentIdToStudent.values())

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        return tuple(self._criterionIdToCriterion.values())

    @property
    def evaluations(self) -> tuple[Evaluation, ...]:
        return tuple(self._studentAndCriterionToEvaluation.values())

    def student(self, student_id: str) -> Student:
        try:
            return self._studentIdToStudent[student_id]
        except KeyError:
            raise DomainError(f"Студент «{student_id}» не найден.") from None

    def criterion(self, criterion_id: str) -> Criterion:
        try:
            return self._criterionIdToCriterion[criterion_id]
        except KeyError:
            raise DomainError(f"Критерий «{criterion_id}» не найден.") from None

    def add_student(self, student: Student) -> None:
        if student.id in self._studentIdToStudent:
            raise DomainError(f"ID студента «{student.id}» уже занят.")
        self._studentIdToStudent[student.id] = student

    def add_criterion(self, criterion: Criterion) -> None:
        if criterion.id in self._criterionIdToCriterion:
            raise DomainError(f"ID критерия «{criterion.id}» уже занят.")
        self._criterionIdToCriterion[criterion.id] = criterion

    def evaluate(self, student_id: str, criterion_id: str, value: object, comment: str = "") -> None:
        evaluation = EvaluationFactory.create(self, student_id, criterion_id, value, comment)
        key = (evaluation.student.id, evaluation.criterion.id)
        self._studentAndCriterionToEvaluation[key] = evaluation

    def cancel_evaluation(self, student_id: str, criterion_id: str) -> None:
        self.student(student_id)
        self.criterion(criterion_id)
        if self._studentAndCriterionToEvaluation.pop((student_id, criterion_id), None) is None:
            raise DomainError("Оценка ещё не выставлена.")


def weighted_score(criteria: tuple[Criterion, ...], evaluations: tuple[Evaluation, ...]) -> Decimal | None:
    if not criteria:
        return None
    criterionIdToScore = {evaluation.criterion.id: evaluation.score.value for evaluation in evaluations}
    weight_sum = sum(criterion.weight for criterion in criteria)
    return sum(
        criterionIdToScore.get(criterion.id, Decimal(0)) / criterion.max_score
        * criterion.weight
        for criterion in criteria
    ) / weight_sum * 10


class TotalStrategy(Protocol):
    name: str

    def calculate(self, criteria: tuple[Criterion, ...], evaluations: tuple[Evaluation, ...]) -> Decimal | None: ...


class FinalStrategy:
    name = "Итоговый (пропуски = 0)"

    def calculate(self, criteria: tuple[Criterion, ...], evaluations: tuple[Evaluation, ...]) -> Decimal | None:
        return weighted_score(criteria, evaluations)


class CurrentStrategy:
    name = "Текущий (предварительный)"

    def calculate(self, criteria: tuple[Criterion, ...], evaluations: tuple[Evaluation, ...]) -> Decimal | None:
        evaluated_ids = {evaluation.criterion.id for evaluation in evaluations}
        return weighted_score(tuple(item for item in criteria if item.id in evaluated_ids), evaluations)


@dataclass(frozen=True)
class Total:
    student: Student
    score: Decimal | None
    graded_count: int
    criteria_count: int
    mode: str


class TotalCalculator:
    """Domain Service: результат зависит и от рубрикатора, и от оценок."""

    def __init__(self, strategy: TotalStrategy) -> None:
        self._strategy = strategy

    def calculate(self, gradebook: Gradebook, student_id: str) -> Total:
        student = gradebook.student(student_id)
        evaluations = tuple(item for item in gradebook.evaluations if item.student.id == student_id)
        return Total(
            student, self._strategy.calculate(gradebook.criteria, evaluations),
            len(evaluations), len(gradebook.criteria), self._strategy.name,
        )
