"""
Authentication Middleware for AWS Cognito JWT Validation.

This module provides:
- JWT token validation against AWS Cognito
- User identity extraction from tokens
- Request context injection for user_id
- Decorator for protecting API endpoints
"""

import os
import json
import time
import logging
from functools import wraps
from urllib.request import urlopen

from flask import request, g
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from errors import error_response

logger = logging.getLogger('expense_tracker.auth')

# Cognito configuration from environment
COGNITO_REGION = os.environ.get('COGNITO_REGION', 'us-east-1')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_CLIENT_ID = os.environ.get('COGNITO_APP_CLIENT_ID', '')  # Match .env variable name

# JWKS URL for Cognito (public keys for JWT verification)
COGNITO_JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"

# Cache for JWKS keys (avoid fetching on every request)
_jwks_cache = {
    'keys': None,
    'fetched_at': 0,
    'ttl': 3600  # Cache for 1 hour
}


def get_jwks_keys():
    """
    Fetch and cache JWKS keys from Cognito.
    Keys are cached for 1 hour to reduce latency.
    """
    current_time = time.time()
    
    # Return cached keys if still valid
    if _jwks_cache['keys'] and (current_time - _jwks_cache['fetched_at']) < _jwks_cache['ttl']:
        return _jwks_cache['keys']
    
    try:
        with urlopen(COGNITO_JWKS_URL, timeout=5) as response:
            jwks = json.loads(response.read().decode('utf-8'))
            _jwks_cache['keys'] = jwks.get('keys', [])
            _jwks_cache['fetched_at'] = current_time
            logger.info("JWKS keys refreshed from Cognito")
            return _jwks_cache['keys']
    except Exception as e:
        logger.error(f"Failed to fetch JWKS keys: {e}")
        # Return cached keys if available, even if expired
        if _jwks_cache['keys']:
            return _jwks_cache['keys']
        raise


def get_key_for_token(token):
    """
    Find the correct public key for a given JWT token.
    Matches the 'kid' (key ID) in the token header.
    """
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as e:
        logger.warning(f"Invalid token header: {e}")
        return None
    
    kid = headers.get('kid')
    if not kid:
        return None
    
    keys = get_jwks_keys()
    for key in keys:
        if key.get('kid') == kid:
            return key
    
    return None


def validate_token(token):
    """
    Validate a Cognito JWT token and extract claims.
    
    Returns:
        dict: Token claims if valid
        
    Raises:
        ValueError: If token is invalid
    """
    if not COGNITO_USER_POOL_ID or not COGNITO_CLIENT_ID:
        raise ValueError("Cognito configuration missing")
    
    # Get the signing key
    key = get_key_for_token(token)
    if not key:
        raise ValueError("Unable to find signing key")
    
    # Expected issuer
    issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    
    try:
        # Decode and validate the token
        claims = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=COGNITO_CLIENT_ID,
            issuer=issuer,
            options={
                'verify_aud': True,
                'verify_iss': True,
                'verify_exp': True,
            }
        )
        
        # Verify token_use claim (should be 'id' for ID tokens)
        token_use = claims.get('token_use')
        if token_use not in ('id', 'access'):
            raise ValueError(f"Invalid token_use: {token_use}")
        
        return claims
        
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTClaimsError as e:
        raise ValueError(f"Invalid token claims: {e}")
    except JWTError as e:
        raise ValueError(f"Token validation failed: {e}")


def get_current_user_id():
    """
    Get the current authenticated user's ID from request context.
    
    Returns:
        str: User ID (Cognito sub claim)
        
    Raises:
        RuntimeError: If no authenticated user in context
    """
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        raise RuntimeError("No authenticated user in request context")
    return user_id


def require_auth(f):
    """
    Decorator to require authentication on an endpoint.
    
    Extracts Bearer token from Authorization header,
    validates it, and injects user_id into Flask g context.
    
    Usage:
        @app.route('/protected')
        @require_auth
        def protected_endpoint():
            user_id = g.user_id
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header:
            return error_response('Authorization header is required', 401)
        
        # Check Bearer token format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return error_response('Invalid Authorization header format. Expected: Bearer <token>', 401)
        
        token = parts[1]
        
        try:
            # Validate token and extract claims
            claims = validate_token(token)
            
            # Extract user ID (sub claim is the unique user identifier)
            user_id = claims.get('sub')
            if not user_id:
                return error_response('Token missing user identifier', 401)
            
            # Inject into Flask request context
            g.user_id = user_id
            g.user_email = claims.get('email', '')
            g.user_name = claims.get('name', '')
            g.token_claims = claims
            
            logger.info(f"Authenticated user: {user_id} ({g.user_email})")
            
        except ValueError as e:
            logger.warning(f"Authentication failed: {e}")
            return error_response(str(e), 401)
        except Exception as e:
            logger.error(f"Unexpected auth error: {e}")
            return error_response('Authentication failed', 401)
        
        return f(*args, **kwargs)
    
    return decorated_function


def optional_auth(f):
    """
    Decorator for optional authentication.
    
    If a valid token is provided, user info is injected into context.
    If no token or invalid token, request proceeds without user context.
    
    Usage:
        @app.route('/public')
        @optional_auth
        def public_endpoint():
            user_id = getattr(g, 'user_id', None)
            if user_id:
                # Authenticated user
            else:
                # Anonymous user
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                try:
                    claims = validate_token(parts[1])
                    g.user_id = claims.get('sub')
                    g.user_email = claims.get('email', '')
                    g.user_name = claims.get('name', '')
                    g.token_claims = claims
                except Exception:
                    pass  # Proceed without auth context
        
        return f(*args, **kwargs)
    
    return decorated_function
