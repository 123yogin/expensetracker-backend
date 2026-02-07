"""
Smart Features Blueprint - Handles receipt photos, voice input, smart categorization, and export functionality.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own data and preferences
"""

import os
import json
import uuid
import csv
import io
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file, g
import psycopg2
from psycopg2.extras import RealDictCursor

from database import get_db
from validators import validate_uuid, generate_uuid, format_amount
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id

smart_bp = Blueprint('smart', __name__, url_prefix='/smart')

# Configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads/receipts')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_expense_with_receipt(row) -> dict:
    """Format expense row with receipt information."""
    return {
        'id': str(row['id']),
        'date': str(row['date']),
        'amount': format_amount(row['amount']),
        'category_id': str(row['category_id']),
        'category_name': row.get('category_name', ''),
        'note': row['note'] or '',
        'input_method': row.get('input_method', 'manual'),
        'voice_confidence': float(row['voice_confidence']) if row.get('voice_confidence') else None,
        'receipt_photo': {
            'filename': row.get('receipt_photo_filename'),
            'path': row.get('receipt_photo_path'),
            'size': row.get('receipt_photo_size')
        } if row.get('receipt_photo_path') else None,
        'created_at': str(row['created_at']) if row['created_at'] else None
    }

# ============================================================
# Receipt Photo Management
# ============================================================

@smart_bp.route('/receipt/upload', methods=['POST'])
@require_auth
def upload_receipt():
    """
    POST /smart/receipt/upload
    Upload a receipt photo for the authenticated user.
    """
    user_id = get_current_user_id()
    
    if 'file' not in request.files:
        return error_response("No file provided", 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response("No file selected", 400)
    
    if not allowed_file(file.filename):
        return error_response("Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP", 400)
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return error_response("File too large. Maximum size: 5MB", 400)
    
    try:
        # Generate unique filename with user_id prefix
        file_id = str(uuid.uuid4())
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        filename = f"{user_id}_{file_id}.{file_extension}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save file
        file.save(filepath)
        
        # Get expense_id if provided
        expense_id = request.form.get('expense_id')
        
        # Update expense with receipt info if expense_id provided (verify ownership)
        if expense_id:
            valid, error = validate_uuid(expense_id)
            if valid:
                db = get_db()
                with db.cursor() as cursor:
                    cursor.execute("""
                        UPDATE expenses 
                        SET receipt_photo_path = %s, 
                            receipt_photo_filename = %s, 
                            receipt_photo_size = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND user_id = %s
                    """, (filepath, original_filename, file_size, expense_id, user_id))
                    db.commit()
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': original_filename,
            'path': filepath,
            'size': file_size,
            'expense_id': expense_id if expense_id else None
        })
        
    except Exception as e:
        return handle_db_error(e, "Failed to upload receipt")


