import sqlite3
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import uvicorn

from graph.workflow import create_aml_graph
from database import DB_PATH, init_db, get_customer_kyc
from config_manager import get_all_configs, set_config
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
    fetch_limit: Optional[int] = Field(default=5, example=3, description="Real-time control on how many top links to fetch and process")

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
    target_id: int
    target_name: str
    kyc_profile_loaded: dict
    region_applied: str
    fetch_limit_applied: int
    total_articles_scanned: int
    confirmed_matches: int
    results: List[ArticleResult]


# --- API ENDPOINTS ---

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Service health check endpoint."""
    return {"status": "healthy", "service": "adverse-media-scanner-v2.5"}


@app.post("/v1/preview-search", status_code=status.HTTP_200_OK)
def preview_search(request: PreviewRequest):
    metadata = fetch_google_news_metadata(request.customer_identifier, request.region)
    return {
        "customer_identifier": request.customer_identifier,
        "region": request.region,
        "total_links_available_on_google": metadata["total_found"],
        "preview_articles": metadata["articles"][:10]
    }


@app.post("/v1/screen", response_model=ScanResponse, status_code=status.HTTP_200_OK)
def screen_entity(request: ScanRequest):
    try:
        kyc = get_customer_kyc(request.customer_identifier)
        kyc_context = f"City: {kyc['city']}, Companies: {kyc['associated_companies']}" if kyc else "No specific KYC data available."

        initial_state = {
            "target_id": 0,
            "target_name": request.customer_identifier,
            "target_context": kyc_context,
            "region": request.region,
            "fetch_limit": request.fetch_limit,
            "search_results": [],
            "current_article": {},
            "analyzed_results": [],
            "errors": []
        }

        final_state = scanner_engine.invoke(initial_state)
        raw_results = final_state.get("analyzed_results", [])
        confirmed_count = sum(1 for item in raw_results if item["analysis"]["is_match"])

        return {
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