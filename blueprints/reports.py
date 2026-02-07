"""
Reports Blueprint - Handles all report-related API endpoints.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user only sees reports for their own data
"""

from decimal import Decimal
from datetime import date, datetime, timedelta
from flask import Blueprint, request, jsonify, g

from database import get_db
from validators import validate_month, format_amount, get_month_date_range
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id


reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/monthly-summary', methods=['GET'])
@require_auth
def monthly_summary():
    """
    GET /reports/monthly-summary?month=YYYY-MM
    Returns aggregate expense statistics for the authenticated user's data.
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
            # User's expense aggregations
            cursor.execute(
                """SELECT 
                       COUNT(*) as transaction_count,
                       COALESCE(SUM(amount), 0) as total_amount,
                       COALESCE(SUM(split_amount), 0) as total_split,
                       COALESCE(AVG(amount), 0) as average_amount,
                       COALESCE(MIN(amount), 0) as min_amount,
                       COALESCE(MAX(amount), 0) as max_amount
                   FROM expenses
                   WHERE date >= %s AND date <= %s AND user_id = %s""",
                (start_date, end_date, user_id)
            )
            expense_row = cursor.fetchone()

            # User's income stats
            cursor.execute(
                """SELECT 
                       COUNT(*) as transaction_count,
                       COALESCE(SUM(amount), 0) as total_amount
                   FROM income
                   WHERE date >= %s AND date <= %s AND user_id = %s""",
                (start_date, end_date, user_id)
            )
            income_row = cursor.fetchone()
            
            total_expense = Decimal(str(expense_row['total_amount'])) if expense_row['total_amount'] else Decimal('0')
            total_split = Decimal(str(expense_row['total_split'])) if expense_row['total_split'] else Decimal('0')
            total_income = Decimal(str(income_row['total_amount'])) if income_row['total_amount'] else Decimal('0')
            
            net_spending = total_expense - total_split
            net_balance = total_income - net_spending
            savings_rate = (net_balance / total_income * 100) if total_income > 0 else Decimal('0')

        return jsonify({
            'month': month,
            'start_date': start_date,
            'end_date': end_date,
            'expense_count': expense_row['transaction_count'],
            'total_expense': format_amount(total_expense),
            'total_owed': format_amount(total_split),
            'net_spending': format_amount(net_spending),
            'average_expense': format_amount(expense_row['average_amount']),
            'min_expense': format_amount(expense_row['min_amount']),
            'max_expense': format_amount(expense_row['max_amount']),
            'income_count': income_row['transaction_count'],
            'total_income': format_amount(total_income),
            'net_balance': format_amount(net_balance),
            'savings_rate': format_amount(savings_rate)
        }), 200
        
    except Exception as e:
        return handle_db_error(e)


@reports_bp.route('/category-breakdown', methods=['GET'])
@require_auth
def category_breakdown():
    """
    GET /reports/category-breakdown?month=YYYY-MM
    Returns expenses grouped by category for the authenticated user.
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
            # Total for user's expenses
            cursor.execute(
                """SELECT COALESCE(SUM(amount), 0) as total
                   FROM expenses
                   WHERE date >= %s AND date <= %s AND user_id = %s""",
                (start_date, end_date, user_id)
            )
            total_row = cursor.fetchone()
            total_amount = Decimal(str(total_row['total'])) if total_row['total'] else Decimal('0')
            
            # Category breakdown for user
            cursor.execute(
                """SELECT 
                       c.id as category_id,
                       c.name as category_name,
                       COUNT(e.id) as transaction_count,
                       COALESCE(SUM(e.amount), 0) as total_amount
                   FROM categories c
                   LEFT JOIN expenses e ON c.id = e.category_id 
                       AND e.date >= %s AND e.date <= %s AND e.user_id = %s
                   WHERE c.is_active = TRUE AND c.user_id = %s
                   GROUP BY c.id, c.name
                   ORDER BY total_amount DESC""",
                (start_date, end_date, user_id, user_id)
            )
            categories = cursor.fetchall()
        
        breakdown = []
        for row in categories:
            cat_amount = Decimal(str(row['total_amount'])) if row['total_amount'] else Decimal('0')
            percentage = (cat_amount / total_amount * 100) if total_amount > 0 else Decimal('0')
            
            breakdown.append({
                'category_id': str(row['category_id']),
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
@require_auth
def daily_trend():
    """
    GET /reports/daily-trend?month=YYYY-MM
    Returns daily expense totals for the authenticated user.
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
            cursor.execute(
                """SELECT 
                       date,
                       COUNT(*) as transaction_count,
                       SUM(amount) as total_amount
                   FROM expenses
                   WHERE date >= %s AND date <= %s AND user_id = %s
                   GROUP BY date
                   ORDER BY date ASC""",
                (start_date, end_date, user_id)
            )
            daily_data = cursor.fetchall()
        
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


@reports_bp.route('/insights', methods=['GET'])
@require_auth
def get_insights():
    """
    GET /reports/insights?month=YYYY-MM
    Returns projection and comparison insights for the authenticated user.
    """
    user_id = get_current_user_id()
    month = request.args.get('month')
    
    valid, error = validate_month(month)
    if not valid:
        return error_response(error, 400)
    
    start_date, end_date = get_month_date_range(month)
    today = date.today()
    
    month_dt = datetime.strptime(month, '%Y-%m')
    import calendar
    days_in_month = calendar.monthrange(month_dt.year, month_dt.month)[1]
    
    if today.year == month_dt.year and today.month == month_dt.month:
        days_passed = today.day
    elif today > date(month_dt.year, month_dt.month, days_in_month):
        days_passed = days_in_month
    else:
        days_passed = 1
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            # User's current month total
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= %s AND date <= %s AND user_id = %s",
                (start_date, end_date, user_id)
            )
            current_total = Decimal(str(cursor.fetchone()['total']))
            
            # User's previous month total
            prev_month_dt = month_dt.replace(day=1) - timedelta(days=1)
            prev_month = prev_month_dt.strftime('%Y-%m')
            ps, pe = get_month_date_range(prev_month)
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= %s AND date <= %s AND user_id = %s",
                (ps, pe, user_id)
            )
            prev_total = Decimal(str(cursor.fetchone()['total']))
            
            # Category comparison for user
            cursor.execute("""
                SELECT 
                    c.name,
                    COALESCE(SUM(CASE WHEN e.date >= %s AND e.date <= %s THEN e.amount ELSE 0 END), 0) as current_amount,
                    COALESCE(SUM(CASE WHEN e.date >= %s AND e.date <= %s THEN e.amount ELSE 0 END), 0) as prev_amount
                FROM categories c
                LEFT JOIN expenses e ON c.id = e.category_id AND e.user_id = %s
                WHERE c.is_active = TRUE AND c.user_id = %s
                GROUP BY c.name
                HAVING SUM(CASE WHEN e.date >= %s AND e.date <= %s THEN e.amount ELSE 0 END) > 0 
                   OR SUM(CASE WHEN e.date >= %s AND e.date <= %s THEN e.amount ELSE 0 END) > 0
            """, (start_date, end_date, ps, pe, user_id, user_id, start_date, end_date, ps, pe))
            cat_comparison = cursor.fetchall()
        
        daily_avg = current_total / Decimal(str(days_passed)) if days_passed > 0 else 0
        projected = daily_avg * Decimal(str(days_in_month))
        
        diff_total = current_total - prev_total
        diff_pct = (diff_total / prev_total * 100) if prev_total > 0 else 0
        
        comparisons = []
        for row in cat_comparison:
            cur = Decimal(str(row['current_amount']))
            prv = Decimal(str(row['prev_amount']))
            diff = cur - prv
            pct = (diff / prv * 100) if prv > 0 else 0
            comparisons.append({
                'name': row['name'],
                'current': format_amount(cur),
                'previous': format_amount(prv),
                'diff': format_amount(diff),
                'percent': round(float(pct), 1)
            })

        return jsonify({
            'daily_average': format_amount(daily_avg),
            'projected_total': format_amount(projected),
            'days_passed': days_passed,
            'days_in_month': days_in_month,
            'prev_month_total': format_amount(prev_total),
            'total_difference_percent': round(float(diff_pct), 1),
            'category_comparisons': comparisons
        }), 200
        
    except Exception as e:
        return handle_db_error(e)


@reports_bp.route('/trends', methods=['GET'])
@require_auth
def get_trends():
    """
    GET /reports/trends?months=6
    Returns monthly savings trend for the authenticated user.
    """
    user_id = get_current_user_id()
    count = request.args.get('months', 6, type=int)
    
    results = []
    current_date = date.today().replace(day=1)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            for i in range(count):
                month_str = current_date.strftime('%Y-%m')
                start_date, end_date = get_month_date_range(month_str)
                
                cursor.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= %s AND date <= %s AND user_id = %s",
                    (start_date, end_date, user_id)
                )
                exp = Decimal(str(cursor.fetchone()['total']))
                
                cursor.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total FROM income WHERE date >= %s AND date <= %s AND user_id = %s",
                    (start_date, end_date, user_id)
                )
                inc = Decimal(str(cursor.fetchone()['total']))
                
                savings = inc - exp
                rate = (savings / inc * 100) if inc > 0 else 0
                
                results.append({
                    'month': month_str,
                    'income': format_amount(inc),
                    'expenses': format_amount(exp),
                    'savings': format_amount(savings),
                    'savings_rate': round(float(rate), 1)
                })
                
                if current_date.month == 1:
                    current_date = current_date.replace(year=current_date.year - 1, month=12)
                else:
                    current_date = current_date.replace(month=current_date.month - 1)
        
        return jsonify(list(reversed(results))), 200
    except Exception as e:
        return handle_db_error(e)
