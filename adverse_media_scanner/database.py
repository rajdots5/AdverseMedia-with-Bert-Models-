import sqlite3

DB_PATH = "aml_scanner.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Core Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS targets (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, context TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS scraped_news (id INTEGER PRIMARY KEY AUTOINCREMENT, target_id INTEGER, url TEXT UNIQUE, title TEXT, content TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS screening_results (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER, is_match BOOLEAN, confidence_score REAL, risk_category TEXT, reasoning TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS region_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, region_name TEXT UNIQUE NOT NULL, allowed_sources TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS system_configs (config_key TEXT PRIMARY KEY, config_value TEXT NOT NULL, description TEXT)''')

    # Internal KYC Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer_kyc (
        customer_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        dob TEXT,
        city TEXT,
        profession TEXT,
        associated_companies TEXT
    )
    ''')

    # 🆕 Knowledge Graph & Traceability Audit Tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS graph_nodes (
        node_id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL, -- 'TARGET', 'ARTICLE', 'ENTITY', 'CATEGORY'
        node_label TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS graph_edges (
        source_id TEXT,
        target_id TEXT,
        relation_type TEXT NOT NULL, -- 'MENTIONED_IN', 'ASSOCIATED_WITH', 'TRIGGERED_RISK'
        weight REAL,
        PRIMARY KEY (source_id, target_id, relation_type)
    )
    ''')

    # Seed Mock KYC Data
    mock_kyc_data = [
        ("CUST-1001", "Nirav Modi", "1971-02-27", "Mumbai", "Diamantaire / Jeweller", "Firestar Diamond, Punjab National Bank, Gitanjali Gems"),
        ("CUST-1002", "Rahul Sharma", "1990-05-12", "Pune", "Software Engineer", "TCS"),
    ]

    for row in mock_kyc_data:
        cursor.execute('''
        INSERT OR IGNORE INTO customer_kyc (customer_id, full_name, dob, city, profession, associated_companies)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', row)

    # Default System Configurations
    default_configs = [
        ("required_articles", "5", "Number of valid articles to analyze per target"),
        ("initial_search_fetch", "12", "Number of search results to fetch from Google News"),
        ("min_content_length", "150", "Minimum characters required to accept a scraped page"),
        ("search_keywords", "fraud,money laundering,scam,arrested,CBI,ED,court order", "Keywords added to Google Search query"),
        ("risk_labels", "Financial Fraud,Money Laundering,Arrest or Extradition,Legal Penalty or Court Order,Normal Business News", "Zero-shot classification candidate labels"),
        ("risk_fallback_keywords", "fraud,scam,money laundering,cbi,ed raid,court,penalty", "Keywords that trigger automatic fraud classification"),
        ("chunk_size", "1000", "Character length of each text chunk for risk analysis"),
        ("max_text_scan_limit", "4000", "Maximum characters of an article to scan")
    ]

    for key, val, desc in default_configs:
        cursor.execute('''
        INSERT OR IGNORE INTO system_configs (config_key, config_value, description)
        VALUES (?, ?, ?)
        ''', (key, val, desc))

    # Seed Regions
    cursor.execute("INSERT OR IGNORE INTO region_configs (region_name, allowed_sources) VALUES (?, ?)", ('India', 'The Hindu,The Indian Express,NDTV,LiveLaw,LiveLawBiz,Hindustan Times,Moneycontrol'))
    
    conn.commit()
    conn.close()

def get_customer_kyc(identifier: str) -> dict:
    """Customer ki poori KYC dictionary return karta hai weighting calculation ke liye."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT customer_id, full_name, city, profession, associated_companies 
        FROM customer_kyc 
        WHERE full_name = ? OR customer_id = ?
    """, (identifier, identifier))
    
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "customer_id": row[0],
            "full_name": row[1],
            "city": row[2] or "",
            "profession": row[3] or "",
            "associated_companies": row[4] or ""
        }
    return {}

def log_graph_audit(target_name: str, article_url: str, article_title: str, match_score: float, risk_category: str):
    """Scan ke baad Knowledge Graph nodes aur edges database me save karta hai."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Nodes insert karein
    cursor.execute("INSERT OR IGNORE INTO graph_nodes (node_id, node_type, node_label) VALUES (?, ?, ?)", 
                   (target_name, 'TARGET', target_name))
    cursor.execute("INSERT OR IGNORE INTO graph_nodes (node_id, node_type, node_label) VALUES (?, ?, ?)", 
                   (article_url, 'ARTICLE', article_title))
    cursor.execute("INSERT OR IGNORE INTO graph_nodes (node_id, node_type, node_label) VALUES (?, ?, ?)", 
                   (risk_category, 'CATEGORY', risk_category))

    # 2. Edges / Relationships insert karein
    cursor.execute("""
        INSERT OR REPLACE INTO graph_edges (source_id, target_id, relation_type, weight)
        VALUES (?, ?, ?, ?)
    """, (target_name, article_url, 'MENTIONED_IN', match_score))

    cursor.execute("""
        INSERT OR REPLACE INTO graph_edges (source_id, target_id, relation_type, weight)
        VALUES (?, ?, ?, ?)
    """, (article_url, risk_category, 'TRIGGERED_RISK', 1.0))

    conn.commit()
    conn.close()