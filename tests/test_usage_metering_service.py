import pytest

from app.services.usage_metering_service import (
    calculate_cost_micro_usd,
)


def test_cost_calculation_from_design_example():
    result = calculate_cost_micro_usd(
        api_calls=1,
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=500,
        reasoning_tokens=100,
    )

    assert result == 6_800


def test_zero_usage_cost():
    result = calculate_cost_micro_usd(
        api_calls=0,
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
    )

    assert result == 0


def test_all_input_tokens_are_cached():
    result = calculate_cost_micro_usd(
        api_calls=1,
        input_tokens=100,
        cached_input_tokens=100,
        output_tokens=0,
        reasoning_tokens=0,
    )

    assert result == 1_100


def test_large_usage_uses_integer_arithmetic():
    result = calculate_cost_micro_usd(
        api_calls=2,
        input_tokens=10_000_000,
        cached_input_tokens=2_500_000,
        output_tokens=5_000_000,
        reasoning_tokens=4_000_000,
    )

    assert result == 57_502_000
    assert isinstance(result, int)


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_calls": -1},
        {"input_tokens": -1},
        {"cached_input_tokens": -1},
        {"output_tokens": -1},
        {"reasoning_tokens": -1},
        {"api_calls": 1.5},
        {"api_calls": True},
        {"cached_input_tokens": 101},
        {"reasoning_tokens": 51},
    ],
)
def test_invalid_usage_quantities_are_rejected(overrides):
    quantities = {
        "api_calls": 1,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 50,
        "reasoning_tokens": 10,
    }

    quantities.update(overrides)

    with pytest.raises(ValueError):
        calculate_cost_micro_usd(**quantities)
