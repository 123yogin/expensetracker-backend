"""
Pagination Utilities
=====================
Standardized pagination for all list endpoints.

Usage in a controller:
    page, per_page = parse_pagination(request)
    items, total = expense_repo.get_all(user_id, page, per_page, filters)
    return paginated(items, page, per_page, total)
"""

from flask import request as flask_request

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 100


def parse_pagination(req=None):
    """
    Extract and validate page and per_page from query parameters.
    Returns (page: int, per_page: int).
    """
    if req is None:
        req = flask_request

    try:
        page = int(req.args.get("page", DEFAULT_PAGE))
    except (ValueError, TypeError):
        page = DEFAULT_PAGE

    try:
        per_page = int(req.args.get("per_page", DEFAULT_PER_PAGE))
    except (ValueError, TypeError):
        per_page = DEFAULT_PER_PAGE

    # Enforce bounds
    page = max(1, page)
    per_page = max(1, min(per_page, MAX_PER_PAGE))

    return page, per_page


def paginate_query(base_query: str, params: list, page: int, per_page: int):
    """
    Add COUNT query and LIMIT/OFFSET to a base query.
    
    Returns:
        count_query: str - query to get total count
        count_params: list - params for count query
        data_query: str - query with LIMIT/OFFSET
        data_params: list - params for data query
    """
    # Count query wraps the original
    count_query = f"SELECT COUNT(*) FROM ({base_query}) AS _count_subq"
    count_params = list(params)

    # Data query adds pagination
    offset = (page - 1) * per_page
    data_query = f"{base_query} LIMIT %s OFFSET %s"
    data_params = list(params) + [per_page, offset]

    return count_query, count_params, data_query, data_params
