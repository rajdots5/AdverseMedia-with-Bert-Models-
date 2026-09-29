import sys
from graph.workflow import create_aml_graph
from database import init_db, get_customer_kyc
from tools.search import fetch_google_news_metadata

def run_scanner(customer_identifier: str, region: str = "India"):
    """
    Runs the fully interactive 2-step compliance screening workflow from the terminal:
    1. Discovers and previews total available links on Google trusted sources in real-time.
    2. Prompts the user interactively to input how many top links they want to fetch and scan.
    3. Loads internal KYC profile and executes LangGraph multi-factor entity resolution & risk analysis.
    """
    init_db()

    print("\n========================================================")
    print(f"🚀 STARTING KNOWLEDGE-GRAPH DRIVEN AML SCANNER")
    print(f"👤 Target Identifier: {customer_identifier.upper()} ({region.upper()})")
    print("========================================================\n")

    # Step 1: Real-Time Discovery Preview (Check total available links before processing)
    print("🔍 [Step 1] Probing Google Trusted Sources for Real-Time Metadata...")
    metadata = fetch_google_news_metadata(customer_identifier, region)
    total_available = metadata["total_found"]
    
    print(f"📊 [Discovery Result] Total {total_available} articles found available on Google for '{customer_identifier}'.")

    if total_available == 0:
        print("❌ No articles found to process. Exiting screening.")
        return

    # Step 2: Interactive Prompt for Fetch Limit
    print("\n" + "-" * 50)
    try:
        user_input = input(f"⚙️ Enter how many top links you want to fetch and scan (1 - {min(total_available, 20)}) [Default: 5]: ").strip()
        fetch_limit = int(user_input) if user_input else 5
    except ValueError:
        print("⚠️ Invalid input detected. Defaulting to fetch limit = 5.")
        fetch_limit = 5
    print("-" * 50 + "\n")

    # Step 3: Internal KYC Profile Lookup
    print("[System] Fetching internal KYC profile...")
    kyc = get_customer_kyc(customer_identifier)
    
    if kyc:
        print(f"✅ KYC Loaded -> City: {kyc['city']} | Profession: {kyc['profession']} | Companies: {kyc['associated_companies']}\n")
        kyc_context = f"City: {kyc['city']}, Companies: {kyc['associated_companies']}"
    else:
        print("⚠️ No internal KYC profile found.\n")
        kyc_context = "No specific KYC data available."

    initial_state = {
        "target_id": 0,
        "target_name": customer_identifier,
        "target_context": kyc_context,
        "region": region,
        "fetch_limit": fetch_limit,  # Pass interactive user-defined fetch limit to workflow state
        "search_results": [],
        "current_article": {},
        "analyzed_results": [],
        "errors": []
    }

    # Step 4: Execute LangGraph AI Pipeline
    print(f"⚡ [Step 4] Executing LangGraph AI Screening Pipeline for top {fetch_limit} links...")
    app = create_aml_graph()
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("📋 FINAL COMPLIANCE SCREENING REPORT (WITH KNOWLEDGE GRAPH AUDIT)")
    print("=" * 60)

    results = final_state.get("analyzed_results", [])
    if not results:
        print("No matched adverse media found or all articles failed content length/scraping filters.")
        return

    for idx, res in enumerate(results, 1):
        analysis = res["analysis"]
        match_status = "CONFIRMED MATCH" if analysis["is_match"] else "NO MATCH (FALSE POSITIVE)"
        
        print(f"\n[{idx}] {res['title']}")
        print(f"🔗 Source URL: {res['url']}")
        print(f"🎯 Entity Resolution: {match_status}")
        print(f"⚖️ Dynamic Match Score (Name + Location + Org): {analysis['entity_confidence'] * 100:.0f}%")
        print(f"⚠️ Risk Category: {analysis['risk_category']} (Risk Score: {analysis['risk_confidence'] * 100:.1f}%)")
        print(f"📝 Audit Trail / Reasoning: {analysis['reasoning']}")
        print("-" * 60)

if __name__ == "__main__":
    TARGET_NAME = "Nirav Modi"
    TARGET_REGION = "India"
    run_scanner(TARGET_NAME, TARGET_REGION)