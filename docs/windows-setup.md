# Setting up pgvector on Windows

Since Docker is not available in your environment, and you need to manually install `pgvector` for your local PostgreSQL instance.

## Prerequisites

1. **PostgreSQL Installed**: Ensure you have PostgreSQL installed.
2. **C++ Build Tools**: You need Visual Studio C++ build tools (MSVC) to compile the extension.
   - Install "Desktop development with C++" workload from Visual Studio Installer.

## Installation Steps (Manual Compilation)

1. **Locate PostgreSQL Directory**:
   Find your installation folder (e.g., `C:\Program Files\PostgreSQL\16\`).

2. **Clone pgvector**:
   Open a terminal (PowerShell or Command Prompt) and run:
   ```powershell
   git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
   cd pgvector
   ```
   *Note: If you don't have git, download the ZIP from GitHub.*

3. **Compile and Install**:
   Open **"x64 Native Tools Command Prompt for VS 2022"** (search in Start Menu).
   Navigate to the `pgvector` folder you just cloned.
   Run:
   ```cmd
   rem Adjust PGROOT to match your Postgres install location!
   set "PGROOT=C:\Program Files\PostgreSQL\16" 
   nmake /F Makefile.win
   nmake /F Makefile.win install
   ```

4. **Enable Extension**:
   Open your SQL tool (psql or pgAdmin) and run:
   ```sql
   CREATE EXTENSION vector;
   ```

## Alternative: Pre-packaged Distributions

If compiling is too difficult, consider using:
- **Neon** (Cloud Postgres with vector)
- **Supabase** (Cloud Postgres with vector)
- **Linux Subsystem for Windows (WSL2)**: Install Ubuntu on WSL2, then install Postgres and pgvector easily via `apt`.

## Verification

Run this SQL command to verify installation:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```
