import asyncio
import json
import sqlite3
import uuid
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from graph.workflow import create_aml_graph
from database import DB_PATH, init_db, get_customer_kyc
from config_manager import get_all_configs, set_config
from observability import PHOENIX_URL, phoenix_status, traced_span
from tools.search import fetch_google_news_metadata

# Initialize FastAPI with OpenAPI metadata
app = FastAPI(
    title="Adverse Media Screening Microservice",
    description="Adverse media screening API with real-time news search and KYC lookup.",
    version="2.5.0"
)
# Ensure database tables exist on startup
init_db()

# Compile the LangGraph engine once at startup
scanner_engine = create_aml_graph()

class UpdateConfigPayload(BaseModel):
    key: str
    value: str

# --- REQUEST & RESPONSE SCHEMAS ---

class PreviewRequest(BaseModel):
    customer_identifier: str = Field(..., example="Nirav Modi", description="Customer ID or Full Legal Name")
    region: str = Field(default="India", example="India", description="Region for filtering trusted news sources")

class ScanRequest(BaseModel):
    customer_identifier: str = Field(..., example="Nirav Modi", description="Customer ID or Full Legal Name for internal KYC lookup")
    region: str = Field(default="India", example="India", description="Region for filtering trusted news sources")
    fetch_limit: Optional[int] = Field(default=5, ge=1, le=20, example=5, description="Number of news articles to process")

class AnalysisDetail(BaseModel):
    is_match: bool
    entity_confidence: float
    risk_confidence: float
    risk_category: str
    reasoning: str

class ArticleResult(BaseModel):
    title: str
    url: str
    analysis: AnalysisDetail

class ScanResponse(BaseModel):
    scan_id: str
    trace_id: Optional[str] = None
    target_id: int
    target_name: str
    kyc_profile_loaded: dict
    region_applied: str
    fetch_limit_applied: int
    total_articles_scanned: int
    confirmed_matches: int
    results: List[ArticleResult]


def load_subject_context(identifier: str):
    with traced_span("load_subject_context", "TOOL") as span:
        if span:
            span.set_attribute("input.value", identifier)
        kyc = get_customer_kyc(identifier)
        companies = [
            company.strip()
            for company in (kyc.get("associated_companies", "") if kyc else "").split(",")
            if company.strip()
        ]
        has_location = bool(kyc and kyc.get("city"))
        kyc_context = (
            f"City: {kyc['city']}, Companies: {kyc['associated_companies']}"
            if kyc else "No specific KYC data available."
        )
        if span:
            span.set_attribute("kyc.profile_found", bool(kyc))
            span.set_attribute("kyc.location_present", has_location)
            span.set_attribute("kyc.associated_company_count", len(companies))
            span.set_attribute("output.value", json.dumps({"kyc_profile": kyc or {}, "target_context": kyc_context}, ensure_ascii=True))
    return kyc, kyc_context


