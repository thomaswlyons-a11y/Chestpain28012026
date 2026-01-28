import streamlit as st
import graphviz
import random
import time
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from io import BytesIO

# Try to import reportlab for PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- 1. VISUAL CONFIGURATION & CSS ---
st.set_page_config(page_title="NHS Clinical Director Sim", layout="wide", page_icon="🫀")

# Custom CSS for "Medical Card" styling
st.markdown("""
<style>
    .metric-card {
        background-color: #F0F2F6;
        border-left: 5px solid #005EB8;
        padding: 15px;
        border-radius: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-card h3 {
        color: #005EB8;
        margin: 0;
    }
    .metric-card p {
        color: #555;
        margin: 0;
        font-size: 0.9em;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #005EB8;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

NHS_BLUE = "#005EB8"

# Initialize Session State
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}
if 'last_run_settings' not in st.session_state:
    st.session_state['last_run_settings'] = {}

# --- 2. HELPER FUNCTIONS ---

def plot_sankey(df):
    """Generates the Patient Flow Diagram"""
    # 1. Start -> Condition
    labels = ["Chest Pain Arrival"] + list(df['Condition'].unique()) + list(df['Outcome'].unique()) + list(df['Action'].unique())
    labels = list(dict.fromkeys(labels)) # Remove duplicates
    label_map = {label: i for i, label in enumerate(labels)}
    
    sources, targets, values, colors = [], [], [], []
    
    # Link 1: Arrival -> Condition
    for cond in df['Condition'].unique():
        count = len(df[df['Condition'] == cond])
        sources.append(label_map["Chest Pain Arrival"])
        targets.append(label_map[cond])
        values.append(count)
        colors.append("#E0E0E0") 
        
    # Link 2: Condition -> Outcome
    flow_1 = df.groupby(['Condition', 'Outcome']).size().reset_index(name='Count')
    for _, row in flow_1.iterrows():
        sources.append(label_map[row['Condition']])
        targets.append(label_map[row['Outcome']])
        values.append(row['Count'])
        if "Rule Out" in row['Outcome']: colors.append("#4CAF50") # Green
        elif "Rule In" in row['Outcome']: colors.append("#F44336") # Red
        else: colors.append("#FF9800") # Orange
        
    # Link 3: Outcome -> Action
    flow_2 = df.groupby(['Outcome', 'Action']).size().reset_index(name='Count')
    for _, row in flow_2.iterrows():
        sources.append(label_map[row['Outcome']])
        targets.append(label_map[row['Action']])
        values.append(row['Count'])
        colors.append("rgba(200,200,200,0.5)")

    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=labels, color=NHS_BLUE),
        link=dict(source=sources, target=targets, value=values, color=colors)
    )])
    fig.update_layout(title_text="Patient Flow: Truth → Triage → Disposition", height=400, margin=dict(l=0,r=0,t=40,b=0))
    return fig

def generate_pdf_report(filename, modality, dest, financials, census, cp_vol):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFillColorRGB(0, 0.36, 0.72) 
    p.rect(0, 750, 612, 50, fill=1, stroke=0)
    p.setFillColorRGB(1, 1, 1) 
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, 765, "NHS Trust - Strategic Capacity Protocol")
    
    p.setFillColorRGB(0,0,0)
    p.setFont("Helvetica", 10)
    p.drawString(450, 765, datetime.now().strftime("%Y-%m-%d %H:%M"))

    y = 700
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "SUMMARY")
    y -= 20
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Strategy: {modality}")
    y -= 15
    p.drawString(50, y, f"Volume: {cp_vol} Chest Pain Pts/Day")
    y -= 15
    p.drawString(50, y, f"Discharge To: {dest}")
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "FINANCIAL IMPACT (DAILY)")
    y -= 20
    p.drawString(50, y, f"Total Cost: £{financials['total']:.2f}")
    y -= 15
    p.drawString(50, y, f"Bed Blocks: {financials['beds_blocked']} patients")

    p.save()
    buffer.seek(0)
    return buffer

# --- 3. SIDEBAR CONTROLS ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/f/fa/NHS-Logo.svg", width=80)
st.sidebar.title("Operations Control")

st.sidebar.subheader("1. Volume & Load")
daily_census = st.sidebar.number_input("Daily ED Census", value=250, step=10)
chest_pain_pct = st.sidebar.slider("% Chest Pain Presentations", 0, 25, 10)
daily_cp_volume = int(daily_census * (chest_pain_pct / 100))
st.sidebar.info(f"📉 Simulating **{daily_cp_volume}** patients")

st.sidebar.subheader("2. Diagnostic Strategy")
test_modality = st.sidebar.radio("Modality:", ("Central Lab", "Point of Care (POC)"))

if test_modality == "Point of Care (POC)":
    test_cost, turnaround_time, availability_chance = 30.00, 20, 0.85
else:
    test_cost, turnaround_time, availability_chance = 5.00, 90, 0.35

st.sidebar.subheader("3. Clinical Limits")
rule_out_limit = st.sidebar.slider("Rule Out (< ng/L)", 0, 20, 5)
rule_in_limit = st.sidebar.slider("Rule In (> ng/L)", 20, 1000, 52)
discharge_dest = st.sidebar.selectbox("Safety Net:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))

consultant_cost = st.sidebar.slider("Consultant Cost (£/hr)", 100, 200, 135)
nurse_cost = st.sidebar.slider("Nurse Cost (£/hr)", 20, 50, 30)

current_settings_sig = f"{daily_census}-{test_modality}-{rule_out_limit}-{discharge_dest}"

# --- 4. TABS & MAIN CONTENT ---
tab1, tab2, tab3 = st.tabs(["📊 Visual Dashboard", "📐 Pathway Design", "📄 Official Report"])

# === TAB 1: VISUAL DASHBOARD ===
with tab1:
    col_header, col_btn = st.columns([3, 1])
    with col_header:
        st.markdown(f"### 🫀 Real-time Capacity Simulator")
        st.caption(f"Strategy: **{test_modality}** | Load: **{daily_cp_volume} Pts/Day**")
    with col_btn:
        st.write("") 
        run_sim = st.button("▶ RUN SIMULATION")

    # SIMULATION LOGIC
    if run_sim:
        with st.spinner("Processing patient flow..."):
            results_log = []
            beds_blocked_count = 0
            total_wait_minutes = 0
            progress_bar = st.progress(0)
            
            for i in range(1, daily_cp_volume + 1):
                # 1. Condition
                is_mi = random.random() < 0.15
                if is_mi:
                    trop = random.randint(50, 5000)
                    condition = "ACS (True)"
                else:
                    trop = random.randint(0, 15)
                    condition = "Non-Cardiac"

                # 2. Availability
                result_ready = random.random() < availability_chance
                
                # 3. Decision
                if result_ready:
                    wait_time = 20
                    if trop < rule_out_limit:
                        outcome = "Rule Out"
                        action = f"Discharge ({discharge_dest})"
                        beds = 0
                    elif trop > rule_in_limit:
                        outcome = "Rule In"
                        action = "Cath Lab"
                        beds = 0
                    else:
                        outcome = "Grey Zone"
                        action = "Admit AMU"
                        beds = 1
                else:
                    wait_time = turnaround_time + 60
                    outcome = "Pending"
                    action = "Bed Blocked (Wait)"
                    beds = 1
                    
                beds_blocked_count += beds
                total_wait_minutes += wait_time
                
                results_log.append({
                    "Patient ID": i, "Condition": condition, "Trop": trop,
                    "Outcome": outcome, "Action": action, "Wait": wait_time
                })
                progress_bar.progress(int((i / daily_cp_volume) * 100))
                time.sleep(0.01)

            # SAVE STATE
            st.session_state['simulation_results'] = pd.DataFrame(results_log)
            st.session_state['financials'] = {
                "waiting_cost": total_wait_minutes * ((consultant_cost + nurse_cost) / 60),
                "test_cost": daily_cp_volume * test_cost,
                "total": (total_wait_minutes * ((consultant_cost + nurse_cost) / 60)) + (daily_cp_volume * test_cost),
                "beds_blocked": beds_blocked_count
            }
            st.session_state['last_run_settings'] = current_settings_sig
            st.success("Analysis Complete")

    # SHOW DASHBOARD (If data exists)
    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        fin = st.session_state['financials']
        
        # 1. KPI CARDS
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""<div class="metric-card"><h3>£{fin['total']:,.0f}</h3><p>Daily Cost</p></div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class="metric-card"><h3>{fin['beds_blocked']}</h3><p>Bed Blocks</p></div>""", unsafe_allow_html=True)
        with k3:
            acs_count = len(df[df['Condition']=='ACS (True)'])
            st.markdown(f"""<div class="metric-card"><h3>{acs_count}</h3><p>True ACS Cases</p></div>""", unsafe_allow_html=True)
        with k4:
            st.markdown(f"""<div class="metric-card"><h3>{df['Wait'].mean():.0f} min</h3><p>Avg Wait</p></div>""", unsafe_allow_html=True)

        st.divider()

        # 2. VISUALS ROW
        v1, v2 = st.columns([1, 1])
        
        with v1:
            st.subheader("🌊 Patient Flow (Sankey)")
            st.plotly_chart(plot_sankey(df), use_container_width=True)
            
        with v2:
            st.subheader("🎯 Troponin Distribution")
            # Scatter Plot: Trop vs Patient, colored by Outcome
            fig_scatter = px.scatter(
                df, x="Patient ID", y="Trop", color="Outcome",
                color_discrete_map={"Rule Out": "green", "Rule In": "red", "Grey Zone": "orange", "Pending": "grey"},
                log_y=True, # Log scale because Troponin spikes are huge
                hover_data=["Condition", "Action"]
            )
            fig_scatter.update_layout(height=400, title="Troponin Levels (Log Scale)")
            st.plotly_chart(fig_scatter, use_container_width=True)

