"""
Expenses Controller (Blueprint)
================================
Thin HTTP adapter. No business logic. No SQL.
Responsibilities:
  1. Parse HTTP request
  2. Call service
  3. Return standardized response
"""

import logging

from flask import Blueprint, request

from auth import require_auth, get_current_user_id
from pagination import parse_pagination
from responses import success, created, no_content, paginated, not_found, validation_error, server_error
from services.expense_service import expense_service, ExpenseServiceError

logger = logging.getLogger(__name__)

expenses_v2_bp = Blueprint("expenses_v2", __name__, url_prefix="/expenses")


@expenses_v2_bp.route("", methods=["GET"])
@require_auth
def list_expenses():
    """
    GET /expenses?page=1&per_page=50&start_date=...&end_date=...&category_id=...
    """
    user_id = get_current_user_id()
    page, per_page = parse_pagination(request)

    try:
        items, total = expense_service.list_expenses(
            user_id=user_id,
            page=page,
            per_page=per_page,
            start_date=request.args.get("start_date"),
            end_date=request.args.get("end_date"),
            category_id=request.args.get("category_id"),
        )
        return paginated(items, page, per_page, total)

    except ExpenseServiceError as e:
        return validation_error(e.message)
    except Exception as e:
        logger.exception("Error listing expenses")
        return server_error("Failed to fetch expenses")


@expenses_v2_bp.route("/<expense_id>", methods=["GET"])
@require_auth
def get_expense(expense_id):
    """
    GET /expenses/{id}
    """
    user_id = get_current_user_id()

    try:
        expense = expense_service.get_expense(expense_id, user_id)
        return success(expense)

    except ExpenseServiceError as e:
        if e.status_code == 404:
            return not_found(e.message)
        return validation_error(e.message)
    except Exception as e:
        logger.exception("Error getting expense %s", expense_id)
        return server_error("Failed to fetch expense")


@expenses_v2_bp.route("", methods=["POST"])
@require_auth
def create_expense():
    """
    POST /expenses
    Body: { date, amount, category_id, note? }
    """
    user_id = get_current_user_id()
    data = request.get_json()

    if not data:
        return validation_error("Request body is required")

    try:
        expense = expense_service.create_expense(user_id, data)
        return created(expense)

    except ExpenseServiceError as e:
        if e.status_code == 404:
            return not_found(e.message)
        return validation_error(e.message)
    except Exception as e:
        logger.exception("Error creating expense")
        return server_error("Failed to create expense")


@expenses_v2_bp.route("/<expense_id>", methods=["PUT"])
@require_auth
def update_expense(expense_id):
    """
    PUT /expenses/{id}
    Body: { date?, amount?, category_id?, note? }
    """
    user_id = get_current_user_id()
    data = request.get_json()

    if not data:
        return validation_error("Request body is required")

    try:
        expense = expense_service.update_expense(expense_id, user_id, data)
        return success(expense)

    except ExpenseServiceError as e:
        if e.status_code == 404:
            return not_found(e.message)
        return validation_error(e.message)
    except Exception as e:
        logger.exception("Error updating expense %s", expense_id)
        return server_error("Failed to update expense")


@expenses_v2_bp.route("/<expense_id>", methods=["DELETE"])
@require_auth
def delete_expense(expense_id):
    """
    DELETE /expenses/{id}
    """
    user_id = get_current_user_id()

    try:
        expense_service.delete_expense(expense_id, user_id)
        return no_content()

    except ExpenseServiceError as e:
        if e.status_code == 404:
            return not_found(e.message)
        return validation_error(e.message)
    except Exception as e:
        logger.exception("Error deleting expense %s", expense_id)
        return server_error("Failed to delete expense")
