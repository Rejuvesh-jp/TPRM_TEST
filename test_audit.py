import requests
import json
import time

# Test login activity logging and audit endpoint
base_url = "http://localhost:8085"

def test_login_and_audit():
    print("🧪 Testing Login Activity Logging")
    print("=" * 40)
    
    # Test 1: Admin login
    admin_login = {
        "username": "rejuveshj@titan.co.in",
        "password": "Rejuvesh@2025"
    }
    
    try:
        response = requests.post(f"{base_url}/api/login", json=admin_login, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Admin login successful: {data['user']['name']} ({data['user']['role']})")
            session_token = data['session_token']
            
            # Test 2: Access audit endpoint
            cookies = {"session_token": session_token}
            audit_response = requests.get(f"{base_url}/api/users/audit", cookies=cookies, timeout=10)
            
            if audit_response.status_code == 200:
                audit_data = audit_response.json()
                activities = audit_data.get('audit_log', [])
                print(f"✅ Audit endpoint working: Found {len(activities)} activity records")
                
                # Show latest 3 activities
                for activity in activities[:3]:
                    timestamp = activity['timestamp'][:19].replace('T', ' ')
                    print(f"  - {timestamp}: {activity['action']} by {activity['name']} ({activity['email']})")
                
            else:
                print(f"❌ Audit endpoint failed: {audit_response.status_code}")
        else:
            print(f"❌ Admin login failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    print("\n🎯 Test completed!")

if __name__ == "__main__":
    test_login_and_audit()