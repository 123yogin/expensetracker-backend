"""
Smart Categorization Blueprint - Handles AI-powered expense categorization.

Features:
- Learn from user categorization patterns
- Suggest categories based on expense notes
- Pattern matching and confidence scoring
- Offline-capable smart suggestions
"""

import re
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from database import get_db
from validators import validate_uuid, generate_uuid
from errors import handle_db_error, error_response

smart_bp = Blueprint('smart', __name__, url_prefix='/smart')

def normalize_text(text):
    """Normalize text for pattern matching."""
    if not text:
        return ""
    # Convert to lowercase, remove extra spaces, keep alphanumeric and spaces
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower()).strip()

def extract_keywords(text):
    """Extract meaningful keywords from text."""
    if not text:
        return []
    
    # Common stop words to ignore
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'between', 'among', 'is', 'was',
        'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
        'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can'
    }
    
    normalized = normalize_text(text)
    words = normalized.split()
    keywords = [word for word in words if len(word) > 2 and word not in stop_words]
    return keywords[:5]  # Return top 5 keywords

def calculate_similarity(text1, text2):
    """Calculate similarity between two texts based on common keywords."""
    keywords1 = set(extract_keywords(text1))
    keywords2 = set(extract_keywords(text2))
    
    if not keywords1 or not keywords2:
        return 0.0
    
    intersection = keywords1.intersection(keywords2)
    union = keywords1.union(keywords2)
    
    return len(intersection) / len(union) if union else 0.0

@smart_bp.route('/suggest-category', methods=['POST'])
def suggest_category():
    """
    POST /smart/suggest-category
    Suggest category based on expense note.
    
    Body:
        note: string (required)
        amount: decimal (optional, for context)
    
    Returns:
        200: Category suggestions with confidence scores
    """
    data = request.get_json()
    note = data.get('note', '').strip()
    amount = data.get('amount')
    
    if not note:
        return jsonify({'suggestions': []})
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get all categorization patterns
            cursor.execute("""
                SELECT cp.note_pattern, cp.category_id, cp.confidence_score, 
                       cp.usage_count, c.name as category_name
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE
                ORDER BY cp.usage_count DESC, cp.confidence_score DESC
            """)
            
            patterns = cursor.fetchall()
            suggestions = []
            
            # Calculate similarity scores
            for pattern in patterns:
                similarity = calculate_similarity(note, pattern['note_pattern'])
                if similarity > 0.1:  # Minimum threshold
                    # Boost confidence based on usage count
                    usage_boost = min(pattern['usage_count'] / 10.0, 0.3)
                    final_confidence = min(similarity + usage_boost, 1.0)
                    
                    suggestions.append({
                        'category_id': str(pattern['category_id']),
                        'category_name': pattern['category_name'],
                        'confidence': round(final_confidence, 2),
                        'reason': f"Similar to: {pattern['note_pattern'][:50]}..."
                    })
            
            # Sort by confidence and limit to top 3
            suggestions.sort(key=lambda x: x['confidence'], reverse=True)
            suggestions = suggestions[:3]
            
            # If no good matches, provide fallback suggestions based on keywords
            if not suggestions:
                fallback_suggestions = get_fallback_suggestions(note, cursor)
                suggestions.extend(fallback_suggestions)
            
            return jsonify({'suggestions': suggestions})
            
    except Exception as e:
        return handle_db_error(e, "Failed to suggest category")

def get_fallback_suggestions(note, cursor):
    """Get fallback category suggestions based on common keywords."""
    keywords = extract_keywords(note)
    if not keywords:
        return []
    
    # Common keyword-to-category mappings
    keyword_mappings = {
        'food': ['Food & Dining', 'Groceries', 'Restaurant'],
        'gas': ['Transportation', 'Fuel'],
        'fuel': ['Transportation', 'Fuel'],
        'uber': ['Transportation'],
        'taxi': ['Transportation'],
        'bus': ['Transportation'],
        'train': ['Transportation'],
        'grocery': ['Groceries', 'Food & Dining'],
        'supermarket': ['Groceries'],
        'restaurant': ['Food & Dining', 'Restaurant'],
        'coffee': ['Food & Dining'],
        'medicine': ['Healthcare', 'Medical'],
        'doctor': ['Healthcare', 'Medical'],
        'hospital': ['Healthcare', 'Medical'],
        'pharmacy': ['Healthcare', 'Medical'],
        'movie': ['Entertainment'],
        'cinema': ['Entertainment'],
        'book': ['Education', 'Entertainment'],
        'gym': ['Health & Fitness'],
        'fitness': ['Health & Fitness'],
        'electricity': ['Utilities'],
        'water': ['Utilities'],
        'internet': ['Utilities'],
        'phone': ['Utilities'],
        'rent': ['Housing'],
        'mortgage': ['Housing'],
        'insurance': ['Insurance'],
        'shopping': ['Shopping'],
        'clothes': ['Shopping', 'Clothing'],
        'shirt': ['Shopping', 'Clothing'],
        'shoes': ['Shopping', 'Clothing']
    }
    
    suggestions = []
    for keyword in keywords:
        if keyword in keyword_mappings:
            for category_name in keyword_mappings[keyword]:
                # Check if category exists
                cursor.execute("""
                    SELECT id, name FROM categories 
                    WHERE LOWER(name) LIKE %s AND is_active = TRUE
                    LIMIT 1
                """, (f'%{category_name.lower()}%',))
                
                row = cursor.fetchone()
                if row:
                    suggestions.append({
                        'category_id': str(row['id']),
                        'category_name': row['name'],
                        'confidence': 0.6,
                        'reason': f"Keyword match: {keyword}"
                    })
                    break
    
    # Remove duplicates and limit
    seen = set()
    unique_suggestions = []
    for suggestion in suggestions:
        if suggestion['category_id'] not in seen:
            seen.add(suggestion['category_id'])
            unique_suggestions.append(suggestion)
    
    return unique_suggestions[:2]

