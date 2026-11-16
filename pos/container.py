"""Composition root: реализации портов выбираются только здесь."""

from dependency_injector import containers, providers

from .adapters.cli import ConsoleApplication
from .adapters.export import CsvTotalExporter
from .adapters.storage import JsonGradebookRepository
from .application import PosFacade
from .domain import CurrentStrategy, FinalStrategy, TotalCalculator


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    repository = providers.Singleton(JsonGradebookRepository, path=config.data_path)
    strategy = providers.Selector(
        config.mode, final=providers.Factory(FinalStrategy), current=providers.Factory(CurrentStrategy),
    )
    calculator = providers.Factory(TotalCalculator, strategy=strategy)
    exporter = providers.Singleton(CsvTotalExporter)
    facade = providers.Factory(PosFacade, repository=repository, calculator=calculator, exporter=exporter)
    application = providers.Factory(
        ConsoleApplication, facade=facade, export_path=config.export_path, mode=strategy.provided.name,
    )
