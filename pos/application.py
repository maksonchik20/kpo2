"""Фасад сценариев: загрузить ведомость, выполнить операцию, сохранить результат."""

from .domain import Criterion, Evaluation, Student, Total, TotalCalculator
from .ports import GradebookRepository, TotalExporter


class PosFacade:
    def __init__(
        self, repository: GradebookRepository, calculator: TotalCalculator,
        exporter: TotalExporter,
    ) -> None:
        self._repository = repository
        self._calculator = calculator
        self._exporter = exporter

    def add_student(self, student_id: str, name: str) -> None:
        gradebook = self._repository.load()
        gradebook.add_student(Student(student_id, name))
        self._repository.save(gradebook)

    def add_criterion(self, criterion_id: str, name: str, max_score: object, weight: object) -> None:
        gradebook = self._repository.load()
        gradebook.add_criterion(Criterion(criterion_id, name, max_score, weight))
        self._repository.save(gradebook)

    def evaluate(self, student_id: str, criterion_id: str, value: object, comment: str = "") -> None:
        gradebook = self._repository.load()
        gradebook.evaluate(student_id, criterion_id, value, comment)
        self._repository.save(gradebook)

    def cancel_evaluation(self, student_id: str, criterion_id: str) -> None:
        gradebook = self._repository.load()
        gradebook.cancel_evaluation(student_id, criterion_id)
        self._repository.save(gradebook)

    def students(self) -> tuple[Student, ...]:
        return self._repository.load().students

    def criteria(self) -> tuple[Criterion, ...]:
        return self._repository.load().criteria

    def evaluations(self) -> tuple[Evaluation, ...]:
        return self._repository.load().evaluations

    def totals(self) -> tuple[Total, ...]:
        gradebook = self._repository.load()
        return tuple(self._calculator.calculate(gradebook, student.id) for student in gradebook.students)

    def export(self, destination: str) -> None:
        self._exporter.export(self.totals(), destination)
