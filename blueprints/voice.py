"""
Voice Input Blueprint - Handles voice-to-expense conversion.

Features:
- Voice transcript processing
- Natural language parsing for expenses
- Voice session tracking
- Integration with smart categorization
"""

import re
import json
from datetime import datetime, date
from flask import Blueprint, request, jsonify

from database import get_db
from validators import validate_uuid, generate_uuid, validate_amount
from errors import handle_db_error, error_response

voice_bp = Blueprint('voice', __name__, url_prefix='/voice')

def parse_amount(text):
    """Extract amount from text."""
    # Look for patterns like: $50, 50 dollars, 50.99, fifty dollars
    amount_patterns = [
        r'\$(\d+(?:\.\d{2})?)',  # $50.99
        r'(\d+(?:\.\d{2})?)\s*(?:dollars?|bucks?|rupees?|rs\.?)',  # 50 dollars
        r'(\d+(?:\.\d{2})?)',  # Just numbers
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, text.lower())
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    
    # Try to parse written numbers (basic)
    number_words = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
        'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
        'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
        'eighty': 80, 'ninety': 90, 'hundred': 100
    }
    
    words = text.lower().split()
    for i, word in enumerate(words):
        if word in number_words:
            amount = number_words[word]
            # Check for "hundred" modifier
            if i + 1 < len(words) and words[i + 1] == 'hundred':
                amount *= 100
            return float(amount)
    
    return None

def parse_category_keywords(text):
    """Extract category hints from text."""
    category_keywords = {
        'food': ['food', 'lunch', 'dinner', 'breakfast', 'meal', 'restaurant', 'cafe', 'pizza', 'burger'],
        'transport': ['uber', 'taxi', 'bus', 'train', 'gas', 'fuel', 'parking', 'metro'],
        'groceries': ['grocery', 'groceries', 'supermarket', 'market', 'vegetables', 'fruits'],
        'entertainment': ['movie', 'cinema', 'game', 'concert', 'show', 'entertainment'],
        'healthcare': ['doctor', 'medicine', 'pharmacy', 'hospital', 'medical', 'health'],
        'utilities': ['electricity', 'water', 'internet', 'phone', 'bill', 'utility'],
        'shopping': ['shopping', 'clothes', 'shirt', 'shoes', 'buy', 'purchase', 'store'],
        'education': ['book', 'course', 'class', 'education', 'school', 'college'],
        'fitness': ['gym', 'fitness', 'workout', 'exercise', 'sports']
    }
    
    text_lower = text.lower()
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    
    return None

def extract_note(text, amount_text=None):
    """Extract the descriptive note from text, removing amount references."""
    # Remove common amount patterns
    cleaned = text
    if amount_text:
        cleaned = cleaned.replace(amount_text, '').strip()
    
    # Remove common voice command prefixes
    prefixes = [
        'i spent', 'spent', 'paid', 'bought', 'purchase', 'add expense',
        'expense for', 'expense of', 'record expense', 'track expense'
    ]
    
    cleaned_lower = cleaned.lower()
    for prefix in prefixes:
        if cleaned_lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    
    # Remove currency symbols and amount patterns
    cleaned = re.sub(r'\$\d+(?:\.\d{2})?', '', cleaned)
    cleaned = re.sub(r'\d+(?:\.\d{2})?\s*(?:dollars?|bucks?|rupees?|rs\.?)', '', cleaned)
    
    return cleaned.strip()

