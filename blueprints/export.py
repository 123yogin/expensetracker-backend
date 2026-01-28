"""
Export Blueprint - Handles data export functionality.

Features:
- CSV export with customizable date ranges and filters
- PDF report generation
- Export history tracking
- Batch export capabilities
"""

import csv
import io
import json
from datetime import datetime, date
from flask import Blueprint, request, jsonify, make_response

from database import get_db
from validators import validate_uuid, generate_uuid
from errors import handle_db_error, error_response

export_bp = Blueprint('export', __name__, url_prefix='/export')

def format_currency(amount):
    """Format amount as currency string."""
    if amount is None:
        return "0.00"
    return f"{float(amount):.2f}"

@export_bp.route('/csv', methods=['POST'])
def export_csv():
    """
    POST /export/csv
    Export expenses to CSV format.
    
    Body:
        start_date: string (optional, YYYY-MM-DD)
        end_date: string (optional, YYYY-MM-DD)
        category_id: UUID (optional)
        include_income: boolean (optional, default false)
        include_receipts: boolean (optional, default false)
    
    Returns:
        200: CSV file content
    """
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    category_id = data.get('category_id')
    include_income = data.get('include_income', False)
    include_receipts = data.get('include_receipts', False)
    
    if category_id and not validate_uuid(category_id):
        return error_response("Invalid category_id", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Build expenses query
            expenses_query = """
                SELECT e.id, e.date, e.amount, e.note, e.created_at,
                       e.is_split, e.split_amount, e.split_with,
                       e.created_via_voice, e.auto_categorized,
                       c.name as category_name,
                       rp.original_filename as receipt_filename
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                LEFT JOIN receipt_photos rp ON e.receipt_photo_id = rp.id
                WHERE 1=1
            """
            params = []
            
            if start_date:
                expenses_query += " AND e.date >= %s"
                params.append(start_date)
            
            if end_date:
                expenses_query += " AND e.date <= %s"
                params.append(end_date)
            
            if category_id:
                expenses_query += " AND e.category_id = %s"
                params.append(category_id)
            
            expenses_query += " ORDER BY e.date DESC, e.created_at DESC"
            
            cursor.execute(expenses_query, params)
            expenses = cursor.fetchall()
            
            # Get income if requested
            income_data = []
            if include_income:
                income_query = """
                    SELECT id, date, amount, source, description, created_at
                    FROM income
                    WHERE 1=1
                """
                income_params = []
                
                if start_date:
                    income_query += " AND date >= %s"
                    income_params.append(start_date)
                
                if end_date:
                    income_query += " AND date <= %s"
                    income_params.append(end_date)
                
                income_query += " ORDER BY date DESC, created_at DESC"
                
                cursor.execute(income_query, income_params)
                income_data = cursor.fetchall()
            
            # Create CSV content
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write expenses
            if expenses:
                # Header
                header = ['Type', 'Date', 'Amount', 'Category', 'Note', 'Created At']
                if include_receipts:
                    header.extend(['Receipt File', 'Voice Input', 'Auto Categorized'])
                if any(e['is_split'] for e in expenses):
                    header.extend(['Split Amount', 'Split With'])
                
                writer.writerow(header)
                
                # Data rows
                for expense in expenses:
                    row = [
                        'Expense',
                        str(expense['date']),
                        format_currency(expense['amount']),
                        expense['category_name'],
                        expense['note'] or '',
                        str(expense['created_at'])
                    ]
                    
                    if include_receipts:
                        row.extend([
                            expense['receipt_filename'] or '',
                            'Yes' if expense['created_via_voice'] else 'No',
                            'Yes' if expense['auto_categorized'] else 'No'
                        ])
                    
                    if any(e['is_split'] for e in expenses):
                        row.extend([
                            format_currency(expense['split_amount']) if expense['is_split'] else '',
                            expense['split_with'] or ''
                        ])
                    
                    writer.writerow(row)
            
            # Write income
            if income_data:
                if expenses:
                    writer.writerow([])  # Empty row separator
                
                # Income header
                writer.writerow(['Type', 'Date', 'Amount', 'Source', 'Description', 'Created At'])
                
                # Income data
                for income in income_data:
                    writer.writerow([
                        'Income',
                        str(income['date']),
                        format_currency(income['amount']),
                        income['source'],
                        income['description'] or '',
                        str(income['created_at'])
                    ])
            
            # Save export history
            export_id = generate_uuid()
            filename = f"expense_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            cursor.execute("""
                INSERT INTO export_history 
                (id, export_type, date_range_start, date_range_end, category_filter, filename, file_size)
                VALUES (%s, 'csv', %s, %s, %s, %s, %s)
            """, (export_id, start_date, end_date, category_id, filename, len(output.getvalue())))
            
            db.commit()
            
            # Create response
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
    except Exception as e:
        return handle_db_error(e, "Failed to export CSV")

@export_bp.route('/summary-csv', methods=['POST'])
def export_summary_csv():
    """
    POST /export/summary-csv
    Export category-wise summary to CSV.
    
    Body:
        start_date: string (optional, YYYY-MM-DD)
        end_date: string (optional, YYYY-MM-DD)
        group_by: string (optional, 'category' or 'month', default 'category')
    
    Returns:
        200: CSV file content
    """
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    group_by = data.get('group_by', 'category')
    
    if group_by not in ['category', 'month']:
        return error_response("group_by must be 'category' or 'month'", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            if group_by == 'category':
                query = """
                    SELECT c.name as category_name,
                           COUNT(e.id) as transaction_count,
                           SUM(e.amount) as total_amount,
                           AVG(e.amount) as avg_amount,
                           MIN(e.amount) as min_amount,
                           MAX(e.amount) as max_amount
                    FROM expenses e
                    JOIN categories c ON e.category_id = c.id
                    WHERE 1=1
                """
            else:  # month
                query = """
                    SELECT DATE_TRUNC('month', e.date) as month,
                           COUNT(e.id) as transaction_count,
                           SUM(e.amount) as total_amount,
                           AVG(e.amount) as avg_amount,
                           MIN(e.amount) as min_amount,
                           MAX(e.amount) as max_amount
                    FROM expenses e
                    WHERE 1=1
                """
            
            params = []
            
            if start_date:
                query += " AND e.date >= %s"
                params.append(start_date)
            
            if end_date:
                query += " AND e.date <= %s"
                params.append(end_date)
            
            if group_by == 'category':
                query += " GROUP BY c.name ORDER BY total_amount DESC"
            else:
                query += " GROUP BY DATE_TRUNC('month', e.date) ORDER BY month DESC"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            if group_by == 'category':
                writer.writerow(['Category', 'Transactions', 'Total Amount', 'Average Amount', 'Min Amount', 'Max Amount'])
                for row in results:
                    writer.writerow([
                        row['category_name'],
                        row['transaction_count'],
                        format_currency(row['total_amount']),
                        format_currency(row['avg_amount']),
                        format_currency(row['min_amount']),
                        format_currency(row['max_amount'])
                    ])
            else:
                writer.writerow(['Month', 'Transactions', 'Total Amount', 'Average Amount', 'Min Amount', 'Max Amount'])
                for row in results:
                    writer.writerow([
                        str(row['month'])[:7],  # YYYY-MM format
                        row['transaction_count'],
                        format_currency(row['total_amount']),
                        format_currency(row['avg_amount']),
                        format_currency(row['min_amount']),
                        format_currency(row['max_amount'])
                    ])
            
            # Save export history
            export_id = generate_uuid()
            filename = f"expense_summary_{group_by}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            cursor.execute("""
                INSERT INTO export_history 
                (id, export_type, date_range_start, date_range_end, filename, file_size)
                VALUES (%s, 'csv', %s, %s, %s, %s)
            """, (export_id, start_date, end_date, filename, len(output.getvalue())))
            
            db.commit()
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
    except Exception as e:
        return handle_db_error(e, "Failed to export summary CSV")
            
            cursor.execute(query, params)
            history = []
            
            for row in cursor.fetchall():
                history.append({
                    'id': str(row['id']),
                    'export_type': row['export_type'],
                    'date_range': {
                        'start': str(row['date_range_start']) if row['date_range_start'] else None,
                        'end': str(row['date_range_end']) if row['date_range_end'] else Nate_range_end,
                       eh.filename, eh.file_size, eh.created_at,
                       c.name as category_name
                FROM export_history eh
                LEFT JOIN categories c ON eh.category_filter = c.id
                WHERE 1=1
            """
            params = []
            
            if export_type:
                query += " AND eh.export_type = %s"
                params.append(export_type)
            
            query += " ORDER BY eh.created_at DESC LIMIT %s"
          export_type: string (optional, 'csv' or 'pdf')
    
    Returns:
        200: List of export records
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    export_type = request.args.get('export_type')
    
    if export_type and export_type not in ['csv', 'pdf']:
        return error_response("export_type must be 'csv' or 'pdf'", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT eh.id, eh.export_type, eh.date_range_start, eh.ds, %s, %s, %s)
            """, (export_id, start_date, end_date, filename, len(json.dumps(report_data))))
            
            db.commit()
            
            return jsonify(report_data)
            
    except Exception as e:
        return handle_db_error(e, "Failed to generate PDF report")

@export_bp.route('/history', methods=['GET'])
def get_export_history():
    """
    GET /export/history
    Get export history.
    
    Query Parameters:
        limit: integer (optional, default 20)
      : txn['note'] or ''
                    }
                    for txn in recent_transactions
                ]
            }
            
            # Save export history
            export_id = generate_uuid()
            filename = f"expense_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            cursor.execute("""
                INSERT INTO export_history 
                (id, export_type, date_range_start, date_range_end, filename, file_size)
                VALUES (%s, 'pdf', %   'total_amount': format_currency(trend['total_amount']),
                        'transaction_count': trend['transaction_count']
                    }
                    for trend in monthly_trend
                ] if include_charts else [],
                'recent_transactions': [
                    {
                        'date': str(txn['date']),
                        'amount': format_currency(txn['amount']),
                        'category': txn['category_name'],
                        'note'               'name': cat['category_name'],
                        'transaction_count': cat['transaction_count'],
                        'total_amount': format_currency(cat['total_amount']),
                        'percentage': float(cat['percentage']) if cat['percentage'] else 0
                    }
                    for cat in categories
                ],
                'monthly_trend': [
                    {
                        'month': str(trend['month'])[:7],  # YYYY-MM
                      summary['total_transactions'],
                    'total_amount': format_currency(summary['total_amount']),
                    'average_amount': format_currency(summary['avg_amount']),
                    'date_range': {
                        'first': str(summary['first_date']) if summary['first_date'] else None,
                        'last': str(summary['last_date']) if summary['last_date'] else None
                    }
                },
                'categories': [
                    {
         t_query += " ORDER BY e.date DESC, e.created_at DESC LIMIT 20"
            
            cursor.execute(recent_query, recent_params)
            recent_transactions = cursor.fetchall()
            
            # Prepare report data
            report_data = {
                'generated_at': datetime.now().isoformat(),
                'date_range': {
                    'start': start_date,
                    'end': end_date
                },
                'summary': {
                    'total_transactions':.amount, e.note, c.name as category_name
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            recent_params = []
            
            if start_date:
                recent_query += " AND e.date >= %s"
                recent_params.append(start_date)
            
            if end_date:
                recent_query += " AND e.date <= %s"
                recent_params.append(end_date)
            
            recenams.append(start_date)
                
                if end_date:
                    trend_query += " AND date <= %s"
                    trend_params.append(end_date)
                
                trend_query += " GROUP BY DATE_TRUNC('month', date) ORDER BY month"
                
                cursor.execute(trend_query, trend_params)
                monthly_trend = cursor.fetchall()
            
            # Get recent transactions
            recent_query = """
                SELECT e.date, e       monthly_trend = []
            if include_charts:
                trend_query = """
                    SELECT DATE_TRUNC('month', date) as month,
                           SUM(amount) as total_amount,
                           COUNT(id) as transaction_count
                    FROM expenses
                    WHERE 1=1
                """
                trend_params = []
                
                if start_date:
                    trend_query += " AND date >= %s"
                    trend_par         category_query += " AND e.date >= %s"
                category_params.append(start_date)
            
            if end_date:
                category_query += " AND e.date <= %s"
                category_params.append(end_date)
            
            category_query += " GROUP BY c.name ORDER BY total_amount DESC"
            
            cursor.execute(category_query, category_params)
            categories = cursor.fetchall()
            
            # Get monthly trend (if include_charts)
      []
            if start_date:
                category_query += " AND date >= %s"
                category_params.append(start_date)
            
            if end_date:
                category_query += " AND date <= %s"
                category_params.append(end_date)
            
            category_query += """)), 2) as percentage
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            
            if start_date:
       nd(end_date)
            
            cursor.execute(summary_query, params)
            summary = cursor.fetchone()
            
            # Get category breakdown
            category_query = """
                SELECT c.name as category_name,
                       COUNT(e.id) as transaction_count,
                       SUM(e.amount) as total_amount,
                       ROUND((SUM(e.amount) * 100.0 / (SELECT SUM(amount) FROM expenses WHERE 1=1
            """
            
            category_params =  SUM(amount) as total_amount,
                       AVG(amount) as avg_amount,
                       MIN(date) as first_date,
                       MAX(date) as last_date
                FROM expenses
                WHERE 1=1
            """
            params = []
            
            if start_date:
                summary_query += " AND date >= %s"
                params.append(start_date)
            
            if end_date:
                summary_query += " AND date <= %s"
                params.appe YYYY-MM-DD)
        include_charts: boolean (optional, default true)
    
    Returns:
        200: Report data for PDF generation
    """
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    include_charts = data.get('include_charts', True)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get summary statistics
            summary_query = """
                SELECT COUNT(id) as total_transactions,
                     rs['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
    except Exception as e:
        return handle_db_error(e, "Failed to export summary CSV")

@export_bp.route('/pdf-report', methods=['POST'])
def export_pdf_report():
    """
    POST /export/pdf-report
    Generate PDF report (simplified version - returns JSON data for frontend PDF generation).
    
    Body:
        start_date: string (optional, YYYY-MM-DD)
        end_date: string (optional,_%H%M%S')}.csv"
            
            cursor.execute("""
                INSERT INTO export_history 
                (id, export_type, date_range_start, date_range_end, filename, file_size)
                VALUES (%s, 'csv', %s, %s, %s, %s)
            """, (export_id, start_date, end_date, filename, len(output.getvalue())))
            
            db.commit()
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headeth'])[:7],  # YYYY-MM format
                        row['transaction_count'],
                        format_currency(row['total_amount']),
                        format_currency(row['avg_amount']),
                        format_currency(row['min_amount']),
                        format_currency(row['max_amount'])
                    ])
            
            # Save export history
            export_id = generate_uuid()
            filename = f"expense_summary_{group_by}_{datetime.now().strftime('%Y%m%d
                        format_currency(row['total_amount']),
                        format_currency(row['avg_amount']),
                        format_currency(row['min_amount']),
                        format_currency(row['max_amount'])
                    ])
            else:
                writer.writerow(['Month', 'Transactions', 'Total Amount', 'Average Amount', 'Min Amount', 'Max Amount'])
                for row in results:
                    writer.writerow([
                        str(row['monute(query, params)
            results = cursor.fetchall()
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            if group_by == 'category':
                writer.writerow(['Category', 'Transactions', 'Total Amount', 'Average Amount', 'Min Amount', 'Max Amount'])
                for row in results:
                    writer.writerow([
                        row['category_name'],
                        row['transaction_count'],

@export_bp.route('/pdf-report', methods=['POST'])
def export_pdf_report():
    """
    POST /export/pdf-report
    Generate PDF report (simplified version - returns JSON data for frontend PDF generation).
    
    Body:
        start_date: string (optional, YYYY-MM-DD)
        end_date: string (optional, YYYY-MM-DD)
        include_charts: boolean (optional, default true)
    
    Returns:
        200: Report data for PDF generation
    """
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    include_charts = data.get('include_charts', True)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get summary statistics
            summary_query = """
                SELECT COUNT(id) as total_transactions,
                       SUM(amount) as total_amount,
                       AVG(amount) as avg_amount,
                       MIN(date) as first_date,
                       MAX(date) as last_date
                FROM expenses
                WHERE 1=1
            """
            params = []
            
            if start_date:
                summary_query += " AND date >= %s"
                params.append(start_date)
            
            if end_date:
                summary_query += " AND date <= %s"
                params.append(end_date)
            
            cursor.execute(summary_query, params)
            summary = cursor.fetchone()
            
            # Get category breakdown
            category_query = """
                SELECT c.name as category_name,
                       COUNT(e.id) as transaction_count,
                       SUM(e.amount) as total_amount,
                       ROUND((SUM(e.amount) * 100.0 / (SELECT SUM(amount) FROM expenses WHERE 1=1
            """
            
            category_params = []
            if start_date:
                category_query += " AND date >= %s"
                category_params.append(start_date)
            
            if end_date:
                category_query += " AND date <= %s"
                category_params.append(end_date)
            
            category_query += ")), 2) as percentage FROM expenses e JOIN categories c ON e.category_id = c.id WHERE 1=1"
            
            if start_date:
                category_query += " AND e.date >= %s"
                category_params.append(start_date)
            
            if end_date:
                category_query += " AND e.date <= %s"
                category_params.append(end_date)
            
            category_query += " GROUP BY c.name ORDER BY total_amount DESC"
            
            cursor.execute(category_query, category_params)
            categories = cursor.fetchall()
            
            # Get monthly trend (if include_charts)
            monthly_trend = []
            if include_charts:
                trend_query = """
                    SELECT DATE_TRUNC('month', date) as month,
                           SUM(amount) as total_amount,
                           COUNT(id) as transaction_count
                    FROM expenses
                    WHERE 1=1
                """
                trend_params = []
                
                if start_date:
                    trend_query += " AND date >= %s"
                    trend_params.append(start_date)
                
                if end_date:
                    trend_query += " AND date <= %s"
                    trend_params.append(end_date)
                
                trend_query += " GROUP BY DATE_TRUNC('month', date) ORDER BY month"
                
                cursor.execute(trend_query, trend_params)
                monthly_trend = cursor.fetchall()
            
            # Get recent transactions
            recent_query = """
                SELECT e.date, e.amount, e.note, c.name as category_name
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            recent_params = []
            
            if start_date:
                recent_query += " AND e.date >= %s"
                recent_params.append(start_date)
            
            if end_date:
                recent_query += " AND e.date <= %s"
                recent_params.append(end_date)
            
            recent_query += " ORDER BY e.date DESC, e.created_at DESC LIMIT 20"
            
            cursor.execute(recent_query, recent_params)
            recent_transactions = cursor.fetchall()
            
            # Prepare report data
            report_data = {
                'generated_at': datetime.now().isoformat(),
                'date_range': {
                    'start': start_date,
                    'end': end_date
                },
                'summary': {
                    'total_transactions': summary['total_transactions'],
                    'total_amount': format_currency(summary['total_amount']),
                    'average_amount': format_currency(summary['avg_amount']),
                    'date_range': {
                        'first': str(summary['first_date']) if summary['first_date'] else None,
                        'last': str(summary['last_date']) if summary['last_date'] else None
                    }
                },
                'categories': [
                    {
                        'name': cat['category_name'],
                        'transaction_count': cat['transaction_count'],
                        'total_amount': format_currency(cat['total_amount']),
                        'percentage': float(cat['percentage']) if cat['percentage'] else 0
                    }
                    for cat in categories
                ],
                'monthly_trend': [
                    {
                        'month': str(trend['month'])[:7],  # YYYY-MM
                        'total_amount': format_currency(trend['total_amount']),
                        'transaction_count': trend['transaction_count']
                    }
                    for trend in monthly_trend
                ] if include_charts else [],
                'recent_transactions': [
                    {
                        'date': str(txn['date']),
                        'amount': format_currency(txn['amount']),
                        'category': txn['category_name'],
                        'note': txn['note'] or ''
                    }
                    for txn in recent_transactions
                ]
            }
            
            # Save export history
            export_id = generate_uuid()
            filename = f"expense_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            cursor.execute("""
                INSERT INTO export_history 
                (id, export_type, date_range_start, date_range_end, filename, file_size)
                VALUES (%s, 'pdf', %s, %s, %s, %s)
            """, (export_id, start_date, end_date, filename, len(json.dumps(report_data))))
            
            db.commit()
            
            return jsonify(report_data)
            
    except Exception as e:
        return handle_db_error(e, "Failed to generate PDF report")

@export_bp.route('/history', methods=['GET'])
def get_export_history():
    """
    GET /export/history
    Get export history.
    
    Query Parameters:
        limit: integer (optional, default 20)
        export_type: string (optional, 'csv' or 'pdf')
    
    Returns:
        200: List of export records
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    export_type = request.args.get('export_type')
    
    if export_type and export_type not in ['csv', 'pdf']:
        return error_response("export_type must be 'csv' or 'pdf'", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT eh.id, eh.export_type, eh.date_range_start, eh.date_range_end,
                       eh.filename, eh.file_size, eh.created_at,
                       c.name as category_name
                FROM export_history eh
                LEFT JOIN categories c ON eh.category_filter = c.id
                WHERE 1=1
            """
            params = []
            
            if export_type:
                query += " AND eh.export_type = %s"
                params.append(export_type)
            
            query += " ORDER BY eh.created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            history = []
            
            for row in cursor.fetchall():
                history.append({
                    'id': str(row['id']),
                    'export_type': row['export_type'],
                    'date_range': {
                        'start': str(row['date_range_start']) if row['date_range_start'] else None,
                        'end': str(row['date_range_end']) if row['date_range_end'] else None
                    },
                    'category_filter': row['category_name'],
                    'filename': row['filename'],
                    'file_size': row['file_size'],
                    'created_at': str(row['created_at'])
                })
            
            return jsonify(history)
            
    except Exception as e:
        return handle_db_error(e, "Failed to fetch export history")