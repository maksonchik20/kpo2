import csv
from decimal import Decimal
from io import StringIO
import sys

import pytest

from pos.adapters.cli import ConsoleApplication
from pos.adapters.export import CsvTotalExporter
from pos.adapters.storage import JsonGradebookRepository, MemoryGradebookRepository
from pos.application import PosFacade
from pos.domain import Criterion, CurrentStrategy, FinalStrategy, Gradebook, Student, TotalCalculator
from pos.main import main


@pytest.fixture
def run_session(monkeypatch, capsys, tmp_path):
    def run(*lines):
        repository = MemoryGradebookRepository()
        facade = PosFacade(repository, TotalCalculator(FinalStrategy()), CsvTotalExporter())
        destination = tmp_path / "totals.csv"
        monkeypatch.setattr(sys, "stdin", StringIO("\n".join(lines) + "\n"))
        ConsoleApplication(facade, str(destination), FinalStrategy.name).run()
        return facade, capsys.readouterr().out, destination

    return run


def test_full_session_supports_correction_cancellation_lists_totals_and_export(run_session):
    facade, output, destination = run_session(
        "1", "s1", "Анна", "1", "s2", "Борис",
        "2", "hw", "Домашние работы", "20", "2",
        "2", "exam", "Экзамен", "10", "3",
        "3", "s1", "hw", "16", "Принято",
        "3", "s1", "hw", "20", "Исправлено",
        "3", "s1", "exam", "9", "",
        "3", "s2", "hw", "10", "",
        "3", "s2", "exam", "4", "",
        "4", "s2", "exam", "5", "6", "7", "8", "0",
    )
    assert len(facade.students()) == 2
    assert len(facade.criteria()) == 2
    assert len(facade.evaluations()) == 3
    assert [total.score for total in facade.totals()] == [Decimal("9.4"), Decimal("2")]
    assert "Анна [s1]: 9.40; оценено 2/2" in output
    assert "Борис [s2]: 2.00; оценено 1/2" in output
    assert "Средний балл: 5.70" in output
    assert "20/20; Исправлено" in output
    assert "Оценка отменена." in output
    assert "Итоги сохранены:" in output
    assert "До свидания!" in output
    with destination.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [fieldToValue["score"] for fieldToValue in rows] == ["9.40", "2.00"]
    assert [fieldToValue["id"] for fieldToValue in rows] == ["s1", "s2"]
    assert all(fieldToValue["mode"] == FinalStrategy.name for fieldToValue in rows)


def test_empty_lists_and_unknown_command_have_clear_messages(run_session):
    _, output, _ = run_session("unknown", "5", "6", "7", "0")
    assert "Неизвестная команда." in output
    assert "Список пуст." in output
    assert "Рубрикатор пуст." in output
    assert "Оценок пока нет." in output
    assert "Студентов пока нет." in output


@pytest.mark.parametrize(
    "fields",
    [
        ("1", "s2", ""),
        ("1", "s1", "Другое имя"),
        ("2", "hw", "Дубликат", "10", "1"),
        ("2", "bad", "Неверный", "0", "1"),
        ("2", "bad", "Неверный", "20", "0"),
        ("2", "bad", "Неверный", "abc", "1"),
        ("2", "bad", "Неверный", "20", "inf"),
        ("3", "unknown", "hw", "10", ""),
        ("3", "s1", "unknown", "10", ""),
        ("3", "s1", "hw", "21", ""),
        ("3", "s1", "hw", "-1", ""),
        ("3", "s1", "hw", "abc", ""),
        ("3", "s1", "hw", "nan", ""),
        ("4", "s1", "unknown"),
    ],
)
def test_invalid_input_returns_to_menu_without_partial_changes(run_session, fields):
    facade, output, _ = run_session(
        "1", "s1", "Анна", "2", "hw", "Домашние работы", "20", "2",
        "3", "s1", "hw", "10", "Старая оценка",
        *fields, "7", "0",
    )
    assert len(facade.students()) == 1
    assert facade.students()[0].name == "Анна"
    assert len(facade.criteria()) == 1
    assert len(facade.evaluations()) == 1
    assert facade.evaluations()[0].score.value == Decimal("10")
    assert facade.evaluations()[0].comment == "Старая оценка"
    assert "Ошибка:" in output
    assert "Анна [s1]: 5.00" in output
    assert "До свидания!" in output


def test_decimal_comma_and_whitespace_are_accepted(run_session):
    facade, _, _ = run_session(
        " 1 ", " s1 ", " Анна ", "2", "hw", "Работа", "2,5", "0,4",
        "3", "s1", "hw", "1,25", "", "0",
    )
    assert facade.students()[0] == Student("s1", "Анна")
    assert facade.totals()[0].score == Decimal("5")


