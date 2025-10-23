from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
import os
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://qbfhwvpgnbgjapkxrpqc.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFiZmh3dnBnbmJnamFwa3hycHFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzUxMDk2NjksImV4cCI6MjA1MDY4NTY2OX0.s-f9s4UR4VZnzVQvslZE9y_yp_wnxBbPJMzjXmrpGbY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Helper Functions
def log_license_action(license_key, account_id, action, ip_address):
    """Log license actions to database"""
    try:
        supabase.table('license_logs').insert({
            'license_key': license_key,
            'account_id': account_id,
            'action': action,
            'ip_address': ip_address
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log action: {str(e)}")

def get_client_ip():
    """Get client IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

# Routes
@app.route('/')
def index():
    """API information endpoint"""
    return jsonify({
        'service': 'MT5 License API',
        'version': '2.0.0',
        'status': 'online',
        'endpoints': {
            'health': '/api/health [GET]',
            'activate': '/api/license/activate [POST]',
            'verify': '/api/license/verify [POST]',
            'deactivate': '/api/license/deactivate [POST]'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        supabase.table('licenses').select('id').limit(1).execute()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503

@app.route('/api/license/activate', methods=['POST'])
def activate_license():
    """Activate license with account ID binding"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key')
        account_id = data.get('account_id')
        
        if not license_key or not account_id:
            return jsonify({'success': False, 'error': 'Missing license_key or account_id'}), 400
        
        # Get license info
        result = supabase.table('licenses').select('*').eq('license_key', license_key).execute()
        
        if not result.data:
            log_license_action(license_key, account_id, 'ACTIVATION_FAILED_INVALID_KEY', get_client_ip())
            return jsonify({'success': False, 'error': 'Invalid license key'}), 404
        
        license_data = result.data[0]
        
        # Check if license is active
        if not license_data['is_active']:
            log_license_action(license_key, account_id, 'ACTIVATION_FAILED_INACTIVE', get_client_ip())
            return jsonify({'success': False, 'error': 'License is inactive'}), 403
        
        # Check expiration
        if license_data['expires_at']:
            expiry = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
            if expiry < datetime.now(timezone.utc):
                log_license_action(license_key, account_id, 'ACTIVATION_FAILED_EXPIRED', get_client_ip())
                return jsonify({'success': False, 'error': 'License has expired'}), 403
        
        # Check if already bound to different account
        if license_data['account_id'] and license_data['account_id'] != account_id:
            log_license_action(license_key, account_id, 'ACTIVATION_FAILED_ALREADY_BOUND', get_client_ip())
            return jsonify({'success': False, 'error': 'License already activated on different account'}), 403
        
        # Check activation limit
        if license_data['current_activations'] >= license_data['max_activations']:
            log_license_action(license_key, account_id, 'ACTIVATION_FAILED_LIMIT_REACHED', get_client_ip())
            return jsonify({'success': False, 'error': 'Maximum activations reached'}), 403
        
        # Activate license
        update_data = {
            'account_id': account_id,
            'current_activations': license_data['current_activations'] + 1,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table('licenses').update(update_data).eq('license_key', license_key).execute()
        
        log_license_action(license_key, account_id, 'ACTIVATION_SUCCESS', get_client_ip())
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'expires_at': license_data['expires_at']
        }), 200
        
    except Exception as e:
        logger.error(f"Activation error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/license/verify', methods=['POST'])
def verify_license():
    """Verify license and account ID"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key')
        account_id = data.get('account_id')
        
        if not license_key or not account_id:
            return jsonify({'success': False, 'error': 'Missing license_key or account_id'}), 400
        
        # Get license info
        result = supabase.table('licenses').select('*').eq('license_key', license_key).execute()
        
        if not result.data:
            return jsonify({'success': False, 'error': 'Invalid license key'}), 404
        
        license_data = result.data[0]
        
        # Check if license is active
        if not license_data['is_active']:
            return jsonify({'success': False, 'error': 'License is inactive'}), 403
        
        # Check expiration
        if license_data['expires_at']:
            expiry = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
            if expiry < datetime.now(timezone.utc):
                return jsonify({'success': False, 'error': 'License has expired'}), 403
        
        # Check account binding
        if license_data['account_id'] != account_id:
            return jsonify({'success': False, 'error': 'License not activated for this account'}), 403
        
        log_license_action(license_key, account_id, 'VERIFICATION_SUCCESS', get_client_ip())
        
        return jsonify({
            'success': True,
            'message': 'License is valid',
            'expires_at': license_data['expires_at']
        }), 200
        
    except Exception as e:
        logger.error(f"Verification error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/license/deactivate', methods=['POST'])
def deactivate_license():
    """Deactivate license (unbind from account)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key')
        account_id = data.get('account_id')
        
        if not license_key or not account_id:
            return jsonify({'success': False, 'error': 'Missing license_key or account_id'}), 400
        
        # Get license info
        result = supabase.table('licenses').select('*').eq('license_key', license_key).execute()
        
        if not result.data:
            return jsonify({'success': False, 'error': 'Invalid license key'}), 404
        
        license_data = result.data[0]
        
        # Check if bound to this account
        if license_data['account_id'] != account_id:
            return jsonify({'success': False, 'error': 'License not activated for this account'}), 403
        
        # Deactivate
        update_data = {
            'account_id': None,
            'current_activations': max(0, license_data['current_activations'] - 1),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table('licenses').update(update_data).eq('license_key', license_key).execute()
        
        log_license_action(license_key, account_id, 'DEACTIVATION_SUCCESS', get_client_ip())
        
        return jsonify({
            'success': True,
            'message': 'License deactivated successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Deactivation error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)