# --- API ENDPOINTS ---

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Service health check endpoint."""
    return {"status": "healthy", "service": "adverse-media-scanner-v2.5"}


@app.get("/v1/observability")
def get_observability_status():
    return phoenix_status()


@app.post("/v1/preview-search", status_code=status.HTTP_200_OK)
def preview_search(request: PreviewRequest):
    with traced_span("preview_news_search", "CHAIN", {"search.region": request.region}) as span:
        if span:
            span.set_attribute("input.value", json.dumps({
                "customer_identifier": request.customer_identifier,
                "region": request.region,
            }, ensure_ascii=True))
        metadata = fetch_google_news_metadata(request.customer_identifier, request.region)
        if span:
            span.set_attribute("search.result_count", metadata["total_found"])
            span.set_attribute("output.value", json.dumps(metadata, ensure_ascii=True))
    return {
        "customer_identifier": request.customer_identifier,
        "region": request.region,
        "total_links_available_on_google": metadata["total_found"],
        "preview_articles": metadata["articles"][:10]
    }


@app.post("/v1/screen", response_model=ScanResponse, status_code=status.HTTP_200_OK)
def screen_entity(request: ScanRequest):
    try:
        scan_id = str(uuid.uuid4())
        fetch_limit = request.fetch_limit or 5

        with traced_span("adverse_media_screening", "AGENT", {
            "session.id": scan_id,
            "scan.region": request.region,
            "scan.article_limit": fetch_limit,
        }) as span:
            if span:
                span.set_attribute("agent.name", "adverse-media-screening")
                span.set_attribute("input.value", json.dumps({
                    "customer_identifier": request.customer_identifier,
                    "region": request.region,
                    "article_limit": fetch_limit,
                }, ensure_ascii=True))
            kyc, kyc_context = load_subject_context(request.customer_identifier)
            initial_state = {
                "target_id": 0,
                "target_name": request.customer_identifier,
                "target_context": kyc_context,
                "region": request.region,
                "fetch_limit": fetch_limit,
                "search_results": [],
                "current_article": {},
                "analyzed_results": [],
                "errors": []
            }
            final_state = scanner_engine.invoke(initial_state)
            raw_results = final_state.get("analyzed_results", [])
            confirmed_count = sum(1 for item in raw_results if item["analysis"]["is_match"])
            trace_id = format(span.get_span_context().trace_id, "032x") if span else None
            if span:
                span.set_attribute("scan.article_count", len(raw_results))
                span.set_attribute("scan.confirmed_matches", confirmed_count)
                span.set_attribute("output.value", json.dumps({
                    "target_id": final_state.get("target_id", 0),
                    "target_name": request.customer_identifier,
                    "kyc_profile_loaded": kyc or {},
                    "article_count": len(raw_results),
                    "confirmed_matches": confirmed_count,
                    "region": request.region,
                    "results": raw_results,
                }, ensure_ascii=True))

        return {
            "scan_id": scan_id,
            "trace_id": trace_id,
            "target_id": final_state.get("target_id", 0),
            "target_name": request.customer_identifier,
            "kyc_profile_loaded": kyc if kyc else {},
            "region_applied": request.region,
            "fetch_limit_applied": request.fetch_limit,
            "total_articles_scanned": len(raw_results),
            "confirmed_matches": confirmed_count,
            "results": raw_results
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screening pipeline error: {str(e)}"
        )


@app.post("/v1/screen/stream")
async def stream_screen_entity(request: ScanRequest):
    async def event_stream():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        scan_id = str(uuid.uuid4())

        def publish(event):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run_scan():
            try:
                publish({"type": "stage", "stage": "prepare", "status": "running"})
                fetch_limit = request.fetch_limit or 5

                with traced_span("adverse_media_screening", "AGENT", {
                    "session.id": scan_id,
                    "scan.region": request.region,
                    "scan.article_limit": fetch_limit,
                }) as span:
                    if span:
                        span.set_attribute("agent.name", "adverse-media-screening")
                        span.set_attribute("input.value", json.dumps({
                            "customer_identifier": request.customer_identifier,
                            "region": request.region,
                            "article_limit": fetch_limit,
                        }, ensure_ascii=True))
                    kyc, kyc_context = load_subject_context(request.customer_identifier)
                    publish({"type": "stage", "stage": "prepare", "status": "complete"})
                    initial_state = {
                        "target_id": 0,
                        "target_name": request.customer_identifier,
                        "target_context": kyc_context,
                        "region": request.region,
                        "fetch_limit": fetch_limit,
                        "search_results": [],
                        "current_article": {},
                        "analyzed_results": [],
                        "errors": [],
                    }
                    final_state = scanner_engine.invoke(
                        initial_state,
                        config={"configurable": {"progress_callback": publish}},
                    )
                    results = final_state.get("analyzed_results", [])
                    confirmed_matches = sum(
                        1 for item in results if item["analysis"]["is_match"]
                    )
                    result = {
                        "target_id": final_state.get("target_id", 0),
                        "target_name": request.customer_identifier,
                        "kyc_profile_loaded": kyc or {},
                        "region_applied": request.region,
                        "fetch_limit_applied": fetch_limit,
                        "total_articles_scanned": len(results),
                        "confirmed_matches": confirmed_matches,
                        "results": results,
                        "scan_id": scan_id,
                    }
                    if span:
                        span.set_attribute("scan.article_count", len(results))
                        span.set_attribute("scan.confirmed_matches", confirmed_matches)
                        span.set_attribute("output.value", json.dumps({
                            "target_id": final_state.get("target_id", 0),
                            "target_name": request.customer_identifier,
                            "kyc_profile_loaded": kyc or {},
                            "article_count": len(results),
                            "confirmed_matches": confirmed_matches,
                            "region": request.region,
                            "results": results,
                        }, ensure_ascii=True))
                        result["trace_id"] = format(span.get_span_context().trace_id, "032x")
                publish({"type": "complete", "result": result})
            except Exception as error:
                publish({"type": "error", "message": str(error)})

        task = asyncio.create_task(asyncio.to_thread(run_scan))
        yield f"data: {json.dumps({'type': 'connected', 'scan_id': scan_id, 'phoenix_url': PHOENIX_URL})}\n\n"

        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=True)}\n\n"
            if event["type"] in ("complete", "error"):
                await task
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/screenings/{target_id}", status_code=status.HTTP_200_OK)
def get_historical_screening(target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, context FROM targets WHERE id = ?", (target_id,))
    target = cursor.fetchone()

    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Target not found in records")

    cursor.execute("""
        SELECT s.url, s.title, r.is_match, r.confidence_score, r.risk_category, r.reasoning
        FROM scraped_news s
        JOIN screening_results r ON s.id = r.article_id
        WHERE s.target_id = ?
    """, (target_id,))
    
    records = cursor.fetchall()
    conn.close()

    history = []
    for row in records:
        history.append({
            "url": row[0],
            "title": row[1],
            "is_match": bool(row[2]),
            "risk_score": row[3],
            "risk_category": row[4],
            "reasoning": row[5]
        })

    return {
        "target_id": target[0],
        "name": target[1],
        "context": target[2],
        "audit_trail": history
    }


@app.get("/v1/configs", tags=["Admin Settings"])
def fetch_system_configurations():
    return get_all_configs()

@app.put("/v1/configs", tags=["Admin Settings"])
def update_system_configuration(payload: UpdateConfigPayload):
    success = set_config(payload.key, payload.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")
    return {"status": "success", "message": f"Configuration '{payload.key}' updated successfully"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)