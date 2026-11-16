from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from pos.domain import (
    Criterion, CurrentStrategy, DomainError, EvaluationFactory, FinalStrategy,
    Gradebook, Score, Student, TotalCalculator,
)


@pytest.fixture
def gradebook():
    book = Gradebook()
    book.add_student(Student("S-1", "Анна"))
    book.add_student(Student("S-2", "Борис"))
    book.add_criterion(Criterion("HW", "Домашняя работа", "20", "2"))
    book.add_criterion(Criterion("EX", "Экзамен", "100", "3"))
    return book


@pytest.mark.parametrize("student_id,name", [("", "Анна"), ("S-1", " \t")])
def test_student_requires_id_and_name(student_id, name):
    with pytest.raises(DomainError):
        Student(student_id, name)


@pytest.mark.parametrize("criterion_id,name", [(" ", "Экзамен"), ("EX", "")])
def test_criterion_requires_id_and_name(criterion_id, name):
    with pytest.raises(DomainError):
        Criterion(criterion_id, name, "10", "1")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "abc"])
@pytest.mark.parametrize("attribute", ["max_score", "weight"])
def test_criterion_requires_positive_finite_maximum_and_weight(attribute, value):
    maximum = value if attribute == "max_score" else "10"
    weight = value if attribute == "weight" else "1"
    with pytest.raises(DomainError):
        Criterion("EX", "Экзамен", maximum, weight)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity", "abc"])
def test_score_requires_finite_nonnegative_number(value):
    with pytest.raises(DomainError):
        Score(value)


def test_entities_use_identity_and_value_object_uses_its_value():
    assert Student("S-1", "Анна") == Student("S-1", "Анна Иванова")
    assert Student("S-1", "Анна") != Student("S-2", "Анна")
    assert Criterion("EX", "Экзамен", "10", "1") == Criterion("EX", "Итог", "20", "2")
    assert Score("1,25") == Score(Decimal("1.25"))
    assert Score("1.25") != Score("1.5")


def test_entity_fields_are_normalized_and_cannot_be_changed():
    student = Student(" S-1 ", " Анна ")
    assert (student.id, student.name) == ("S-1", "Анна")
    with pytest.raises(FrozenInstanceError):
        student.id = "S-2"
    with pytest.raises(FrozenInstanceError):
        Score("3").value = Decimal("4")


@pytest.mark.parametrize("kind", ["student", "criterion"])
def test_duplicate_id_cannot_replace_existing_entity(gradebook, kind):
    before = (gradebook.students, gradebook.criteria)
    with pytest.raises(DomainError, match="уже занят"):
        if kind == "student":
            gradebook.add_student(Student("S-1", "Другое имя"))
        else:
            gradebook.add_criterion(Criterion("HW", "Другая работа", "10", "1"))
    assert (gradebook.students, gradebook.criteria) == before
    assert gradebook.student("S-1").name == "Анна"
    assert gradebook.criterion("HW").max_score == Decimal("20")


@pytest.mark.parametrize("value", ["0", "20"])
def test_factory_accepts_score_boundaries_and_uses_registered_entities(gradebook, value):
    evaluation = EvaluationFactory.create(gradebook, "S-1", "HW", value, "Проверено")
    assert evaluation.student is gradebook.student("S-1")
    assert evaluation.criterion is gradebook.criterion("HW")
    assert evaluation.score == Score(value)
    assert evaluation.comment == "Проверено"
    assert gradebook.evaluations == ()


@pytest.mark.parametrize("student_id,criterion_id", [("missing", "HW"), ("S-1", "missing")])
def test_factory_and_aggregate_reject_unknown_references(gradebook, student_id, criterion_id):
    with pytest.raises(DomainError, match="не найден"):
        EvaluationFactory.create(gradebook, student_id, criterion_id, "5")
    with pytest.raises(DomainError, match="не найден"):
        gradebook.evaluate(student_id, criterion_id, "5")
    assert gradebook.evaluations == ()


@pytest.mark.parametrize("value", ["-1", "20.01", "NaN"])
def test_invalid_correction_preserves_previous_evaluation(gradebook, value):
    gradebook.evaluate("S-1", "HW", "12", "Первый результат")
    previous = gradebook.evaluations
    with pytest.raises(DomainError):
        gradebook.evaluate("S-1", "HW", value, "Ошибка")
    assert gradebook.evaluations == previous


def test_correction_replaces_one_evaluation_and_cancel_removes_it(gradebook):
    gradebook.evaluate("S-1", "HW", "10", "Первый результат")
    gradebook.evaluate("S-1", "HW", "15", "Исправлено")
    assert len(gradebook.evaluations) == 1
    assert gradebook.evaluations[0].score == Score("15")
    assert gradebook.evaluations[0].comment == "Исправлено"
    gradebook.cancel_evaluation("S-1", "HW")
    assert gradebook.evaluations == ()
    with pytest.raises(DomainError, match="ещё не выставлена"):
        gradebook.cancel_evaluation("S-1", "HW")


