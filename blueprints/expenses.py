"""
Expenses Blueprint - Handles all expense-related API endpoints.

Production-hardened endpoints with USER ISOLATION:
- Strict validation with centralized validators
- Decimal amounts quantized to 2 decimal places
- Future date rejection
- Flask g context for database connections
- Proper error handling without leaking stack traces
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own expenses
"""

import psycopg2
from flask import Blueprint, request, jsonify, g

from database import get_db
from validators import (
    validate_uuid,
    validate_date,
    validate_amount,
    format_amount,
    generate_uuid
)
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id


expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')


def format_expense(row) -> dict:
    """
    Format an expense row for JSON response.
    Helper function to eliminate code duplication.
    
    Note: amount is returned as string to preserve precision.
    """
    return {
        'id': str(row['id']),
        'date': str(row['date']) if row['date'] else None,
        'amount': format_amount(row['amount']),
        'category_id': str(row['category_id']),
        'category_name': row['category_name'],
        'note': row['note'],
        'is_split': row['is_split'],
        'split_amount': format_amount(row['split_amount']),
        'split_with': row['split_with'],
        'created_at': str(row['created_at']) if row['created_at'] else None,
        'updated_at': str(row['updated_at']) if row['updated_at'] else None
    }


# SQL query for fetching expense with category name (reusable)
EXPENSE_SELECT_QUERY = """
    SELECT e.id, e.date, e.amount, e.category_id, e.note,
           e.is_split, e.split_amount, e.split_with,
           e.created_at, e.updated_at, c.name as category_name
    FROM expenses e
    JOIN categories c ON e.category_id = c.id
"""


@expenses_bp.route('', methods=['GET'])
@require_auth
def get_expenses():
    """
    GET /expenses
    List expenses for the authenticated user with optional filters.
    
    Query parameters:
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional)
        category_id: UUID (optional)
    
    Returns:
        200: List of expense objects (user's expenses only)
        400: Validation error
        401: Unauthorized
    """
    user_id = get_current_user_id()
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id')
    
    # Build query with USER ISOLATION filter
    query = EXPENSE_SELECT_QUERY + " WHERE e.user_id = %s"
    params = [user_id]
    
    if start_date:
        valid, error = validate_date(start_date, reject_future=False)
        if not valid:
            return error_response(f'Invalid start_date: {error}', 400)
        query += " AND e.date >= %s"
        params.append(start_date)
    
    if end_date:
        valid, error = validate_date(end_date, reject_future=False)
        if not valid:
            return error_response(f'Invalid end_date: {error}', 400)
        query += " AND e.date <= %s"
        params.append(end_date)
    
    if category_id:
        valid, error = validate_uuid(category_id)
        if not valid:
            return error_response(f'Invalid category_id: {error}', 400)
        query += " AND e.category_id = %s"
        params.append(category_id)
    
    # Order by date descending, then by creation time
    query += " ORDER BY e.date DESC, e.created_at DESC"
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(query, params)
            expenses = cursor.fetchall()
        return jsonify([format_expense(row) for row in expenses]), 200
    except Exception as e:
        return handle_db_error(e)


