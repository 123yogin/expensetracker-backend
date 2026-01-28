"""
Templates Blueprint - Handles expense template management for quick entry.

Features:
- CRUD operations for expense templates
- Quick shortcuts management
- Template-based expense creation
"""

import psycopg2
from flask import Blueprint, request, jsonify

from database import get_db
from validators import (
    validate_uuid,
    validate_amount,
    format_amount,
    generate_uuid
)
from errors import handle_db_error, error_response


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
def get_templates():
    """
    GET /templates
    List all active expense templates.
    
    Returns:
        200: List of template objects
    """
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.is_active = TRUE
                ORDER BY t.name
            """)
            templates = [format_template(row) for row in cursor.fetchall()]
            return jsonify(templates)
    except Exception as e:
        return handle_db_error(e, "Failed to fetch templates")


@templates_bp.route('', methods=['POST'])
def create_template():
    """
    POST /templates
    Create a new expense template.
    
    Body:
        name: string (required)
        category_id: UUID (required)
        default_amount: decimal (optional)
        note_template: string (optional)
    
    Returns:
        201: Created template object
        400: Validation error
    """
    data = request.get_json()
    
    # Validate required fields
    name = data.get('name', '').strip()
    if not name:
        return error_response("Template name is required", 400)
    
    category_id = data.get('category_id')
    if not validate_uuid(category_id):
        return error_response("Valid category_id is required", 400)
    
    # Optional fields
    default_amount = data.get('default_amount')
    if default_amount is not None:
        valid, error = validate_amount(default_amount)
        if not valid:
            return error_response(error, 400)
    
    note_template = data.get('note_template', '').strip()
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists
            cursor.execute("SELECT id FROM categories WHERE id = %s AND is_active = TRUE", (category_id,))
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            # Create template
            template_id = generate_uuid()
            cursor.execute("""
                INSERT INTO expense_templates (id, name, category_id, default_amount, note_template)
                VALUES (%s, %s, %s, %s, %s)
            """, (template_id, name, category_id, default_amount, note_template))
            
            # Fetch created template with category name
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.id = %s
            """, (template_id,))
            
            template = format_template(cursor.fetchone())
            db.commit()
            return jsonify(template), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to create template")


@templates_bp.route('/<template_id>', methods=['PUT'])
def update_template(template_id):
    """
    PUT /templates/{id}
    Update an existing template.
    
    Returns:
        200: Updated template object
        404: Template not found
        400: Validation error
    """
    if not validate_uuid(template_id):
        return error_response("Invalid template ID", 400)
    
    data = request.get_json()
    
    # Validate fields if provided
    name = data.get('name', '').strip() if 'name' in data else None
    if name is not None and not name:
        return error_response("Template name cannot be empty", 400)
    
    category_id = data.get('category_id')
    if category_id is not None and not validate_uuid(category_id):
        return error_response("Invalid category_id", 400)
    
    default_amount = data.get('default_amount')
    if default_amount is not None:
        valid, error = validate_amount(default_amount)
        if not valid:
            return error_response(error, 400)
    
    note_template = data.get('note_template', '').strip() if 'note_template' in data else None
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if template exists
            cursor.execute("SELECT id FROM expense_templates WHERE id = %s", (template_id,))
            if not cursor.fetchone():
                return error_response("Template not found", 404)
            
            # Check if category exists (if provided)
            if category_id:
                cursor.execute("SELECT id FROM categories WHERE id = %s AND is_active = TRUE", (category_id,))
                if not cursor.fetchone():
                    return error_response("Category not found or inactive", 404)
            
            # Build update query dynamically
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
            
            cursor.execute(f"""
                UPDATE expense_templates 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """, update_values)
            
            # Fetch updated template
            cursor.execute("""
                SELECT t.id, t.name, t.category_id, t.default_amount, 
                       t.note_template, t.is_active, t.created_at,
                       c.name as category_name
                FROM expense_templates t
                JOIN categories c ON t.category_id = c.id
                WHERE t.id = %s
            """, (template_id,))
            
            template = format_template(cursor.fetchone())
            db.commit()
            return jsonify(template)
            
    except Exception as e:
        return handle_db_error(e, "Failed to update template")


@templates_bp.route('/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    """
    DELETE /templates/{id}
    Soft delete a template (set is_active = FALSE).
    
    Returns:
        204: Template deleted
        404: Template not found
    """
    if not validate_uuid(template_id):
        return error_response("Invalid template ID", 400)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE expense_templates 
                SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND is_active = TRUE
            """, (template_id,))
            
            if cursor.rowcount == 0:
                return error_response("Template not found", 404)
            
            db.commit()
            return '', 204
            
    except Exception as e:
        return handle_db_error(e, "Failed to delete template")


# Quick Shortcuts endpoints
@templates_bp.route('/shortcuts', methods=['GET'])
def get_shortcuts():
    """
    GET /templates/shortcuts
    Get quick shortcuts for dashboard.
    
    Returns:
        200: List of shortcut objects
    """
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.category_id, s.position, s.is_active,
                       c.name as category_name
                FROM quick_shortcuts s
                JOIN categories c ON s.category_id = c.id
                WHERE s.is_active = TRUE AND c.is_active = TRUE
                ORDER BY s.position
            """)
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
def create_shortcut():
    """
    POST /templates/shortcuts
    Create a new quick shortcut.
    
    Body:
        category_id: UUID (required)
        position: integer (optional, auto-assigned if not provided)
    
    Returns:
        201: Created shortcut object
        400: Validation error
    """
    data = request.get_json()
    
    category_id = data.get('category_id')
    if not validate_uuid(category_id):
        return error_response("Valid category_id is required", 400)
    
    position = data.get('position')
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            # Check if category exists
            cursor.execute("SELECT id FROM categories WHERE id = %s AND is_active = TRUE", (category_id,))
            if not cursor.fetchone():
                return error_response("Category not found or inactive", 404)
            
            # Auto-assign position if not provided
            if position is None:
                cursor.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM quick_shortcuts WHERE is_active = TRUE")
                position = cursor.fetchone()[0]
            
            # Create shortcut
            shortcut_id = generate_uuid()
            cursor.execute("""
                INSERT INTO quick_shortcuts (id, category_id, position)
                VALUES (%s, %s, %s)
            """, (shortcut_id, category_id, position))
            
            # Fetch created shortcut
            cursor.execute("""
                SELECT s.id, s.category_id, s.position, s.is_active,
                       c.name as category_name
                FROM quick_shortcuts s
                JOIN categories c ON s.category_id = c.id
                WHERE s.id = %s
            """, (shortcut_id,))
            
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