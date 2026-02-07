"""
Receipts Blueprint - Handles receipt photo capture and processing.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own receipts
"""

import os
import uuid
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, g
from werkzeug.utils import secure_filename

from database import get_db
from validators import validate_uuid, generate_uuid
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id

receipts_bp = Blueprint('receipts', __name__, url_prefix='/receipts')

# Allowed file extensions for receipts
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_upload_folder():
    """Get the upload folder path, create if doesn't exist."""
    upload_folder = os.path.join(os.getcwd(), 'uploads', 'receipts')
    os.makedirs(upload_folder, exist_ok=True)
    return upload_folder

def simulate_ocr(filename):
    """
    Simulate OCR processing for receipt text extraction.
    In a real implementation, this would use OCR libraries like Tesseract.
    """
    extracted_text = f"Receipt from store - {filename}"
    
    import random
    extracted_amount = round(random.uniform(10.0, 500.0), 2)
    extracted_date = datetime.now().date()
    
    return {
        'text': extracted_text,
        'amount': extracted_amount,
        'date': extracted_date
    }


@receipts_bp.route('/upload', methods=['POST'])
@require_auth
def upload_receipt():
    """
    POST /receipts/upload
    Upload a receipt photo for the authenticated user.
    """
    user_id = get_current_user_id()
    
    if 'file' not in request.files:
        return error_response("No file provided", 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response("No file selected", 400)
    
    if not allowed_file(file.filename):
        return error_response("File type not allowed. Use PNG, JPG, JPEG, GIF, or WEBP", 400)
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return error_response("File too large. Maximum size is 10MB", 400)
    
    expense_id = request.form.get('expense_id')
    if expense_id:
        valid, error = validate_uuid(expense_id)
        if not valid:
            return error_response("Invalid expense_id", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if expense exists and belongs to user (if provided)
            if expense_id:
                cursor.execute(
                    "SELECT id FROM expenses WHERE id = %s AND user_id = %s",
                    (expense_id, user_id)
                )
                if not cursor.fetchone():
                    return error_response("Expense not found", 404)
            
            # Generate unique filename with user_id prefix
            receipt_id = generate_uuid()
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{user_id}_{receipt_id}.{file_extension}"
            
            # Save file
            upload_folder = get_upload_folder()
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # Simulate OCR processing
            ocr_result = simulate_ocr(file.filename)
            
            # Save receipt record with user_id
            cursor.execute("""
                INSERT INTO receipt_photos 
                (id, expense_id, filename, original_filename, file_size, mime_type, 
                 processed, extracted_text, extracted_amount, extracted_date, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                receipt_id, expense_id, filename, file.filename, file_size,
                file.content_type, True, ocr_result['text'], 
                ocr_result['amount'], ocr_result['date'], user_id
            ))
            
            # Update expense with receipt_photo_id if expense_id provided
            if expense_id:
                cursor.execute("""
                    UPDATE expenses SET receipt_photo_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (receipt_id, expense_id, user_id))
            
            db.commit()
            
            return jsonify({
                'id': receipt_id,
                'filename': filename,
                'original_filename': file.filename,
                'file_size': file_size,
                'extracted_text': ocr_result['text'],
                'extracted_amount': str(ocr_result['amount']),
                'extracted_date': str(ocr_result['date']),
                'expense_id': expense_id
            }), 201
            
    except Exception as e:
        try:
            if 'file_path' in locals():
                os.remove(file_path)
        except:
            pass
        return handle_db_error(e, "Failed to upload receipt")


@receipts_bp.route('/<receipt_id>', methods=['GET'])
@require_auth
def get_receipt(receipt_id):
    """
    GET /receipts/{id}
    Get receipt details (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(receipt_id)
    if not valid:
        return error_response("Invalid receipt ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.expense_id, r.filename, r.original_filename,
                       r.file_size, r.mime_type, r.upload_date, r.processed,
                       r.extracted_text, r.extracted_amount, r.extracted_date,
                       e.date as expense_date, e.amount as expense_amount,
                       e.note as expense_note, c.name as category_name
                FROM receipt_photos r
                LEFT JOIN expenses e ON r.expense_id = e.id
                LEFT JOIN categories c ON e.category_id = c.id
                WHERE r.id = %s AND r.user_id = %s
            """, (receipt_id, user_id))
            
            row = cursor.fetchone()
            if not row:
                return error_response("Receipt not found", 404)
            
            receipt = {
                'id': str(row['id']),
                'expense_id': str(row['expense_id']) if row['expense_id'] else None,
                'filename': row['filename'],
                'original_filename': row['original_filename'],
                'file_size': row['file_size'],
                'mime_type': row['mime_type'],
                'upload_date': str(row['upload_date']),
                'processed': row['processed'],
                'extracted_text': row['extracted_text'],
                'extracted_amount': str(row['extracted_amount']) if row['extracted_amount'] else None,
                'extracted_date': str(row['extracted_date']) if row['extracted_date'] else None,
                'expense': {
                    'date': str(row['expense_date']) if row['expense_date'] else None,
                    'amount': str(row['expense_amount']) if row['expense_amount'] else None,
                    'note': row['expense_note'],
                    'category_name': row['category_name']
                } if row['expense_id'] else None
            }
            
            return jsonify(receipt)
            
    except Exception as e:
        return handle_db_error(e, "Failed to fetch receipt")


@receipts_bp.route('/<receipt_id>/link', methods=['POST'])
@require_auth
def link_receipt_to_expense(receipt_id):
    """
    POST /receipts/{id}/link
    Link receipt to an expense (both must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(receipt_id)
    if not valid:
        return error_response("Invalid receipt ID", 400)
    
    data = request.get_json()
    expense_id = data.get('expense_id')
    
    valid, error = validate_uuid(expense_id)
    if not valid:
        return error_response("Valid expense_id is required", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if receipt exists and belongs to user
            cursor.execute(
                "SELECT id FROM receipt_photos WHERE id = %s AND user_id = %s",
                (receipt_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Receipt not found", 404)
            
            # Check if expense exists and belongs to user
            cursor.execute(
                "SELECT id FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Expense not found", 404)
            
            # Update receipt with expense_id
            cursor.execute("""
                UPDATE receipt_photos SET expense_id = %s
                WHERE id = %s AND user_id = %s
            """, (expense_id, receipt_id, user_id))
            
            # Update expense with receipt_photo_id
            cursor.execute("""
                UPDATE expenses SET receipt_photo_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
            """, (receipt_id, expense_id, user_id))
            
            db.commit()
            return jsonify({'message': 'Receipt linked to expense successfully'})
            
    except Exception as e:
        return handle_db_error(e, "Failed to link receipt to expense")


@receipts_bp.route('', methods=['GET'])
@require_auth
def get_receipts():
    """
    GET /receipts
    Get all receipts for authenticated user with optional filters.
    """
    user_id = get_current_user_id()
    
    expense_id = request.args.get('expense_id')
    unlinked = request.args.get('unlinked', '').lower() == 'true'
    
    if expense_id:
        valid, error = validate_uuid(expense_id)
        if not valid:
            return error_response("Invalid expense_id", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT r.id, r.expense_id, r.filename, r.original_filename,
                       r.file_size, r.upload_date, r.extracted_amount,
                       r.extracted_date, e.note as expense_note,
                       c.name as category_name
                FROM receipt_photos r
                LEFT JOIN expenses e ON r.expense_id = e.id
                LEFT JOIN categories c ON e.category_id = c.id
                WHERE r.user_id = %s
            """
            params = [user_id]
            
            if expense_id:
                query += " AND r.expense_id = %s"
                params.append(expense_id)
            
            if unlinked:
                query += " AND r.expense_id IS NULL"
            
            query += " ORDER BY r.upload_date DESC"
            
            cursor.execute(query, params)
            receipts = []
            
            for row in cursor.fetchall():
                receipts.append({
                    'id': str(row['id']),
                    'expense_id': str(row['expense_id']) if row['expense_id'] else None,
                    'filename': row['filename'],
                    'original_filename': row['original_filename'],
                    'file_size': row['file_size'],
                    'upload_date': str(row['upload_date']),
                    'extracted_amount': str(row['extracted_amount']) if row['extracted_amount'] else None,
                    'extracted_date': str(row['extracted_date']) if row['extracted_date'] else None,
                    'expense_note': row['expense_note'],
                    'category_name': row['category_name']
                })
            
            return jsonify(receipts)
            
    except Exception as e:
        return handle_db_error(e, "Failed to fetch receipts")


@receipts_bp.route('/<receipt_id>', methods=['DELETE'])
@require_auth
def delete_receipt(receipt_id):
    """
    DELETE /receipts/{id}
    Delete a receipt and its file (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(receipt_id)
    if not valid:
        return error_response("Invalid receipt ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get receipt details (verify ownership)
            cursor.execute(
                "SELECT filename, expense_id FROM receipt_photos WHERE id = %s AND user_id = %s",
                (receipt_id, user_id)
            )
            row = cursor.fetchone()
            
            if not row:
                return error_response("Receipt not found", 404)
            
            filename = row['filename']
            expense_id = row['expense_id']
            
            # Remove receipt_photo_id from expense if linked
            if expense_id:
                cursor.execute("""
                    UPDATE expenses SET receipt_photo_id = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (expense_id, user_id))
            
            # Delete receipt record
            cursor.execute(
                "DELETE FROM receipt_photos WHERE id = %s AND user_id = %s",
                (receipt_id, user_id)
            )
            
            # Delete physical file
            try:
                upload_folder = get_upload_folder()
                file_path = os.path.join(upload_folder, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as file_error:
                current_app.logger.warning(f"Failed to delete receipt file {filename}: {file_error}")
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete receipt")