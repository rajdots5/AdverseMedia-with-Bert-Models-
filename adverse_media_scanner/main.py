import sys
from graph.workflow import create_aml_graph
from database import init_db, get_customer_kyc

def run_scanner(customer_identifier: str, region: str = "India"):
    init_db()

    print("\n========================================================")
    print(f"🚀 STARTING KNOWLEDGE-GRAPH DRIVEN AML SCANNER")
    print(f"👤 Target Identifier: {customer_identifier.upper()} ({region.upper()})")
    print("========================================================\n")

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
        "search_results": [],
        "current_article": {},
        "analyzed_results": [],
        "errors": []
    }

    app = create_aml_graph()
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("📋 FINAL COMPLIANCE SCREENING REPORT (WITH KNOWLEDGE GRAPH AUDIT)")
    print("=" * 60)

    results = final_state.get("analyzed_results", [])
    if not results:
        print("No matched adverse media found or all articles failed scraping.")
        return

    for idx, res in enumerate(results, 1):
        analysis = res["analysis"]
        match_status = "CONFIRMED MATCH" if analysis["is_match"] else "NO MATCH (FALSE POSITIVE)"
        
        print(f"\n[{idx}] {res['title']}")
        print(f"🔗 Source URL: {res['url']}")
        print(f"🎯 Entity Resolution: {match_status}")
        print(f"⚖️ Dynamic Match Score (Name + Location + Org): {analysis['entity_confidence'] * 100:.0f}%")
        print(f"⚠️  Risk Category: {analysis['risk_category']} (Risk Score: {analysis['risk_confidence'] * 100:.1f}%)")
        print(f"📝 Audit Trail / Reasoning: {analysis['reasoning']}")
        print("-" * 60)

if __name__ == "__main__":
    TARGET_NAME = "Nirav Modi"
    TARGET_REGION = "India"
    run_scanner(TARGET_NAME, TARGET_REGION)