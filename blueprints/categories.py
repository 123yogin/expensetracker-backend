"""
Categories Blueprint - Handles all category-related API endpoints.

Production-hardened endpoints:
- Centralized validation using validators module
- Flask g context for database connections
- Proper error handling without leaking stack traces
"""

import sqlite3
from flask import Blueprint, request, jsonify

from database import get_db
from validators import validate_uuid, generate_uuid
from errors import handle_db_error, error_response


categories_bp = Blueprint('categories', __name__, url_prefix='/categories')


def format_category(row) -> dict:
    """
    Format a category row for JSON response.
    Helper function to eliminate code duplication.
    """
    return {
        'id': row['id'],
        'name': row['name'],
        'is_active': bool(row['is_active']),
        'created_at': row['created_at']
    }


@categories_bp.route('', methods=['GET'])
def get_categories():
    """
    GET /categories
    Returns list of all categories (active and inactive).
    Ordered: active first, then alphabetically by name.
    """
    db = get_db()
    try:
        cursor = db.execute(
            """SELECT id, name, is_active, created_at 
               FROM categories 
               ORDER BY is_active DESC, name"""
        )
        categories = cursor.fetchall()
        return jsonify([format_category(row) for row in categories]), 200
    except Exception as e:
        return handle_db_error(e)


@categories_bp.route('', methods=['POST'])
def create_category():
    """
    POST /categories
    Creates a new category.
    
    Request body: { "name": "Category Name" }
    
    Returns:
        201: Created category object
        400: Validation error
        409: Category name already exists
    """
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    name = data.get('name')
    
    if not name or not isinstance(name, str) or not name.strip():
        return error_response('Category name is required', 400)
    
    name = name.strip()
    
    # Validate name length (reasonable limit)
    if len(name) > 100:
        return error_response('Category name must be 100 characters or less', 400)
    
    # Generate UUID in backend only
    category_id = generate_uuid()
    
    db = get_db()
    try:
        db.execute(
            "INSERT INTO categories (id, name) VALUES (?, ?)",
            (category_id, name)
        )
        db.commit()
        
        # Fetch the created category
        cursor = db.execute(
            "SELECT id, name, is_active, created_at FROM categories WHERE id = ?",
            (category_id,)
        )
        category = cursor.fetchone()
        
        return jsonify(format_category(category)), 201
        
    except sqlite3.IntegrityError as e:
        if 'UNIQUE constraint failed' in str(e):
            return error_response('Category name already exists', 409)
        return handle_db_error(e)
    except Exception as e:
        return handle_db_error(e)


@categories_bp.route('/<category_id>', methods=['PUT'])
def update_category(category_id):
    """
    PUT /categories/<uuid>
    Renames an existing category.
    
    Request body: { "name": "New Category Name" }
    
    Returns:
        200: Updated category object
        400: Validation error or invalid UUID
        404: Category not found
        409: Category name already exists
    """
    # Validate UUID format
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response(error, 400)
    
    data = request.get_json()
    
    if not data:
        return error_response('Request body is required', 400)
    
    name = data.get('name')
    
    if not name or not isinstance(name, str) or not name.strip():
        return error_response('Category name is required', 400)
    
    name = name.strip()
    
    if len(name) > 100:
        return error_response('Category name must be 100 characters or less', 400)
    
    db = get_db()
    try:
        # Check if category exists
        cursor = db.execute(
            "SELECT id FROM categories WHERE id = ?",
            (category_id,)
        )
        if not cursor.fetchone():
            return error_response('Category not found', 404)
        
        db.execute(
            "UPDATE categories SET name = ? WHERE id = ?",
            (name, category_id)
        )
        db.commit()
        
        # Fetch the updated category
        cursor = db.execute(
            "SELECT id, name, is_active, created_at FROM categories WHERE id = ?",
            (category_id,)
        )
        category = cursor.fetchone()
        
        return jsonify(format_category(category)), 200
        
    except sqlite3.IntegrityError as e:
        if 'UNIQUE constraint failed' in str(e):
            return error_response('Category name already exists', 409)
        return handle_db_error(e)
    except Exception as e:
        return handle_db_error(e)


@categories_bp.route('/<category_id>/status', methods=['PATCH'])
def update_category_status(category_id):
    """
    PATCH /categories/<uuid>/status
    Updates a category's active status.
    
    Request body: { "is_active": boolean }
    
    Returns:
        200: Updated category object
        400: Validation error or invalid UUID
        404: Category not found
    """
    # Validate UUID format
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response(error, 400)
    
    data = request.get_json()
    
    if not data or 'is_active' not in data:
        return error_response('is_active status is required', 400)
    
    # Ensure is_active is a boolean
    if not isinstance(data['is_active'], bool):
        return error_response('is_active must be a boolean', 400)
    
    is_active = 1 if data['is_active'] else 0
    
    db = get_db()
    try:
        cursor = db.execute(
            "SELECT id FROM categories WHERE id = ?",
            (category_id,)
        )
        if not cursor.fetchone():
            return error_response('Category not found', 404)
        
        db.execute(
            "UPDATE categories SET is_active = ? WHERE id = ?",
            (is_active, category_id)
        )
        db.commit()
        
        cursor = db.execute(
            "SELECT id, name, is_active, created_at FROM categories WHERE id = ?",
            (category_id,)
        )
        category = cursor.fetchone()
        
        return jsonify(format_category(category)), 200
        
    except Exception as e:
        return handle_db_error(e)


@categories_bp.route('/<category_id>', methods=['DELETE'])
def delete_category(category_id):
    """
    DELETE /categories/<uuid>
    Soft deletes a category by setting is_active = 0.
    
    Returns:
        200: Success message
        400: Invalid UUID or category already deleted
        404: Category not found
    """
    # Validate UUID format
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response(error, 400)
    
    db = get_db()
    try:
        # Check if category exists and get current status
        cursor = db.execute(
            "SELECT id, is_active FROM categories WHERE id = ?",
            (category_id,)
        )
        category = cursor.fetchone()
        
        if not category:
            return error_response('Category not found', 404)
        
        if category['is_active'] == 0:
            return error_response('Category is already deleted', 400)
        
        # Soft delete - set is_active to 0
        db.execute(
            "UPDATE categories SET is_active = 0 WHERE id = ?",
            (category_id,)
        )
        db.commit()
        
        return jsonify({'message': 'Category deleted successfully'}), 200
        
    except Exception as e:
        return handle_db_error(e)
