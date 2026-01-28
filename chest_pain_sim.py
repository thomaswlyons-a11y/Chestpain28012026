import streamlit as st
import graphviz
import random
import time
import pandas as pd
from datetime import datetime
from io import BytesIO

# Try to import reportlab, handle error if missing
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- 1. CONFIGURATION & STATE ---
st.set_page_config(page_title="NHS Clinical Director Sim", layout="wide", page_icon="🏥")
NHS_BLUE = "#005EB8"

# Initialize Session State
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}
if 'last_run_settings' not in st.session_state:
    st.session_state['last_run_settings'] = {}

# --- 2. SIDEBAR CONTROLS ---
st.sidebar.title("⚙️ Operations Control")

st.sidebar.header("1. Department Volume")
daily_census = st.sidebar.number_input("Avg. Daily ED Attendances", value=250, step=10)
chest_pain_pct = st.sidebar.slider("% Presenting with Chest Pain", 0, 25, 8)
daily_cp_volume = int(daily_census * (chest_pain_pct / 100))
st.sidebar.caption(f"📉 Est. Chest Pain Load: {daily_cp_volume} pts/day")

st.sidebar.divider()

st.sidebar.header("2. Strategy")
test_modality = st.sidebar.radio("Troponin Modality:", ("Central Lab (High Sensitivity)", "Point of Care (POC)"))

# Define variables based on selection
if test_modality == "Point of Care (POC)":
    test_cost = 30.00
    turnaround_time = 20
    availability_chance = 0.85 
else:
    test_cost = 5.00
    turnaround_time = 90
    availability_chance = 0.35

st.sidebar.header("3. Thresholds & Logistics")
rule_out_limit = st.sidebar.number_input("Rule Out (<)", value=5)
rule_in_limit = st.sidebar.number_input("Rule In (>)", value=52)
discharge_dest = st.sidebar.selectbox("Discharge To:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))

consultant_cost = st.sidebar.slider("Consultant Cost (£/hr)", 100, 200, 135)
nurse_cost = st.sidebar.slider("Nurse Cost (£/hr)", 20, 50, 30)

# Capture current settings signature to check for staleness later
current_settings_sig = f"{daily_census}-{test_modality}-{rule_out_limit}-{discharge_dest}"

# --- 3. PDF GENERATOR FUNCTION ---
def generate_pdf_report(filename, modality, dest, financials, census, cp_vol):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Header / Title
    p.setFillColorRGB(0, 0.36, 0.72) # NHS Blue
    p.rect(0, 750, 612, 50, fill=1, stroke=0)
    p.setFillColorRGB(1, 1, 1) # White text
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, 765, "NHS Trust - Strategic Capacity Protocol")
    
    # Timestamp info
    p.setFillColorRGB(0,0,0)
    p.setFont("Helvetica", 10)
    p.drawString(450, 765, datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Body Content
    y = 700
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "1. OPERATIONAL CONFIGURATION")
    y -= 20
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"• Diagnostic Strategy: {modality}")
    y -= 15
    p.drawString(50, y, f"• Daily Census: {census} (Chest Pain Vol: {cp_vol})")
    y -= 15
    p.drawString(50, y, f"• Discharge Pathway: {dest}")
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "2. CLINICAL ALGORITHM")
    y -= 20
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"• Rule Out (Discharge): < {rule_out_limit} ng/L")
    y -= 15
    p.drawString(50, y, f"• Rule In (Intervention): > {rule_in_limit} ng/L")
    y -= 15
    p.drawString(50, y, f"• Observe (Admit AMU): {rule_out_limit} - {rule_in_limit} ng/L")
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "3. FINANCIAL & CAPACITY FORECAST (Daily)")
    y -= 20
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"• Test Costs (Kit): £{financials['test_cost']:.2f}")
    y -= 15
    p.drawString(50, y, f"• Clinical Time Wasted: £{financials['waiting_cost']:.2f}")
    y -= 15
    p.drawString(50, y, f"• TOTAL DAILY COST: £{financials['total']:.2f}")
    y -= 15
    p.drawString(50, y, f"• Bed Blocks (Delays): {financials['beds_blocked']} patients")
    
    # Annual Projection
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "4. ANNUAL PROJECTION")
    y -= 20
    annual_cost = financials['total'] * 365
    p.setFont("Helvetica-Bold", 14)
    p.setFillColorRGB(0.8, 0, 0) # Red
    p.drawString(50, y, f"£{annual_cost:,.2f} / year")

    p.save()
    buffer.seek(0)
    return buffer

# --- 4. TABS ---
tab1, tab2, tab3 = st.tabs(["📐 Design Pathway", "🚑 Run Simulation", "📊 Capacity Report"])

# === TAB 1: DESIGN ===
with tab1:
    col_graph, col_letter = st.columns([3, 2])
    with col_graph:
        st.subheader(f"Flowchart: {test_modality}")
        
        # Graphviz
        dot = graphviz.Digraph(comment='Pathway')
        dot.attr(rankdir='TB')
        dot.attr('node', shape='box', style='filled', fillcolor=NHS_BLUE, fontcolor='white', fontname='Arial')
        
        dot.node('Start', 'Patient Arrives')
        dot.node('Triage', f'Test: {test_modality}')
        dot.node('Out', f'Low Risk (<{rule_out_limit})')
        dot.node('Obs', 'Observe / Retest')
        dot.node('In', f'High Risk (>{rule_in_limit})')
        dot.node('Dest', f'DISCHARGE to {discharge_dest}', fillcolor='#4CAF50')
        dot.node('Cath', 'Cath Lab', fillcolor='#F44336')
        
        dot.edge('Start', 'Triage')
        dot.edge('Triage', 'Out')
        dot.edge('Triage', 'Obs')
        dot.edge('Triage', 'In')
        dot.edge('Out', 'Dest')
        dot.edge('In', 'Cath')
        
        st.graphviz_chart(dot)

    with col_letter:
        st.subheader("📨 GP Letter")
        st.info("Auto-generated text based on settings.")
        st.text_area("Draft:", f"Dear GP,\nPatient discharged to {discharge_dest}.\nTrop < {rule_out_limit}ng/L.\nRegards, ED", height=150)

