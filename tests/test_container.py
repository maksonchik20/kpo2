from decimal import Decimal
from io import StringIO
import sys

from dependency_injector import providers

from pos.adapters.storage import JsonGradebookRepository, MemoryGradebookRepository
from pos.container import Container
from pos.domain import CurrentStrategy, FinalStrategy


def configured_container(tmp_path, mode="final"):
    container = Container()
    container.config.from_dict({
        "data_path": str(tmp_path / "gradebook.json"),
        "export_path": str(tmp_path / "totals.csv"),
        "mode": mode,
    })
    return container


def test_production_container_shares_repository_across_facades_and_console(tmp_path, monkeypatch, capsys):
    container = configured_container(tmp_path)
    assert isinstance(container.repository(), JsonGradebookRepository)
    assert container.repository() is container.repository()
    first = container.facade()
    second = container.facade()
    assert first is not second
    first.add_student("s1", "Анна")
    second.add_criterion("hw", "Работа", "10", "1")
    first.evaluate("s1", "hw", "8")
    assert second.totals()[0].score == Decimal("8")
    monkeypatch.setattr(sys, "stdin", StringIO("7\n0\n"))
    container.application().run()
    assert "Анна [s1]: 8.00" in capsys.readouterr().out
    assert (tmp_path / "gradebook.json").is_file()


def test_repository_override_is_used_before_facade_creation(tmp_path):
    container = configured_container(tmp_path)
    repository = MemoryGradebookRepository()
    with container.repository.override(providers.Object(repository)):
        facade = container.facade()
        facade.add_student("s1", "Анна")
        assert repository.load().students[0].id == "s1"
        assert container.facade().students()[0].name == "Анна"
    assert not (tmp_path / "gradebook.json").exists()
    assert container.facade().students() == ()


def test_strategy_selector_changes_totals_with_the_same_repository(tmp_path):
    container = configured_container(tmp_path)
    repository = MemoryGradebookRepository()
    with container.repository.override(providers.Object(repository)):
        final_facade = container.facade()
        final_facade.add_student("s1", "Анна")
        final_facade.add_criterion("hw", "Работа", "20", "2")
        final_facade.add_criterion("exam", "Экзамен", "10", "3")
        final_facade.evaluate("s1", "hw", "10")
        container.config.mode.from_value("current")
        current_facade = container.facade()
        assert final_facade.totals()[0].score == Decimal("2")
        assert final_facade.totals()[0].mode == FinalStrategy.name
        assert current_facade.totals()[0].score == Decimal("5")
        assert current_facade.totals()[0].mode == CurrentStrategy.name
        assert len(repository.load().evaluations) == 1


def test_separate_containers_have_independent_repositories(tmp_path):
    first = configured_container(tmp_path / "first")
    second = configured_container(tmp_path / "second")
    first.facade().add_student("s1", "Анна")
    assert second.facade().students() == ()
