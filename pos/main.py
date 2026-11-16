from __future__ import annotations

import argparse
from decimal import DecimalException

from dependency_injector import providers

from .adapters.storage import MemoryGradebookRepository
from .container import Container
from .domain import DomainError
from .ports import ExportError, StorageError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ПОС — преподавательская оценка студентов")
    parser.add_argument("--data", default="data/gradebook.json", help="путь к ведомости JSON")
    parser.add_argument("--export", help="путь для экспорта итогов CSV")
    parser.add_argument("--mode", choices=("final", "current"), default="final", help="итоговый или текущий расчёт")
    parser.add_argument("--demo", action="store_true", help="демо без изменения сохранённой ведомости")
    args = parser.parse_args(argv)
    export_path = args.export or ("exports/demo-totals.csv" if args.demo else "exports/totals.csv")
    container = Container()
    container.config.from_dict({"data_path": args.data, "export_path": export_path, "mode": args.mode})
    if args.demo:
        container.repository.override(providers.Singleton(MemoryGradebookRepository))
    try:
        application = container.application()
        if args.demo:
            application.run_demo()
        else:
            application.run()
    except EOFError:
        print("\nВвод завершён. До свидания!")
    except KeyboardInterrupt:
        print("\nРабота прервана.")
        return 130
    except (DomainError, StorageError, ExportError, DecimalException) as error:
        print(f"Ошибка: {error}")
        return 1
    return 0