@pytest.mark.parametrize("text", ["", "1\ns1\n", "2\nhw\nРабота\n20\n", "3\ns1\n"])
def test_eof_at_menu_or_midway_through_form_exits_without_saving(text, monkeypatch, capsys, tmp_path):
    data_path = tmp_path / "gradebook.json"
    monkeypatch.setattr(sys, "stdin", StringIO(text))
    assert main(["--data", str(data_path)]) == 0
    assert "Ввод завершён" in capsys.readouterr().out
    assert not data_path.exists()


def test_ctrl_c_exits_without_traceback(monkeypatch, capsys, tmp_path):
    class InterruptedInput(StringIO):
        def readline(self, *args, **kwargs):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stdin", InterruptedInput())
    assert main(["--data", str(tmp_path / "gradebook.json")]) == 130
    assert "Работа прервана." in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments,expected,mode",
    [([], "2.00", FinalStrategy.name), (["--mode", "current"], "5.00", CurrentStrategy.name)],
)
def test_main_defaults_to_final_and_supports_current_mode(
    arguments, expected, mode, monkeypatch, capsys, tmp_path,
):
    data_path = tmp_path / "gradebook.json"
    export_path = tmp_path / "totals.csv"
    gradebook = Gradebook()
    gradebook.add_student(Student("s1", "Анна"))
    gradebook.add_criterion(Criterion("hw", "Работа", "20", "2"))
    gradebook.add_criterion(Criterion("exam", "Экзамен", "10", "3"))
    gradebook.evaluate("s1", "hw", "10")
    JsonGradebookRepository(data_path).save(gradebook)
    monkeypatch.setattr(sys, "stdin", StringIO("7\n8\n0\n"))
    assert main(["--data", str(data_path), "--export", str(export_path), *arguments]) == 0
    output = capsys.readouterr().out
    assert f"Режим: {mode}" in output
    assert f"Анна [s1]: {expected}; оценено 1/2" in output
    with export_path.open(encoding="utf-8-sig", newline="") as stream:
        fieldToValue = next(csv.DictReader(stream))
    assert fieldToValue["score"] == expected
    assert fieldToValue["mode"] == mode


@pytest.mark.parametrize(
    "mode,expected", [("final", ["9.00", "2.00"]), ("current", ["9.00", "5.00"])],
)
def test_demo_exports_both_modes_without_changing_existing_gradebook(mode, expected, capsys, tmp_path):
    data_path = tmp_path / "existing.json"
    export_path = tmp_path / "demo.csv"
    gradebook = Gradebook()
    gradebook.add_student(Student("keep", "Сохранённый студент"))
    JsonGradebookRepository(data_path).save(gradebook)
    original = data_path.read_bytes()
    assert main(["--demo", "--data", str(data_path), "--export", str(export_path), "--mode", mode]) == 0
    assert data_path.read_bytes() == original
    output = capsys.readouterr().out
    assert output.count("Ожидаемый отказ:") == 2
    assert "Исправление оценки" in output
    assert "Отмена оценки" in output
    assert "Итоги сохранены:" in output
    with export_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [fieldToValue["score"] for fieldToValue in rows] == expected
    assert [fieldToValue["id"] for fieldToValue in rows] == ["s1", "s2"]


def test_invalid_export_destination_is_reported_and_menu_continues(monkeypatch, capsys, tmp_path):
    destination = tmp_path / "not-csv.json"
    monkeypatch.setattr(sys, "stdin", StringIO("8\n0\n"))
    assert main(["--data", str(tmp_path / "data.json"), "--export", str(destination)]) == 0
    output = capsys.readouterr().out
    assert "Для экспорта нужен файл с расширением .csv" in output
    assert "До свидания!" in output
    assert not destination.exists()


def test_demo_export_failure_returns_nonzero(capsys, tmp_path):
    assert main(["--demo", "--export", str(tmp_path / "not-csv.json")]) == 1
    assert "Ошибка:" in capsys.readouterr().out


def test_invalid_storage_path_is_reported_without_traceback(capsys, tmp_path):
    assert main(["--data", str(tmp_path / "not-json.txt")]) == 1
    assert "Для ведомости нужен файл с расширением .json" in capsys.readouterr().out


def test_demo_default_export_does_not_replace_regular_export(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "exports" / "totals.csv"
    destination.parent.mkdir()
    original = b"id,name,score\nold,Existing student,7.00\n"
    destination.write_bytes(original)
    assert main(["--demo"]) == 0
    assert destination.read_bytes() == original
    assert (tmp_path / "exports" / "demo-totals.csv").is_file()
    assert "exports/demo-totals.csv" in capsys.readouterr().out
