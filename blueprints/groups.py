"""
Groups Blueprint - Handles group expense splitting functionality.

Production-hardened endpoints with USER ISOLATION:
- AUTHENTICATION REQUIRED: All endpoints require valid JWT
- USER ISOLATION: Each user can only access their own groups
"""

from flask import Blueprint, request, jsonify, g
from database import get_db
from errors import handle_db_error, error_response
from validators import generate_uuid, validate_uuid, validate_amount, validate_date
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

            # Get all members for these groups in a single query (avoids N+1).
            if groups:
                group_ids = [str(g['id']) for g in groups]
                cursor.execute("""
                    SELECT id, name, group_id
                    FROM group_members
                    WHERE group_id::text = ANY(%s::text[])
                """, (group_ids,))
                members_by_group = {}
                for m in cursor.fetchall() or []:
                    members_by_group.setdefault(str(m['group_id']), []).append(
                        {'id': m['id'], 'name': m['name']}
                    )
                for group in groups:
                    group['members'] = members_by_group.get(str(group['id']), [])

            return jsonify(groups)
    except Exception as e:
        return handle_db_error(e, "Failed to get groups")

@groups_bp.route('/groups', methods=['POST'])
@require_auth
def create_group():
    """Create a new group for the authenticated user"""
    user_id = get_current_user_id()
    
    data = request.get_json()
    if not data:
        return error_response('Request body is required', 400)
    name = data.get('name')
    description = data.get('description')
    members = data.get('members', [])  # List of member names

    if not name:
        return error_response('Group name is required', 400)

    db = get_db()
    try:
        with db.cursor() as cursor:
            group_id = generate_uuid()
            # Insert with user_id
            cursor.execute("""
                INSERT INTO groups (id, name, description, user_id)
                VALUES (%s, %s, %s, %s)
            """, (group_id, name, description, user_id))

            # Add members (coerce to string; skip blanks / non-strings)
            for member_name in (members or []):
                member_str = str(member_name).strip() if member_name is not None else ''
                if member_str:
                    member_id = generate_uuid()
                    cursor.execute("""
                        INSERT INTO group_members (id, group_id, name)
                        VALUES (%s, %s, %s)
                    """, (member_id, group_id, member_str))

            db.commit()
            return jsonify({'id': group_id, 'message': 'Group created successfully'}), 201
    except Exception as e:
        db.rollback()
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

            # Get all splits for these expenses in a single query (avoids N+1).
            if expenses:
                expense_ids = [str(e['id']) for e in expenses]
                cursor.execute("""
                    SELECT es.expense_id, es.amount, gm.name as member_name
                    FROM expense_splits es
                    JOIN group_members gm ON es.member_id = gm.id
                    WHERE es.expense_id::text = ANY(%s::text[])
                """, (expense_ids,))
                splits_by_expense = {}
                for s in cursor.fetchall() or []:
                    splits_by_expense.setdefault(str(s['expense_id']), []).append(
                        {'amount': s['amount'], 'member_name': s['member_name']}
                    )
                for expense in expenses:
                    expense['splits'] = splits_by_expense.get(str(expense['id']), [])

            return jsonify(expenses)
    except Exception as e:
        return handle_db_error(e, "Failed to get group expenses")

@groups_bp.route('/groups/<group_id>/expenses', methods=['POST'])
@require_auth
def add_group_expense(group_id):
    """Add a split expense to a group (must belong to authenticated user)"""
    user_id = get_current_user_id()
    
    data = request.get_json()
    if not data:
        return error_response('Request body is required', 400)
    description = data.get('description')
    date = data.get('date')
    paid_by_id = data.get('paid_by_id')
    splits = data.get('splits')  # List of {member_id: uuid, amount: float}

    if not all([data.get('amount'), description, date, paid_by_id, splits]):
        return error_response('Missing required fields', 400)

    # Validate the group id (URL), payer, amount and date up front.
    valid, err = validate_uuid(group_id)
    if not valid:
        return error_response('Invalid group ID', 400)
    valid, err = validate_uuid(paid_by_id)
    if not valid:
        return error_response('Invalid paid_by_id', 400)
    amount, err = validate_amount(data.get('amount'))
    if err:
        return error_response(err, 400)
    valid, err = validate_date(date)
    if not valid:
        return error_response(err, 400)

    # Validate splits: must be a non-empty list of {member_id (uuid), amount}.
    if not isinstance(splits, list) or not splits:
        return error_response('splits must be a non-empty list', 400)
    validated_splits = []
    for split in splits:
        if not isinstance(split, dict):
            return error_response('Each split must be an object', 400)
        valid, err = validate_uuid(split.get('member_id'))
        if not valid:
            return error_response('Invalid split member_id', 400)
        split_amount, err = validate_amount(split.get('amount'))
        if err:
            return error_response(f"Invalid split amount: {err}", 400)
        validated_splits.append((split['member_id'], split_amount))

    # Splits must not exceed the total expense amount.
    if sum((sa for _, sa in validated_splits)) > amount:
        return error_response('Split amounts exceed the expense total', 400)

    db = get_db()
    try:
        with db.cursor() as cursor:
            # Verify group ownership
            cursor.execute(
                "SELECT id FROM groups WHERE id = %s AND user_id = %s",
                (group_id, user_id)
            )
            if not cursor.fetchone():
                return error_response('Group not found', 404)

            # Verify the payer is a member of this group.
            cursor.execute(
                "SELECT 1 FROM group_members WHERE id = %s AND group_id = %s",
                (paid_by_id, group_id)
            )
            if not cursor.fetchone():
                return error_response('paid_by_id is not a member of this group', 400)

            expense_id = generate_uuid()

            # Create the expense record with user_id
            cursor.execute("""
                INSERT INTO expenses (id, amount, note, date, group_id, paid_by_member_id, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (expense_id, amount, description, date, group_id, paid_by_id, user_id))

            # Create split records (only members of this group)
            for member_id, split_amount in validated_splits:
                cursor.execute(
                    "SELECT 1 FROM group_members WHERE id = %s AND group_id = %s",
                    (member_id, group_id)
                )
                if not cursor.fetchone():
                    db.rollback()
                    return error_response('A split member_id is not in this group', 400)
                cursor.execute("""
                    INSERT INTO expense_splits (id, expense_id, member_id, amount)
                    VALUES (%s, %s, %s, %s)
                """, (generate_uuid(), expense_id, member_id, split_amount))

            db.commit()
            return jsonify({'id': expense_id, 'message': 'Expense added successfully'}), 201

    except Exception as e:
        db.rollback()
        return handle_db_error(e, "Failed to add group expense")
