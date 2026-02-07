"""
Income Blueprint - Handles all income-related API endpoints.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own income records
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


income_bp = Blueprint('income', __name__, url_prefix='/income')


def format_income(row) -> dict:
    """
    Format an income row for JSON response.
    """
    return {
        'id': str(row['id']),
        'date': str(row['date']) if row['date'] else None,
        'amount': format_amount(row['amount']),
        'source': row['source'],
        'description': row['description'],
        'created_at': str(row['created_at']) if row['created_at'] else None,
        'updated_at': str(row['updated_at']) if row['updated_at'] else None
    }


# SQL query for fetching income
INCOME_SELECT_QUERY = """
    SELECT id, date, amount, source, description, created_at, updated_at
    FROM income
"""


@income_bp.route('', methods=['GET'])
@require_auth
def get_income():
    """
    GET /income
    List income for the authenticated user with optional filters.
    
    Query parameters:
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional)
        source: String (optional)
    
    Returns:
        200: List of income objects (user's income only)
        400: Validation error
        401: Unauthorized
    """
    user_id = get_current_user_id()
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    source = request.args.get('source')
    
    # Build query with USER ISOLATION filter
    query = INCOME_SELECT_QUERY + " WHERE user_id = %s"
    params = [user_id]
    
    if start_date:
        valid, error = validate_date(start_date, reject_future=False)
        if not valid:
            return error_response(f'Invalid start_date: {error}', 400)
        query += " AND date >= %s"
        params.append(start_date)
    
    if end_date:
        valid, error = validate_date(end_date, reject_future=False)
        if not valid:
            return error_response(f'Invalid end_date: {error}', 400)
        query += " AND date <= %s"
        params.append(end_date)
    
    if source:
        query += " AND source = %s"
        params.append(source)
    
    # Order by date descending, then by creation time
    query += " ORDER BY date DESC, created_at DESC"
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(query, params)
            income_list = cursor.fetchall()
        return jsonify([format_income(row) for row in income_list]), 200
    except Exception as e:
        return handle_db_error(e)


@income_bp.route('', methods=['POST'])
@require_auth
def create_income():
    """
    POST /income
    Create a new income entry for the authenticated user.
    
    Request body: {
        "date": "YYYY-MM-DD",      (required, cannot be future)
        "amount": "123.45",         (required, positive, max 2 decimals)
        "source": "string",         (required)
        "description": "string"     (optional)
    }
    """
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    # Validate date
    date = data.get('date')
    valid, error = validate_date(date, reject_future=True)
    if not valid:
        return error_response(error, 400)
    
    # Validate amount
    validated_amount, error = validate_amount(data.get('amount'))
    if error:
        return error_response(error, 400)
    
    # Validate source
    source = data.get('source')
    if not source or not isinstance(source, str) or not source.strip():
        return error_response('Source is required', 400)
    source = source.strip()
    
    # Get and sanitize description
    description = data.get('description', '') or ''
    if not isinstance(description, str):
        return error_response('Description must be a string', 400)
    description = description.strip()
    
    if len(description) > 500:
        return error_response('Description must be 500 characters or less', 400)
    
    # Generate UUID
    income_id = generate_uuid()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Insert with user_id for isolation
            cursor.execute(
                """INSERT INTO income (id, date, amount, source, description, user_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (income_id, date, str(validated_amount), source, description, user_id)
            )
            db.commit()
            
            cursor.execute(
                INCOME_SELECT_QUERY + " WHERE id = %s AND user_id = %s",
                (income_id, user_id)
            )
            income = cursor.fetchone()
        
        return jsonify(format_income(income)), 201
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@income_bp.route('/<income_id>', methods=['PUT'])
@require_auth
def update_income(income_id):
    """
    PUT /income/<uuid>
    Update an existing income (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(income_id)
    if not valid:
        return error_response(f'Invalid income ID: {error}', 400)
    
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if income exists AND belongs to user
            cursor.execute(
                "SELECT id FROM income WHERE id = %s AND user_id = %s",
                (income_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Income not found', 404)
            
            # Build update query
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
            
            if 'source' in data:
                source = data['source']
                if not source or not isinstance(source, str) or not source.strip():
                    return error_response('Source cannot be empty', 400)
                updates.append("source = %s")
                params.append(source.strip())
            
            if 'description' in data:
                description = data['description'] or ''
                if not isinstance(description, str):
                    return error_response('Description must be a string', 400)
                description = description.strip()
                if len(description) > 500:
                    return error_response('Description must be 500 characters or less', 400)
                updates.append("description = %s")
                params.append(description)
            
            if not updates:
                return error_response('No fields to update', 400)
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(income_id)
            params.append(user_id)  # Enforce ownership
            
            # Update with ownership enforcement
            query = f"UPDATE income SET {', '.join(updates)} WHERE id = %s AND user_id = %s"
            cursor.execute(query, params)
            db.commit()
            
            cursor.execute(
                INCOME_SELECT_QUERY + " WHERE id = %s AND user_id = %s",
                (income_id, user_id)
            )
            income = cursor.fetchone()
        
        return jsonify(format_income(income)), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@income_bp.route('/<income_id>', methods=['DELETE'])
@require_auth
def delete_income(income_id):
    """
    DELETE /income/<uuid>
    Delete an income entry (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(income_id)
    if not valid:
        return error_response(f'Invalid income ID: {error}', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check ownership
            cursor.execute(
                "SELECT id FROM income WHERE id = %s AND user_id = %s",
                (income_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Income not found', 404)
            
            # Delete with ownership enforcement
            cursor.execute(
                "DELETE FROM income WHERE id = %s AND user_id = %s",
                (income_id, user_id)
            )
            db.commit()
        
        return jsonify({'message': 'Income deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