# === TAB 2: SIMULATION ===
with tab2:
    st.markdown(f"### 🏥 Simulate 24 Hours ({daily_cp_volume} Chest Pain Patients)")
    
    if st.button("🔴 Run 24-Hour Simulation", type="primary"):
        results_log = []
        beds_blocked_count = 0
        total_wait_minutes = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Simulation Loop
        for i in range(1, daily_cp_volume + 1):
            
            # 15% True ACS Prevalence
            is_mi = random.random() < 0.15
            
            # Assign Troponin
            if is_mi:
                trop = random.randint(50, 5000)
                condition = "ACS (True)"
            else:
                trop = random.randint(0, 15)
                condition = "Non-Cardiac"

            # Check Availability
            result_ready = random.random() < availability_chance
            
            # Logic
            if result_ready:
                wait_time = 20
                if trop < rule_out_limit:
                    outcome = "Rule Out"
                    action = f"Discharge {discharge_dest}"
                    beds = 0
                elif trop > rule_in_limit:
                    outcome = "Rule In"
                    action = "Cath Lab"
                    beds = 0
                else:
                    outcome = "Grey Zone"
                    action = "Admit AMU"
                    beds = 1 # Clinical Block
            else:
                wait_time = turnaround_time + 60
                outcome = "Pending"
                action = "Bed Blocked (Waiting)"
                beds = 1 # Process Block
                
            beds_blocked_count += beds
            total_wait_minutes += wait_time
            
            results_log.append({
                "Patient ID": i,
                "Condition": condition,
                "Trop": trop,
                "Action": action,
                "Wait": wait_time
            })
            
            progress_bar.progress(int((i / daily_cp_volume) * 100))
            time.sleep(0.01)
            
        # SAVE RESULTS TO SESSION STATE
        st.session_state['simulation_results'] = pd.DataFrame(results_log)
        
        # Calculate Costs
        staff_cost_per_min = (consultant_cost + nurse_cost) / 60
        waiting_cost = total_wait_minutes * staff_cost_per_min
        testing_cost = daily_cp_volume * test_cost
        
        st.session_state['financials'] = {
            "waiting_cost": waiting_cost,
            "test_cost": testing_cost,
            "total": waiting_cost + testing_cost,
            "beds_blocked": beds_blocked_count
        }
        
        # Mark these results as valid for current settings
        st.session_state['last_run_settings'] = current_settings_sig
        
        status_text.success("Simulation Complete!")

    # Show Data Table if results exist
    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        st.dataframe(df.head(10))
        st.caption("Showing first 10 patients of the shift.")

# === TAB 3: REPORTING ===
with tab3:
    st.header("📋 Strategic Capacity Report")
    
    # 1. Stale Data Check
    if st.session_state['simulation_results'] is None:
        st.warning("⚠️ No data. Please go to Tab 2 and run the simulation.")
    elif st.session_state['last_run_settings'] != current_settings_sig:
        st.error("⚠️ **SETTINGS CHANGED:** The sidebar settings do not match the last simulation. Please Re-Run the Simulation in Tab 2 to update this report.")
    else:
        # 2. Display Report
        fin = st.session_state['financials']
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Daily Impact")
            st.metric("Total Daily Cost", f"£{fin['total']:,.2f}")
            st.metric("Beds Blocked", f"{fin['beds_blocked']} / {daily_cp_volume}")
            
            # Dynamic Warning Logic
            block_rate = fin['beds_blocked'] / daily_cp_volume
            if block_rate > 0.20: # If >20% of patients are blocked
                st.error(f"🚨 **CRITICAL OVERCROWDING:** {block_rate*100:.1f}% of chest pain patients are blocking beds due to delays/observation. Switch to POC or raise Rule-out thresholds.")
            else:
                st.success(f"✅ **GOOD FLOW:** Only {block_rate*100:.1f}% of patients experienced delays.")

        with col2:
            st.subheader("Actions")
            
            # Filename Input
            user_filename = st.text_input("Report Filename:", placeholder="e.g. Q1_Capacity_Plan")
            
            if not user_filename:
                # Default timestamp name if empty
                file_name_final = f"Protocol_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            else:
                # Ensure .pdf extension
                file_name_final = user_filename if user_filename.endswith('.pdf') else f"{user_filename}.pdf"

            if HAS_REPORTLAB:
                pdf_bytes = generate_pdf_report(
                    file_name_final, test_modality, discharge_dest, fin, daily_census, daily_cp_volume
                )
                
                st.download_button(
                    label="📄 Download Official PDF Report",
                    data=pdf_bytes,
                    file_name=file_name_final,
                    mime="application/pdf"
                )
            else:
                st.error("❌ 'reportlab' library missing. PDF generation disabled.")
