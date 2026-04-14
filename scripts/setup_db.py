"""
TPRM_AI Database Setup Script
Run this to set up PostgreSQL with pgvector for the TPRM project.
Usage: python scripts/setup_db.py
"""
import subprocess
import sys
import getpass

PSQL = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"


def run_sql(sql, db="postgres", user="postgres", password="", capture=True):
    """Execute SQL via psql and return output."""
    env = {"PGPASSWORD": password}
    import os
    full_env = os.environ.copy()
    full_env.update(env)
    result = subprocess.run(
        [PSQL, "-U", user, "-h", "127.0.0.1", "-p", "5432", "-d", db, "-c", sql],
        capture_output=capture,
        text=True,
        env=full_env,
    )
    return result


def main():
    print("=" * 60)
    print("TPRM_AI — PostgreSQL + pgvector Setup")
    print("=" * 60)
    print()

    password = getpass.getpass("Enter PostgreSQL 'postgres' superuser password: ")

    # Test connection
    print("\n[1/6] Testing connection...")
    r = run_sql("SELECT version();", password=password)
    if r.returncode != 0:
        print(f"  FAILED: {r.stderr.strip()}")
        sys.exit(1)
    version_line = [l for l in r.stdout.splitlines() if "PostgreSQL" in l]
    print(f"  OK: {version_line[0].strip() if version_line else 'Connected'}")

    # Check pgvector availability
    print("\n[2/6] Checking pgvector availability...")
    r = run_sql(
        "SELECT name, default_version FROM pg_available_extensions WHERE name='vector';",
        password=password,
    )
    if "vector" in r.stdout:
        version = r.stdout.strip().split("\n")
        print(f"  OK: pgvector is available")
        for line in version:
            if "vector" in line:
                print(f"  {line.strip()}")
    else:
        print("  WARNING: pgvector extension is NOT available in your PostgreSQL installation.")
        print("  You need to install the pgvector extension files first.")
        print("  See docs/windows-setup.md for instructions.")
        print("  Continuing with remaining setup...")

    # Create database
    print("\n[3/6] Creating database 'tprm_db'...")
    r = run_sql("SELECT 1 FROM pg_database WHERE datname='tprm_db';", password=password)
    if "1" in r.stdout:
        print("  OK: Database 'tprm_db' already exists")
    else:
        r = run_sql("CREATE DATABASE tprm_db;", password=password)
        if r.returncode == 0:
            print("  OK: Created database 'tprm_db'")
        else:
            print(f"  ERROR: {r.stderr.strip()}")

    # Create user
    print("\n[4/6] Creating user 'tprm_user'...")
    r = run_sql("SELECT 1 FROM pg_roles WHERE rolname='tprm_user';", password=password)
    if "1" in r.stdout:
        print("  OK: User 'tprm_user' already exists")
    else:
        r = run_sql(
            "CREATE ROLE tprm_user WITH LOGIN PASSWORD 'tprm_password';",
            password=password,
        )
        if r.returncode == 0:
            print("  OK: Created user 'tprm_user'")
        else:
            print(f"  ERROR: {r.stderr.strip()}")

    # Grant privileges
    print("\n[5/6] Granting privileges...")
    run_sql("GRANT ALL PRIVILEGES ON DATABASE tprm_db TO tprm_user;", password=password)
    r = run_sql(
        "GRANT ALL ON SCHEMA public TO tprm_user;",
        db="tprm_db",
        password=password,
    )
    print("  OK: Privileges granted")

    # Enable pgvector extension in tprm_db
    print("\n[6/6] Enabling pgvector extension in tprm_db...")
    r = run_sql(
        "CREATE EXTENSION IF NOT EXISTS vector;",
        db="tprm_db",
        password=password,
    )
    if r.returncode == 0:
        # Verify
        r2 = run_sql(
            "SELECT extname, extversion FROM pg_extension WHERE extname='vector';",
            db="tprm_db",
            password=password,
        )
        if "vector" in r2.stdout:
            print("  OK: pgvector extension enabled!")
            for line in r2.stdout.splitlines():
                if "vector" in line:
                    print(f"  {line.strip()}")
        else:
            print("  WARNING: Extension command ran but vector not found.")
            print("  The extension files may not be installed. See docs/windows-setup.md")
    else:
        print(f"  ERROR: {r.stderr.strip()}")
        print("  The pgvector extension files need to be installed first.")
        print("  See docs/windows-setup.md for instructions.")

    # Final verification
    print("\n" + "=" * 60)
    print("Verification — connecting as tprm_user to tprm_db...")
    r = run_sql("SELECT 1 as connection_ok;", db="tprm_db", user="tprm_user", password="tprm_password")
    if r.returncode == 0:
        print("  OK: tprm_user can connect to tprm_db")
    else:
        print(f"  ERROR: {r.stderr.strip()}")

    print("\nSetup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
