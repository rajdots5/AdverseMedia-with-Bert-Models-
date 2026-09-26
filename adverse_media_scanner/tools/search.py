import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from config_manager import get_config_list

def is_trusted_source(source_name: str, allowed_agencies: list) -> bool:
    if not source_name or not allowed_agencies:
        return False
    source_name_lower = source_name.lower()
    for allowed in allowed_agencies:
        if allowed.lower().strip() in source_name_lower:
            return True
    return False

def get_adverse_news(name: str, allowed_sources: list, max_results: int = 5):
    # 🆕 Database se live keywords uthana
    keywords = get_config_list("search_keywords", ["fraud", "money laundering", "scam", "arrested"])
    
    # Keyword list se OR condition banana (jaise 'fraud OR scam OR "money laundering"')
    boolean_parts = []
    for kw in keywords:
        if " " in kw:
            boolean_parts.append(f'"{kw}"')
        else:
            boolean_parts.append(kw)
            
    boolean_query = " OR ".join(boolean_parts)
    query = f'"{name}" AND ({boolean_query})'
    
    print(f"🔍 Searching Google News for: {query}")
    print(f"📋 Allowed Sources: {allowed_sources}\n")

    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    results = []
    try:
        req = urllib.request.Request(
            rss_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = root.findall('./channel/item')
        
        for item in items:
            if len(results) >= max_results:
                break
                
            source_elem = item.find('source')
            source_name = source_elem.text if source_elem is not None else ""
            
            if not is_trusted_source(source_name, allowed_sources):
                continue
                
            title = item.find('title').text if item.find('title') is not None else ""
            url = item.find('link').text if item.find('link') is not None else ""
            
            results.append({"title": title, "url": url, "source": source_name})
            
    except Exception as e:
        print(f"❌ Search error: {e}")
        
    return results