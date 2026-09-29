import sqlite3
from database import DB_PATH

def get_config(key: str, default: str = "") -> str:
    """Database se configuration value read karta hai."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT config_value FROM system_configs WHERE config_key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default

def get_config_int(key: str, default: int = 0) -> int:
    """Integer config helper."""
    val = get_config(key, str(default))
    try:
        return int(val)
    except ValueError:
        return default

def get_config_list(key: str, default: list = None) -> list:
    """Comma-separated string ko list me convert karta hai."""
    val = get_config(key, "")
    if not val:
        return default or []
    return [item.strip() for item in val.split(",") if item.strip()]

def set_config(key: str, value: str) -> bool:
    """Frontend se aane wale updates ko database me save karta hai."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO system_configs (config_key, config_value)
        VALUES (?, ?)
        ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value
        """, (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_all_configs() -> dict:
    """Frontend UI ko saari settings ek sath dikhane ke liye."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT config_key, config_value, description FROM system_configs")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {"value": row[1], "description": row[2]} for row in rows}