# TPRM AI - Enterprise User Management System

## Overview

The TPRM AI platform now includes an enterprise-level user management system designed for secure on-premises deployment. This system provides comprehensive user administration capabilities with enterprise-grade security features.

## Features

### 🔐 Security Features
- **Password Hashing**: SHA-256 with salt-based hashing for secure password storage
- **Password Strength Validation**: Enforced complex password requirements
- **Audit Logging**: Comprehensive tracking of all user management actions
- **Session-Based Authentication**: Secure session management with HTTP-only cookies
- **Role-Based Access Control**: Admin-only access to user management functions

### 👥 User Management
- **Full CRUD Operations**: Create, read, update, and delete users
- **Role Management**: Support for admin and analyst roles
- **User Profiles**: Complete user information management
- **Backup System**: Automatic backup of user data during modifications
- **Self-Protection**: Users cannot delete their own accounts

### 📊 Monitoring & Audit
- **Activity Tracking**: All user management actions are logged with timestamps
- **Admin Dashboard**: Real-time view of system users and recent activities
- **User Statistics**: Overview of user counts and role distribution

## Deployment Guide

### Prerequisites

1. **Python 3.8+** installed on the server
2. **PostgreSQL database** set up and accessible
3. **Git** for cloning the repository (optional)

### Installation Steps

1. **Clone/Download the Application**
   ```bash
   git clone <repository-url>
   cd TPRM_AI
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Setup**
   - Ensure PostgreSQL is running
   - Configure database connection in `webapp/config.py`
   - Run database initialization:
     ```bash
     python -c "from webapp.db import init_db; init_db()"
     ```

4. **Create Initial Admin User**
   ```bash
   python setup_admin.py
   ```
   
   The script will prompt for:
   - Admin email address
   - Full name
   - Secure password (with strength validation)
   
   Example:
   ```
   Admin Email Address: admin@company.com
   Admin Full Name: System Administrator
   Admin Password: [hidden]
   Confirm Password: [hidden]
   ```

5. **Start the Application**
   ```bash
   python -m webapp.main
   ```

   The application will be available at: `http://localhost:8085`

### Configuration

#### Application Settings
Edit `webapp/config.py` to customize:
- Database connection parameters
- Session timeout settings
- Application host and port
- Security settings

#### User Storage
User data is stored in `config/users.json` with the following structure:
```json
{
  "users": [
    {
      "email": "admin@company.com",
      "name": "System Administrator",
      "role": "admin",
      "password_hash": "...",
      "salt": "...",
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "audit_log": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "action": "CREATE_USER",
      "user": "admin@company.com",
      "target": "user@company.com",
      "details": "User created via admin interface"
    }
  ]
}
```

## User Management Interface

### Accessing User Management
1. Log in with an admin account
2. Navigate to **User Management** in the sidebar (System section)
3. The interface provides:
   - User grid with cards showing user details
   - Create user modal with form validation
   - Edit user functionality
   - Delete user capabilities (with safeguards)
   - Audit log viewer

### User Creation
When creating users, the system:
- Validates email format and uniqueness
- Enforces password strength requirements
- Requires role selection (admin/analyst)
- Logs the creation action
- Sends confirmation to the admin

### Password Requirements
All passwords must contain:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}\|;:,.<>?)

### Role Descriptions
- **Admin**: Full system access including user management
- **Analyst**: Standard assessment creation and analysis capabilities

## API Endpoints

The user management system exposes the following API endpoints:

### User Operations
- `GET /api/users` - List all users (admin only)
- `POST /api/users` - Create new user (admin only)
- `PUT /api/users/{email}` - Update user (admin only)
- `DELETE /api/users/{email}` - Delete user (admin only)
- `GET /api/users/audit` - Get audit log (admin only)

### Authentication
- `POST /login` - User login
- `GET /logout` - User logout
- Session validation on all protected routes

## Security Considerations

### Production Deployment
1. **HTTPS**: Always use HTTPS in production
2. **Database Security**: Secure your PostgreSQL instance
3. **File Permissions**: Restrict access to `config/users.json`
4. **Backup Strategy**: Regular backups of user data and audit logs
5. **Network Security**: Configure firewall rules appropriately

### Backup and Recovery
The system automatically creates backups during user modifications:
- Backups stored in `config/users_backup_*.json`
- Timestamped for easy recovery
- Manual backup recommended before major changes

### Monitoring
Monitor the audit log for:
- Unusual login patterns
- Multiple failed authentication attempts
- Unauthorized access attempts
- Bulk user modifications

## Troubleshooting

### Common Issues

1. **Cannot access user management**
   - Ensure you're logged in as an admin user
   - Check user role in `config/users.json`

2. **Password validation errors**
   - Verify password meets all requirements
   - Check for hidden characters or encoding issues

3. **Database connection issues**
   - Verify PostgreSQL is running
   - Check connection parameters in config
   - Ensure database permissions are correct

4. **Users.json permission errors**
   - Check file read/write permissions
   - Ensure config directory exists
   - Verify sufficient disk space

### Logs and Debugging
- Application logs: Check console output for errors
- Audit logs: Review `/api/users/audit` for user activity
- Session issues: Clear browser cookies and restart

## Maintenance

### Regular Tasks
1. **Review audit logs** monthly for security analysis
2. **Backup user data** before system updates
3. **Update passwords** according to organization policy
4. **Remove inactive users** periodically

### Updates
When updating the application:
1. Backup `config/users.json`
2. Stop the application
3. Update code
4. Test user management functionality
5. Restart application

## Support

For issues with the user management system:
1. Check the troubleshooting section
2. Review application logs
3. Verify configuration settings
4. Check database connectivity

The system is designed for enterprise reliability and can be integrated into existing IT infrastructure and monitoring systems.