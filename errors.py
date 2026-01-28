"""
Centralized error handling for the Expense Tracker API.

Production-hardened error responses:
- Consistent JSON error format
- No stack traces leaked to clients
- Proper HTTP status codes
- Logging for debugging (without exposing to users)
"""

import logging
from functools import wraps
from flask import jsonify
import psycopg2
from psycopg2 import errors as pg_errors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('expense_tracker')


class APIError(Exception):
    """
    Base exception for API errors.
    Allows raising custom errors with specific status codes.
    """
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(APIError):
    """Resource not found (404)."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)


class ValidationError(APIError):
    """Validation error (400)."""
    def __init__(self, message: str):
        super().__init__(message, 400)


class ConflictError(APIError):
    """Conflict error, e.g., duplicate entry (409)."""
    def __init__(self, message: str):
        super().__init__(message, 409)


def error_response(message: str, status_code: int = 400):
    """
    Create a standardized error response.
    
    Args:
        message: User-friendly error message
        status_code: HTTP status code
        
    Returns:
        Tuple of (response, status_code)
    """
    return jsonify({'error': message}), status_code


def handle_db_error(e: Exception, context_message: str = None):
    """
    Handle database errors gracefully.
    
    Args:
        e: The exception that occurred
        context_message: Optional context message for logging (e.g., "Failed to fetch templates")
    """
    error_str = str(e)
    context = f" - {context_message}" if context_message else ""
    
    # Handle specific PostgreSQL errors via psycopg2
    if isinstance(e, pg_errors.UniqueViolation):
        logger.warning(f"UniqueViolation{context}: {error_str}")
        return error_response("A record with this value already exists", 409)
    
    if isinstance(e, pg_errors.ForeignKeyViolation):
        logger.warning(f"ForeignKeyViolation{context}: {error_str}")
        return error_response("Referenced record does not exist", 400)
    
    if isinstance(e, pg_errors.NotNullViolation):
        logger.warning(f"NotNullViolation{context}: {error_str}")
        return error_response("Required field is missing", 400)
    
    if isinstance(e, (psycopg2.OperationalError, psycopg2.DatabaseError)):
        logger.error(f"Database Error{context}: {error_str}")
        # Check if it's a table doesn't exist error
        if "does not exist" in error_str.lower() or "relation" in error_str.lower():
            logger.error(f"Table may not exist. Error: {error_str}")
            return error_response("Database table not found. Please run migrations.", 500)
        return error_response("Database connection error", 500)
    
    # Generic error - log it but don't expose details
    logger.error(f"Unexpected error{context}: {type(e).__name__}: {error_str}")
    return error_response("An unexpected error occurred", 500)


def register_error_handlers(app):
    """
    Register global error handlers with Flask app.
    Called from create_app() in app.py.
    """
    
    @app.errorhandler(APIError)
    def handle_api_error(error):
        """Handle custom API errors."""
        return error_response(error.message, error.status_code)
    
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors."""
        return error_response("Bad request", 400)
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors."""
        return error_response("Resource not found", 404)
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        return error_response("Method not allowed", 405)
    
    @app.errorhandler(500)
    def internal_error(error):
        """
        Handle 500 Internal Server Error.
        Log the actual error but don't expose it to the client.
        """
        logger.error(f"Internal server error: {error}")
        return error_response("Internal server error", 500)
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """
        Catch-all handler for unexpected exceptions.
        Ensures no stack traces leak to clients in production.
        """
        logger.exception(f"Unhandled exception: {error}")
        return error_response("An unexpected error occurred", 500)
