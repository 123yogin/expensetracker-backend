"""
Budgets Blueprint - Handles budget-related API endpoints.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own budgets
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify, g

from database import get_db
from validators import (
    validate_uuid,
    validate_amount,
    format_amount,
    generate_uuid,
    validate_month,
    get_month_date_range
)
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id


budgets_bp = Blueprint('budgets', __name__, url_prefix='/budgets')


def format_budget(row):
    return {
        'id': str(row['id']),
        'category_id': str(row['category_id']),
        'category_name': row['category_name'],
        'amount': format_amount(row['amount']),
        'created_at': str(row['created_at']) if row['created_at'] else None,
        'updated_at': str(row['updated_at']) if row['updated_at'] else None
    }


@budgets_bp.route('', methods=['GET'])
@require_auth
def get_budgets():
    """
    GET /budgets
    List all budgets for the authenticated user with category info.
    """
    user_id = get_current_user_id()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT b.id, b.category_id, b.amount, b.created_at, b.updated_at, c.name as category_name
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                WHERE b.user_id = %s
                ORDER BY c.name
            """, (user_id,))
            budgets = cursor.fetchall()
        return jsonify([format_budget(row) for row in budgets]), 200
    except Exception as e:
        return handle_db_error(e)


@budgets_bp.route('', methods=['POST'])
@require_auth
def save_budget():
    """
    POST /budgets
    Create or update a budget for a category (Upsert) for the authenticated user.
    
    Request body: {
        "category_id": "uuid",
        "amount": "123.45"
    }
    """
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
        
    category_id = data.get('category_id')
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response(f'Invalid category_id: {error}', 400)
        
    validated_amount, error = validate_amount(data.get('amount'))
    if error:
        return error_response(error, 400)
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists AND belongs to user
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Category not found', 404)
            
            # Upsert: Check existing budget for this user's category
            cursor.execute(
                "SELECT id FROM budgets WHERE category_id = %s AND user_id = %s",
                (category_id, user_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing budget
                budget_id = existing['id']
                cursor.execute(
                    "UPDATE budgets SET amount = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
                    (str(validated_amount), budget_id, user_id)
                )
            else:
                # Insert new budget with user_id
                budget_id = generate_uuid()
                cursor.execute(
                    "INSERT INTO budgets (id, category_id, amount, user_id) VALUES (%s, %s, %s, %s)",
                    (budget_id, category_id, str(validated_amount), user_id)
                )
            
            db.commit()
            
            # Fetch updated budget
            cursor.execute("""
                SELECT b.id, b.category_id, b.amount, b.created_at, b.updated_at, c.name as category_name
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                WHERE b.id = %s AND b.user_id = %s
            """, (budget_id, user_id))
            budget = cursor.fetchone()
            
        return jsonify(format_budget(budget)), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@budgets_bp.route('/<budget_id>', methods=['DELETE'])
@require_auth
def delete_budget(budget_id):
    """
    DELETE /budgets/<uuid>
    Delete a budget (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(budget_id)
    if not valid:
        return error_response(f'Invalid budget ID: {error}', 400)
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Delete with ownership enforcement
            cursor.execute(
                "DELETE FROM budgets WHERE id = %s AND user_id = %s",
                (budget_id, user_id)
            )
            if cursor.rowcount == 0:
                return error_response('Budget not found', 404)
            db.commit()
            
        return jsonify({'message': 'Budget deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@budgets_bp.route('/status', methods=['GET'])
@require_auth
def get_budget_status():
    """
    GET /budgets/status?month=YYYY-MM
    Get budget vs aggregate actual expenses for specific month (user's data only).
    """
    user_id = get_current_user_id()
    
    month = request.args.get('month')
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
        
    start_date, end_date = get_month_date_range(month)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get all user's active categories with their budgets
            cursor.execute("""
                SELECT c.id as category_id, c.name as category_name, b.id as budget_id, b.amount as budget_amount
                FROM categories c
                LEFT JOIN budgets b ON c.id = b.category_id AND b.user_id = %s
                WHERE c.is_active = TRUE AND c.user_id = %s
                ORDER BY c.name
            """, (user_id, user_id))
            budgets = cursor.fetchall()
            
            # Get user's actual spending for the month grouped by category
            cursor.execute("""
                SELECT category_id, COALESCE(SUM(amount - split_amount), 0) as spent_amount
                FROM expenses
                WHERE date >= %s AND date <= %s AND user_id = %s
                GROUP BY category_id
            """, (start_date, end_date, user_id))
            spending = {str(row['category_id']): row['spent_amount'] for row in cursor.fetchall()}
            
            results = []
            for b in budgets:
                cat_id_str = str(b['category_id'])
                budget_amount = Decimal(str(b['budget_amount'])) if b['budget_amount'] is not None else Decimal('0')
                spent_amount = Decimal(str(spending.get(cat_id_str, 0)))
                
                if budget_amount > 0:
                    percentage = (spent_amount / budget_amount * 100)
                else:
                    percentage = Decimal('0')
                
                results.append({
                    'budget_id': str(b['budget_id']) if b['budget_id'] else None,
                    'category_id': cat_id_str,
                    'category_name': b['category_name'],
                    'budget_amount': format_amount(budget_amount),
                    'spent_amount': format_amount(spent_amount),
                    'remaining_amount': format_amount(budget_amount - spent_amount),
                    'percentage': round(float(percentage), 1),
                    'has_budget': b['budget_id'] is not None
                })
                
            results.sort(key=lambda x: x['percentage'], reverse=True)
            
        return jsonify(results), 200
        
    except Exception as e:
        return handle_db_error(e)
