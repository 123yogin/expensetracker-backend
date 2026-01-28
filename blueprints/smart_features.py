"""
Smart Features Blueprint - Handles receipt photos, voice input, smart categorization, and export functionality.

Features:
- Receipt photo upload and management
- Smart categorization based on learning patterns
- Voice input processing
- Export functionality (CSV, PDF)
- Offline sync support
"""

import os
import json
import uuid
import csv
import io
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_file
import psycopg2
from psycopg2.extras import RealDictCursor

from database import get_db
from validators import validate_uuid, generate_uuid, format_amount
from errors import handle_db_error, error_response

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
def upload_receipt():
    """
    POST /smart/receipt/upload
    Upload a receipt photo.
    
    Form Data:
        file: image file (required)
        expense_id: UUID (optional, to associate with existing expense)
    
    Returns:
        200: Upload success with file info
        400: Validation error
    """
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
        # Generate unique filename
        file_id = str(uuid.uuid4())
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        filename = f"{file_id}.{file_extension}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save file
        file.save(filepath)
        
        # Get expense_id if provided
        expense_id = request.form.get('expense_id')
        
        # Update expense with receipt info if expense_id provided
        if expense_id and validate_uuid(expense_id):
            db = get_db()
            with db.cursor() as cursor:
                cursor.execute("""
                    UPDATE expenses 
                    SET receipt_photo_path = %s, 
                        receipt_photo_filename = %s, 
                        receipt_photo_size = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (filepath, original_filename, file_size, expense_id))
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
def get_receipt(file_id):
    """
    GET /smart/receipt/{file_id}
    Retrieve a receipt photo.
    
    Returns:
        200: Image file
        404: File not found
    """
    if not validate_uuid(file_id):
        return error_response("Invalid file ID", 400)
    
    # Find file with this ID
    for ext in ALLOWED_EXTENSIONS:
        filepath = os.path.join(UPLOAD_FOLDER, f"{file_id}.{ext}")
        if os.path.exists(filepath):
            return send_file(filepath)
    
    return error_response("Receipt not found", 404)

@smart_bp.route('/receipt/<file_id>', methods=['DELETE'])
def delete_receipt(file_id):
    """
    DELETE /smart/receipt/{file_id}
    Delete a receipt photo.
    
    Returns:
        204: Deleted successfully
        404: File not found
    """
    if not validate_uuid(file_id):
        return error_response("Invalid file ID", 400)
    
    try:
        db = get_db()
        deleted = False
        
        # Find and delete file
        for ext in ALLOWED_EXTENSIONS:
            filepath = os.path.join(UPLOAD_FOLDER, f"{file_id}.{ext}")
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
                        WHERE receipt_photo_path = %s
                    """, (filepath,))
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
def suggest_category():
    """
    POST /smart/categorization/suggest
    Suggest category based on note text using learned patterns.
    
    Body:
        note: string (required)
    
    Returns:
        200: Suggested category with confidence
        400: Validation error
    """
    data = request.get_json()
    note = data.get('note', '').strip().lower()
    
    if not note:
        return jsonify({'suggestion': None, 'confidence': 0.0})
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Find matching patterns using text search
            cursor.execute("""
                SELECT cp.category_id, cp.confidence_score, cp.usage_count,
                       c.name as category_name
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE
                  AND to_tsvector('english', cp.note_keywords) @@ plainto_tsquery('english', %s)
                ORDER BY cp.confidence_score DESC, cp.usage_count DESC
                LIMIT 3
            """, (note,))
            
            patterns = cursor.fetchall()
            
            if not patterns:
                return jsonify({'suggestion': None, 'confidence': 0.0})
            
            # Return best match
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
def learn_categorization():
    """
    POST /smart/categorization/learn
    Learn from user's categorization choice.
    
    Body:
        note: string (required)
        category_id: UUID (required)
        confidence: float (optional, default 0.7)
    
    Returns:
        200: Learning recorded
        400: Validation error
    """
    data = request.get_json()
    
    note = data.get('note', '').strip().lower()
    category_id = data.get('category_id')
    confidence = data.get('confidence', 0.7)
    
    if not note or not validate_uuid(category_id):
        return error_response("Note and valid category_id are required", 400)
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Extract keywords from note (simple approach)
            keywords = ' '.join([word for word in note.split() if len(word) > 2])
            
            # Check if pattern already exists
            cursor.execute("""
                SELECT id, usage_count, confidence_score 
                FROM categorization_patterns 
                WHERE note_keywords = %s AND category_id = %s
            """, (keywords, category_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing pattern
                new_usage_count = existing[1] + 1
                # Increase confidence with more usage (max 0.95)
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
                # Create new pattern
                pattern_id = generate_uuid()
                cursor.execute("""
                    INSERT INTO categorization_patterns 
                    (id, note_keywords, category_id, confidence_score)
                    VALUES (%s, %s, %s, %s)
                """, (pattern_id, keywords, category_id, confidence))
            
            db.commit()
            return jsonify({'success': True, 'learned': True})
            
    except Exception as e:
        return handle_db_error(e, "Failed to learn categorization")

# ============================================================
# Voice Input Processing
# ============================================================

@smart_bp.route('/voice/process', methods=['POST'])
def process_voice_input():
    """
    POST /smart/voice/process
    Process voice input text and extract expense information.
    
    Body:
        text: string (required) - transcribed voice text
        confidence: float (optional) - voice recognition confidence
    
    Returns:
        200: Parsed expense data
        400: Validation error
    """
    data = request.get_json()
    text = data.get('text', '').strip().lower()
    confidence = data.get('confidence', 0.8)
    
    if not text:
        return error_response("Voice text is required", 400)
    
    try:
        # Simple voice parsing logic (can be enhanced with NLP)
        parsed_data = {
            'amount': None,
            'note': text,
            'suggested_category': None,
            'confidence': confidence,
            'input_method': 'voice'
        }
        
        # Extract amount using regex patterns
        import re
        
        # Look for patterns like "spent 50", "paid 100", "₹200", "rupees 150"
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
        
        # Get category suggestion based on the text
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT cp.category_id, c.name as category_name, cp.confidence_score
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE
                  AND to_tsvector('english', cp.note_keywords) @@ plainto_tsquery('english', %s)
                ORDER BY cp.confidence_score DESC, cp.usage_count DESC
                LIMIT 1
            """, (text,))
            
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
def export_csv():
    """
    POST /smart/export/csv
    Export expenses to CSV format.
    
    Body:
        start_date: string (optional) - YYYY-MM-DD
        end_date: string (optional) - YYYY-MM-DD
        category_ids: array (optional) - filter by categories
    
    Returns:
        200: CSV file download
        400: Validation error
    """
    data = request.get_json() or {}
    
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    category_ids = data.get('category_ids', [])
    
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Build query with filters
            query = """
                SELECT e.date, e.amount, c.name as category, e.note,
                       e.is_split, e.split_amount, e.split_with,
                       e.input_method, e.receipt_photo_filename,
                       e.created_at
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            params = []
            
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
            
            # Write header
            writer.writerow([
                'Date', 'Amount (₹)', 'Category', 'Note', 
                'Is Split', 'Split Amount (₹)', 'Split With',
                'Input Method', 'Has Receipt', 'Created At'
            ])
            
            # Write data
            for expense in expenses:
                writer.writerow([
                    expense['date'],
                    format_amount(expense['amount']),
                    expense['category'],
                    expense['note'] or '',
                    'Yes' if expense['is_split'] else 'No',
                    format_amount(expense['split_amount']) if expense['split_amount'] else '',
                    expense['split_with'] or '',
                    expense['input_method'] or 'manual',
                    'Yes' if expense['receipt_photo_filename'] else 'No',
                    expense['created_at']
                ])
            
            # Log export
            export_id = generate_uuid()
            cursor.execute("""
                INSERT INTO export_logs (id, export_type, date_range_start, date_range_end, total_records)
                VALUES (%s, 'csv', %s, %s, %s)
            """, (export_id, start_date, end_date, len(expenses)))
            db.commit()
            
            # Prepare file response
            output.seek(0)
            csv_data = output.getvalue()
            output.close()
            
            # Create file-like object for send_file
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

@smart_bp.route('/export/summary', methods=['GET'])
def export_summary():
    """
    GET /smart/export/summary
    Get export history and statistics.
    
    Returns:
        200: Export summary data
    """
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get recent exports
            cursor.execute("""
                SELECT export_type, total_records, created_at
                FROM export_logs
                ORDER BY created_at DESC
                LIMIT 10
            """)
            recent_exports = cursor.fetchall()
            
            # Get export statistics
            cursor.execute("""
                SELECT 
                    export_type,
                    COUNT(*) as export_count,
                    SUM(total_records) as total_records_exported,
                    MAX(created_at) as last_export
                FROM export_logs
                GROUP BY export_type
            """)
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
def get_preferences():
    """
    GET /smart/preferences
    Get user preferences for smart features.
    
    Returns:
        200: User preferences object
    """
    try:
        db = get_db()
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT preference_key, preference_value
                FROM user_preferences
            """)
            
            preferences = {}
            for row in cursor.fetchall():
                preferences[row['preference_key']] = row['preference_value']
            
            return jsonify(preferences)
            
    except Exception as e:
        return handle_db_error(e, "Failed to get preferences")

@smart_bp.route('/preferences', methods=['PUT'])
def update_preferences():
    """
    PUT /smart/preferences
    Update user preferences.
    
    Body:
        preferences: object with preference keys and values
    
    Returns:
        200: Updated preferences
        400: Validation error
    """
    data = request.get_json()
    preferences = data.get('preferences', {})
    
    if not preferences:
        return error_response("Preferences object is required", 400)
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            for key, value in preferences.items():
                cursor.execute("""
                    INSERT INTO user_preferences (id, preference_key, preference_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (preference_key) 
                    DO UPDATE SET 
                        preference_value = EXCLUDED.preference_value,
                        updated_at = CURRENT_TIMESTAMP
                """, (generate_uuid(), key, json.dumps(value)))
            
            db.commit()
            return jsonify({'success': True, 'updated': len(preferences)})
            
    except Exception as e:
        return handle_db_error(e, "Failed to update preferences")