@pytest.mark.parametrize("student_id,criterion_id", [("missing", "HW"), ("S-1", "missing")])
def test_cancel_unknown_reference_does_not_remove_other_evaluations(gradebook, student_id, criterion_id):
    gradebook.evaluate("S-1", "HW", "10")
    before = gradebook.evaluations
    with pytest.raises(DomainError):
        gradebook.cancel_evaluation(student_id, criterion_id)
    assert gradebook.evaluations == before


def test_public_collections_are_snapshots(gradebook):
    students, criteria, evaluations = gradebook.students, gradebook.criteria, gradebook.evaluations
    assert all(isinstance(items, tuple) for items in (students, criteria, evaluations))
    gradebook.add_student(Student("S-3", "Вера"))
    gradebook.add_criterion(Criterion("TEST", "Тест", "5", "1"))
    gradebook.evaluate("S-1", "HW", "10")
    assert len(students) == 2
    assert len(criteria) == 2
    assert evaluations == ()


@pytest.mark.parametrize("strategy", [FinalStrategy(), CurrentStrategy()])
def test_weighted_total_normalizes_different_maxima_and_arbitrary_weights(gradebook, strategy):
    gradebook.evaluate("S-1", "HW", "10")
    gradebook.evaluate("S-1", "EX", "80")
    gradebook.evaluate("S-2", "HW", "20")
    total = TotalCalculator(strategy).calculate(gradebook, "S-1")
    assert total.score == Decimal("6.8")
    assert (total.graded_count, total.criteria_count) == (2, 2)
    assert total.student.id == "S-1"
    assert total.mode == strategy.name


def test_missing_grade_and_explicit_zero_have_different_current_results(gradebook):
    gradebook.evaluate("S-1", "HW", "10")
    final = TotalCalculator(FinalStrategy())
    current = TotalCalculator(CurrentStrategy())
    assert final.calculate(gradebook, "S-1").score == Decimal("2")
    assert current.calculate(gradebook, "S-1").score == Decimal("5")
    gradebook.evaluate("S-1", "EX", "0")
    assert final.calculate(gradebook, "S-1").score == Decimal("2")
    assert current.calculate(gradebook, "S-1").score == Decimal("2")
    assert current.calculate(gradebook, "S-1").graded_count == 2


def test_no_grades_means_zero_final_but_no_current_score(gradebook):
    assert TotalCalculator(FinalStrategy()).calculate(gradebook, "S-1").score == Decimal("0")
    assert TotalCalculator(CurrentStrategy()).calculate(gradebook, "S-1").score is None


@pytest.mark.parametrize("value,expected", [("0", Decimal("0")), ("10", Decimal("10"))])
@pytest.mark.parametrize("strategy", [FinalStrategy(), CurrentStrategy()])
def test_all_minimum_or_maximum_scores_reach_exact_scale_endpoints(value, expected, strategy):
    gradebook = Gradebook()
    gradebook.add_student(Student("S-1", "Анна"))
    for criterion_id in ("A", "B", "C"):
        gradebook.add_criterion(Criterion(criterion_id, "Работа", "10", "1"))
        gradebook.evaluate("S-1", criterion_id, value)
    assert TotalCalculator(strategy).calculate(gradebook, "S-1").score == expected


@pytest.mark.parametrize("strategy", [FinalStrategy(), CurrentStrategy()])
def test_empty_rubric_has_no_total(strategy):
    gradebook = Gradebook()
    gradebook.add_student(Student("S-1", "Анна"))
    total = TotalCalculator(strategy).calculate(gradebook, "S-1")
    assert total.score is None
    assert (total.graded_count, total.criteria_count) == (0, 0)


def test_total_is_recalculated_after_correction_cancellation_and_rubric_change(gradebook):
    calculator = TotalCalculator(FinalStrategy())
    gradebook.evaluate("S-1", "HW", "10")
    assert calculator.calculate(gradebook, "S-1").score == Decimal("2")
    gradebook.evaluate("S-1", "HW", "20")
    assert calculator.calculate(gradebook, "S-1").score == Decimal("4")
    gradebook.add_criterion(Criterion("TEST", "Тест", "10", "5"))
    assert calculator.calculate(gradebook, "S-1").score == Decimal("2")
    gradebook.cancel_evaluation("S-1", "HW")
    assert calculator.calculate(gradebook, "S-1").score == Decimal("0")


def test_domain_service_uses_injected_strategy_and_only_this_students_grades(gradebook):
    class FixedStrategy:
        name = "Тестовая"

        def calculate(self, criteria, evaluations):
            assert len(criteria) == 2
            assert len(evaluations) == 1
            assert evaluations[0].student.id == "S-1"
            return Decimal("3.25")

    gradebook.evaluate("S-1", "HW", "10")
    gradebook.evaluate("S-2", "EX", "90")
    total = TotalCalculator(FixedStrategy()).calculate(gradebook, "S-1")
    assert total.score == Decimal("3.25")
    assert total.mode == "Тестовая"
    with pytest.raises(DomainError, match="не найден"):
        TotalCalculator(FinalStrategy()).calculate(gradebook, "missing")
