from flask import Blueprint, request, jsonify
from database import get_db
from errors import handle_db_error
from validators import generate_uuid
import json

groups_bp = Blueprint('groups', __name__)

@groups_bp.route('/groups', methods=['GET'])
def get_groups():
    """Get all groups with their members"""
    try:
        db = get_db()
        with db.cursor() as cursor:
            # Get groups
            cursor.execute("""
                SELECT id, name, description, created_at 
                FROM groups 
                ORDER BY created_at DESC
            """)
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
def create_group():
    """Create a new group"""
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    members = data.get('members', []) # List of member names
    
    if not name:
        return jsonify({'error': 'Group name is required'}), 400
        
    try:
        db = get_db()
        with db.cursor() as cursor:
            group_id = generate_uuid()
            cursor.execute("""
                INSERT INTO groups (id, name, description)
                VALUES (%s, %s, %s)
            """, (group_id, name, description))
            
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
def get_group_expenses(group_id):
    """Get expenses for a specific group"""
    try:
        db = get_db()
        with db.cursor() as cursor:
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
def add_group_expense(group_id):
    """Add a split expense to a group"""
    data = request.get_json()
    amount = data.get('amount')
    description = data.get('description')
    date = data.get('date')
    paid_by_id = data.get('paid_by_id')
    splits = data.get('splits') # List of {member_id: uuid, amount: float}
    
    if not all([amount, description, date, paid_by_id, splits]):
        return jsonify({'error': 'Missing required fields'}), 400
        
    try:
        db = get_db()
        with db.cursor() as cursor:
            expense_id = generate_uuid()
            
            # 1. Create the expense record
            cursor.execute("""
                INSERT INTO expenses (id, amount, note, date, group_id, paid_by_member_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (expense_id, amount, description, date, group_id, paid_by_id))
            
            # 2. Create split records
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
