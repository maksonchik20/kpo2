import csv
from decimal import Decimal
import json

import pytest

from pos.adapters import utils
from pos.adapters.export import CsvTotalExporter
from pos.adapters.storage import JsonGradebookRepository, MemoryGradebookRepository
from pos.adapters.utils import format_score
from pos.domain import Criterion, CurrentStrategy, FinalStrategy, Gradebook, Student, TotalCalculator
from pos.ports import ExportError, StorageError


def sample_gradebook():
    gradebook = Gradebook()
    gradebook.add_student(Student("s1", 'Анна, "Аня"\nИванова'))
    gradebook.add_student(Student("s2", "Борис"))
    gradebook.add_criterion(Criterion("hw", "Домашняя работа", Decimal("20"), Decimal("1")))
    gradebook.add_criterion(Criterion("exam", "Экзамен", Decimal("10"), Decimal("3")))
    gradebook.evaluate("s1", "hw", "15.50", "Исправление, версия 2\nПроверено")
    return gradebook


def test_json_roundtrip_preserves_fields_and_restores_domain_behavior(tmp_path):
    path = tmp_path / "nested" / "book.json"
    repository = JsonGradebookRepository(path)
    assert repository.load().students == ()
    gradebook = sample_gradebook()
    repository.save(gradebook)
    restored = JsonGradebookRepository(path).load()
    assert restored.student("s1").name == gradebook.student("s1").name
    assert restored.criterion("hw").max_score == Decimal("20")
    assert restored.criterion("exam").weight == Decimal("3")
    assert restored.evaluations == gradebook.evaluations
    assert restored.evaluations[0].score.value == Decimal("15.50")
    assert restored.evaluations[0].comment == "Исправление, версия 2\nПроверено"
    restored.cancel_evaluation("s1", "hw")
    repository.save(restored)
    assert repository.load().evaluations == ()
    fieldToValue = json.loads(path.read_text())
    assert fieldToValue["criteria"][0]["max_score"] == "20"


@pytest.mark.parametrize("content", ["", "{broken", "[]", "{}", '{"version":2}', '{"version":true}'])
def test_invalid_json_is_rejected_without_changing_file(tmp_path, content):
    path = tmp_path / "book.json"
    path.write_text(content)
    with pytest.raises(StorageError):
        JsonGradebookRepository(path).load()
    assert path.read_text() == content


@pytest.mark.parametrize(
    "problem",
    ["duplicate_student", "duplicate_criterion", "duplicate_evaluation", "unknown_student",
     "unknown_criterion", "out_of_range", "bad_collection", "bad_fields"],
)
def test_inconsistent_json_cannot_bypass_domain_rules(tmp_path, problem):
    path = tmp_path / "book.json"
    repository = JsonGradebookRepository(path)
    repository.save(sample_gradebook())
    fieldToValue = json.loads(path.read_text())
    if problem == "duplicate_student":
        fieldToValue["students"].append(fieldToValue["students"][0])
    elif problem == "duplicate_criterion":
        fieldToValue["criteria"].append(fieldToValue["criteria"][0])
    elif problem == "duplicate_evaluation":
        fieldToValue["evaluations"].append(fieldToValue["evaluations"][0])
    elif problem == "unknown_student":
        fieldToValue["evaluations"][0]["student_id"] = "missing"
    elif problem == "unknown_criterion":
        fieldToValue["evaluations"][0]["criterion_id"] = "missing"
    elif problem == "out_of_range":
        fieldToValue["evaluations"][0]["score"] = "21"
    elif problem == "bad_collection":
        fieldToValue["criteria"] = "wrong"
    else:
        del fieldToValue["evaluations"][0]["comment"]
    content = json.dumps(fieldToValue)
    path.write_text(content)
    with pytest.raises(StorageError):
        repository.load()
    assert path.read_text() == content


def test_memory_repository_returns_independent_snapshots():
    repository = MemoryGradebookRepository()
    gradebook = sample_gradebook()
    repository.save(gradebook)
    gradebook.add_student(Student("s3", "Вера"))
    loaded = repository.load()
    assert len(loaded.students) == 2
    loaded.cancel_evaluation("s1", "hw")
    assert len(repository.load().evaluations) == 1
    assert MemoryGradebookRepository().load().students == ()


def test_failed_atomic_save_keeps_previous_file_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "book.json"
    repository = JsonGradebookRepository(path)
    repository.save(sample_gradebook())
    previous = path.read_bytes()

    def deny_replace(source, destination):
        raise PermissionError("Запись запрещена")

    monkeypatch.setattr(utils.os, "replace", deny_replace)
    with pytest.raises(StorageError, match="сохранить"):
        repository.save(Gradebook())
    assert path.read_bytes() == previous
    assert sorted(item.name for item in tmp_path.iterdir()) == ["book.json"]


def test_file_errors_are_reported_as_storage_errors(tmp_path):
    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(StorageError, match="прочитать"):
        JsonGradebookRepository(directory).load()
    parent = tmp_path / "regular_file"
    parent.write_text("occupied")
    with pytest.raises(StorageError, match="сохранить"):
        JsonGradebookRepository(parent / "book.json").save(Gradebook())
    assert parent.read_text() == "occupied"


@pytest.mark.parametrize("path", ["book.csv", "book", ""])
def test_json_repository_requires_json_extension(path):
    with pytest.raises(StorageError, match=".json"):
        JsonGradebookRepository(path)


@pytest.mark.parametrize("strategy,expected", [(FinalStrategy(), "1.94"), (CurrentStrategy(), "7.75")])
def test_csv_exports_selected_strategy_completeness_and_unicode(tmp_path, strategy, expected):
    gradebook = sample_gradebook()
    calculator = TotalCalculator(strategy)
    totals = tuple(calculator.calculate(gradebook, student.id) for student in gradebook.students)
    path = tmp_path / "exports" / "totals.csv"
    CsvTotalExporter().export(totals, str(path))
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0] == {
        "id": "s1", "name": gradebook.student("s1").name,
        "score": expected, "graded_count": "1", "criteria_count": "2", "mode": strategy.name,
    }
    assert rows[1]["score"] == ("0.00" if isinstance(strategy, FinalStrategy) else "")


def test_empty_export_still_has_header_and_rounding_is_half_up(tmp_path):
    path = tmp_path / "empty.csv"
    CsvTotalExporter().export((), str(path))
    with path.open(encoding="utf-8-sig", newline="") as stream:
        assert list(csv.reader(stream)) == [["id", "name", "score", "graded_count", "criteria_count", "mode"]]
    assert format_score(Decimal("7.125")) == "7.13"
    assert format_score(None) == "-"


def test_export_rejects_non_csv_and_preserves_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "book.json"
    path.write_text("keep")
    with pytest.raises(ExportError, match=".csv"):
        CsvTotalExporter().export((), str(path))
    assert path.read_text() == "keep"
    csv_path = tmp_path / "totals.csv"
    csv_path.write_text("previous export")

    def deny_replace(source, destination):
        raise PermissionError("Запись запрещена")

    monkeypatch.setattr(utils.os, "replace", deny_replace)
    with pytest.raises(ExportError, match="выгрузить"):
        CsvTotalExporter().export((), str(csv_path))
    assert csv_path.read_text() == "previous export"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["book.json", "totals.csv"]
