"""
Reports Blueprint - Handles all report-related API endpoints.

Production-hardened endpoints:
- Strict month format validation
- Aggregation done in SQL (not Python) for performance
- Flask g context for database connections
- Proper error handling without leaking stack traces
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify

from database import get_db
from validators import validate_month, format_amount, get_month_date_range
from errors import handle_db_error, error_response


reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/monthly-summary', methods=['GET'])
def monthly_summary():
    """
    GET /reports/monthly-summary?month=YYYY-MM
    Returns aggregate expense statistics for the month.
    
    All aggregation is performed in SQL for optimal performance.
    
    Query parameters:
        month: YYYY-MM format (required)
    
    Returns:
        200: Monthly summary object with totals and statistics
        400: Invalid month format
    """
    month = request.args.get('month')
    
    # Validate month format
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
    
    start_date, end_date = get_month_date_range(month)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Single SQL query for all aggregations (no N+1 queries)
            cursor.execute(
                """SELECT 
                       COUNT(*) as transaction_count,
                       COALESCE(SUM(amount), 0) as total_amount,
                       COALESCE(AVG(amount), 0) as average_amount,
                       COALESCE(MIN(amount), 0) as min_amount,
                       COALESCE(MAX(amount), 0) as max_amount
                   FROM expenses
                   WHERE date >= %s AND date <= %s""",
                (start_date, end_date)
            )
            row = cursor.fetchone()
        
        return jsonify({
            'month': month,
            'start_date': start_date,
            'end_date': end_date,
            'transaction_count': row['transaction_count'],
            'total_amount': format_amount(row['total_amount']),
            'average_amount': format_amount(row['average_amount']),
            'min_amount': format_amount(row['min_amount']),
            'max_amount': format_amount(row['max_amount'])
        }), 200
        
    except Exception as e:
        return handle_db_error(e)


@reports_bp.route('/category-breakdown', methods=['GET'])
def category_breakdown():
    """
    GET /reports/category-breakdown?month=YYYY-MM
    Returns expenses grouped by category for the month.
    
    Uses a single SQL query with LEFT JOIN and GROUP BY
    to avoid N+1 query problems. Percentages calculated in Python
    only after aggregation is complete.
    
    Query parameters:
        month: YYYY-MM format (required)
    
    Returns:
        200: Category breakdown with totals and percentages
        400: Invalid month format
    """
    month = request.args.get('month')
    
    # Validate month format
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
    
    start_date, end_date = get_month_date_range(month)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Single query to get total for percentage calculation
            cursor.execute(
                """SELECT COALESCE(SUM(amount), 0) as total
                   FROM expenses
                   WHERE date >= %s AND date <= %s""",
                (start_date, end_date)
            )
            total_row = cursor.fetchone()
            total_amount = Decimal(str(total_row['total'])) if total_row['total'] else Decimal('0')
            
            # Single query with LEFT JOIN and GROUP BY (aggregation in SQL)
            # This avoids N+1 queries - we get all categories with their totals at once
            cursor.execute(
                """SELECT 
                       c.id as category_id,
                       c.name as category_name,
                       COUNT(e.id) as transaction_count,
                       COALESCE(SUM(e.amount), 0) as total_amount
                   FROM categories c
                   LEFT JOIN expenses e ON c.id = e.category_id 
                       AND e.date >= %s AND e.date <= %s
                   WHERE c.is_active = TRUE
                   GROUP BY c.id, c.name
                   ORDER BY total_amount DESC""",
                (start_date, end_date)
            )
            categories = cursor.fetchall()
        
        # Build breakdown with percentages (minimal Python processing)
        breakdown = []
        for row in categories:
            cat_amount = Decimal(str(row['total_amount'])) if row['total_amount'] else Decimal('0')
            percentage = (cat_amount / total_amount * 100) if total_amount > 0 else Decimal('0')
            
            breakdown.append({
                'category_id': row['category_id'],
                'category_name': row['category_name'],
                'transaction_count': row['transaction_count'],
                'total_amount': format_amount(cat_amount),
                'percentage': format_amount(percentage)
            })
        
        return jsonify({
            'month': month,
            'start_date': start_date,
            'end_date': end_date,
            'total_amount': format_amount(total_amount),
            'categories': breakdown
        }), 200
        
    except Exception as e:
        return handle_db_error(e)


@reports_bp.route('/daily-trend', methods=['GET'])
def daily_trend():
    """
    GET /reports/daily-trend?month=YYYY-MM
    Returns daily expense totals for the month.
    
    Aggregation (COUNT, SUM) done in SQL with GROUP BY.
    Running total calculated in Python after fetching aggregated data.
    
    Query parameters:
        month: YYYY-MM format (required)
    
    Returns:
        200: Daily trend data with running totals
        400: Invalid month format
    """
    month = request.args.get('month')
    
    # Validate month format
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
    
    start_date, end_date = get_month_date_range(month)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Single SQL query with GROUP BY for aggregation (not looping in Python)
            cursor.execute(
                """SELECT 
                       date,
                       COUNT(*) as transaction_count,
                       SUM(amount) as total_amount
                   FROM expenses
                   WHERE date >= %s AND date <= %s
                   GROUP BY date
                   ORDER BY date ASC""",
                (start_date, end_date)
            )
            daily_data = cursor.fetchall()
        
        # Calculate running total (this must be done in order, so Python is appropriate)
        running_total = Decimal('0')
        trend = []
        
        for row in daily_data:
            day_amount = Decimal(str(row['total_amount']))
            running_total += day_amount
            
            trend.append({
                'date': str(row['date']) if row['date'] else None,
                'transaction_count': row['transaction_count'],
                'daily_total': format_amount(day_amount),
                'running_total': format_amount(running_total)
            })
        
        return jsonify({
            'month': month,
            'start_date': start_date,
            'end_date': end_date,
            'total_amount': format_amount(running_total),
            'days_with_expenses': len(trend),
            'daily_data': trend
        }), 200
        
    except Exception as e:
        return handle_db_error(e)
