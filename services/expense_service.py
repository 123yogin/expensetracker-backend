"""
Expense Service
================
Business logic for expense operations.
Validates inputs, enforces business rules, delegates to repository.
Controllers call this — never the repository directly.
"""

import logging
from typing import Optional

from repositories.expense_repository import expense_repo
from validators import validate_uuid, validate_amount, validate_date

logger = logging.getLogger(__name__)


class ExpenseServiceError(Exception):
    """Raised when a business rule is violated."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ExpenseService:
    """Business logic layer for expenses."""

    def __init__(self, repo=None):
        self._repo = repo or expense_repo

    def list_expenses(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """
        Get paginated list of expenses for a user.
        Returns (items, total_count).
        """
        # Validate optional filters
        if start_date:
            valid, err = validate_date(start_date)
            if not valid:
                raise ExpenseServiceError(f"Invalid start_date: {err}")

        if end_date:
            valid, err = validate_date(end_date)
            if not valid:
                raise ExpenseServiceError(f"Invalid end_date: {err}")

        if category_id:
            valid, err = validate_uuid(category_id)
            if not valid:
                raise ExpenseServiceError(f"Invalid category_id: {err}")

        return self._repo.get_paginated(
            user_id=user_id,
            page=page,
            per_page=per_page,
            start_date=start_date,
            end_date=end_date,
            category_id=category_id,
        )

    def get_expense(self, expense_id: str, user_id: str) -> dict:
        """Get a single expense by ID."""
        valid, err = validate_uuid(expense_id)
        if not valid:
            raise ExpenseServiceError(f"Invalid expense ID: {err}")

        expense = self._repo.get_by_id(expense_id, user_id)
        if not expense:
            raise ExpenseServiceError("Expense not found", 404)

        return expense

    def create_expense(self, user_id: str, data: dict) -> dict:
        """
        Create a new expense with full validation.
        
        Required fields in data:
          - date: YYYY-MM-DD
          - amount: positive number
          - category_id: valid UUID of an active category
        
        Optional:
          - note: string
        """
        # Validate date
        date = data.get("date")
        if not date:
            raise ExpenseServiceError("Date is required")
        valid, err = validate_date(date)
        if not valid:
            raise ExpenseServiceError(f"Invalid date: {err}")

        # Validate amount
        raw_amount = data.get("amount")
        if raw_amount is None:
            raise ExpenseServiceError("Amount is required")
        validated_amount, err = validate_amount(raw_amount)
        if err:
            raise ExpenseServiceError(err)

        # Validate category
        category_id = data.get("category_id")
        if not category_id:
            raise ExpenseServiceError("Category ID is required")
        valid, err = validate_uuid(category_id)
        if not valid:
            raise ExpenseServiceError(f"Invalid category_id: {err}")

        # Business rule: category must exist and belong to user
        if not self._repo.category_exists(category_id, user_id):
            raise ExpenseServiceError("Category not found or inactive", 404)

        note = (data.get("note") or "").strip()

        expense = self._repo.create(
            user_id=user_id,
            date=date,
            amount=str(validated_amount),
            category_id=category_id,
            note=note,
        )

        logger.info("Expense created: %s for user %s", expense["id"], user_id)
        return expense

    def update_expense(self, expense_id: str, user_id: str, data: dict) -> dict:
        """Update an existing expense with validation."""
        valid, err = validate_uuid(expense_id)
        if not valid:
            raise ExpenseServiceError(f"Invalid expense ID: {err}")

        # Validate fields if provided
        update_fields = {}

        if "date" in data:
            valid, err = validate_date(data["date"])
            if not valid:
                raise ExpenseServiceError(f"Invalid date: {err}")
            update_fields["date"] = data["date"]

        if "amount" in data:
            validated_amount, err = validate_amount(data["amount"])
            if err:
                raise ExpenseServiceError(err)
            update_fields["amount"] = str(validated_amount)

        if "category_id" in data:
            valid, err = validate_uuid(data["category_id"])
            if not valid:
                raise ExpenseServiceError(f"Invalid category_id: {err}")
            if not self._repo.category_exists(data["category_id"], user_id):
                raise ExpenseServiceError("Category not found or inactive", 404)
            update_fields["category_id"] = data["category_id"]

        if "note" in data:
            update_fields["note"] = (data["note"] or "").strip()

        if not update_fields:
            raise ExpenseServiceError("No fields to update")

        result = self._repo.update(expense_id, user_id, **update_fields)
        if result is None:
            raise ExpenseServiceError("Expense not found", 404)

        logger.info("Expense updated: %s for user %s", expense_id, user_id)
        return result

    def delete_expense(self, expense_id: str, user_id: str) -> None:
        """Delete an expense."""
        valid, err = validate_uuid(expense_id)
        if not valid:
            raise ExpenseServiceError(f"Invalid expense ID: {err}")

        deleted = self._repo.delete(expense_id, user_id)
        if not deleted:
            raise ExpenseServiceError("Expense not found", 404)

        logger.info("Expense deleted: %s for user %s", expense_id, user_id)


# Singleton instance
expense_service = ExpenseService()
