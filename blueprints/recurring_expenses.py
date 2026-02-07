"""
Recurring Expenses Blueprint
Handles management of recurring bills and expenses.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own recurring expenses
"""

from flask import Blueprint, request, jsonify, g
from datetime import date, timedelta
import psycopg2

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

recurring_bp = Blueprint('recurring', __name__, url_prefix='/recurring')

VALID_FREQUENCIES = ['daily', 'weekly', 'monthly', 'yearly']

def format_recurring(row):
    """Format recurring expense row for JSON response."""
    return {
        'id': str(row['id']),
        'title': row['title'],
        'amount': format_amount(row['amount']),
        'category_id': str(row['category_id']) if row['category_id'] else None,
        'category_name': row['category_name'],
        'frequency': row['frequency'],
        'next_date': str(row['next_date']),
        'note': row['note'],
        'is_active': bool(row['is_active']),
        'created_at': str(row['created_at']) if row['created_at'] else None,
        'updated_at': str(row['updated_at']) if row['updated_at'] else None
    }

@recurring_bp.route('', methods=['GET'])
@require_auth
def get_recurring_expenses():
    """
    GET /recurring
    List all recurring expenses for the authenticated user (active first, then by next_date).
    """
    user_id = get_current_user_id()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.id, r.title, r.amount, r.category_id, r.frequency, 
                    r.next_date, r.note, r.is_active, r.created_at, r.updated_at,
                    c.name as category_name
                FROM recurring_expenses r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.user_id = %s
                ORDER BY r.is_active DESC, r.next_date ASC
            """, (user_id,))
            items = cursor.fetchall()
            
        return jsonify([format_recurring(item) for item in items]), 200
    except Exception as e:
        return handle_db_error(e)

@recurring_bp.route('/upcoming', methods=['GET'])
@require_auth
def get_upcoming_bills():
    """
    GET /recurring/upcoming
    Get user's bills due in the next 30 days.
    """
    user_id = get_current_user_id()
    
    days = request.args.get('days', 30, type=int)
    today = date.today()
    limit_date = today + timedelta(days=days)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.id, r.title, r.amount, r.category_id, r.frequency, 
                    r.next_date, r.note, r.is_active, r.created_at, r.updated_at,
                    c.name as category_name
                FROM recurring_expenses r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.is_active = TRUE 
                AND r.next_date >= %s 
                AND r.next_date <= %s
                AND r.user_id = %s
                ORDER BY r.next_date ASC
            """, (today, limit_date, user_id))
            items = cursor.fetchall()
            
        return jsonify([format_recurring(item) for item in items]), 200
    except Exception as e:
        return handle_db_error(e)

@recurring_bp.route('', methods=['POST'])
@require_auth
def create_recurring():
    """
    POST /recurring
    Create a new recurring expense for the authenticated user.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    if not data:
        return error_response('Request body is required', 400)
    
    # Validation
    title = data.get('title')
    if not title or not title.strip():
        return error_response('Title is required', 400)
    
    validated_amount, error = validate_amount(data.get('amount'))
    if error:
        return error_response(error, 400)
    
    category_id = data.get('category_id')
    if category_id:
        valid, error = validate_uuid(category_id)
        if not valid:
            return error_response(f'Invalid category_id: {error}', 400)
    
    frequency = data.get('frequency')
    if frequency not in VALID_FREQUENCIES:
        return error_response(f'Invalid frequency. Must be one of {VALID_FREQUENCIES}', 400)
    
    # Start date / Next date
    next_date_str = data.get('next_date')
    valid, error = validate_date(next_date_str, reject_future=False)
    if not valid:
        return error_response(f'Invalid next_date: {error}', 400)
    
    note = data.get('note', '')
    
    new_id = generate_uuid()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check category if provided AND verify ownership
            if category_id:
                cursor.execute(
                    "SELECT id FROM categories WHERE id = %s AND user_id = %s",
                    (category_id, user_id)
                )
                if not cursor.fetchone():
                    return error_response('Category not found', 404)
            
            # Insert with user_id
            cursor.execute("""
                INSERT INTO recurring_expenses 
                (id, title, amount, category_id, frequency, next_date, note, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (new_id, title.strip(), str(validated_amount), category_id, frequency, next_date_str, note, user_id))
            
            db.commit()
            
            # Fetch created item
            cursor.execute("""
                SELECT 
                    r.id, r.title, r.amount, r.category_id, r.frequency, 
                    r.next_date, r.note, r.is_active, r.created_at, r.updated_at,
                    c.name as category_name
                FROM recurring_expenses r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.id = %s AND r.user_id = %s
            """, (new_id, user_id))
            item = cursor.fetchone()
            
        return jsonify(format_recurring(item)), 201
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)

