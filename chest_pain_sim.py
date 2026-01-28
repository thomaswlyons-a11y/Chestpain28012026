import streamlit as st
import graphviz
import random
import time
import pandas as pd

# --- 1. GLOBAL SETTINGS & STYLING ---
st.set_page_config(page_title="NHS Clinical Director Sim", layout="wide", page_icon="🏥")

NHS_BLUE = "#005EB8"

# Initialize Session State
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}

# --- 2. SIDEBAR: OPERATIONS & DEMOGRAPHICS ---
st.sidebar.title("⚙️ Operations Control")

st.sidebar.header("1. Department Volume")
daily_census = st.sidebar.number_input("Avg. Daily ED Attendances", value=250, step=10, help="Total patients entering ED per 24h")
chest_pain_pct = st.sidebar.slider("% Presenting with Chest Pain", 0, 25, 8, help="Typical NHS average is ~6-10%")
acs_prevalence = st.sidebar.slider("% of CP that are ACS (True MI)", 0, 30, 15, help="How many chest pain patients actually have an MI?")

# Calculate expected chest pain volume
daily_cp_volume = int(daily_census * (chest_pain_pct / 100))
st.sidebar.markdown(f"**📉 Expected Caseload:** `{daily_cp_volume}` CP patients/day")

st.sidebar.divider()

st.sidebar.header("2. Diagnostics Strategy")
test_modality = st.sidebar.radio("Select Troponin Modality:", ("Central Lab (High Sensitivity)", "Point of Care (POC)"))

if test_modality == "Point of Care (POC)":
    test_cost = 30.00
    turnaround_time = 20
    availability_chance = 0.85 
else:
    test_cost = 5.00
    turnaround_time = 90
    availability_chance = 0.35

