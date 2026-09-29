import sqlite3
import re
import urllib.parse
from bs4 import BeautifulSoup
import requests
from database import DB_PATH

def fetch_allowed_sources_from_db(region_name: str) -> list:
    """Database se region ke mutabiq allowed sources (with domains) fetch karta hai."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT allowed_sources FROM region_configs WHERE region_name = ?", (region_name,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            return [s.strip() for s in row[0].split(',') if s.strip()]
    except Exception as e:
        print(f"⚠️ Error fetching allowed sources from DB: {e}")
    return []

def extract_domain(source_string: str) -> str:
    """Database string se domain extract karta hai (jaise 'The Hindu (thehindu.com)' -> 'thehindu.com')."""
    match = re.search(r'\((.*?)\)', source_string)
    if match:
        return match.group(1).strip()
    return source_string.lower().replace(" ", "") + ".com"

def fetch_google_news_metadata(target_name: str, region_name: str = "India") -> dict:
    """
    Real-time metadata discovery: Hits Google RSS feed restricted to DB trusted sources 
    and returns total count and list of articles without heavy scraping.
    """
    allowed_sources = fetch_allowed_sources_from_db(region_name)
    site_filters = [f"site:{extract_domain(s)}" for s in allowed_sources if extract_domain(s)]
    
    if site_filters:
        query = f'"{target_name}" AND ({" OR ".join(site_filters)})'
    else:
        query = f'"{target_name}"'

    print(f"🎯 Targeted Google Search Query: {query}")
    
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch Google News RSS. Status Code: {response.status_code}")
            return {"total_found": 0, "articles": []}

        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        all_articles = []
        for item in items:
            title = item.title.text if item.title else "No Title"
            link = item.link.text if item.link else ""
            if link:
                all_articles.append({"title": title, "url": link})

        return {
            "total_found": len(all_articles),
            "articles": all_articles
        }
    except Exception as e:
        print(f"❌ Metadata probe error: {e}")
        return {"total_found": 0, "articles": []}

def get_adverse_news(target_name: str, allowed_sources: list = None, max_results: int = 5, region_name: str = "India") -> list:
    """
    Performs real-time search discovery and returns only the user-specified 
    top 'max_results' links for deep AI processing.
    """
    metadata = fetch_google_news_metadata(target_name, region_name=region_name)
    all_articles = metadata["articles"]
    
    # 🛠️ Ensures exact user requested limit (e.g., 3, 10, etc.) is sliced correctly
    selected_articles = all_articles[:max_results]
    print(f"📦 Fetched top {len(selected_articles)} articles from trusted sites for AI risk evaluation.")
    return selected_articles