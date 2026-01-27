"""
Expenses Blueprint - Handles all expense-related API endpoints.

Production-hardened endpoints:
- Strict validation with centralized validators
- Decimal amounts quantized to 2 decimal places
- Future date rejection
- Flask g context for database connections
- Proper error handling without leaking stack traces
"""

import psycopg2
from flask import Blueprint, request, jsonify

from database import get_db
from validators import (
    validate_uuid,
    validate_date,
    validate_amount,
    format_amount,
    generate_uuid
)
from errors import handle_db_error, error_response


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
def get_expenses():
    """
    GET /expenses
    List expenses with optional filters.
    
    Query parameters:
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional)
        category_id: UUID (optional)
    
    Returns:
        200: List of expense objects
        400: Validation error
    """
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id')
    
    # Build query with optional filters (parameterized for SQL injection safety)
    query = EXPENSE_SELECT_QUERY + " WHERE 1=1"
    params = []
    
    if start_date:
        # Allow past dates in filters (don't reject future for filtering)
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
def create_expense():
    """
    POST /expenses
    Create a new expense.
    
    Request body: {
        "date": "YYYY-MM-DD",      (required, cannot be future)
        "amount": "123.45",         (required, positive, max 2 decimals)
        "category_id": "uuid",      (required)
        "note": "optional note"     (optional)
    }
    
    Returns:
        201: Created expense object
        400: Validation error
        404: Category not found or inactive
    """
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
            # Verify category exists and is active (single query)
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND is_active = TRUE",
                (category_id,)
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
            
            # Insert expense with validated amount
            cursor.execute(
                """INSERT INTO expenses (id, date, amount, category_id, note, is_split, split_amount, split_with)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (expense_id, date, str(validated_amount), category_id, note, is_split, str(split_amount), split_with)
            )
            db.commit()
            
            # Fetch the created expense with category name
            cursor.execute(
                EXPENSE_SELECT_QUERY + " WHERE e.id = %s",
                (expense_id,)
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
def update_expense(expense_id):
    """
    PUT /expenses/<uuid>
    Update an existing expense.
    
    Request body (all fields optional): {
        "date": "YYYY-MM-DD",
        "amount": "123.45",
        "category_id": "uuid",
        "note": "optional note"
    }
    
    Returns:
        200: Updated expense object
        400: Validation error or no fields to update
        404: Expense or category not found
    """
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
            # Check if expense exists
            cursor.execute(
                "SELECT id FROM expenses WHERE id = %s",
                (expense_id,)
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
                
                # Verify category exists and is active
                cursor.execute(
                    "SELECT id FROM categories WHERE id = %s AND is_active = TRUE",
                    (category_id,)
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
            
            # Execute update (parameterized query for SQL injection safety)
            query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            db.commit()
            
            # Fetch the updated expense
            cursor.execute(
                EXPENSE_SELECT_QUERY + " WHERE e.id = %s",
                (expense_id,)
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
def delete_expense(expense_id):
    """
    DELETE /expenses/<uuid>
    Hard deletes an expense (non-recoverable).
    
    Returns:
        200: Success message
        400: Invalid UUID
        404: Expense not found
    """
    # Validate UUID format
    valid, error = validate_uuid(expense_id)
    if not valid:
        return error_response(f'Invalid expense ID: {error}', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if expense exists
            cursor.execute(
                "SELECT id FROM expenses WHERE id = %s",
                (expense_id,)
            )
            if not cursor.fetchone():
                return error_response('Expense not found', 404)
            
            cursor.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
            db.commit()
        
        return jsonify({'message': 'Expense deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
