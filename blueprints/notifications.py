from flask import Blueprint, jsonify
from database import get_db
from errors import handle_db_error
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/notifications/alerts', methods=['GET'])
def get_alerts():
    """Get active budget alerts"""
    try:
        current_month = datetime.now().strftime('%Y-%m')
        
        db = get_db()
        with db.cursor() as cursor:
            # 1. Check for new alerts (Budget vs Actual)
            cursor.execute("""
                WITH monthly_spending AS (
                    SELECT category_id, SUM(amount) as spent
                    FROM expenses 
                    WHERE to_char(date, 'YYYY-MM') = %s
                    GROUP BY category_id
                )
                SELECT 
                    c.id as category_id, 
                    c.name as category_name, 
                    b.amount as budget_limit,
                    COALESCE(ms.spent, 0) as spent
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                LEFT JOIN monthly_spending ms ON b.category_id = ms.category_id
            """, (current_month,))
            
            budgets = cursor.fetchall()
            
            alerts = []
            for b in budgets:
                spent = float(b['spent'])
                limit = float(b['budget_limit'])
                
                if limit > 0:
                    percentage = (spent / limit) * 100
                    
                    if percentage >= 100:
                        alerts.append({
                            'type': 'critical',
                            'message': f"Budget exceeded for {b['category_name']}! Used {int(percentage)}%",
                            'category_id': b['category_id']
                        })
                    elif percentage >= 80:
                        alerts.append({
                            'type': 'warning',
                            'message': f"Approaching limit for {b['category_name']}. Used {int(percentage)}%",
                            'category_id': b['category_id']
                        })
            
            # 2. Check for Low Balance / Cash Flow Warning
            cursor.execute("""
                SELECT 
                    (SELECT COALESCE(SUM(amount), 0) FROM income WHERE to_char(date, 'YYYY-MM') = %s) as total_income,
                    (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE to_char(date, 'YYYY-MM') = %s) as total_expense
            """, (current_month, current_month))
            cash_flow = cursor.fetchone()
            
            if cash_flow:
                income = float(cash_flow['total_income'])
                expenses = float(cash_flow['total_expense'])
                balance = income - expenses
                
                # Alert if spending > 90% of income (Living Paycheck to Paycheck warning)
                if income > 0 and expenses > (income * 0.9):
                     alerts.append({
                        'type': 'warning',
                        'message': f"High spending alert! You have used {int((expenses/income)*100)}% of your monthly income.",
                        'category_id': 'cash_flow'
                    })
                
                # Critical alert if expenses > income
                if expenses > income:
                    alerts.append({
                        'type': 'critical',
                        'message': f"Deficit Warning! You have spent {int(expenses - income)} more than your income this month.",
                        'category_id': 'deficit'
                    })

            return jsonify(alerts)
            
    except Exception as e:
        return handle_db_error(e, "Failed to check alerts")