# === TAB 2: PATHWAY DESIGN ===
with tab1: # Actually, let's keep Dashboard separate. Moving to Tab 2 context.
    pass 

with tab2:
    col_graph, col_letter = st.columns([3, 2])
    with col_graph:
        st.subheader(f"Flowchart: {test_modality}")
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

# === TAB 3: REPORTING ===
with tab3:
    st.header("📋 Director's Report")
    
    if st.session_state['simulation_results'] is None:
        st.warning("⚠️ Run simulation first.")
    elif st.session_state['last_run_settings'] != current_settings_sig:
        st.error("⚠️ Settings changed. Please re-run simulation.")
    else:
        fin = st.session_state['financials']
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Proj. Annual Cost", f"£{fin['total']*365:,.0f}")
            if fin['beds_blocked'] / daily_cp_volume > 0.2:
                st.error("🚨 CRITICAL: High Bed Blocking detected.")
            else:
                st.success("✅ Flow is efficient.")
        
        with col2:
            user_filename = st.text_input("Report Filename:", "Capacity_Plan.pdf")
            if HAS_REPORTLAB:
                pdf_data = generate_pdf_report(user_filename, test_modality, discharge_dest, fin, daily_census, daily_cp_volume)
                st.download_button("Download PDF", pdf_data, file_name=user_filename, mime="application/pdf")
            else:
                st.error("PDF Library missing (reportlab).")
