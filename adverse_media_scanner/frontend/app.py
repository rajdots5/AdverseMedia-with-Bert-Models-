import streamlit as st
import requests
import pandas as pd

# FastAPI Backend URL
BACKEND_URL = "http://127.0.0.1:8000"

# Page Config
st.set_page_config(
    page_title="AML Enterprise Screening Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Dark Mode Financial Theme)
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 8px; border: 1px solid #30363d; }
    .stAlert { background-color: #1f242d; color: #ffffff; border: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

# Sidebar Navigation
st.sidebar.title("🛡️ AML Risk Hub")
st.sidebar.markdown("---")
app_mode = st.sidebar.selectbox("Navigation", ["🔍 Live Screening", "📜 Audit Trail & Graph Logs", "⚙️ Admin & Rule Engine"])

# ==========================================
# 1. LIVE SCREENING MODULE
# ==========================================
if app_mode == "🔍 Live Screening":
    st.title("🔍 KYC-Driven Adverse Media Screener")
    st.markdown("Run automated multi-factor entity resolution and risk intelligence checks against internal KYC profiles.")

    col1, col2 = st.columns([2, 1])
    with col1:
        customer_id = st.text_input("Customer Identifier / Legal Name", value="Nirav Modi", help="Enter exact name or CUST-ID matching the database records.")
    with col2:
        region = st.selectbox("Jurisdiction Region", ["India", "Global"], index=0)

    if st.button("🚀 Execute Compliance Scan", type="primary", use_container_width=True):
        if not customer_id.strip():
            st.warning("Please provide a valid customer identifier.")
        else:
            with st.spinner("Executing LangGraph agents, parsing news, and running BERT models..."):
                try:
                    payload = {"customer_identifier": customer_id.strip(), "region": region}
                    response = requests.post(f"{BACKEND_URL}/v1/screen", json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state['last_scan_result'] = data
                        st.success("Screening Completed Successfully!")
                    else:
                        st.error(f"Server Error: {response.json().get('detail', 'Unknown error')}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Could not connect to FastAPI backend. Ensure `api.py` is running on port 8000.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {str(e)}")

    # Display Results if available
    if 'last_scan_result' in st.session_state:
        res = st.session_state['last_scan_result']
        st.markdown("---")
        
        # Metrics Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Target Entity", res.get("target_name"))
        m2.metric("Articles Scanned", res.get("total_articles_scanned"))
        m3.metric("Confirmed Matches", res.get("confirmed_matches"), delta_color="inverse")
        m4.metric("Jurisdiction", res.get("region_applied"))

        # KYC Profile Details Expander
        kyc = res.get("kyc_profile_loaded", {})
        if kyc:
            with st.expander("👤 Loaded Internal KYC Profile"):
                kc1, kc2, kc3 = st.columns(3)
                kc1.write(f"**Customer ID:** {kyc.get('customer_id')}")
                kc1.write(f"**Full Name:** {kyc.get('full_name')}")
                kc2.write(f"**City:** {kyc.get('city')}")
                kc2.write(f"**Profession:** {kyc.get('profession')}")
                kc3.write(f"**Associated Companies:** {kyc.get('associated_companies')}")

        st.subheader("📋 Screening Findings & Audit Trail")
        results_list = res.get("results", [])
        
        if not results_list:
            st.info("No relevant financial adverse media found matching the criteria.")
        else:
            for idx, item in enumerate(results_list, 1):
                analysis = item["analysis"]
                is_match = analysis["is_match"]
                
                box_color = "#1f242d" if is_match else "#0d1117"
                status_badge = "🟢 CONFIRMED MATCH" if is_match else "⚪ FILTERED OUT / FALSE POSITIVE"
                
                with st.container():
                    st.markdown(f"""
                        <div style="background-color: {box_color}; padding: 15px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 10px;">
                            <h4>[{idx}] {item['title']}</h4>
                            <p><a href="{item['url']}" target="_blank" style="color: #58a6ff;">🔗 Source Link</a></p>
                            <p><b>Status:</b> {status_badge}</p>
                            <p><b>Dynamic Match Score:</b> {analysis['entity_confidence'] * 100:.0f}% &nbsp;|&nbsp; <b>Risk Severity Score:</b> {analysis['risk_confidence'] * 100:.1f}%</p>
                            <p><b>Risk Category:</b> <span style="color: #f85149;">{analysis['risk_category']}</span></p>
                            <p><b>Audit Trail / Reasoning:</b> <code>{analysis['reasoning']}</code></p>
                        </div>
                    """, unsafe_allow_html=True)

# ==========================================
# 2. HISTORICAL AUDIT TRAIL
# ==========================================
elif app_mode == "📜 Audit Trail & Graph Logs":
    st.title("📜 Compliance Audit Logs")
    st.markdown("Retrieve historical screening results and decision lineage stored in the SQLite compliance repository.")

    target_id_input = st.number_input("Enter Target Record ID", min_value=1, step=1, value=1)
    
    if st.button("Fetch Audit Trail"):
        try:
            res = requests.get(f"{BACKEND_URL}/v1/screenings/{target_id_input}")
            if res.status_code == 200:
                history_data = res.json()
                st.subheader(f"Audit Dossier for: {history_data.get('name')}")
                st.write(f"**Stored Context:** {history_data.get('context')}")
                
                audit_trail = history_data.get("audit_trail", [])
                if audit_trail:
                    df = pd.DataFrame(audit_trail)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No audit logs found for this Record ID.")
            else:
                st.warning("Record ID not found in database.")
        except Exception as e:
            st.error(f"Error connecting to backend: {e}")

# ==========================================
# 3. ADMIN SETTINGS & RULE ENGINE
# ==========================================
elif app_mode == "⚙️ Admin & Rule Engine":
    st.title("⚙️ Compliance Rule Engine & System Configurations")
    st.markdown("Dynamically modify operational parameters, risk labels, and search keywords without touching code.")

    try:
        res = requests.get(f"{BACKEND_URL}/v1/configs")
        if res.status_code == 200:
            configs = res.json()
            
            with st.form("config_form"):
                updated_configs = {}
                for key, val in configs.items():
                    updated_configs[key] = st.text_input(f"Config Key: `{key}`", value=str(val))
                
                submit = st.form_submit_button("💾 Save Configuration Changes", type="primary")
                if submit:
                    success_count = 0
                    for k, v in updated_configs.items():
                        r = requests.put(f"{BACKEND_URL}/v1/configs", json={"key": k, "value": v})
                        if r.status_code == 200:
                            success_count += 1
                    if success_count > 0:
                        st.success("Configurations updated successfully across the system!")
                    else:
                        st.error("Failed to update some configurations.")
        else:
            st.error("Failed to fetch configurations from backend.")
    except Exception as e:
        st.error(f"Backend connection error: {e}")