@recurring_bp.route('/<item_id>', methods=['PUT'])
@require_auth
def update_recurring(item_id):
    """
    PUT /recurring/<item_id>
    Update a recurring expense (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(item_id)
    if not valid:
        return error_response(error, 400)
    
    data = request.get_json()
    if not data:
        return error_response('Request body is required', 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check existence AND ownership
            cursor.execute(
                "SELECT id FROM recurring_expenses WHERE id = %s AND user_id = %s",
                (item_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Recurring expense not found', 404)
            
            updates = []
            params = []
            
            if 'title' in data:
                title = data['title'].strip()
                if not title:
                    return error_response('Title cannot be empty', 400)
                updates.append("title = %s")
                params.append(title)
            
            if 'amount' in data:
                validated_amount, error = validate_amount(data['amount'])
                if error:
                    return error_response(error, 400)
                updates.append("amount = %s")
                params.append(str(validated_amount))
            
            if 'category_id' in data:
                cat_id = data['category_id']
                if cat_id:
                    valid, error = validate_uuid(cat_id)
                    if not valid:
                        return error_response(f'Invalid category_id: {error}', 400)
                    # Verify category ownership
                    cursor.execute(
                        "SELECT id FROM categories WHERE id = %s AND user_id = %s",
                        (cat_id, user_id)
                    )
                    if not cursor.fetchone():
                        return error_response('Category not found', 404)
                updates.append("category_id = %s")
                params.append(cat_id)
            
            if 'frequency' in data:
                if data['frequency'] not in VALID_FREQUENCIES:
                    return error_response(f'Invalid frequency', 400)
                updates.append("frequency = %s")
                params.append(data['frequency'])
                
            if 'next_date' in data:
                valid, error = validate_date(data['next_date'], reject_future=False)
                if not valid:
                    return error_response(f'Invalid next_date: {error}', 400)
                updates.append("next_date = %s")
                params.append(data['next_date'])
            
            if 'note' in data:
                updates.append("note = %s")
                params.append(data['note'])
                
            if 'is_active' in data:
                if not isinstance(data['is_active'], bool):
                    return error_response('is_active must be a boolean', 400)
                updates.append("is_active = %s")
                params.append(data['is_active'])
            
            if not updates:
                return error_response('No fields to update', 400)
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(item_id)
            params.append(user_id)  # Enforce ownership
            
            query = f"UPDATE recurring_expenses SET {', '.join(updates)} WHERE id = %s AND user_id = %s"
            cursor.execute(query, params)
            db.commit()
            
            # Fetch updated
            cursor.execute("""
                SELECT 
                    r.id, r.title, r.amount, r.category_id, r.frequency, 
                    r.next_date, r.note, r.is_active, r.created_at, r.updated_at,
                    c.name as category_name
                FROM recurring_expenses r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.id = %s AND r.user_id = %s
            """, (item_id, user_id))
            item = cursor.fetchone()
            
        return jsonify(format_recurring(item)), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)

@recurring_bp.route('/<item_id>', methods=['DELETE'])
@require_auth
def delete_recurring(item_id):
    """
    DELETE /recurring/<item_id>
    Delete a recurring expense (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(item_id)
    if not valid:
        return error_response(error, 400)
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Delete with ownership enforcement
            cursor.execute(
                "DELETE FROM recurring_expenses WHERE id = %s AND user_id = %s",
                (item_id, user_id)
            )
            if cursor.rowcount == 0:
                return error_response('Recurring expense not found', 404)
            db.commit()
            
        return jsonify({'message': 'Recurring expense deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)
