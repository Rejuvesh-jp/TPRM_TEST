#!/usr/bin/env python3
"""
Initial Admin User Setup for TPRM AI
====================================
This script creates the first admin user for on-premises deployment.
Run this after deploying the application to create your initial admin account.

Usage:
    python setup_admin.py
"""
import json
import hashlib
import secrets
import sys
from pathlib import Path
from datetime import datetime
from getpass import getpass
import re

PROJECT_ROOT = Path(__file__).resolve().parent
USERS_FILE = PROJECT_ROOT / "config" / "users.json"

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is valid"

def hash_password(password, salt=None):
    """Hash password with salt"""
    if salt is None:
        salt = secrets.token_hex(32)
    
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return pwd_hash, salt

def create_users_file():
    """Create initial users.json structure"""
    config_dir = PROJECT_ROOT / "config"
    config_dir.mkdir(exist_ok=True)
    
    users_data = {
        "users": [],
        "audit_log": []
    }
    
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, indent=2)
    
    print(f"✓ Created users configuration at: {USERS_FILE}")

def add_admin_user(email, name, password):
    """Add admin user to users.json"""
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {"users": [], "audit_log": []}
    
    # Check if user already exists
    for user in data["users"]:
        if user["email"].lower() == email.lower():
            print(f"❌ User with email {email} already exists!")
            return False
    
    # Hash password
    pwd_hash, salt = hash_password(password)
    
    # Create user record
    user_record = {
        "email": email,
        "name": name,
        "role": "admin",
        "password_hash": pwd_hash,
        "salt": salt,
        "created_at": datetime.now().isoformat()
    }
    
    # Add user
    data["users"].append(user_record)
    
    # Add audit log entry
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "CREATE_USER",
        "user": "SYSTEM_SETUP",
        "target": email,
        "details": "Initial admin user created during setup"
    }
    data["audit_log"].append(audit_entry)
    
    # Save to file
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"✓ Admin user created successfully!")
    return True

def main():
    print("=" * 60)
    print("TPRM AI - Initial Admin User Setup")
    print("=" * 60)
    print()
    
    # Check if users file exists
    if not USERS_FILE.exists():
        print("No users configuration found. Creating new users file...")
        create_users_file()
        print()
    else:
        # Check if there are already users and migrate format if needed
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle old format (array) vs new format (object)
        if isinstance(data, list):
            print("Converting users file to new format...")
            # Migrate old format to new format
            old_users = data
            new_data = {
                "users": [],
                "audit_log": []
            }
            
            # Convert old users to new format
            for old_user in old_users:
                # Hash the plain text password
                pwd_hash, salt = hash_password(old_user["password"])
                
                new_user = {
                    "email": old_user["email"],
                    "name": old_user["name"],
                    "role": old_user["role"],
                    "password_hash": pwd_hash,
                    "salt": salt,
                    "created_at": datetime.now().isoformat()
                }
                new_data["users"].append(new_user)
                
                # Add migration audit entry
                audit_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "action": "MIGRATE_USER",
                    "user": "SYSTEM_MIGRATION",
                    "target": old_user["email"],
                    "details": "User migrated from old format to new format"
                }
                new_data["audit_log"].append(audit_entry)
            
            # Save migrated data
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2)
            
            print(f"✓ Migrated {len(old_users)} users to new format")
            data = new_data
        
        if data.get("users"):
            print(f"Found {len(data['users'])} existing users.")
            proceed = input("Do you want to add another admin user? (y/N): ").strip().lower()
            if proceed not in ['y', 'yes']:
                print("Setup cancelled.")
                return
            print()
    
    print("Please provide details for the initial admin user:")
    print()
    
    # Get email
    while True:
        email = input("Admin Email Address: ").strip()
        if not email:
            print("❌ Email address is required!")
            continue
        
        if not validate_email(email):
            print("❌ Please enter a valid email address!")
            continue
        
        break
    
    # Get name
    while True:
        name = input("Admin Full Name: ").strip()
        if not name:
            print("❌ Full name is required!")
            continue
        break
    
    # Get password
    while True:
        password = getpass("Admin Password: ")
        if not password:
            print("❌ Password is required!")
            continue
        
        is_valid, message = validate_password(password)
        if not is_valid:
            print(f"❌ {message}")
            continue
        
        confirm = getpass("Confirm Password: ")
        if password != confirm:
            print("❌ Passwords do not match!")
            continue
        
        break
    
    print()
    print("Creating admin user...")
    
    if add_admin_user(email, name, password):
        print()
        print("🎉 Setup completed successfully!")
        print()
        print("You can now start the TPRM AI application:")
        print("  python -m webapp.main")
        print()
        print("Access the application at: http://localhost:8085")
        print(f"Login with: {email}")
        print()
        print("For user management, visit: http://localhost:8085/users")
    else:
        print()
        print("❌ Setup failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()