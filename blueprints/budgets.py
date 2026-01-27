"""
Budgets Blueprint - Handles budget-related API endpoints.
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify

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
def get_budgets():
    """
    GET /budgets
    List all budgets with category info.
    """
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT b.id, b.category_id, b.amount, b.created_at, b.updated_at, c.name as category_name
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                ORDER BY c.name
            """)
            budgets = cursor.fetchall()
        return jsonify([format_budget(row) for row in budgets]), 200
    except Exception as e:
        return handle_db_error(e)


@budgets_bp.route('', methods=['POST'])
def save_budget():
    """
    POST /budgets
    Create or update a budget for a category (Upsert).
    
    Request body: {
        "category_id": "uuid",
        "amount": "123.45"
    }
    """
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
            # Check if category exists
            cursor.execute("SELECT id FROM categories WHERE id = %s", (category_id,))
            if not cursor.fetchone():
                return error_response('Category not found', 404)
            
            # Upsert logic (Insert or Update if exists)
            # Check existing budget
            cursor.execute("SELECT id FROM budgets WHERE category_id = %s", (category_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update
                budget_id = existing['id']
                cursor.execute(
                    "UPDATE budgets SET amount = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (str(validated_amount), budget_id)
                )
            else:
                # Insert
                budget_id = generate_uuid()
                cursor.execute(
                    "INSERT INTO budgets (id, category_id, amount) VALUES (%s, %s, %s)",
                    (budget_id, category_id, str(validated_amount))
                )
            
            db.commit()
            
            # Fetch updated budget
            cursor.execute("""
                SELECT b.id, b.category_id, b.amount, b.created_at, b.updated_at, c.name as category_name
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                WHERE b.id = %s
            """, (budget_id,))
            budget = cursor.fetchone()
            
        return jsonify(format_budget(budget)), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@budgets_bp.route('/<budget_id>', methods=['DELETE'])
def delete_budget(budget_id):
    """
    DELETE /budgets/<uuid>
    Delete a budget.
    """
    valid, error = validate_uuid(budget_id)
    if not valid:
        return error_response(f'Invalid budget ID: {error}', 400)
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM budgets WHERE id = %s", (budget_id,))
            if cursor.rowcount == 0:
                return error_response('Budget not found', 404)
            db.commit()
            
        return jsonify({'message': 'Budget deleted successfully'}), 200
        
    except Exception as e:
        db.rollback()
        return handle_db_error(e)


@budgets_bp.route('/status', methods=['GET'])
def get_budget_status():
    """
    GET /budgets/status?month=YYYY-MM
    Get budget vs aggregate actual expenses for specific month.
    """
    month = request.args.get('month')
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
        
    start_date, end_date = get_month_date_range(month)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get all active categories with their budgets (LEFT JOIN)
            cursor.execute("""
                SELECT c.id as category_id, c.name as category_name, b.id as budget_id, b.amount as budget_amount
                FROM categories c
                LEFT JOIN budgets b ON c.id = b.category_id
                WHERE c.is_active = TRUE
                ORDER BY c.name
            """)
            budgets = cursor.fetchall()
            
            # Get actual spending for the month grouped by category
            cursor.execute("""
                SELECT category_id, COALESCE(SUM(amount - split_amount), 0) as spent_amount
                FROM expenses
                WHERE date >= %s AND date <= %s
                GROUP BY category_id
            """, (start_date, end_date))
            # Use string keys for reliable lookup
            spending = {str(row['category_id']): row['spent_amount'] for row in cursor.fetchall()}
            
            results = []
            for b in budgets:
                cat_id_str = str(b['category_id'])
                budget_amount = Decimal(str(b['budget_amount'])) if b['budget_amount'] is not None else Decimal('0')
                spent_amount = Decimal(str(spending.get(cat_id_str, 0)))
                
                # Percentage is 0 if no budget, or >100 if spent > budget
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
                
            # Sort by percentage descending (highest usage first)
            results.sort(key=lambda x: x['percentage'], reverse=True)
            
        return jsonify(results), 200
        
    except Exception as e:
        return handle_db_error(e)
