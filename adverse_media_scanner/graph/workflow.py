import json
import sqlite3
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from tools.search import get_adverse_news
from tools.scraper import scrape_article
from tools.analyzer import resolve_entity_with_weights, classify_risk
from database import DB_PATH, get_customer_kyc, log_graph_audit
from config_manager import get_config_int
from observability import mark_span_error, traced_span


def emit_progress(config, event):
    callback = (config or {}).get("configurable", {}).get("progress_callback")
    if callback:
        callback(event)


def search_node(state: AgentState, config=None) -> dict:
    target_region = state.get("region", "India")
    # 🚀 Interactive terminal ya API payload se aane wala fetch_limit state se uthao
    user_fetch_limit = state.get("fetch_limit", 5)

    emit_progress(config, {"type": "stage", "stage": "search", "status": "running"})
    with traced_span("news_search", "TOOL", {"search.region": target_region}) as span:
        if span:
            span.set_attribute("input.value", json.dumps({
                "target_name": state["target_name"],
                "region": target_region,
                "article_limit": user_fetch_limit,
            }, ensure_ascii=True))
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT allowed_sources FROM region_configs WHERE region_name = ?", (target_region,))
        row = cursor.fetchone()
        conn.close()

        allowed_list = [s.strip() for s in row[0].split(',')] if row else []
        if span:
            span.set_attribute("search.allowed_sources", json.dumps(allowed_list, ensure_ascii=True))
        print(f"\n[Node 1: Search] Target: {state['target_name']} | Region: {target_region} | Requested Limit: {user_fetch_limit}")
        articles = get_adverse_news(
            state["target_name"],
            allowed_sources=allowed_list,
            max_results=user_fetch_limit,
            region_name=target_region
        )
        if span:
            span.set_attribute("search.result_count", len(articles))
            span.set_attribute("output.value", json.dumps({
                "result_count": len(articles),
                "articles": articles,
            }, ensure_ascii=True))

    emit_progress(config, {
        "type": "search_complete",
        "count": len(articles),
        "articles": [{"title": item["title"], "url": item["url"]} for item in articles],
    })
    emit_progress(config, {"type": "stage", "stage": "search", "status": "complete"})
    return {"search_results": articles}


