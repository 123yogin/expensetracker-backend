"""
Smart Categorization Blueprint - Handles AI-powered expense categorization.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own patterns
"""

import re
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g

from database import get_db
from validators import validate_uuid, generate_uuid
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id

# Changed blueprint name to avoid conflict with smart_features.py
smart_categorization_bp = Blueprint('smart_categorization', __name__, url_prefix='/smart-categorization')


def normalize_text(text):
    """Normalize text for pattern matching."""
    if not text:
        return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower()).strip()


def extract_keywords(text):
    """Extract meaningful keywords from text."""
    if not text:
        return []
    
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
    return keywords[:5]


def calculate_similarity(text1, text2):
    """Calculate similarity between two texts based on common keywords."""
    keywords1 = set(extract_keywords(text1))
    keywords2 = set(extract_keywords(text2))
    
    if not keywords1 or not keywords2:
        return 0.0
    
    intersection = keywords1.intersection(keywords2)
    union = keywords1.union(keywords2)
    
    return len(intersection) / len(union) if union else 0.0


@smart_categorization_bp.route('/suggest-category', methods=['POST'])
@require_auth
def suggest_category():
    """
    POST /smart-categorization/suggest-category
    Suggest category based on expense note for authenticated user.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    note = data.get('note', '').strip()
    amount = data.get('amount')
    
    if not note:
        return jsonify({'suggestions': []})
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Get user's categorization patterns
            cursor.execute("""
                SELECT cp.note_pattern, cp.category_id, cp.confidence_score, 
                       cp.usage_count, c.name as category_name
                FROM categorization_patterns cp
                JOIN categories c ON cp.category_id = c.id
                WHERE c.is_active = TRUE AND c.user_id = %s
                ORDER BY cp.usage_count DESC, cp.confidence_score DESC
            """, (user_id,))
            
            patterns = cursor.fetchall()
            suggestions = []
            
            for pattern in patterns:
                similarity = calculate_similarity(note, pattern['note_pattern'])
                if similarity > 0.1:
                    usage_boost = min(pattern['usage_count'] / 10.0, 0.3)
                    final_confidence = min(similarity + usage_boost, 1.0)
                    
                    suggestions.append({
                        'category_id': str(pattern['category_id']),
                        'category_name': pattern['category_name'],
                        'confidence': round(final_confidence, 2),
                        'reason': f"Similar to: {pattern['note_pattern'][:50]}..."
                    })
            
            suggestions.sort(key=lambda x: x['confidence'], reverse=True)
            suggestions = suggestions[:3]
            
            if not suggestions:
                fallback_suggestions = get_fallback_suggestions(note, cursor, user_id)
                suggestions.extend(fallback_suggestions)
            
            return jsonify({'suggestions': suggestions})
            
    except Exception as e:
        return handle_db_error(e, "Failed to suggest category")


def get_fallback_suggestions(note, cursor, user_id):
    """Get fallback category suggestions based on common keywords."""
    keywords = extract_keywords(note)
    if not keywords:
        return []
    
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
                # Check if user's category exists
                cursor.execute("""
                    SELECT id, name FROM categories 
                    WHERE LOWER(name) LIKE %s AND is_active = TRUE AND user_id = %s
                    LIMIT 1
                """, (f'%{category_name.lower()}%', user_id))
                
                row = cursor.fetchone()
                if row:
                    suggestions.append({
                        'category_id': str(row['id']),
                        'category_name': row['name'],
                        'confidence': 0.6,
                        'reason': f"Keyword match: {keyword}"
                    })
                    break
    
    seen = set()
    unique_suggestions = []
    for suggestion in suggestions:
        if suggestion['category_id'] not in seen:
            seen.add(suggestion['category_id'])
            unique_suggestions.append(suggestion)
    
    return unique_suggestions[:2]


@smart_categorization_bp.route('/learn-pattern', methods=['POST'])
@require_auth
def learn_pattern():
    """
    POST /smart-categorization/learn-pattern
    Learn from user categorization choice.
    """
    user_id = get_current_user_id()
    
    data = request.get_json()
    note = data.get('note', '').strip()
    category_id = data.get('category_id')
    confidence = data.get('confidence', 1.0)
    
    if not note:
        return error_response("Note is required", 400)
    
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response("Valid category_id is required", 400)
    
    if not (0.0 <= confidence <= 1.0):
        return error_response("Confidence must be between 0.0 and 1.0", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists and belongs to user
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            normalized_note = normalize_text(note)
            
            # Check if similar pattern already exists for this user
            cursor.execute("""
                SELECT id, usage_count FROM categorization_patterns
                WHERE note_pattern = %s AND category_id = %s AND user_id = %s
            """, (normalized_note, category_id, user_id))
            
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE categorization_patterns
                    SET usage_count = usage_count + 1,
                        confidence_score = GREATEST(confidence_score, %s),
                        last_used = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (confidence, existing['id']))
            else:
                pattern_id = generate_uuid()
                cursor.execute("""
                    INSERT INTO categorization_patterns
                    (id, note_pattern, category_id, confidence_score, usage_count, user_id)
                    VALUES (%s, %s, %s, %s, 1, %s)
                """, (pattern_id, normalized_note, category_id, confidence, user_id))
            
            db.commit()
            return jsonify({'message': 'Pattern learned successfully'}), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to learn pattern")


@smart_categorization_bp.route('/patterns', methods=['GET'])
@require_auth
def get_patterns():
    """
    GET /smart-categorization/patterns
    Get all learned categorization patterns for authenticated user.
    """
    user_id = get_current_user_id()
    
    category_id = request.args.get('category_id')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    if category_id:
        valid, error = validate_uuid(category_id)
        if not valid:
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
                WHERE c.is_active = TRUE AND cp.user_id = %s
            """
            params = [user_id]
            
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


@smart_categorization_bp.route('/patterns/<pattern_id>', methods=['DELETE'])
@require_auth
def delete_pattern(pattern_id):
    """
    DELETE /smart-categorization/patterns/{id}
    Delete a learned pattern (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(pattern_id)
    if not valid:
        return error_response("Invalid pattern ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "DELETE FROM categorization_patterns WHERE id = %s AND user_id = %s",
                (pattern_id, user_id)
            )
            
            if cursor.rowcount == 0:
                return error_response("Pattern not found", 404)
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete pattern")


@smart_categorization_bp.route('/cleanup-patterns', methods=['POST'])
@require_auth
def cleanup_patterns():
    """
    POST /smart-categorization/cleanup-patterns
    Clean up old or low-confidence patterns for authenticated user.
    """
    user_id = get_current_user_id()
    
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
                WHERE user_id = %s
                AND (last_used < %s OR confidence_score < %s OR usage_count < %s)
                AND created_at < %s
            """, (user_id, cutoff_date, min_confidence, min_usage, cutoff_date))
            
            deleted_count = cursor.rowcount
            db.commit()
            
            return jsonify({
                'message': f'Cleaned up {deleted_count} patterns',
                'deleted_count': deleted_count
            })
            
    except Exception as e:
        return handle_db_error(e, "Failed to cleanup patterns")