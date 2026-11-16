"""Консоль обращается только к фасаду, не читает и не изменяет JSON напрямую."""

from __future__ import annotations

from decimal import Decimal, DecimalException

from ..application import PosFacade
from ..domain import DomainError
from ..ports import ExportError, StorageError
from .utils import format_score


def display_score(value: Decimal | None) -> str:
    return "нет данных" if value is None else format_score(value)


class ConsoleApplication:
    def __init__(self, facade: PosFacade, export_path: str, mode: str) -> None:
        self._facade = facade
        self._export_path = export_path
        self._mode = mode

    def run(self) -> None:
        print(f"ПОС — ведомость оценок. Режим: {self._mode}.")
        numberToAction = {
            "1": self._add_student, "2": self._add_criterion,
            "3": self._evaluate, "4": self._cancel,
            "5": self._show_lists, "6": self._show_evaluations,
            "7": self._show_totals, "8": self._export,
        }
        while True:
            try:
                command = input(
                    "\n1. Добавить студента\n2. Добавить критерий\n"
                    "3. Выставить / исправить оценку\n4. Отменить оценку\n"
                    "5. Студенты и критерии\n6. Выставленные оценки\n"
                    "7. Итоги\n8. Экспорт итогов в CSV\n0. Выход\nВыбор: "
                ).strip()
                if command == "0":
                    print("До свидания!")
                    return
                action = numberToAction.get(command)
                if action is None:
                    print("Неизвестная команда.")
                else:
                    action()
            except (DomainError, StorageError, ExportError) as error:
                print(f"Ошибка: {error}")
            except DecimalException:
                print("Ошибка: числа слишком велики для расчёта.")

    def _add_student(self) -> None:
        student_id = input("ID студента: ").strip()
        name = input("Имя: ").strip()
        self._facade.add_student(student_id, name)
        print("Студент добавлен.")

    def _add_criterion(self) -> None:
        criterion_id = input("ID критерия: ").strip()
        name = input("Название: ").strip()
        maximum = input("Максимальный балл: ").strip()
        weight = input("Вес (> 0, например 0,4 или 2): ").strip()
        self._facade.add_criterion(criterion_id, name, maximum, weight)
        print("Критерий добавлен.")

    def _evaluate(self) -> None:
        student_id = input("ID студента: ").strip()
        criterion_id = input("ID критерия: ").strip()
        score = input("Балл (существующая оценка будет заменена): ").strip()
        comment = input("Комментарий (можно пустой): ").strip()
        self._facade.evaluate(student_id, criterion_id, score, comment)
        print("Оценка сохранена.")

    def _cancel(self) -> None:
        student_id = input("ID студента: ").strip()
        criterion_id = input("ID критерия: ").strip()
        self._facade.cancel_evaluation(student_id, criterion_id)
        print("Оценка отменена.")

    def _show_lists(self) -> None:
        students = self._facade.students()
        criteria = self._facade.criteria()
        print("Студенты:")
        for student in students:
            print(f"  {student.id}: {student.name}")
        if not students:
            print("  Список пуст.")
        print("Критерии:")
        for criterion in criteria:
            print(f"  {criterion.id}: {criterion.name}; максимум {criterion.max_score}; вес {criterion.weight}")
        if not criteria:
            print("  Рубрикатор пуст.")

    def _show_evaluations(self) -> None:
        evaluations = self._facade.evaluations()
        if not evaluations:
            print("Оценок пока нет.")
        for evaluation in evaluations:
            print(
                f"{evaluation.student.name} [{evaluation.student.id}] — "
                f"{evaluation.criterion.name} [{evaluation.criterion.id}]: "
                f"{evaluation.score.value}/{evaluation.criterion.max_score}; {evaluation.comment}"
            )

    def _show_totals(self) -> None:
        totals = self._facade.totals()
        print(f"Режим: {self._mode}. Шкала итога: 0–10.")
        if not totals:
            print("Студентов пока нет.")
        for total in totals:
            print(
                f"{total.student.name} [{total.student.id}]: {display_score(total.score)}; "
                f"оценено {total.graded_count}/{total.criteria_count}"
            )
        scores = [total.score for total in totals if total.score is not None]
        if scores:
            print(f"Средний балл: {display_score(sum(scores) / len(scores))}.")

    def _export(self) -> None:
        self._facade.export(self._export_path)
        print(f"Итоги сохранены: {self._export_path}")

    def run_demo(self) -> None:
        print("ПОС — демонстрация на отдельной ведомости.")
        self._facade.add_student("s1", "Анна Иванова")
        self._facade.add_student("s2", "Борис Петров")
        self._facade.add_criterion("hw", "Домашние работы", "20", "2")
        self._facade.add_criterion("exam", "Экзамен", "10", "3")
        self._show_lists()
        self._facade.evaluate("s1", "hw", "16", "Работа принята")
        self._facade.evaluate("s1", "exam", "9")
        self._facade.evaluate("s2", "hw", "10")
        print("\nИсправление оценки Анны: 16 → 18.")
        self._facade.evaluate("s1", "hw", "18", "Исправленная работа")
        self._facade.evaluate("s2", "exam", "4")
        print("Отмена оценки Бориса за экзамен.")
        self._facade.cancel_evaluation("s2", "exam")
        for criterion_id, score in (("exam", "12"), ("unknown", "5")):
            try:
                self._facade.evaluate("s1", criterion_id, score)
            except DomainError as error:
                print(f"Ожидаемый отказ: {error}")
        self._show_evaluations()
        self._show_totals()
        self._export()