@voice_bp.route('/process', methods=['POST'])
def process_voice_input():
    """
    POST /voice/process
    Process voice transcript and extract expense information.
    
    Body:
        transcript: string (required)
        confidence: decimal (optional, speech recognition confidence)
    
    Returns:
        200: Parsed expense information
    """
    data = request.get_json()
    transcript = data.get('transcript', '').strip()
    speech_confidence = data.get('confidence', 1.0)
    
    if not transcript:
        return error_response("Transcript is required", 400)
    
    # Parse the transcript
    parsed_amount = parse_amount(transcript)
    category_hint = parse_category_keywords(transcript)
    note = extract_note(transcript)
    
    # Calculate overall confidence
    confidence = speech_confidence
    if parsed_amount is None:
        confidence *= 0.5  # Lower confidence if no amount found
    if not category_hint:
        confidence *= 0.8  # Slightly lower if no category hint
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Save voice session
            session_id = generate_uuid()
            cursor.execute("""
                INSERT INTO voice_sessions 
                (id, transcript, parsed_amount, parsed_category, parsed_note, confidence_score)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session_id, transcript, parsed_amount, category_hint, note, confidence))
            
            db.commit()
            
            result = {
                'session_id': session_id,
                'transcript': transcript,
                'parsed': {
                    'amount': parsed_amount,
                    'category_hint': category_hint,
                    'note': note,
                    'confidence': round(confidence, 2)
                },
                'suggestions': []
            }
            
            # Get category suggestions if we have a note
            if note:
                # Import here to avoid circular imports
                from blueprints.smart_categorization import suggest_category
                try:
                    # Get smart category suggestions
                    cursor.execute("""
                        SELECT cp.category_id, c.name as category_name, cp.confidence_score
                        FROM categorization_patterns cp
                        JOIN categories c ON cp.category_id = c.id
                        WHERE c.is_active = TRUE
                        ORDER BY cp.usage_count DESC, cp.confidence_score DESC
                        LIMIT 3
                    """)
                    
                    for row in cursor.fetchall():
                        result['suggestions'].append({
                            'category_id': str(row['category_id']),
                            'category_name': row['category_name'],
                            'confidence': float(row['confidence_score']),
                            'source': 'smart_categorization'
                        })
                except:
                    pass  # Fallback gracefully
            
            return jsonify(result)
            
    except Exception as e:
        return handle_db_error(e, "Failed to process voice input")

@voice_bp.route('/create-expense', methods=['POST'])
def create_expense_from_voice():
    """
    POST /voice/create-expense
    Create expense from voice session.
    
    Body:
        session_id: UUID (required)
        amount: decimal (required)
        category_id: UUID (required)
        note: string (optional)
        date: string (optional, defaults to today)
    
    Returns:
        201: Created expense
    """
    data = request.get_json()
    session_id = data.get('session_id')
    amount = data.get('amount')
    category_id = data.get('category_id')
    note = data.get('note', '').strip()
    expense_date = data.get('date', str(date.today()))
    
    if not validate_uuid(session_id):
        return error_response("Valid session_id is required", 400)
    
    if not amount:
        return error_response("Amount is required", 400)
    
    valid, error = validate_amount(amount)
    if not valid:
        return error_response(error, 400)
    
    if not validate_uuid(category_id):
        return error_response("Valid category_id is required", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if voice session exists
            cursor.execute("SELECT id FROM voice_sessions WHERE id = %s", (session_id,))
            if not cursor.fetchone():
                return error_response("Voice session not found", 404)
            
            # Check if category exists
            cursor.execute("SELECT id FROM categories WHERE id = %s AND is_active = TRUE", (category_id,))
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            # Create expense
            expense_id = generate_uuid()
            cursor.execute("""
                INSERT INTO expenses (id, date, amount, category_id, note, created_via_voice)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (expense_id, expense_date, amount, category_id, note))
            
            # Update voice session with created expense
            cursor.execute("""
                UPDATE voice_sessions 
                SET created_expense_id = %s
                WHERE id = %s
            """, (expense_id, session_id))
            
            # Learn from this categorization for smart suggestions
            if note:
                try:
                    cursor.execute("""
                        INSERT INTO categorization_patterns 
                        (id, note_pattern, category_id, confidence_score, usage_count)
                        VALUES (%s, %s, %s, 0.8, 1)
                        ON CONFLICT (note_pattern, category_id) DO UPDATE SET
                        usage_count = categorization_patterns.usage_count + 1,
                        last_used = CURRENT_TIMESTAMP
                    """, (generate_uuid(), note.lower().strip(), category_id))
                except:
                    pass  # Ignore conflicts
            
            # Fetch created expense with category name
            cursor.execute("""
                SELECT e.id, e.date, e.amount, e.category_id, e.note, 
                       e.created_at, e.created_via_voice, c.name as category_name
                FROM expenses e
                JOIN categories c ON e.category_id = c.id
                WHERE e.id = %s
            """, (expense_id,))
            
            row = cursor.fetchone()
            expense = {
                'id': str(row['id']),
                'date': str(row['date']),
                'amount': str(row['amount']),
                'category_id': str(row['category_id']),
                'category_name': row['category_name'],
                'note': row['note'],
                'created_at': str(row['created_at']),
                'created_via_voice': row['created_via_voice']
            }
            
            db.commit()
            return jsonify(expense), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to create expense from voice")

@voice_bp.route('/sessions', methods=['GET'])
def get_voice_sessions():
    """
    GET /voice/sessions
    Get voice input sessions.
    
    Query Parameters:
        limit: integer (optional, default 20)
        processed: boolean (optional, filter by processed status)
    
    Returns:
        200: List of voice sessions
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    processed = request.args.get('processed')
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT vs.id, vs.transcript, vs.parsed_amount, vs.parsed_category,
                       vs.parsed_note, vs.confidence_score, vs.created_at,
                       vs.created_expense_id, e.amount as expense_amount,
                       c.name as expense_category_name
                FROM voice_sessions vs
                LEFT JOIN expenses e ON vs.created_expense_id = e.id
                LEFT JOIN categories c ON e.category_id = c.id
                WHERE 1=1
            """
            params = []
            
            if processed is not None:
                if processed.lower() == 'true':
                    query += " AND vs.created_expense_id IS NOT NULL"
                else:
                    query += " AND vs.created_expense_id IS NULL"
            
            query += " ORDER BY vs.created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            sessions = []
            
            for row in cursor.fetchall():
                sessions.append({
                    'id': str(row['id']),
                    'transcript': row['transcript'],
                    'parsed_amount': float(row['parsed_amount']) if row['parsed_amount'] else None,
                    'parsed_category': row['parsed_category'],
                    'parsed_note': row['parsed_note'],
                    'confidence_score': float(row['confidence_score']) if row['confidence_score'] else None,
                    'created_at': str(row['created_at']),
                    'processed': row['created_expense_id'] is not None,
                    'expense': {
                        'id': str(row['created_expense_id']) if row['created_expense_id'] else None,
                        'amount': str(row['expense_amount']) if row['expense_amount'] else None,
                        'category_name': row['expense_category_name']
                    } if row['created_expense_id'] else None
                })
            
            return jsonify(sessions)
            
    except Exception as e:
        return handle_db_error(e, "Failed to fetch voice sessions")

@voice_bp.route('/sessions/<session_id>', methods=['DELETE'])
def delete_voice_session(session_id):
    """
    DELETE /voice/sessions/{id}
    Delete a voice session.
    
    Returns:
        204: Session deleted
        404: Session not found
    """
    if not validate_uuid(session_id):
        return error_response("Invalid session ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM voice_sessions WHERE id = %s", (session_id,))
            
            if cursor.rowcount == 0:
                return error_response("Voice session not found", 404)
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete voice session")