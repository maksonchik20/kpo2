from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from pos.application import PosFacade
from pos.domain import DomainError, FinalStrategy, Gradebook, Score, TotalCalculator
from pos.ports import ExportError, StorageError


@dataclass
class FakeRepository:
    state: Gradebook = field(default_factory=Gradebook)
    loads: int = 0
    saves: int = 0
    fail_save: bool = False

    def load(self):
        self.loads += 1
        return deepcopy(self.state)

    def save(self, gradebook):
        self.saves += 1
        if self.fail_save:
            raise StorageError("Не удалось сохранить")
        self.state = deepcopy(gradebook)


@dataclass
class RecordingExporter:
    exports: list = field(default_factory=list)
    fail_export: bool = False

    def export(self, totals, destination):
        if self.fail_export:
            raise ExportError("Не удалось выгрузить")
        self.exports.append((totals, destination))


@pytest.fixture
def repository():
    return FakeRepository()


@pytest.fixture
def exporter():
    return RecordingExporter()


@pytest.fixture
def facade(repository, exporter):
    return PosFacade(repository, TotalCalculator(FinalStrategy()), exporter)


def populate(facade):
    facade.add_student("S-1", "Анна")
    facade.add_criterion("HW", "Домашняя работа", "20", "2")
    facade.add_criterion("EX", "Экзамен", "100", "3")


def test_facade_loads_changes_and_saves_each_successful_operation(facade, repository):
    populate(facade)
    facade.evaluate("S-1", "HW", "10", "Проверено")
    assert (repository.loads, repository.saves) == (4, 4)
    assert facade.students()[0].name == "Анна"
    assert [criterion.id for criterion in facade.criteria()] == ["HW", "EX"]
    assert facade.evaluations()[0].score == Score("10")
    assert facade.evaluations()[0].comment == "Проверено"
    assert facade.totals()[0].score == Decimal("2")
    assert repository.saves == 4


@pytest.mark.parametrize(
    "operation",
    ["invalid_student", "duplicate", "invalid_criterion", "unknown_student",
     "unknown_criterion", "score", "missing_grade"],
)
def test_rejected_command_does_not_save_or_change_persisted_state(facade, repository, operation):
    populate(facade)
    before_saves = repository.saves
    with pytest.raises(DomainError):
        if operation == "invalid_student":
            facade.add_student("S-2", "")
        elif operation == "duplicate":
            facade.add_student("S-1", "Другое имя")
        elif operation == "invalid_criterion":
            facade.add_criterion("BAD", "Некорректный", "0", "1")
        elif operation == "unknown_student":
            facade.evaluate("missing", "HW", "10")
        elif operation == "unknown_criterion":
            facade.evaluate("S-1", "missing", "10")
        elif operation == "score":
            facade.evaluate("S-1", "HW", "21")
        else:
            facade.cancel_evaluation("S-1", "HW")
    assert repository.saves == before_saves
    assert len(repository.state.students) == 1
    assert repository.state.students[0].name == "Анна"
    assert len(repository.state.criteria) == 2
    assert repository.state.evaluations == ()


def test_failed_save_leaves_previous_persisted_evaluation(facade, repository):
    populate(facade)
    facade.evaluate("S-1", "HW", "10")
    repository.fail_save = True
    with pytest.raises(StorageError):
        facade.evaluate("S-1", "HW", "20")
    assert repository.state.evaluations[0].score == Score("10")
    assert facade.totals()[0].score == Decimal("2")


def test_correction_and_cancellation_are_saved_and_change_next_total(facade, repository):
    populate(facade)
    facade.evaluate("S-1", "HW", "10")
    facade.evaluate("S-1", "HW", "20", "Исправлено")
    assert facade.totals()[0].score == Decimal("4")
    assert len(repository.state.evaluations) == 1
    facade.cancel_evaluation("S-1", "HW")
    assert facade.evaluations() == ()
    assert facade.totals()[0].score == Decimal("0")
    assert repository.saves == 6


def test_export_uses_one_fresh_snapshot_and_does_not_save(facade, repository, exporter):
    populate(facade)
    facade.evaluate("S-1", "HW", "10")
    facade.evaluate("S-1", "EX", "80")
    before_loads, before_saves = repository.loads, repository.saves
    facade.export("result.csv")
    assert repository.loads == before_loads + 1
    assert repository.saves == before_saves
    totals, destination = exporter.exports[0]
    assert destination == "result.csv"
    assert totals[0].score == Decimal("6.8")
    assert (totals[0].graded_count, totals[0].criteria_count) == (2, 2)
    facade.evaluate("S-1", "EX", "100")
    facade.export("updated.csv")
    assert exporter.exports[1][0][0].score == Decimal("8")
    assert exporter.exports[0][0][0].score == Decimal("6.8")


def test_export_failure_propagates_without_mutating_the_gradebook(facade, repository, exporter):
    populate(facade)
    facade.evaluate("S-1", "HW", "10")
    before_saves = repository.saves
    exporter.fail_export = True
    with pytest.raises(ExportError):
        facade.export("result.csv")
    assert repository.saves == before_saves
    assert repository.state.evaluations[0].score == Score("10")


def test_empty_gradebook_can_be_viewed_and_exported(facade, repository, exporter):
    assert facade.students() == ()
    assert facade.criteria() == ()
    assert facade.evaluations() == ()
    assert facade.totals() == ()
    facade.export("empty.csv")
    assert exporter.exports == [((), "empty.csv")]
    assert repository.saves == 0