st.sidebar.header("3. Clinical Thresholds")
rule_out_limit = st.sidebar.number_input("Rule Out Cutoff (ng/L)", value=5)
rule_in_limit = st.sidebar.number_input("Rule In Cutoff (ng/L)", value=52)
discharge_dest = st.sidebar.selectbox("Low Risk Discharge To:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))

# Staff Costs
with st.sidebar.expander("Staff Cost Settings"):
    consultant_cost = st.slider("Consultant Cost (£/hr)", 100, 200, 135)
    nurse_cost = st.slider("Nurse Cost (£/hr)", 20, 50, 30)

# --- 3. HELPER FUNCTIONS ---
def generate_simple_report(modality, dest, financials, census, cp_vol):
    """Generates a text-based protocol report"""
    content = f"""
    OFFICIAL NHS CAPACTIY PLAN - GENERATED REPORT
    =============================================
    
    OPERATIONAL PARAMETERS
    ----------------------
    Daily Census: {census} patients
    Chest Pain Load: {cp_vol} patients/day ({chest_pain_pct}%)
    Strategy: {modality}
    
    CLINICAL ALGORITHM
    ------------------
    1. RULE OUT: Troponin < {rule_out_limit} ng/L -> Discharged to {dest}
    2. OBSERVE:  Troponin {rule_out_limit}-{rule_in_limit} ng/L
    3. RULE IN:  Troponin > {rule_in_limit} ng/L
    
    FINANCIAL FORECAST (DAILY)
    --------------------------
    Diagnostic Cost: £{financials['test_cost']:.2f}
    Wasted Staff Time Cost: £{financials['waiting_cost']:.2f}
    Total Daily Cost: £{financials['total']:.2f}
    
    PROJECTED ANNUAL COST (x365)
    ----------------------------
    £{financials['total'] * 365:,.2f}
    """
    return content.encode('utf-8')

# --- 4. MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["📐 Design Pathway", "🚑 Run Simulation", "📊 Capacity Report"])

with tab1:
    col_graph, col_letter = st.columns([3, 2])
    with col_graph:
        st.subheader(f"Pathway for {daily_cp_volume} Patients/Day")
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
        st.subheader("📨 GP Letter Preview")
        st.info("System auto-generates this on discharge.")
        st.text_area("Draft:", f"Dear GP,\nPatient discharged to {discharge_dest}.\nTrop < {rule_out_limit}ng/L.\nRegards, ED", height=150)

with tab2:
    st.markdown(f"### 🏥 Simulate 24 Hours ({daily_cp_volume} Chest Pain Patients)")
    st.write("This simulation generates a full day's worth of patients based on your prevalence settings.")
    
    if st.button("🔴 Run 24-Hour Simulation", type="primary"):
        results_log = []
        beds_blocked_count = 0
        total_wait_minutes = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Loop through the calculated daily volume
        for i in range(1, daily_cp_volume + 1):
            
            # 1. Determine Condition (True ACS vs Non-Cardiac)
            is_mi = random.random() < (acs_prevalence / 100)
            
            # 2. Assign Troponin
            if is_mi:
                trop = random.randint(50, 5000)
                condition_label = "ACS (True)"
            else:
                trop = random.randint(0, 15) # Some non-cardiacs have slightly raised trop
                condition_label = "Non-Cardiac"

            # 3. Availability Check
            result_ready = random.random() < availability_chance
            
            # 4. Pathway Logic
            if result_ready:
                wait_time = 20
                if trop < rule_out_limit:
                    outcome = "✅ Rule Out"
                    action = f"Discharge to {discharge_dest}"
                    beds = 0
                elif trop > rule_in_limit:
                    outcome = "🚨 Rule In"
                    action = "Cath Lab Transfer"
                    beds = 0
                else:
                    outcome = "⚠️ Grey Zone"
                    action = "Admit AMU"
                    beds = 1
            else:
                wait_time = turnaround_time + 60
                outcome = "⏳ Delayed"
                action = "Bed Blocked (Waiting)"
                beds = 1
                
            beds_blocked_count += beds
            total_wait_minutes += wait_time
            
            results_log.append({
                "Patient ID": i,
                "Condition": condition_label,
                "Trop": trop,
                "Action": action,
                "Wait (min)": wait_time
            })
            
            # Update Progress Bar
            progress_bar.progress(int((i / daily_cp_volume) * 100))
            status_text.text(f"Processing Patient {i}/{daily_cp_volume}")
            time.sleep(0.02) # Faster processing for larger volumes
            
        # Store Data
        st.session_state['simulation_results'] = pd.DataFrame(results_log)
        
        # Financial Math
        staff_cost_per_min = (consultant_cost + nurse_cost) / 60
        waiting_cost = total_wait_minutes * staff_cost_per_min
        testing_cost = daily_cp_volume * test_cost
        
        st.session_state['financials'] = {
            "waiting_cost": waiting_cost,
            "test_cost": testing_cost,
            "total": waiting_cost + testing_cost,
            "beds_blocked": beds_blocked_count
        }
        status_text.text("24-Hour Shift Complete.")

    # Show Data if Run
    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        fin = st.session_state['financials']
        
        # Dashboard
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Total CP Patients", daily_cp_volume)
        kpi2.metric("True ACS Cases", len(df[df['Condition'] == "ACS (True)"]))
        kpi3.metric("Beds Blocked", fin['beds_blocked'], delta_color="inverse")
        kpi4.metric("Total Daily Cost", f"£{fin['total']:,.0f}")
        
        with st.expander("View Patient Log"):
            st.dataframe(df)

with tab3:
    st.header("📋 Strategic Capacity Report")
    
    if st.session_state['simulation_results'] is not None:
        fin = st.session_state['financials']
        
        # 1. Visualization
        st.subheader("Cost Breakdown (Daily)")
        cost_df = pd.DataFrame({
            "Cost Type": ["Diagnostic Tests (Kit)", "Clinical Time (Wasted Waiting)"],
            "Amount (£)": [fin['test_cost'], fin['waiting_cost']]
        })
        st.bar_chart(cost_df.set_index("Cost Type"))
        
        # 2. Annual Projection
        st.divider()
        st.subheader("📅 Annual Forecast (x365 days)")
        
        col1, col2 = st.columns(2)
        annual_cost = fin['total'] * 365
        annual_blocks = fin['beds_blocked'] * 365
        
        with col1:
            st.metric("Proj. Annual Budget Impact", f"£{annual_cost:,.0f}")
        with col2:
            st.metric("Proj. Bed Days Lost", f"{annual_blocks:,.0f}", help="Total bed days consumed by delays")
            
        if annual_blocks > 1000:
            st.error("🚨 **CRITICAL WARNING:** Your current pathway is causing significant bed blocking. Consider switching to POC to improve flow.")
        
        # 3. Download
        txt_data = generate_simple_report(test_modality, discharge_dest, fin, daily_census, daily_cp_volume)
        st.download_button("📄 Download Capacity Plan (TXT)", data=txt_data, file_name="capacity_plan.txt", mime="text/plain")
        
    else:
        st.info("Run the simulation in Tab 2 to generate the report.")