@smart_bp.route('/receipt/<file_id>', methods=['GET'])
@require_auth
def get_receipt(file_id):
    """
    GET /smart/receipt/{file_id}
    Retrieve a receipt photo (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(file_id)
    if not valid:
        return error_response("Invalid file ID", 400)
    
    # Find file with this ID (user prefix ensures ownership)
    for ext in ALLOWED_EXTENSIONS:
        filepath = os.path.join(UPLOAD_FOLDER, f"{user_id}_{file_id}.{ext}")
        if os.path.exists(filepath):
            return send_file(filepath)
    
    return error_response("Receipt not found", 404)


@smart_bp.route('/receipt/<file_id>', methods=['DELETE'])
@require_auth
def delete_receipt(file_id):
    """
    DELETE /smart/receipt/{file_id}
    Delete a receipt photo (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(file_id)
    if not valid:
        return error_response("Invalid file ID", 400)
    
    try:
        db = get_db()
        deleted = False
        
        # Find and delete file (user prefix ensures ownership)
        for ext in ALLOWED_EXTENSIONS:
            filepath = os.path.join(UPLOAD_FOLDER, f"{user_id}_{file_id}.{ext}")
            if os.path.exists(filepath):
                os.remove(filepath)
                deleted = True
                
                # Update any expenses that reference this file
                with db.cursor() as cursor:
                    cursor.execute("""
                        UPDATE expenses 
                        SET receipt_photo_path = NULL, 
                            receipt_photo_filename = NULL, 
                            receipt_photo_size = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE receipt_photo_path = %s AND user_id = %s
                    """, (filepath, user_id))
                    db.commit()
                break
        
        if not deleted:
            return error_response("Receipt not found", 404)
        
        return '', 204
        
    except Exception as e:
        return handle_db_error(e, "Failed to delete receipt")


# ============================================================
# Smart Categorization
# ============================================================

@smart_bp.route('/categorization/suggest', methods=['POST'])
@require_auth
def suggest_category():
    """
    POST /smart/categorization/suggest
    Suggest category based on note text using learned patterns for authenticated user.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    note = data.get('note', '').strip().lower()
    
    if not note:
        return jsonify({'suggestion': None, 'confidence': 0.0})
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Find matching patterns for this user
            cursor.execute("""
                SELECT cp.category_id, cp.confidence_score, cp.usage_count,
                       c.name as category_name
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE AND c.user_id = %s
                  AND to_tsvector('english', cp.note_keywords) @@ plainto_tsquery('english', %s)
                ORDER BY cp.confidence_score DESC, cp.usage_count DESC
                LIMIT 3
            """, (user_id, note))
            
            patterns = cursor.fetchall()
            
            if not patterns:
                return jsonify({'suggestion': None, 'confidence': 0.0})
            
            best_match = patterns[0]
            return jsonify({
                'suggestion': {
                    'category_id': str(best_match['category_id']),
                    'category_name': best_match['category_name']
                },
                'confidence': float(best_match['confidence_score']),
                'alternatives': [
                    {
                        'category_id': str(p['category_id']),
                        'category_name': p['category_name'],
                        'confidence': float(p['confidence_score'])
                    } for p in patterns[1:]
                ]
            })
            
    except Exception as e:
        return handle_db_error(e, "Failed to suggest category")


@smart_bp.route('/categorization/learn', methods=['POST'])
@require_auth
def learn_categorization():
    """
    POST /smart/categorization/learn
    Learn from user's categorization choice.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    
    note = data.get('note', '').strip().lower()
    category_id = data.get('category_id')
    confidence = data.get('confidence', 0.7)
    
    valid, error = validate_uuid(category_id)
    if not note or not valid:
        return error_response("Note and valid category_id are required", 400)
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Verify category belongs to user
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Category not found", 404)
            
            # Extract keywords from note
            keywords = ' '.join([word for word in note.split() if len(word) > 2])
            
            # Check if pattern already exists for this user
            cursor.execute("""
                SELECT id, usage_count, confidence_score 
                FROM categorization_patterns 
                WHERE note_keywords = %s AND category_id = %s AND user_id = %s
            """, (keywords, category_id, user_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing pattern
                new_usage_count = existing[1] + 1
                new_confidence = min(0.95, existing[2] + 0.05)
                
                cursor.execute("""
                    UPDATE categorization_patterns 
                    SET usage_count = %s, 
                        confidence_score = %s,
                        last_used = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_usage_count, new_confidence, existing[0]))
            else:
                # Create new pattern with user_id
                pattern_id = generate_uuid()
                cursor.execute("""
                    INSERT INTO categorization_patterns 
                    (id, note_keywords, category_id, confidence_score, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (pattern_id, keywords, category_id, confidence, user_id))
            
            db.commit()
            return jsonify({'success': True, 'learned': True})
            
    except Exception as e:
        return handle_db_error(e, "Failed to learn categorization")


# ============================================================
# Voice Input Processing
# ============================================================

@smart_bp.route('/voice/process', methods=['POST'])
@require_auth
def process_voice_input():
    """
    POST /smart/voice/process
    Process voice input text and extract expense information for authenticated user.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    text = data.get('text', '').strip().lower()
    confidence = data.get('confidence', 0.8)
    
    if not text:
        return error_response("Voice text is required", 400)
    
    try:
        parsed_data = {
            'amount': None,
            'note': text,
            'suggested_category': None,
            'confidence': confidence,
            'input_method': 'voice'
        }
        
        import re
        
        amount_patterns = [
            r'(?:spent|paid|cost|costs|costed)\s+(?:₹|rs\.?|rupees?)\s*(\d+(?:\.\d{2})?)',
            r'(?:spent|paid|cost|costs|costed)\s+(\d+(?:\.\d{2})?)\s*(?:₹|rs\.?|rupees?)',
            r'(?:spent|paid|cost|costs|costed)\s+(\d+(?:\.\d{2})?)',
            r'₹\s*(\d+(?:\.\d{2})?)',
            r'(\d+(?:\.\d{2})?)\s*(?:₹|rs\.?|rupees?)',
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                parsed_data['amount'] = match.group(1)
                break
        
        # Get category suggestion for this user
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT cp.category_id, c.name as category_name, cp.confidence_score
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE AND c.user_id = %s
                  AND to_tsvector('english', cp.note_keywords) @@ plainto_tsquery('english', %s)
                ORDER BY cp.confidence_score DESC, cp.usage_count DESC
                LIMIT 1
            """, (user_id, text))
            
            suggestion = cursor.fetchone()
            if suggestion:
                parsed_data['suggested_category'] = {
                    'category_id': str(suggestion['category_id']),
                    'category_name': suggestion['category_name'],
                    'confidence': float(suggestion['confidence_score'])
                }
        
        return jsonify(parsed_data)
        
    except Exception as e:
        return handle_db_error(e, "Failed to process voice input")


# ============================================================
# Export Functionality
# ============================================================

@smart_bp.route('/export/csv', methods=['POST'])
@require_auth
def export_csv():
    """
    POST /smart/export/csv
    Export authenticated user's expenses to CSV format.
    """
    user_id = get_current_user_id()
    
    data = request.get_json() or {}
    
    start_date = data.get('start_date') or None
    end_date = data.get('end_date') or None
    category_ids = data.get('category_ids', [])
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Build query with user isolation
            query = """
                SELECT e.date, e.amount, c.name as category, e.note,
                       e.is_split, e.split_amount, e.split_with,
                       e.created_at
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE e.user_id = %s
            """
            params = [user_id]
            
            if start_date:
                query += " AND e.date >= %s"
                params.append(start_date)
            
            if end_date:
                query += " AND e.date <= %s"
                params.append(end_date)
            
            if category_ids:
                placeholders = ','.join(['%s'] * len(category_ids))
                query += f" AND e.category_id IN ({placeholders})"
                params.extend(category_ids)
            
            query += " ORDER BY e.date DESC, e.created_at DESC"
            
            cursor.execute(query, params)
            expenses = cursor.fetchall()
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            writer.writerow([
                'Date', 'Amount (₹)', 'Category', 'Note', 
                'Is Split', 'Split Amount (₹)', 'Split With', 'Created At'
            ])
            
            for expense in expenses:
                writer.writerow([
                    expense['date'],
                    format_amount(expense['amount']),
                    expense['category'],
                    expense['note'] or '',
                    'Yes' if expense['is_split'] else 'No',
                    format_amount(expense['split_amount']) if expense['split_amount'] else '',
                    expense['split_with'] or '',
                    expense['created_at']
                ])
            
            # Log export with user_id
            export_id = generate_uuid()
            cursor.execute("""
                INSERT INTO export_logs (id, export_type, date_range_start, date_range_end, total_records, user_id)
                VALUES (%s, 'csv', %s, %s, %s, %s)
            """, (export_id, start_date, end_date, len(expenses), user_id))
            db.commit()
            
            output.seek(0)
            csv_data = output.getvalue()
            output.close()
            
            csv_buffer = io.BytesIO(csv_data.encode('utf-8'))
            csv_buffer.seek(0)
            
            filename = f"expenses_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            return send_file(
                csv_buffer,
                mimetype='text/csv',
                as_attachment=True,
                download_name=filename
            )
            
    except Exception as e:
        return handle_db_error(e, "Failed to export CSV")


@smart_bp.route('/export/pdf', methods=['POST'])
@require_auth
def export_pdf():
    """
    POST /smart/export/pdf
    Export authenticated user's expenses to PDF format.
    """
    user_id = get_current_user_id()
    
    data = request.get_json() or {}
    
    start_date = data.get('start_date') or None
    end_date = data.get('end_date') or None
    category_ids = data.get('category_ids', [])
    
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT e.date, e.amount, c.name as category, e.note,
                       e.is_split, e.split_amount
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE e.user_id = %s
            """
            params = [user_id]
            
            if start_date:
                query += " AND e.date >= %s"
                params.append(start_date)
            
            if end_date:
                query += " AND e.date <= %s"
                params.append(end_date)
            
            if category_ids:
                placeholders = ','.join(['%s'] * len(category_ids))
                query += f" AND e.category_id IN ({placeholders})"
                params.extend(category_ids)
            
            query += " ORDER BY e.date DESC, e.created_at DESC"
            
            cursor.execute(query, params)
            expenses = cursor.fetchall()
            
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            
            styles = getSampleStyleSheet()
            title_style = styles['Title']
            
            title_text = "Expense Report"
            if start_date and end_date:
                title_text += f" ({start_date} to {end_date})"
            elements.append(Paragraph(title_text, title_style))
            elements.append(Spacer(1, 20))
            
            table_data = [['Date', 'Category', 'Note', 'Amount', 'Split?']]
            
            total_amount = 0
            
            for exp in expenses:
                amount = float(exp['amount'])
                total_amount += amount
                
                note = exp['note'] or ''
                if len(note) > 20:
                    note = note[:17] + '...'
                    
                table_data.append([
                    str(exp['date']),
                    exp['category'],
                    note,
                    f"₹{format_amount(amount)}",
                    'Yes' if exp['is_split'] else 'No'
                ])
            
            table_data.append(['', '', 'Total', f"₹{format_amount(total_amount)}", ''])
            
            table = Table(table_data, colWidths=[80, 100, 180, 80, 50])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -2), 1, colors.black),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
            ]))
            
            elements.append(table)
            doc.build(elements)
            
            # Log export with user_id
            export_id = generate_uuid()
            cursor.execute("""
                INSERT INTO export_logs (id, export_type, date_range_start, date_range_end, total_records, user_id)
                VALUES (%s, 'pdf', %s, %s, %s, %s)
            """, (export_id, start_date, end_date, len(expenses), user_id))
            db.commit()
            
            buffer.seek(0)
            filename = f"expenses_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            return send_file(
                buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )

    except ImportError:
        return error_response("PDF generation library (reportlab) not installed", 500)
    except Exception as e:
        return handle_db_error(e, "Failed to export PDF")


@smart_bp.route('/export/summary', methods=['GET'])
@require_auth
def export_summary():
    """
    GET /smart/export/summary
    Get export history and statistics for authenticated user.
    """
    user_id = get_current_user_id()
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get user's recent exports
            cursor.execute("""
                SELECT export_type, total_records, created_at
                FROM export_logs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 10
            """, (user_id,))
            recent_exports = cursor.fetchall()
            
            # Get user's export statistics
            cursor.execute("""
                SELECT 
                    export_type,
                    COUNT(*) as export_count,
                    SUM(total_records) as total_records_exported,
                    MAX(created_at) as last_export
                FROM export_logs
                WHERE user_id = %s
                GROUP BY export_type
            """, (user_id,))
            stats = cursor.fetchall()
            
            return jsonify({
                'recent_exports': [
                    {
                        'type': exp['export_type'],
                        'records': exp['total_records'],
                        'date': str(exp['created_at'])
                    } for exp in recent_exports
                ],
                'statistics': [
                    {
                        'type': stat['export_type'],
                        'count': stat['export_count'],
                        'total_records': stat['total_records_exported'],
                        'last_export': str(stat['last_export'])
                    } for stat in stats
                ]
            })
            
    except Exception as e:
        return handle_db_error(e, "Failed to get export summary")


# ============================================================
# User Preferences
# ============================================================

@smart_bp.route('/preferences', methods=['GET'])
@require_auth
def get_preferences():
    """
    GET /smart/preferences
    Get user preferences for smart features.
    """
    user_id = get_current_user_id()
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT preference_key, preference_value
                FROM user_preferences
                WHERE user_id = %s
            """, (user_id,))
            
            preferences = {}
            for row in cursor.fetchall():
                preferences[row['preference_key']] = row['preference_value']
            
            return jsonify(preferences)
            
    except Exception as e:
        return handle_db_error(e, "Failed to get preferences")


@smart_bp.route('/preferences', methods=['PUT'])
@require_auth
def update_preferences():
    """
    PUT /smart/preferences
    Update user preferences.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    preferences = data.get('preferences', {})
    
    if not preferences:
        return error_response("Preferences object is required", 400)
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            for key, value in preferences.items():
                cursor.execute("""
                    INSERT INTO user_preferences (id, preference_key, preference_value, user_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (preference_key, user_id) 
                    DO UPDATE SET 
                        preference_value = EXCLUDED.preference_value,
                        updated_at = CURRENT_TIMESTAMP
                """, (generate_uuid(), key, json.dumps(value), user_id))
            
            db.commit()
            return jsonify({'success': True, 'updated': len(preferences)})
            
    except Exception as e:
        return handle_db_error(e, "Failed to update preferences")