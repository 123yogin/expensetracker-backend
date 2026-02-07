"""
Templates Blueprint - Handles expense template management for quick entry.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own templates and shortcuts
"""

import psycopg2
from flask import Blueprint, request, jsonify, g

from database import get_db
from validators import (
    validate_uuid,
    validate_amount,
    format_amount,
    generate_uuid
)
from errors import handle_db_error, error_response
from auth import require_auth, get_current_user_id


templates_bp = Blueprint('templates', __name__, url_prefix='/templates')


def format_template(row) -> dict:
    """Format a template row for JSON response."""
    return {
        'id': str(row['id']),
        'name': row['name'],
        'category_id': str(row['category_id']),
        'category_name': row['category_name'],
        'default_amount': format_amount(row['default_amount']),
        'note_template': row['note_template'],
        'is_active': row['is_active'],
        'created_at': str(row['created_at']) if row['created_at'] else None
    }


@templates_bp.route('', methods=['GET'])
@require_auth
def get_templates():
    """
    GET /templates
    List all active expense templates for the authenticated user.
    """
    user_id = get_current_user_id()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.is_active = TRUE AND t.user_id = %s
                ORDER BY t.name
            """, (user_id,))
            templates = [format_template(row) for row in cursor.fetchall()]
            return jsonify(templates)
    except Exception as e:
        return handle_db_error(e, "Failed to fetch templates")


@templates_bp.route('', methods=['POST'])
@require_auth
def create_template():
    """
    POST /templates
    Create a new expense template for the authenticated user.
    """
    user_id = get_current_user_id()
    data = request.get_json()
    
    # Validate required fields
    name = data.get('name', '').strip()
    if not name:
        return error_response("Template name is required", 400)
    
    category_id = data.get('category_id')
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response("Valid category_id is required", 400)
    
    # Optional fields
    default_amount = data.get('default_amount')
    if default_amount is not None:
        validated_amount, error = validate_amount(default_amount)
        if error:
            return error_response(error, 400)
        default_amount = str(validated_amount)
    
    note_template = data.get('note_template', '').strip()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists AND belongs to user
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            # Create template with user_id
            template_id = generate_uuid()
            cursor.execute("""
                INSERT INTO expense_templates (id, name, category_id, default_amount, note_template, user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (template_id, name, category_id, default_amount, note_template, user_id))
            
            # Fetch created template with category name
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.id = %s AND t.user_id = %s
            """, (template_id, user_id))
            
            template = format_template(cursor.fetchone())
            db.commit()
            return jsonify(template), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to create template")


@templates_bp.route('/<template_id>', methods=['PUT'])
@require_auth
def update_template(template_id):
    """
    PUT /templates/{id}
    Update an existing template (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(template_id)
    if not valid:
        return error_response("Invalid template ID", 400)
    
    data = request.get_json()
    
    # Validate fields if provided
    name = data.get('name', '').strip() if 'name' in data else None
    if name is not None and not name:
        return error_response("Template name cannot be empty", 400)
    
    category_id = data.get('category_id')
    if category_id is not None:
        valid, error = validate_uuid(category_id)
        if not valid:
            return error_response("Invalid category_id", 400)
    
    default_amount = data.get('default_amount')
    if default_amount is not None:
        validated_amount, error = validate_amount(default_amount)
        if error:
            return error_response(error, 400)
        default_amount = str(validated_amount)
    
    note_template = data.get('note_template', '').strip() if 'note_template' in data else None
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if template exists AND belongs to user
            cursor.execute(
                "SELECT id FROM expense_templates WHERE id = %s AND user_id = %s",
                (template_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Template not found", 404)
            
            # Check if category exists AND belongs to user (if provided)
            if category_id:
                cursor.execute(
                    "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                    (category_id, user_id)
                )
                if not cursor.fetchone():
                    return error_response("Category not found or inactive", 404)
            
            # Build update query
            update_fields = []
            update_values = []
            
            if name is not None:
                update_fields.append("name = %s")
                update_values.append(name)
            if category_id is not None:
                update_fields.append("category_id = %s")
                update_values.append(category_id)
            if default_amount is not None:
                update_fields.append("default_amount = %s")
                update_values.append(default_amount)
            if note_template is not None:
                update_fields.append("note_template = %s")
                update_values.append(note_template)
            
            if not update_fields:
                return error_response("No fields to update", 400)
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(template_id)
            update_values.append(user_id)
            
            cursor.execute(f"""
                UPDATE expense_templates 
                SET {', '.join(update_fields)}
                WHERE id = %s AND user_id = %s
            """, update_values)
            
            # Fetch updated template
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.id = %s AND t.user_id = %s
            """, (template_id, user_id))
            
            template = format_template(cursor.fetchone())
            db.commit()
            return jsonify(template)
            
    except Exception as e:
        return handle_db_error(e, "Failed to update template")


@templates_bp.route('/<template_id>', methods=['DELETE'])
@require_auth
def delete_template(template_id):
    """
    DELETE /templates/{id}
    Soft delete a template (must belong to authenticated user).
    """
    user_id = get_current_user_id()
    
    valid, error = validate_uuid(template_id)
    if not valid:
        return error_response("Invalid template ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE expense_templates 
                SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND is_active = TRUE AND user_id = %s
            """, (template_id, user_id))
            
            if cursor.rowcount == 0:
                return error_response("Template not found", 404)
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete template")


# Quick Shortcuts endpoints
@templates_bp.route('/shortcuts', methods=['GET'])
@require_auth
def get_shortcuts():
    """
    GET /templates/shortcuts
    Get quick shortcuts for the authenticated user's dashboard.
    """
    user_id = get_current_user_id()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.category_id, s.position, s.is_active,
                       c.name as category_name
                FROM quick_shortcuts s
                JOIN categories c ON s.category_id = c.id
                WHERE s.is_active = TRUE AND c.is_active = TRUE AND s.user_id = %s
                ORDER BY s.position
            """, (user_id,))
            shortcuts = []
            for row in cursor.fetchall():
                shortcuts.append({
                    'id': str(row['id']),
                    'category_id': str(row['category_id']),
                    'category_name': row['category_name'],
                    'position': row['position']
                })
            return jsonify(shortcuts)
    except Exception as e:
        return handle_db_error(e, "Failed to fetch shortcuts")


@templates_bp.route('/shortcuts', methods=['POST'])
@require_auth
def create_shortcut():
    """
    POST /templates/shortcuts
    Create a new quick shortcut for the authenticated user.
    """
    user_id = get_current_user_id()
    data = request.get_json()
    
    category_id = data.get('category_id')
    valid, error = validate_uuid(category_id)
    if not valid:
        return error_response("Valid category_id is required", 400)
    
    position = data.get('position')
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists AND belongs to user
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s AND is_active = TRUE AND user_id = %s",
                (category_id, user_id)
            )
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            # Auto-assign position if not provided
            if position is None:
                cursor.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM quick_shortcuts WHERE is_active = TRUE AND user_id = %s",
                    (user_id,)
                )
                position = cursor.fetchone()[0]
            
            # Create shortcut with user_id
            shortcut_id = generate_uuid()
            cursor.execute("""
                INSERT INTO quick_shortcuts (id, category_id, position, user_id)
                VALUES (%s, %s, %s, %s)
            """, (shortcut_id, category_id, position, user_id))
            
            # Fetch created shortcut
            cursor.execute("""
                SELECT s.id, s.category_id, s.position, s.is_active,
                       c.name as category_name
                FROM quick_shortcuts s
                JOIN categories c ON s.category_id = c.id
                WHERE s.id = %s AND s.user_id = %s
            """, (shortcut_id, user_id))
            
            row = cursor.fetchone()
            shortcut = {
                'id': str(row['id']),
                'category_id': str(row['category_id']),
                'category_name': row['category_name'],
                'position': row['position']
            }
            
            db.commit()
            return jsonify(shortcut), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to create shortcut")