from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from datetime import datetime
import hashlib
import hmac
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# Supabase Configuration
SUPABASE_URL = "https://qbfhwvpgnbgjapkxrpqc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFiZmh3dnBnbmJnamFwa3hycHFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk5OTk2MTgsImV4cCI6MjA3NTU3NTYxOH0.VweA2K5QfKbeWMfNGjABOJA1kRnoFmyjEOKrEW9Dmp8"
SHARED_SECRET = "YOUR_SHARED_SECRET_1A2B3C4D"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_signature(data: dict, secret: str) -> str:
    """Generate HMAC-SHA256 signature"""
    message = f"{data.get('key')}:{data.get('guid')}:{data.get('version')}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "MT5 License API",
        "version": "1.0.0",
        "endpoints": {
            "check_license": "/api/v1/check_license [POST]",
            "register_hwid": "/api/v1/register_hwid [POST]",
            "health": "/health [GET]"
        }
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/v1/check_license', methods=['POST'])
def check_license():
    """
    Check license validity
    Request: {
        "key": "LICENSE-KEY",
        "guid": "HWID-GUID",
        "version": 202
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "DENIED",
                "code": 400,
                "message": "Invalid request"
            }), 400
        
        license_key = data.get('key')
        hwid = data.get('guid')
        version = data.get('version')
        
        if not all([license_key, hwid, version]):
            return jsonify({
                "status": "DENIED",
                "code": 400,
                "message": "Missing required fields"
            }), 400
        
        # Query license from Supabase
        response = supabase.table('licenses').select('*').eq('license_key', license_key).execute()
        
        if not response.data or len(response.data) == 0:
            return jsonify({
                "status": "DENIED",
                "code": 404,
                "message": "License not found"
            }), 404
        
        license_data = response.data[0]
        
        # Check if license is active
        if not license_data.get('is_active'):
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "License is inactive"
            }), 403
        
        # Check expiry date
        expiry_date = datetime.fromisoformat(license_data['expiry_date'].replace('Z', '+00:00'))
        if datetime.now(expiry_date.tzinfo) > expiry_date:
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "License expired"
            }), 403
        
        # Check HWID
        registered_hwid = license_data.get('hwid')
        
        if registered_hwid is None:
            # First time use - register HWID
            supabase.table('licenses').update({
                'hwid': hwid,
                'last_used': datetime.utcnow().isoformat()
            }).eq('license_key', license_key).execute()
            
            # Log usage
            supabase.table('license_usage_logs').insert({
                'license_key': license_key,
                'hwid': hwid,
                'action': 'first_activation',
                'ip_address': request.remote_addr
            }).execute()
            
            return jsonify({
                "status": "GRANTED",
                "code": 200,
                "message": "License verified. Access granted.",
                "secret_key": SHARED_SECRET
            }), 200
        
        elif registered_hwid == hwid:
            # HWID matches - update last used
            supabase.table('licenses').update({
                'last_used': datetime.utcnow().isoformat()
            }).eq('license_key', license_key).execute()
            
            # Log usage
            supabase.table('license_usage_logs').insert({
                'license_key': license_key,
                'hwid': hwid,
                'action': 'verification',
                'ip_address': request.remote_addr
            }).execute()
            
            return jsonify({
                "status": "GRANTED",
                "code": 200,
                "message": "License verified. Access granted.",
                "secret_key": SHARED_SECRET
            }), 200
        
        else:
            # HWID mismatch
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "HWID mismatch. License locked to another device."
            }), 403
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            "status": "ERROR",
            "code": 500,
            "message": "Internal server error"
        }), 500

@app.route('/api/v1/register_hwid', methods=['POST'])
def register_hwid():
    """
    Manually register HWID (for resetting)
    Request: {
        "key": "LICENSE-KEY",
        "guid": "NEW-HWID"
    }
    """
    try:
        data = request.get_json()
        
        license_key = data.get('key')
        new_hwid = data.get('guid')
        
        if not all([license_key, new_hwid]):
            return jsonify({
                "status": "ERROR",
                "message": "Missing required fields"
            }), 400
        
        # Update HWID
        response = supabase.table('licenses').update({
            'hwid': new_hwid
        }).eq('license_key', license_key).execute()
        
        if not response.data or len(response.data) == 0:
            return jsonify({
                "status": "ERROR",
                "message": "License not found"
            }), 404
        
        return jsonify({
            "status": "SUCCESS",
            "message": "HWID registered successfully"
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)