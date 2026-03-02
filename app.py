"""
Personal Expense Tracker API
==================================
Flask REST API with PostgreSQL backend.

Production-hardened:
- Centralized configuration (no hardcoded secrets)
- Connection pooling
- Rate limiting
- Security headers
- Request logging with timing
- Standardized error handling
- Health check with DB verification
"""

import logging
import os
import sys

from flask import Flask, jsonify
from flask_cors import CORS


def create_app(testing: bool = False):
    """
    Application factory pattern.

    Args:
        testing: If True, enable testing mode

    Returns:
        Configured Flask application
    """
    # ---- Configuration ----
    from config import get_config
    cfg = get_config()

    # ---- Logging ----
    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    # Log config warnings
    for warning in cfg.validate():
        logger.warning("CONFIG: %s", warning)

    # ---- Flask App ----
    app = Flask(__name__)
    app.config.update(
        TESTING=testing,
        DEBUG=cfg.DEBUG,
        SECRET_KEY=cfg.SECRET_KEY,
        MAX_CONTENT_LENGTH=cfg.MAX_UPLOAD_BYTES,
    )

    # ---- CORS ----
    CORS(
        app,
        origins=cfg.FRONTEND_ORIGINS,
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Cache-Control"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    # ---- Middleware ----
    from middleware import register_middleware, setup_rate_limiting
    register_middleware(app)
    setup_rate_limiting(app)

    # ---- Database ----
    from database import init_pool, close_db, run_migrations
    app.teardown_appcontext(close_db)

    # ---- Error Handlers ----
    from errors import register_error_handlers
    register_error_handlers(app)

    # ---- Register Blueprints (existing) ----
    from blueprints.categories import categories_bp
    from blueprints.expenses import expenses_bp
    from blueprints.reports import reports_bp
    from blueprints.income import income_bp
    from blueprints.budgets import budgets_bp
    from blueprints.recurring_expenses import recurring_bp
    from blueprints.templates import templates_bp
    from blueprints.smart_features import smart_bp
    from blueprints.groups import groups_bp
    from blueprints.notifications import notifications_bp
    from blueprints.receipts import receipts_bp
    from blueprints.smart_categorization import smart_categorization_bp
    from blueprints.voice import voice_bp
    from blueprints.export import export_bp

    app.register_blueprint(categories_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(income_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(recurring_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(smart_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(smart_categorization_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(export_bp)

    # ---- Health Check (with DB verification) ----
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint for monitoring and load balancers."""
        health = {"status": "healthy", "service": "expense-tracker-api"}

        # Verify database connectivity
        try:
            from database import get_db
            db = get_db()
            with db.cursor() as cursor:
                cursor.execute("SELECT 1")
            health["database"] = "connected"
        except Exception as e:
            health["status"] = "degraded"
            health["database"] = f"error: {str(e)}"
            return jsonify(health), 503

        return jsonify(health), 200

    # ---- API Info ----
    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "Personal Expense Tracker API",
            "version": "2.0.0",
            "docs": "/health for status",
        }), 200

    # ---- Database Init ----
    with app.app_context():
        init_pool(app)
        try:
            run_migrations()
        except Exception as e:
            logger.error("Migration failed (app will still start): %s", e)

    logger.info(
        "Application started (debug=%s, origins=%s)",
        cfg.DEBUG,
        cfg.FRONTEND_ORIGINS,
    )

    return app


# Create app instance for Gunicorn: gunicorn app:app
app = create_app()


# Local development
if __name__ == "__main__":
    from config import get_config
    cfg = get_config()
    app.run(
        debug=cfg.DEBUG,
        host="0.0.0.0",
        port=cfg.PORT,
    )