def process_and_persist_node(state: AgentState, config=None) -> dict:
    print(f"\n[Node 2: Processing & Knowledge Graph Audit]")
    target_name = state["target_name"]
    emit_progress(config, {"type": "stage", "stage": "record", "status": "running"})
    with traced_span("create_screening_record", "TOOL") as span:
        if span:
            span.set_attribute("input.value", json.dumps({
                "target_name": target_name,
                "target_context": state["target_context"],
            }, ensure_ascii=True))
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO targets (name, context) VALUES (?, ?)",
            (target_name, state["target_context"])
        )
        target_id = cursor.lastrowid
        conn.commit()
        conn.close()
        if span:
            span.set_attribute("database.record_created", True)
            span.set_attribute("output.value", json.dumps({
                "target_id": target_id,
                "record": {"name": target_name, "context": state["target_context"]},
            }, ensure_ascii=True))
    emit_progress(config, {"type": "stage", "stage": "record", "status": "complete", "target_id": target_id})

    analyzed_list = []
    MIN_CONTENT_LENGTH = get_config_int("min_content_length", 150)
    
    kyc_profile = get_customer_kyc(target_name)

    articles = state.get("search_results", [])
    emit_progress(config, {"type": "stage", "stage": "processing", "status": "running", "count": len(articles)})

    for index, item in enumerate(articles, 1):
        url = item["url"]
        title = item["title"]

        emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "scrape", "status": "running"})
        with traced_span("scrape_article", "TOOL", {
            "article.index": index,
            "article.title": title,
        }) as span:
            if span:
                span.set_attribute("input.value", json.dumps({"url": url, "title": title}, ensure_ascii=True))
            scraped = scrape_article(url)
            content = scraped.get("text", "")
            if span:
                span.set_attribute("scrape.extracted_characters", len(content))
                span.set_attribute("scrape.has_content", bool(content))
                if scraped.get("error"):
                    mark_span_error(span, "scrape", "ArticleExtractionFailed")
                span.set_attribute("output.value", json.dumps(scraped, ensure_ascii=True))

        if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
            print(f"⏭️ Skipping (Insufficient content): {title[:35]}...")
            emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "scrape", "status": "skipped", "detail": "Insufficient article text"})
            for skipped_stage in ("entity", "risk", "persist"):
                emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": skipped_stage, "status": "skipped", "detail": "Article extraction did not produce enough text"})
            continue

        emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "scrape", "status": "complete"})

        print(f"\n⚡ Running Weighted Resolution for: '{title[:35]}...'")
        emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "entity", "status": "running"})
        with traced_span("resolve_entity", "CHAIN", {
            "article.index": index,
            "article.title": title,
        }) as span:
            if span:
                span.set_attribute("input.value", json.dumps({
                    "target_name": target_name,
                    "kyc_profile": kyc_profile,
                    "article_text": content,
                }, ensure_ascii=True))
            resolution = resolve_entity_with_weights(target_name, kyc_profile, content)
            if span:
                span.set_attribute("entity.match", resolution["is_match"])
                span.set_attribute("entity.confidence", resolution["entity_confidence"])
                span.set_attribute("entity.financial_context", resolution["financial_context"])
                span.set_attribute("entity.matched_association_count", resolution["matched_association_count"])
                for factor, score in resolution["factor_scores"].items():
                    span.set_attribute(f"entity.factor.{factor}", score)
                span.set_attribute("entity.ner_used", resolution["ner_used"])
                span.set_attribute("entity.extracted_names", json.dumps(resolution["extracted_names"], ensure_ascii=True))
                span.set_attribute("output.value", json.dumps(resolution, ensure_ascii=True))
        emit_progress(config, {
            "type": "article_stage", "index": index, "title": title,
            "stage": "entity", "status": "complete",
            "is_match": resolution["is_match"],
            "confidence": resolution["entity_confidence"],
        })
        
        if not resolution["is_match"]:
            print("⏭️ Filtered out by Financial/Entity Check.")
            emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "risk", "status": "skipped", "detail": "Entity match threshold was not met"})
            analysis = {
                "is_match": False,
                "entity_confidence": resolution["entity_confidence"],
                "risk_confidence": 0.0,
                "risk_category": "None",
                "reasoning": resolution["reasoning"]
            }
        else:
            print("🎯 Match Confirmed! Running Risk Classification...")
            emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "risk", "status": "running"})
            with traced_span("classify_risk", "CHAIN", {
                "article.index": index,
                "article.title": title,
            }) as span:
                if span:
                    span.set_attribute("input.value", json.dumps({"article_text": content}, ensure_ascii=True))
                risk_data = classify_risk(content)
                if span:
                    span.set_attribute("input.value", json.dumps({
                        "article_text": content,
                        "candidate_labels": risk_data["candidate_labels"],
                        "fallback_keywords": risk_data["fallback_keywords"],
                        "chunk_size": risk_data["chunk_size"],
                        "max_text_scan_limit": risk_data["max_text_scan_limit"],
                    }, ensure_ascii=True))
                    span.set_attribute("risk.category", risk_data["risk_category"])
                    span.set_attribute("risk.confidence", risk_data["confidence_score"])
                    span.set_attribute("risk.chunks_analyzed", risk_data["chunks_analyzed"])
                    span.set_attribute("risk.fallback_used", risk_data["fallback_used"])
                    span.set_attribute("output.value", json.dumps(risk_data, ensure_ascii=True))
            analysis = {
                "is_match": True,
                "entity_confidence": resolution["entity_confidence"],
                "risk_confidence": risk_data["confidence_score"],
                "risk_category": risk_data["risk_category"],
                "reasoning": resolution["reasoning"]
            }
            emit_progress(config, {
                "type": "article_stage", "index": index, "title": title,
                "stage": "risk", "status": "complete",
                "category": risk_data["risk_category"],
                "confidence": risk_data["confidence_score"],
            })
            with traced_span("persist_knowledge_graph_audit", "TOOL") as audit_span:
                audit_input = {
                    "target_name": target_name,
                    "article_url": scraped["url"],
                    "article_title": title,
                    "match_score": resolution["entity_confidence"],
                    "risk_category": risk_data["risk_category"],
                }
                if audit_span:
                    audit_span.set_attribute("input.value", json.dumps(audit_input, ensure_ascii=True))
                log_graph_audit(**audit_input)
                if audit_span:
                    audit_span.set_attribute("database.graph_audit_saved", True)
                    audit_span.set_attribute("output.value", "{\"graph_audit_saved\":true}")

        emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "persist", "status": "running"})
        with traced_span("persist_analysis", "TOOL", {
            "article.index": index,
            "article.title": title,
        }) as span:
            if span:
                span.set_attribute("input.value", json.dumps({
                    "target_id": target_id,
                    "article_url": scraped["url"],
                    "article_title": title,
                    "article_text": content,
                    "analysis": analysis,
                }, ensure_ascii=True))
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO scraped_news (target_id, url, title, content) VALUES (?, ?, ?, ?)",
                (target_id, scraped["url"], title, content)
            )
            article_id = cursor.lastrowid
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
            if span:
                span.set_attribute("database.analysis_saved", True)
                span.set_attribute("database.article_id", article_id)
                span.set_attribute("output.value", json.dumps({
                    "analysis_saved": True,
                    "article_id": article_id,
                    "analysis": analysis,
                }, ensure_ascii=True))
        emit_progress(config, {"type": "article_stage", "index": index, "title": title, "stage": "persist", "status": "complete"})

        analyzed_list.append({
            "title": title,
            "url": scraped["url"],
            "analysis": analysis
        })
        emit_progress(config, {"type": "article_complete", "index": index, "title": title, "result": analyzed_list[-1]})

    emit_progress(config, {"type": "stage", "stage": "processing", "status": "complete", "count": len(analyzed_list)})
    emit_progress(config, {"type": "stage", "stage": "complete", "status": "complete", "count": len(analyzed_list)})
    return {"analyzed_results": analyzed_list, "target_id": target_id}

def create_aml_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("search", search_node)
    workflow.add_node("process_and_persist", process_and_persist_node)
    workflow.set_entry_point("search")
    workflow.add_edge("search", "process_and_persist")
    workflow.add_edge("process_and_persist", END)
    return workflow.compile()