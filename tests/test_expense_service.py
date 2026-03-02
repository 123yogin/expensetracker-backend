"""
Unit Tests for Expense Service
================================
Tests business logic in isolation.
Repository is mocked — no database needed.
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from services.expense_service import ExpenseService, ExpenseServiceError
from tests.conftest import TEST_USER_ID, TEST_USER_ID_2


class TestExpenseServiceCreate:
    """Tests for ExpenseService.create_expense()"""

    def setup_method(self):
        """Set up mock repository for each test."""
        self.mock_repo = MagicMock()
        self.service = ExpenseService(repo=self.mock_repo)

    def test_create_expense_success(self):
        """Should create an expense with valid data."""
        self.mock_repo.category_exists.return_value = True
        self.mock_repo.create.return_value = {
            "id": "test-id",
            "date": "2026-01-15",
            "amount": "100.00",
            "category_id": "cat-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "note": "Groceries",
        }

        result = self.service.create_expense(
            user_id=TEST_USER_ID,
            data={
                "date": "2026-01-15",
                "amount": "100.00",
                "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                "note": "Groceries",
            },
        )

        assert result["id"] == "test-id"
        assert result["amount"] == "100.00"
        self.mock_repo.create.assert_called_once()

    def test_create_expense_missing_date(self):
        """Should raise error when date is missing."""
        with pytest.raises(ExpenseServiceError, match="Date is required"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={"amount": "100", "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6"},
            )

    def test_create_expense_invalid_date(self):
        """Should raise error when date format is wrong."""
        with pytest.raises(ExpenseServiceError, match="Invalid date"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "15-01-2026",
                    "amount": "100",
                    "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                },
            )

    def test_create_expense_missing_amount(self):
        """Should raise error when amount is missing."""
        with pytest.raises(ExpenseServiceError, match="Amount is required"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "2026-01-15",
                    "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                },
            )

    def test_create_expense_negative_amount(self):
        """Should raise error for negative amount."""
        with pytest.raises(ExpenseServiceError, match="greater than zero"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "2026-01-15",
                    "amount": "-50",
                    "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                },
            )

    def test_create_expense_zero_amount(self):
        """Should raise error for zero amount."""
        with pytest.raises(ExpenseServiceError, match="greater than zero"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "2026-01-15",
                    "amount": "0",
                    "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                },
            )

    def test_create_expense_invalid_category_id(self):
        """Should raise error for invalid UUID format."""
        with pytest.raises(ExpenseServiceError, match="Invalid category_id"):
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "2026-01-15",
                    "amount": "100",
                    "category_id": "not-a-uuid",
                },
            )

    def test_create_expense_nonexistent_category(self):
        """Should raise 404 when category doesn't exist."""
        self.mock_repo.category_exists.return_value = False

        with pytest.raises(ExpenseServiceError, match="Category not found") as exc_info:
            self.service.create_expense(
                user_id=TEST_USER_ID,
                data={
                    "date": "2026-01-15",
                    "amount": "100",
                    "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                },
            )
        assert exc_info.value.status_code == 404

    def test_create_expense_trims_note(self):
        """Should strip whitespace from notes."""
        self.mock_repo.category_exists.return_value = True
        self.mock_repo.create.return_value = {"id": "test-id"}

        self.service.create_expense(
            user_id=TEST_USER_ID,
            data={
                "date": "2026-01-15",
                "amount": "100",
                "category_id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                "note": "  trimmed note  ",
            },
        )

        call_args = self.mock_repo.create.call_args
        assert call_args.kwargs["note"] == "trimmed note"


class TestExpenseServiceList:
    """Tests for ExpenseService.list_expenses()"""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = ExpenseService(repo=self.mock_repo)

    def test_list_expenses_with_pagination(self):
        """Should delegate pagination to repository."""
        self.mock_repo.get_paginated.return_value = (
            [{"id": "1"}, {"id": "2"}],
            10,
        )

        items, total = self.service.list_expenses(
            user_id=TEST_USER_ID, page=2, per_page=5
        )

        assert len(items) == 2
        assert total == 10
        self.mock_repo.get_paginated.assert_called_once_with(
            user_id=TEST_USER_ID,
            page=2,
            per_page=5,
            start_date=None,
            end_date=None,
            category_id=None,
        )

    def test_list_expenses_with_invalid_date_filter(self):
        """Should raise validation error for bad date filter."""
        with pytest.raises(ExpenseServiceError, match="Invalid start_date"):
            self.service.list_expenses(
                user_id=TEST_USER_ID, start_date="bad-date"
            )


class TestExpenseServiceDelete:
    """Tests for ExpenseService.delete_expense()"""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = ExpenseService(repo=self.mock_repo)

    def test_delete_expense_success(self):
        """Should successfully delete an existing expense."""
        self.mock_repo.delete.return_value = True

        self.service.delete_expense(
            "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6", TEST_USER_ID
        )

        self.mock_repo.delete.assert_called_once()

    def test_delete_expense_not_found(self):
        """Should raise 404 when expense doesn't exist."""
        self.mock_repo.delete.return_value = False

        with pytest.raises(ExpenseServiceError, match="not found") as exc_info:
            self.service.delete_expense(
                "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6", TEST_USER_ID
            )
        assert exc_info.value.status_code == 404

    def test_delete_expense_invalid_id(self):
        """Should raise validation error for bad UUID."""
        with pytest.raises(ExpenseServiceError, match="Invalid expense ID"):
            self.service.delete_expense("not-a-uuid", TEST_USER_ID)


class TestExpenseServiceUpdate:
    """Tests for ExpenseService.update_expense()"""

    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = ExpenseService(repo=self.mock_repo)

    def test_update_expense_partial(self):
        """Should allow partial updates."""
        self.mock_repo.update.return_value = {
            "id": "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
            "amount": "200.00",
        }

        result = self.service.update_expense(
            "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
            TEST_USER_ID,
            {"amount": "200.00"},
        )

        assert result["amount"] == "200.00"

    def test_update_expense_empty_data(self):
        """Should raise error when no fields provided."""
        with pytest.raises(ExpenseServiceError, match="No fields to update"):
            self.service.update_expense(
                "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                TEST_USER_ID,
                {},
            )

    def test_update_expense_not_found(self):
        """Should raise 404 when expense doesn't belong to user."""
        self.mock_repo.update.return_value = None

        with pytest.raises(ExpenseServiceError, match="not found"):
            self.service.update_expense(
                "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6",
                TEST_USER_ID,
                {"amount": "200.00"},
            )
