"""
Groups Blueprint - Handles group expense splitting functionality.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own groups
"""

from flask import Blueprint, request, jsonify, g
from database import get_db
from errors import handle_db_error, error_response
from validators import generate_uuid
from auth import require_auth, get_current_user_id
import json

groups_bp = Blueprint('groups', __name__)

@groups_bp.route('/groups', methods=['GET'])
@require_auth
def get_groups():
    """Get all groups for the authenticated user with their members"""
    user_id = get_current_user_id()
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Get user's groups
            cursor.execute("""
                SELECT id, name, description, created_at 
                FROM groups 
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            groups = cursor.fetchall() or []
            
            # Get members for each group
            for group in groups:
                cursor.execute("""
                    SELECT id, name 
                    FROM group_members 
                    WHERE group_id = %s
                """, (group['id'],))
                group['members'] = cursor.fetchall() or []
                
            return jsonify(groups)
    except Exception as e:
        return handle_db_error(e, "Failed to get groups")

@groups_bp.route('/groups', methods=['POST'])
@require_auth
def create_group():
    """Create a new group for the authenticated user"""
    user_id = get_current_user_id()
    
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    members = data.get('members', [])  # List of member names
    
    if not name:
        return error_response('Group name is required', 400)
        
    try:
        db = get_db()
        with db.cursor() as cursor:
            group_id = generate_uuid()
            # Insert with user_id
            cursor.execute("""
                INSERT INTO groups (id, name, description, user_id)
                VALUES (%s, %s, %s, %s)
            """, (group_id, name, description, user_id))
            
            # Add members
            for member_name in members:
                if member_name.strip():
                    member_id = generate_uuid()
                    cursor.execute("""
                        INSERT INTO group_members (id, group_id, name)
                        VALUES (%s, %s, %s)
                    """, (member_id, group_id, member_name.strip()))
            
            db.commit()
            return jsonify({'id': group_id, 'message': 'Group created successfully'}), 201
    except Exception as e:
        return handle_db_error(e, "Failed to create group")

@groups_bp.route('/groups/<group_id>/expenses', methods=['GET'])
@require_auth
def get_group_expenses(group_id):
    """Get expenses for a specific group (must belong to authenticated user)"""
    user_id = get_current_user_id()
    
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Verify group ownership
            cursor.execute(
                "SELECT id FROM groups WHERE id = %s AND user_id = %s",
                (group_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Group not found', 404)
            
            # Get expenses with enhanced details
            cursor.execute("""
                SELECT e.id, e.amount, e.note as description, e.date, 
                       c.name as category_name,
                       m.name as paid_by_name,
                       m.id as paid_by_id
                FROM expenses e
                LEFT JOIN categories c ON e.category_id = c.id
                LEFT JOIN group_members m ON e.paid_by_member_id = m.id
                WHERE e.group_id = %s
                ORDER BY e.date DESC
            """, (group_id,))
            expenses = cursor.fetchall() or []
            
            # Get splits for each expense
            for expense in expenses:
                cursor.execute("""
                    SELECT es.amount, gm.name as member_name
                    FROM expense_splits es
                    JOIN group_members gm ON es.member_id = gm.id
                    WHERE es.expense_id = %s
                """, (expense['id'],))
                expense['splits'] = cursor.fetchall() or []
            
            return jsonify(expenses)
    except Exception as e:
        return handle_db_error(e, "Failed to get group expenses")

@groups_bp.route('/groups/<group_id>/expenses', methods=['POST'])
@require_auth
def add_group_expense(group_id):
    """Add a split expense to a group (must belong to authenticated user)"""
    user_id = get_current_user_id()
    
    data = request.get_json()
    amount = data.get('amount')
    description = data.get('description')
    date = data.get('date')
    paid_by_id = data.get('paid_by_id')
    splits = data.get('splits')  # List of {member_id: uuid, amount: float}
    
    if not all([amount, description, date, paid_by_id, splits]):
        return error_response('Missing required fields', 400)
        
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Verify group ownership
            cursor.execute(
                "SELECT id FROM groups WHERE id = %s AND user_id = %s",
                (group_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Group not found', 404)
            
            expense_id = generate_uuid()
            
            # Create the expense record with user_id
            cursor.execute("""
                INSERT INTO expenses (id, amount, note, date, group_id, paid_by_member_id, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (expense_id, amount, description, date, group_id, paid_by_id, user_id))
            
            # Create split records
            for split in splits:
                if split['amount'] > 0:
                    cursor.execute("""
                        INSERT INTO expense_splits (id, expense_id, member_id, amount)
                        VALUES (%s, %s, %s, %s)
                    """, (generate_uuid(), expense_id, split['member_id'], split['amount']))
            
            db.commit()
            return jsonify({'id': expense_id, 'message': 'Expense added successfully'}), 201
            
    except Exception as e:
        return handle_db_error(e, "Failed to add group expense")
