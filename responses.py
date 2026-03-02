"""
Standardized API Response Builder
==================================
All API endpoints MUST return responses through these helpers
to ensure consistent JSON structure across the application.

Success response:
{
    "success": true,
    "data": { ... },
    "meta": { "page": 1, "per_page": 50, "total": 200 }  // for paginated
}

Error response:
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human readable message",
        "details": { ... }  // optional
    }
}
"""

from flask import jsonify


# ---- Error Codes ----

class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    DB_ERROR = "DB_ERROR"
    BAD_REQUEST = "BAD_REQUEST"


# ---- Success Responses ----

def success(data=None, status=200, meta=None):
    """Return a standardized success response."""
    body = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def created(data=None):
    """Return a 201 Created response."""
    return success(data, status=201)


def no_content():
    """Return a 204 No Content response."""
    return "", 204


def paginated(items, page, per_page, total):
    """Return a paginated success response."""
    return success(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


# ---- Error Responses ----

def error(message, status=400, code=ErrorCode.BAD_REQUEST, details=None):
    """Return a standardized error response."""
    body = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def validation_error(message, details=None):
    return error(message, 400, ErrorCode.VALIDATION_ERROR, details)


def not_found(message="Resource not found"):
    return error(message, 404, ErrorCode.NOT_FOUND)


def unauthorized(message="Authentication required"):
    return error(message, 401, ErrorCode.UNAUTHORIZED)


def forbidden(message="Access denied"):
    return error(message, 403, ErrorCode.FORBIDDEN)


def conflict(message="Resource already exists"):
    return error(message, 409, ErrorCode.CONFLICT)


def server_error(message="Internal server error"):
    return error(message, 500, ErrorCode.SERVER_ERROR)


def db_error(message="Database error"):
    return error(message, 500, ErrorCode.DB_ERROR)
