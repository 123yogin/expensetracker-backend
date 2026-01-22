"""
Centralized validation helpers for the Expense Tracker API.

Production-hardened validators:
- UUID format validation (v4 only)
- Date format validation with optional future date rejection
- Amount validation with Decimal precision
- Month format validation for reports
"""

import uuid
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# Precompiled regex for performance
UUID_V4_REGEX = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE
)

DATE_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MONTH_REGEX = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def validate_uuid(value: str) -> tuple[bool, str | None]:
    """
    Validate UUID v4 format strictly.
    
    Args:
        value: String to validate as UUID v4
        
    Returns:
        (True, None) if valid, (False, error_message) if invalid
    """
    if not value or not isinstance(value, str):
        return False, "UUID is required"
    
    # Quick regex check first (faster than exception handling)
    if not UUID_V4_REGEX.match(value):
        return False, "Invalid UUID v4 format"
    
    # Double-check with uuid module for strict validation
    try:
        parsed = uuid.UUID(value, version=4)
        # Ensure it's actually a v4 UUID
        if parsed.version != 4:
            return False, "UUID must be version 4"
        return True, None
    except (ValueError, AttributeError):
        return False, "Invalid UUID format"


def generate_uuid() -> str:
    """
    Generate a new UUID v4.
    ONLY place where UUIDs should be generated in the backend.
    """
    return str(uuid.uuid4())


def validate_date(date_string: str, reject_future: bool = True) -> tuple[bool, str | None]:
    """
    Validate date format YYYY-MM-DD.
    
    Args:
        date_string: String to validate
        reject_future: If True, reject dates in the future (default: True)
        
    Returns:
        (True, None) if valid, (False, error_message) if invalid
    """
    if not date_string or not isinstance(date_string, str):
        return False, "Date is required"
    
    # Quick format check
    if not DATE_REGEX.match(date_string):
        return False, "Invalid date format. Use YYYY-MM-DD"
    
    try:
        parsed_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        
        # Reject future dates for expense entries
        if reject_future and parsed_date > date.today():
            return False, "Date cannot be in the future"
        
        return True, None
    except ValueError:
        return False, "Invalid date. Check year, month, and day values"


def validate_month(month_string: str) -> tuple[bool, str | None]:
    """
    Validate month format YYYY-MM for reports.
    
    Args:
        month_string: String to validate (e.g., "2026-01")
        
    Returns:
        (True, None) if valid, (False, error_message) if invalid
    """
    if not month_string or not isinstance(month_string, str):
        return False, "Month parameter is required (format: YYYY-MM)"
    
    if not MONTH_REGEX.match(month_string):
        return False, "Invalid month format. Use YYYY-MM"
    
    try:
        datetime.strptime(month_string, '%Y-%m')
        return True, None
    except ValueError:
        return False, "Invalid month value"


def validate_amount(amount_value) -> tuple[Decimal | None, str | None]:
    """
    Validate and convert amount to Decimal with 2 decimal places.
    
    Args:
        amount_value: Value to validate (string, int, or float)
        
    Returns:
        (Decimal, None) on success, (None, error_message) on failure
        
    Rules:
        - Must be a positive number
        - Must not be zero
        - Quantized to exactly 2 decimal places
    """
    if amount_value is None:
        return None, "Amount is required"
    
    try:
        # Convert to string first to avoid float precision issues
        amount_str = str(amount_value).strip()
        
        if not amount_str:
            return None, "Amount is required"
        
        amount = Decimal(amount_str)
        
        # Check for special values
        if not amount.is_finite():
            return None, "Amount must be a valid number"
        
        # Reject zero and negative
        if amount <= 0:
            return None, "Amount must be greater than zero"
        
        # Check for too many decimal places before quantizing
        # This prevents silent rounding of user input
        if amount.as_tuple().exponent < -2:
            return None, "Amount cannot have more than 2 decimal places"
        
        # Quantize to exactly 2 decimal places
        quantized = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        return quantized, None
        
    except (InvalidOperation, ValueError, TypeError):
        return None, "Invalid amount format"


def format_amount(amount) -> str:
    """
    Format amount as string with exactly 2 decimal places.
    Safe for None values and various input types.
    
    Args:
        amount: Value to format (Decimal, str, int, float, or None)
        
    Returns:
        Formatted string like "123.45"
    """
    if amount is None:
        return "0.00"
    
    try:
        decimal_amount = Decimal(str(amount))
        quantized = decimal_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return str(quantized)
    except (InvalidOperation, ValueError):
        return "0.00"


def get_month_date_range(month_string: str) -> tuple[str, str]:
    """
    Get the start and end dates for a given month.
    
    Args:
        month_string: Month in YYYY-MM format (must be pre-validated)
        
    Returns:
        (start_date, end_date) as strings in YYYY-MM-DD format
    """
    from datetime import timedelta
    
    year, month = map(int, month_string.split('-'))
    start_date = f"{year:04d}-{month:02d}-01"
    
    # Calculate last day of month
    if month == 12:
        next_month_year = year + 1
        next_month = 1
    else:
        next_month_year = year
        next_month = month + 1
    
    last_day = date(next_month_year, next_month, 1) - timedelta(days=1)
    end_date = last_day.strftime('%Y-%m-%d')
    
    return start_date, end_date
