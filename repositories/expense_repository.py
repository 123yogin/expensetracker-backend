"""
Expense Repository
===================
All SQL queries related to expenses live here.
No business logic — just data access.
"""

import logging
from typing import Optional

from repositories.base import BaseRepository
from validators import generate_uuid, format_amount

logger = logging.getLogger(__name__)


class ExpenseRepository(BaseRepository):
    """Data access layer for expenses."""

    # ---- Formatters ----

    @staticmethod
    def _format_row(row: dict) -> dict:
        """Format a raw DB row into API-friendly dict."""
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "date": str(row["date"]),
            "amount": format_amount(row["amount"]),
            "category_id": str(row["category_id"]),
            "category_name": row.get("category_name", ""),
            "note": row.get("note") or "",
            "is_split": row.get("is_split", False),
            "split_amount": format_amount(row["split_amount"]) if row.get("split_amount") else None,
            "split_with": row.get("split_with") or "",
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        }

    # ---- Queries ----

    def get_paginated(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """
        Get paginated expenses for a user with optional filters.
        Returns (items, total_count).
        """
        # Build WHERE clause
        where_clauses = ["e.user_id = %s"]
        params = [user_id]

        if start_date:
            where_clauses.append("e.date >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("e.date <= %s")
            params.append(end_date)
        if category_id:
            where_clauses.append("e.category_id = %s")
            params.append(category_id)

        where_sql = " AND ".join(where_clauses)

        # Count query
        count_sql = f"SELECT COUNT(*) FROM expenses e WHERE {where_sql}"
        total = self._execute_count(count_sql, tuple(params))

        # Data query with pagination
        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT e.id, e.date, e.amount, e.category_id, e.note,
                   e.is_split, e.split_amount, e.split_with,
                   e.created_at, e.updated_at,
                   c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE {where_sql}
            ORDER BY e.date DESC, e.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])

        rows = self._execute_all(data_sql, tuple(params))
        items = [self._format_row(row) for row in rows]

        return items, total

    def get_by_id(self, expense_id: str, user_id: str) -> Optional[dict]:
        """Get a single expense by ID, enforcing user ownership."""
        row = self._execute_one(
            """
            SELECT e.id, e.date, e.amount, e.category_id, e.note,
                   e.is_split, e.split_amount, e.split_with,
                   e.created_at, e.updated_at,
                   c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.id = %s AND e.user_id = %s
            """,
            (expense_id, user_id),
        )
        return self._format_row(row) if row else None

    def create(
        self,
        user_id: str,
        date: str,
        amount: str,
        category_id: str,
        note: str = "",
    ) -> dict:
        """Create a new expense and return the created record."""
        expense_id = generate_uuid()

        self._execute_modify(
            """
            INSERT INTO expenses (id, date, amount, category_id, note, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (expense_id, date, amount, category_id, note, user_id),
        )
        self._commit()

        return self.get_by_id(expense_id, user_id)

    def update(
        self,
        expense_id: str,
        user_id: str,
        date: Optional[str] = None,
        amount: Optional[str] = None,
        category_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[dict]:
        """Update an existing expense. Returns updated record or None if not found."""
        # Build SET clause dynamically
        set_clauses = []
        params = []

        if date is not None:
            set_clauses.append("date = %s")
            params.append(date)
        if amount is not None:
            set_clauses.append("amount = %s")
            params.append(amount)
        if category_id is not None:
            set_clauses.append("category_id = %s")
            params.append(category_id)
        if note is not None:
            set_clauses.append("note = %s")
            params.append(note)

        if not set_clauses:
            return self.get_by_id(expense_id, user_id)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.extend([expense_id, user_id])

        affected = self._execute_modify(
            f"""
            UPDATE expenses
            SET {', '.join(set_clauses)}
            WHERE id = %s AND user_id = %s
            """,
            tuple(params),
        )

        if affected == 0:
            return None

        self._commit()
        return self.get_by_id(expense_id, user_id)

    def delete(self, expense_id: str, user_id: str) -> bool:
        """Delete an expense. Returns True if deleted, False if not found."""
        affected = self._execute_modify(
            "DELETE FROM expenses WHERE id = %s AND user_id = %s",
            (expense_id, user_id),
        )
        if affected > 0:
            self._commit()
            return True
        return False

    def category_exists(self, category_id: str, user_id: str) -> bool:
        """Check if a category exists and belongs to the user."""
        row = self._execute_one(
            "SELECT 1 FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
            (category_id, user_id),
        )
        return row is not None


# Singleton instance
expense_repo = ExpenseRepository()
