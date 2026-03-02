"""
Unit Tests for Validators
===========================
Tests input validation helpers used across all services.
Pure unit tests — no database, no Flask app needed.
"""

import pytest
from decimal import Decimal

from validators import (
    validate_uuid,
    validate_date,
    validate_month,
    validate_amount,
    format_amount,
    generate_uuid,
    get_month_date_range,
)


class TestValidateUUID:
    """Tests for UUID v4 validation."""

    def test_valid_uuid(self):
        valid, err = validate_uuid("a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6")
        assert valid is True
        assert err is None

    def test_generated_uuid_is_valid(self):
        uid = generate_uuid()
        valid, err = validate_uuid(uid)
        assert valid is True

    def test_empty_string(self):
        valid, err = validate_uuid("")
        assert valid is False
        assert "required" in err.lower()

    def test_none(self):
        valid, err = validate_uuid(None)
        assert valid is False

    def test_invalid_format(self):
        valid, err = validate_uuid("not-a-uuid")
        assert valid is False

    def test_uuid_v1_rejected(self):
        # UUID v1 has version=1 in the third group
        valid, err = validate_uuid("550e8400-e29b-11d4-a716-446655440000")
        assert valid is False

    def test_integer_rejected(self):
        valid, err = validate_uuid(12345)
        assert valid is False


class TestValidateDate:
    """Tests for date validation."""

    def test_valid_date(self):
        valid, err = validate_date("2026-01-15")
        assert valid is True
        assert err is None

    def test_valid_past_date(self):
        valid, err = validate_date("2020-06-15")
        assert valid is True

    def test_future_date_rejected(self):
        valid, err = validate_date("2099-12-31")
        assert valid is False
        assert "future" in err.lower()

    def test_future_date_allowed_when_flag_off(self):
        valid, err = validate_date("2099-12-31", reject_future=False)
        assert valid is True

    def test_invalid_format_dd_mm_yyyy(self):
        valid, err = validate_date("15-01-2026")
        assert valid is False

    def test_invalid_format_slash(self):
        valid, err = validate_date("2026/01/15")
        assert valid is False

    def test_invalid_day_32(self):
        valid, err = validate_date("2026-01-32")
        assert valid is False

    def test_invalid_month_13(self):
        valid, err = validate_date("2026-13-15")
        assert valid is False

    def test_empty_string(self):
        valid, err = validate_date("")
        assert valid is False

    def test_none(self):
        valid, err = validate_date(None)
        assert valid is False


class TestValidateMonth:
    """Tests for month format validation."""

    def test_valid_month(self):
        valid, err = validate_month("2026-01")
        assert valid is True

    def test_invalid_month_00(self):
        valid, err = validate_month("2026-00")
        assert valid is False

    def test_invalid_month_13(self):
        valid, err = validate_month("2026-13")
        assert valid is False

    def test_invalid_format(self):
        valid, err = validate_month("01-2026")
        assert valid is False

    def test_full_date_rejected(self):
        valid, err = validate_month("2026-01-15")
        assert valid is False


class TestValidateAmount:
    """Tests for amount validation."""

    def test_valid_integer(self):
        amount, err = validate_amount("100")
        assert err is None
        assert amount == Decimal("100.00")

    def test_valid_decimal(self):
        amount, err = validate_amount("99.99")
        assert err is None
        assert amount == Decimal("99.99")

    def test_valid_float(self):
        amount, err = validate_amount(50.5)
        assert err is None
        assert amount == Decimal("50.50")

    def test_zero_rejected(self):
        amount, err = validate_amount("0")
        assert amount is None
        assert "greater than zero" in err.lower()

    def test_negative_rejected(self):
        amount, err = validate_amount("-10")
        assert amount is None
        assert "greater than zero" in err.lower()

    def test_too_many_decimals_rejected(self):
        amount, err = validate_amount("10.999")
        assert amount is None
        assert "2 decimal" in err.lower()

    def test_none_rejected(self):
        amount, err = validate_amount(None)
        assert amount is None

    def test_empty_string_rejected(self):
        amount, err = validate_amount("")
        assert amount is None

    def test_text_rejected(self):
        amount, err = validate_amount("abc")
        assert amount is None

    def test_very_large_amount(self):
        amount, err = validate_amount("999999999.99")
        assert err is None
        assert amount == Decimal("999999999.99")


class TestFormatAmount:
    """Tests for amount formatting."""

    def test_format_integer(self):
        assert format_amount(100) == "100.00"

    def test_format_decimal(self):
        assert format_amount(Decimal("99.95")) == "99.95"

    def test_format_string(self):
        assert format_amount("50.5") == "50.50"

    def test_format_none(self):
        assert format_amount(None) == "0.00"

    def test_format_invalid(self):
        assert format_amount("abc") == "0.00"


class TestGetMonthDateRange:
    """Tests for month date range calculation."""

    def test_january(self):
        start, end = get_month_date_range("2026-01")
        assert start == "2026-01-01"
        assert end == "2026-01-31"

    def test_february_non_leap(self):
        start, end = get_month_date_range("2026-02")
        assert start == "2026-02-01"
        assert end == "2026-02-28"

    def test_february_leap_year(self):
        start, end = get_month_date_range("2024-02")
        assert start == "2024-02-01"
        assert end == "2024-02-29"

    def test_december(self):
        start, end = get_month_date_range("2026-12")
        assert start == "2026-12-01"
        assert end == "2026-12-31"