@expenses_bp.route('', methods=['POST'])
@require_auth
def create_expense():
    """
    POST /expenses
    Create a new expense for the authenticated user.
    
    Request body: {
        "date": "YYYY-MM-DD",      (required, cannot be future)
        "amount": "123.45",         (required, positive, max 2 decimals)
        "category_id": "uuid",      (required)
        "note": "optional note"     (optional)
    }
    
    Returns:
        201: Created expense object
        400: Validation error
        401: Unauthorized
        404: Category not found or inactive
    """
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    # Validate date (required, no future dates for expenses)
    date = data.get('date')
    valid, error = validate_date(date, reject_future=True)
    if not valid:
        return error_response(error, 400)
    
    # Validate amount (required, positive, 2 decimal places)
    validated_amount, error = validate_amount(data.get('amount'))
    if error:
        return error_response(error, 400)
    
    # Validate category_id (required, valid UUID v4)
    category_id = data.get('category_id')
    if not category_id:
        return error_response('Category ID is required', 400)
    
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response(f'Invalid category_id: {error}', 400)
    
    # Get and sanitize note (optional)
    note = data.get('note', '') or ''
    if not isinstance(note, str):
        return error_response('Note must be a string', 400)
    note = note.strip()
    
    # Validate note length
    if len(note) > 500:
        return error_response('Note must be 500 characters or less', 400)
    
    # Generate UUID in backend only
    expense_id = generate_uuid()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Verify category exists, is active, and BELONGS TO USER
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Category not found or inactive', 404)
            
            # Split fields
            is_split = bool(data.get('is_split', False))
            split_amount = 0
            split_with = data.get('split_with', '')

            if is_split:
                split_amount, error = validate_amount(data.get('split_amount', 0))
                if error:
                    return error_response(f'Invalid split_amount: {error}', 400)
            
            # Insert expense with user_id for isolation
            cursor.execute(
                """INSERT INTO expenses (id, date, amount, category_id, note, is_split, split_amount, split_with, user_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (expense_id, date, str(validated_amount), category_id, note, is_split, str(split_amount), split_with, user_id)
            )
            db.commit()
            
            # Fetch the created expense with category name
            cursor.execute(
                EXPENSE_SELECT_QUERY + " WHERE e.id = %s AND e.user_id = %s",
                (expense_id, user_id)
            )
            expense = cursor.fetchone()
        
        return jsonify(format_expense(expense)), 201
        
    except psycopg2.IntegrityError as e:
        db.rollback()
        if 'foreign key' in str(e).lower():
            return error_response('Invalid category ID', 400)
        return handle_db_error(e)
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@expenses_bp.route('/<expense_id>', methods=['PUT'])
@require_auth
def update_expense(expense_id):
    """
    PUT /expenses/<uuid>
    Update an existing expense (must belong to authenticated user).
    
    Request body (all fields optional): {
        "date": "YYYY-MM-DD",
        "amount": "123.45",
        "category_id": "uuid",
        "note": "optional note"
    }
    
    Returns:
        200: Updated expense object
        400: Validation error or no fields to update
        401: Unauthorized
        404: Expense not found (or belongs to another user)
    """
    user_id = get_current_user_id()
    
    # Validate expense UUID format
    valid, error = validate_uuid(expense_id)
    if not valid:
        return error_response(f'Invalid expense ID: {error}', 400)
    
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if expense exists AND belongs to user (ownership check)
            cursor.execute(
                "SELECT id FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Expense not found', 404)
            
            # Build update query dynamically based on provided fields
            updates = []
            params = []
            
            if 'date' in data:
                valid, error = validate_date(data['date'], reject_future=True)
                if not valid:
                    return error_response(error, 400)
                updates.append("date = %s")
                params.append(data['date'])
            
            if 'amount' in data:
                validated_amount, error = validate_amount(data['amount'])
                if error:
                    return error_response(error, 400)
                updates.append("amount = %s")
                params.append(str(validated_amount))
            
            if 'category_id' in data:
                category_id = data['category_id']
                valid, error = validate_uuid(category_id)
                if not valid:
                    return error_response(f'Invalid category_id: {error}', 400)
                
                # Verify category exists, is active, and BELONGS TO USER
                cursor.execute(
                    "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                    (category_id, user_id)
                )
                if not cursor.fetchone():
                    return error_response('Category not found or inactive', 404)
                
                updates.append("category_id = %s")
                params.append(category_id)
            
            if 'note' in data:
                note = data['note'] or ''
                if not isinstance(note, str):
                    return error_response('Note must be a string', 400)
                note = note.strip()
                if len(note) > 500:
                    return error_response('Note must be 500 characters or less', 400)
                updates.append("note = %s")
                params.append(note)

            if 'is_split' in data:
                is_split = bool(data['is_split'])
                updates.append("is_split = %s")
                params.append(is_split)
            
            if 'split_amount' in data:
                s_amount, error = validate_amount(data['split_amount'])
                if error:
                    return error_response(f'Invalid split_amount: {error}', 400)
                updates.append("split_amount = %s")
                params.append(str(s_amount))
            
            if 'split_with' in data:
                updates.append("split_with = %s")
                params.append(data['split_with'])
            
            if not updates:
                return error_response('No fields to update', 400)
            
            # Add updated_at timestamp
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(expense_id)
            params.append(user_id)  # Enforce ownership in WHERE clause
            
            # Execute update with ownership check
            query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = %s AND user_id = %s"
            cursor.execute(query, params)
            db.commit()
            
            # Fetch the updated expense
            cursor.execute(
                EXPENSE_SELECT_QUERY + " WHERE e.id = %s AND e.user_id = %s",
                (expense_id, user_id)
            )
            expense = cursor.fetchone()
        
        return jsonify(format_expense(expense)), 200
        
    except psycopg2.IntegrityError as e:
        db.rollback()
        if 'foreign key' in str(e).lower():
            return error_response('Invalid category ID', 400)
        return handle_db_error(e)
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@expenses_bp.route('/<expense_id>', methods=['DELETE'])
@require_auth
def delete_expense(expense_id):
    """
    DELETE /expenses/<uuid>
    Hard deletes an expense (must belong to authenticated user).
    
    Returns:
        200: Success message
        400: Invalid UUID
        401: Unauthorized
        404: Expense not found (or belongs to another user)
    """
    user_id = get_current_user_id()
    
    # Validate UUID format
    valid, error = validate_uuid(expense_id)
    if not valid:
        return error_response(f'Invalid expense ID: {error}', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if expense exists AND belongs to user
            cursor.execute(
                "SELECT id FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Expense not found', 404)
            
            # Delete with ownership enforcement
            cursor.execute(
                "DELETE FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            db.commit()
        
        return jsonify({'message': 'Expense deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
