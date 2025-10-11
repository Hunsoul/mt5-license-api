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
    """Check license validity"""
    try:
        data = request.get_json()
        
        # Debug: Print request
        print(f"\n{'='*50}")
        print(f"📥 License Check Request")
        print(f"{'='*50}")
        
        if not data:
            print("❌ No JSON data received")
            return jsonify({
                "status": "DENIED",
                "code": 400,
                "message": "Invalid request"
            }), 400
        
        license_key = data.get('key')
        hwid = data.get('guid')
        version = data.get('version')
        
        print(f"License Key: {license_key}")
        print(f"HWID: {hwid}")
        print(f"Version: {version}")
        
        if not all([license_key, hwid, version]):
            print("❌ Missing required fields")
            return jsonify({
                "status": "DENIED",
                "code": 400,
                "message": "Missing required fields"
            }), 400
        
        # Query license from Supabase
        print(f"\n🔍 Querying database...")
        response = supabase.table('licenses').select('*').eq('license_key', license_key).execute()
        
        print(f"Database response: {response.data}")
        
        if not response.data or len(response.data) == 0:
            print("❌ License not found in database")
            return jsonify({
                "status": "DENIED",
                "code": 404,
                "message": "License not found"
            }), 404
        
        license_data = response.data[0]
        print(f"\n📋 License Data:")
        print(f"  - Status: {license_data.get('is_active')}")
        print(f"  - Expiry: {license_data.get('expiry_date')}")
        print(f"  - Current HWID: {license_data.get('hwid')}")
        
        # Check if license is active
        if not license_data.get('is_active'):
            print("❌ License is inactive")
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "License is inactive"
            }), 403
        
        # Check expiry date
        expiry_date = datetime.fromisoformat(license_data['expiry_date'].replace('Z', '+00:00'))
        if datetime.now(expiry_date.tzinfo) > expiry_date:
            print("❌ License expired")
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "License expired"
            }), 403
        
        # Check HWID
        registered_hwid = license_data.get('hwid')
        
        if registered_hwid is None:
            # First time use - register HWID
            print(f"\n🔄 First time activation!")
            print(f"   Registering HWID: {hwid}")
            
            update_result = supabase.table('licenses').update({
                'hwid': hwid,
                'last_used': datetime.utcnow().isoformat()
            }).eq('license_key', license_key).execute()
            
            print(f"✅ Update Result: {update_result.data}")
            
            # Log usage
            try:
                supabase.table('license_usage_logs').insert({
                    'license_key': license_key,
                    'hwid': hwid,
                    'action': 'first_activation',
                    'ip_address': request.remote_addr
                }).execute()
                print("✅ Usage logged")
            except Exception as log_error:
                print(f"⚠️ Failed to log usage: {log_error}")
            
            print(f"\n{'='*50}")
            print(f"✅ LICENSE GRANTED - First Activation")
            print(f"{'='*50}\n")
            
            return jsonify({
                "status": "GRANTED",
                "code": 200,
                "message": "License verified. Access granted.",
                "hwid": hwid
            }), 200
        
        elif registered_hwid == hwid:
            # HWID matches - update last used
            print(f"\n✅ HWID Match!")
            
            supabase.table('licenses').update({
                'last_used': datetime.utcnow().isoformat()
            }).eq('license_key', license_key).execute()
            
            # Log usage
            try:
                supabase.table('license_usage_logs').insert({
                    'license_key': license_key,
                    'hwid': hwid,
                    'action': 'verification',
                    'ip_address': request.remote_addr
                }).execute()
            except Exception as log_error:
                print(f"⚠️ Failed to log usage: {log_error}")
            
            print(f"\n{'='*50}")
            print(f"✅ LICENSE GRANTED - Verified")
            print(f"{'='*50}\n")
            
            return jsonify({
                "status": "GRANTED",
                "code": 200,
                "message": "License verified. Access granted."
            }), 200
        
        else:
            # HWID mismatch
            print(f"\n❌ HWID Mismatch!")
            print(f"   Expected: {registered_hwid}")
            print(f"   Received: {hwid}")
            
            return jsonify({
                "status": "DENIED",
                "code": 403,
                "message": "HWID mismatch. License locked to another device."
            }), 403
    
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "status": "ERROR",
            "code": 500,
            "message": "Internal server error"
        }), 500

@app.route('/api/v1/register_hwid', methods=['POST'])
def register_hwid():
    """Manually register HWID (for resetting)"""
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