@smart_bp.route('/learn-pattern', methods=['POST'])
def learn_pattern():
    """
    POST /smart/learn-pattern
    Learn from user categorization choice.
    
    Body:
        note: string (required)
        category_id: UUID (required)
        confidence: decimal (optional, default 1.0)
    
    Returns:
        201: Pattern learned successfully
    """
    data = request.get_json()
    note = data.get('note', '').strip()
    category_id = data.get('category_id')
    confidence = data.get('confidence', 1.0)
    
    if not note:
        return error_response("Note is required", 400)
    
    if not validate_uuid(category_id):
        return error_response("Valid category_id is required", 400)
    
    if not (0.0 <= confidence <= 1.0):
        return error_response("Confidence must be between 0.0 and 1.0", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists
            cursor.execute("SELECT id FROM categories WHERE id = %s AND is_active = TRUE", (category_id,))
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            normalized_note = normalize_text(note)
            
            # Check if similar pattern already exists
            cursor.execute("""
                SELECT id, usage_count FROM categorization_patterns
                WHERE note_pattern = %s AND category_id = %s
            """, (normalized_note, category_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing pattern
                cursor.execute("""
                    UPDATE categorization_patterns
                    SET usage_count = usage_count + 1,
                        confidence_score = GREATEST(confidence_score, %s),
                        last_used = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (confidence, existing['id']))
            else:
                # Create new pattern
                pattern_id = generate_uuid()
                cursor.execute("""
                    INSERT INTO categorization_patterns
                    (id, note_pattern, category_id, confidence_score, usage_count)
                    VALUES (%s, %s, %s, %s, 1)
                """, (pattern_id, normalized_note, category_id, confidence))
            
            db.commit()
            return jsonify({'message': 'Pattern learned successfully'}), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to learn pattern")

@smart_bp.route('/patterns', methods=['GET'])
def get_patterns():
    """
    GET /smart/patterns
    Get all learned categorization patterns.
    
    Query Parameters:
        category_id: UUID (optional, filter by category)
        limit: integer (optional, default 50)
    
    Returns:
        200: List of patterns
    """
    category_id = request.args.get('category_id')
    limit = min(int(request.args.get('limit', 50)), 100)  # Max 100
    
    if category_id and not validate_uuid(category_id):
        return error_response("Invalid category_id", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            query = """
                SELECT cp.id, cp.note_pattern, cp.category_id, cp.confidence_score,
                       cp.usage_count, cp.last_used, cp.created_at,
                       c.name as category_name
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE
            """
            params = []
            
            if category_id:
                query += " AND cp.category_id = %s"
                params.append(category_id)
            
            query += " ORDER BY cp.usage_count DESC, cp.confidence_score DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            patterns = []
            
            for row in cursor.fetchall():
                patterns.append({
                    'id': str(row['id']),
                    'note_pattern': row['note_pattern'],
                    'category_id': str(row['category_id']),
                    'category_name': row['category_name'],
                    'confidence_score': float(row['confidence_score']),
                    'usage_count': row['usage_count'],
                    'last_used': str(row['last_used']),
                    'created_at': str(row['created_at'])
                })
            
            return jsonify(patterns)
            
    except Exception as e:
        return handle_db_error(e, "Failed to fetch patterns")

@smart_bp.route('/patterns/<pattern_id>', methods=['DELETE'])
def delete_pattern(pattern_id):
    """
    DELETE /smart/patterns/{id}
    Delete a learned pattern.
    
    Returns:
        204: Pattern deleted
        404: Pattern not found
    """
    if not validate_uuid(pattern_id):
        return error_response("Invalid pattern ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM categorization_patterns WHERE id = %s", (pattern_id,))
            
            if cursor.rowcount == 0:
                return error_response("Pattern not found", 404)
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete pattern")

@smart_bp.route('/cleanup-patterns', methods=['POST'])
def cleanup_patterns():
    """
    POST /smart/cleanup-patterns
    Clean up old or low-confidence patterns.
    
    Body:
        days_old: integer (optional, default 90)
        min_confidence: decimal (optional, default 0.3)
        min_usage: integer (optional, default 2)
    
    Returns:
        200: Cleanup completed with count
    """
    data = request.get_json() or {}
    days_old = data.get('days_old', 90)
    min_confidence = data.get('min_confidence', 0.3)
    min_usage = data.get('min_usage', 2)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            cursor.execute("""
                DELETE FROM categorization_patterns
                WHERE (last_used < %s OR confidence_score < %s OR usage_count < %s)
                AND created_at < %s
            """, (cutoff_date, min_confidence, min_usage, cutoff_date))
            
            deleted_count = cursor.rowcount
            db.commit()
            
            return jsonify({
                'message': f'Cleaned up {deleted_count} patterns',
                'deleted_count': deleted_count
            })
            
    except Exception as e:
        return handle_db_error(e, "Failed to cleanup patterns")