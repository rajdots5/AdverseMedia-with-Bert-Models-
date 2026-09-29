import sqlite3
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from tools.search import get_adverse_news
from tools.scraper import scrape_article
from tools.analyzer import resolve_entity_with_weights, classify_risk
from database import DB_PATH, get_customer_kyc, log_graph_audit
from config_manager import get_config_int

def search_node(state: AgentState) -> dict:
    target_region = state.get("region", "India")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT allowed_sources FROM region_configs WHERE region_name = ?", (target_region,))
    row = cursor.fetchone()
    conn.close()
    
    allowed_list = [s.strip() for s in row[0].split(',')] if row else []
    
    # 🚀 Interactive terminal ya API payload se aane wala fetch_limit state se uthao
    user_fetch_limit = state.get("fetch_limit", 5)

    print(f"\n[Node 1: Search] Target: {state['target_name']} | Region: {target_region} | Requested Limit: {user_fetch_limit}")
    
    # 🛠️ CRITICAL FIX: max_results me user_fetch_limit pass karna taaki hardcoded 5 override ho jaye
    articles = get_adverse_news(
        state["target_name"], 
        allowed_sources=allowed_list, 
        max_results=user_fetch_limit,
        region_name=target_region
    )
    
    return {"search_results": articles}


def process_and_persist_node(state: AgentState) -> dict:
    print(f"\n[Node 2: Processing & Knowledge Graph Audit]")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    target_name = state["target_name"]
    
    cursor.execute(
        "INSERT INTO targets (name, context) VALUES (?, ?)",
        (target_name, state["target_context"])
    )
    target_id = cursor.lastrowid
    conn.commit()
    conn.close()

    analyzed_list = []
    MIN_CONTENT_LENGTH = get_config_int("min_content_length", 150)
    
    kyc_profile = get_customer_kyc(target_name)

    for item in state.get("search_results", []):
        url = item["url"]
        title = item["title"]

        scraped = scrape_article(url)
        content = scraped.get("text", "")

        if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
            print(f"⏭️ Skipping (Insufficient content): {title[:35]}...")
            continue

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO scraped_news (target_id, url, title, content) VALUES (?, ?, ?, ?)",
            (target_id, scraped["url"], title, content)
        )
        conn.commit()
        article_id = cursor.lastrowid
        conn.close()

        print(f"\n⚡ Running Weighted Resolution for: '{title[:35]}...'")
        
        resolution = resolve_entity_with_weights(target_name, kyc_profile, content)
        
        if not resolution["is_match"]:
            print("⏭️ Filtered out by Financial/Entity Check.")
            analysis = {
                "is_match": False,
                "entity_confidence": resolution["entity_confidence"],
                "risk_confidence": 0.0,
                "risk_category": "None",
                "reasoning": resolution["reasoning"]
            }
        else:
            print("🎯 Match Confirmed! Running Risk Classification...")
            risk_data = classify_risk(content)
            analysis = {
                "is_match": True,
                "entity_confidence": resolution["entity_confidence"],
                "risk_confidence": risk_data["confidence_score"],
                "risk_category": risk_data["risk_category"],
                "reasoning": resolution["reasoning"]
            }
            
            log_graph_audit(
                target_name=target_name,
                article_url=scraped["url"],
                article_title=title,
                match_score=resolution["entity_confidence"],
                risk_category=risk_data["risk_category"]
            )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO screening_results 
            (article_id, is_match, confidence_score, risk_category, reasoning)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                article_id,
                analysis["is_match"],
                analysis["risk_confidence"],
                analysis["risk_category"],
                analysis["reasoning"]
            )
        )
        conn.commit()
        conn.close()

        analyzed_list.append({
            "title": title,
            "url": scraped["url"],
            "analysis": analysis
        })

    return {"analyzed_results": analyzed_list, "target_id": target_id}

def create_aml_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("search", search_node)
    workflow.add_node("process_and_persist", process_and_persist_node)
    workflow.set_entry_point("search")
    workflow.add_edge("search", "process_and_persist")
    workflow.add_edge("process_and_persist", END)
    return workflow.compile()