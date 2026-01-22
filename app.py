"""
Personal Expense Tracker API
Flask REST API with PostgreSQL backend.

Production-hardened version:
- Debug mode disabled
- CORS restricted to frontend origin
- Centralized error handling
- Database connection management via Flask g context
- Idempotent database initialization (tables created on startup if not exist)
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

from database import init_db, init_app as init_db_app
from errors import register_error_handlers
from blueprints.categories import categories_bp
from blueprints.expenses import expenses_bp
from blueprints.reports import reports_bp


# Frontend origins - configure for your deployment
# For local development with Vite, supports both default and alternate ports
FRONTEND_ORIGINS = os.environ.get('FRONTEND_ORIGINS', 'http://localhost:5173,http://localhost:5174,http://192.168.1.10:5173').split(',')


def create_app(testing: bool = False):
    """
    Application factory pattern.
    
    Args:
        testing: If True, enable testing mode
        
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Configuration
    app.config.update(
        TESTING=testing,
        # Disable debug in production - controlled via environment
        DEBUG=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
    )
    
    # Enable CORS only for the frontend origins (security hardening)
    # This prevents other websites from making requests to our API
    CORS(app, origins=FRONTEND_ORIGINS, supports_credentials=True)
    
    # Initialize database connection management
    init_db_app(app)
    
    # Register centralized error handlers
    register_error_handlers(app)
    
    # Register blueprints
    app.register_blueprint(categories_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(reports_bp)
    
    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint for monitoring."""
        return jsonify({
            'status': 'healthy',
            'message': 'Expense Tracker API is running'
        }), 200
    
    # Root endpoint - API documentation
    @app.route('/', methods=['GET'])
    def root():
        """API documentation endpoint."""
        return jsonify({
            'name': 'Personal Expense Tracker API',
            'version': '1.1.0',
            'endpoints': {
                'categories': {
                    'GET /categories': 'List all categories',
                    'POST /categories': 'Create category',
                    'PUT /categories/<id>': 'Rename category',
                    'PATCH /categories/<id>/status': 'Update category status',
                    'DELETE /categories/<id>': 'Soft delete category'
                },
                'expenses': {
                    'GET /expenses': 'List expenses (with optional filters)',
                    'POST /expenses': 'Create expense',
                    'PUT /expenses/<id>': 'Update expense',
                    'DELETE /expenses/<id>': 'Delete expense'
                },
                'reports': {
                    'GET /reports/monthly-summary': 'Get monthly summary',
                    'GET /reports/category-breakdown': 'Get category breakdown',
                    'GET /reports/daily-trend': 'Get daily trend'
                }
            }
        }), 200
    
    # Initialize database tables on app creation
    with app.app_context():
        init_db()
    
    return app


# Create app instance for Gunicorn (production)
# Gunicorn will call: gunicorn app:app
app = create_app()


# Local development
if __name__ == '__main__':
    # Run with debug DISABLED by default for production safety
    # Set FLASK_DEBUG=true environment variable for development
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5001))
    )
