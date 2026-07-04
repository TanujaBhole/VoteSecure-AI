import sqlite3
import os

db_path = os.path.join('voting.db')

if not os.path.exists(db_path):
    print("Database not found. No migration needed.")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if election table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='election'")
    if cursor.fetchone():
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(election)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'code' not in columns:
            print("Adding 'code' to election table...")
            cursor.execute("ALTER TABLE election ADD COLUMN code VARCHAR(50) DEFAULT 'TEMP_CODE'")
            # Update existing records to have unique temp codes
            cursor.execute("SELECT id FROM election")
            ids = cursor.fetchall()
            for row_id in ids:
                cursor.execute("UPDATE election SET code = ? WHERE id = ?", (f"ELEC{row_id[0]}", row_id[0]))
                
        if 'status' not in columns:
            print("Adding 'status' to election table...")
            cursor.execute("ALTER TABLE election ADD COLUMN status VARCHAR(20) DEFAULT 'Upcoming'")
            
    # Check if candidate table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='candidate'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(candidate)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'photo_filename' not in columns:
            print("Adding 'photo_filename' to candidate table...")
            cursor.execute("ALTER TABLE candidate ADD COLUMN photo_filename VARCHAR(200)")
            
        if 'symbol_filename' not in columns:
            print("Adding 'symbol_filename' to candidate table...")
            cursor.execute("ALTER TABLE candidate ADD COLUMN symbol_filename VARCHAR(200)")

    conn.commit()
    print("Migration successful.")
except Exception as e:
    print(f"Error during migration: {e}")
finally:
    conn.close()
