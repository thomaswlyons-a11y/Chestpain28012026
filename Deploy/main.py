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

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="NHS Clinical Director Sim", layout="wide", page_icon="🫀")

NHS_BLUE = "#005EB8"

st.markdown("""
<style>
    .metric-card {
        background-color: #F0F2F6;
        border-left: 5px solid #005EB8;
        padding: 15px;
        border-radius: 5px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .metric-card h3 { color: #005EB8; margin: 0; }
    .metric-card p { color: #555; margin: 0; font-size: 0.9em; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #005EB8; color: white; height: 3em; }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}
if 'last_run_settings' not in st.session_state:
    st.session_state['last_run_settings'] = ""

# --- 2. THE SIMULATION ENGINE (MACROS2 / ESC) ---

def generate_patient_profile(i, acs_prevalence):
    """Generates complex patient profiles"""
    rand = random.random() * 100
    
    # 1. Determine Condition
    if rand < acs_prevalence: 
        condition = "NSTEMI" # True MI
        heart_score = random.randint(5, 10)
        base_trop = random.randint(20, 800)
        delta = random.randint(10, 100)
    elif rand < (acs_prevalence + 5):
        condition = "Unstable Angina" # Ischaemia, no Trop rise
        heart_score = random.randint(4, 9)
        base_trop = random.randint(0, 10) 
        delta = random.randint(0, 2)
    elif rand < (acs_prevalence + 15):
        condition = "Chronic Injury" # Stable high trop (e.g. CKD)
        heart_score = random.randint(3, 8)
        base_trop = random.randint(20, 60)
        delta = random.randint(0, 3)
    else:
        condition = "Non-Cardiac"
        heart_score = random.choices([0,1,2,3,4,5], weights=[30,30,20,10,5,5])[0]
        base_trop = random.randint(0, 6)
        delta = random.randint(0, 1)

    return {
        "Patient ID": i,
        "Condition": condition,
        "HEART Score": heart_score,
        "T0": base_trop,
        "T1": base_trop + delta
    }

def run_shift(volume, chest_pain_pct, acs_prevalence, strategy_settings, limits, discharge_dest):
    """Runs the simulation logic"""
    results_log = []
    beds_blocked_count = 0
    total_wait_minutes = 0
    daily_cp_volume = int(volume * (chest_pain_pct / 100))
    
    for i in range(1, daily_cp_volume + 1):
        p = generate_patient_profile(i, acs_prevalence)
        
        # Resource Check
        result_ready = random.random() < strategy_settings['availability']
        
        # LOGIC: ESC 0h/1h Protocol Simulation
        if not result_ready:
            outcome, action, wait = "Pending", "Bed Blocked (Wait)", 90 + 60
            beds = 1
        else:
            # Rule Out: Low T0 OR (Low T0 + No Delta)
            if p['T0'] < limits['rule_out'] or (p['T0'] < 12 and (p['T1'] - p['T0']) < 3):
                # Safety Net Check: Unstable Angina logic
                if p['Condition'] == "Unstable Angina" and p['HEART Score'] >= 4 and random.random() < 0.5:
                     outcome, action, wait, beds = "Clinical Rescue", "Admit (High Risk Story)", 120, 1
                else:
                     outcome, action, wait, beds = "Rule Out", f"Discharge ({discharge_dest})", 20, 0
            
            # Rule In: High T0 OR High Delta
            elif p['T0'] > limits['rule_in'] or (p['T1'] - p['T0']) > 5:
                outcome, action, wait, beds = "Rule In", "Cath Lab/Cardio", 60, 0
                
            # Grey Zone
            else:
                outcome, action, wait, beds = "Observe", "Admit AMU (Serial Trop)", 180, 1
        
        beds_blocked_count += beds
        total_wait_minutes += wait
        
        # Add result to log
        p.update({"Outcome": outcome, "Action": action, "Wait": wait})
        results_log.append(p)

    df = pd.DataFrame(results_log)
    financials = {
        "waiting_minutes": total_wait_minutes,
        "test_count": daily_cp_volume,
        "test_unit_cost": strategy_settings['cost'],
        "beds_blocked": beds_blocked_count,
        "total_cost": 0 # Calculated later
    }
    return df, financials, daily_cp_volume

# --- 3. VISUALS (CHARTS) ---

def plot_sankey(df):
    labels = ["Arrival"] + list(df['Condition'].unique()) + list(df['Outcome'].unique()) + list(df['Action'].unique())
    labels = list(dict.fromkeys(labels))
    label_map = {label: i for i, label in enumerate(labels)}
    
    sources, targets, values, colors = [], [], [], []
    
    # 1. Arrival -> Condition
    for cond in df['Condition'].unique():
        count = len(df[df['Condition'] == cond])
        sources.append(label_map["Arrival"])
        targets.append(label_map[cond])
        values.append(count)
        colors.append("#E0E0E0")
        
    # 2. Condition -> Outcome
    flow_1 = df.groupby(['Condition', 'Outcome']).size().reset_index(name='Count')
    for _, row in flow_1.iterrows():
        sources.append(label_map[row['Condition']])
        targets.append(label_map[row['Outcome']])
        values.append(row['Count'])
        if "Rule Out" in row['Outcome']: colors.append("#4CAF50")
        elif "Rule In" in row['Outcome']: colors.append("#F44336")
        else: colors.append("#FF9800")
        
    # 3. Outcome -> Action
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
    fig.update_layout(height=400, margin=dict(l=0,r=0,t=20,b=20))
    return fig

def plot_scatter(df):
    # Fixed T0 plotting
    fig = px.scatter(
        df, x="Patient ID", y="T0", color="Outcome",
        color_discrete_map={"Rule Out": "green", "Rule In": "red", "Grey Zone": "orange", "Pending": "grey"},
        log_y=True, labels={"T0": "Presentation Troponin (ng/L)"},
        hover_data=["Condition", "Action", "T1"]
    )
    fig.update_layout(height=400, margin=dict(l=0,r=0,t=20,b=20))
    return fig

def render_flowchart(modality, limits, dest):
    dot = graphviz.Digraph(comment='Pathway')
    dot.attr(rankdir='TB')
    dot.attr('node', shape='box', style='filled', fillcolor=NHS_BLUE, fontcolor='white', fontname='Arial')
    dot.node('Start', 'Patient Arrives')
    dot.node('Triage', f'Test: {modality}')
    dot.node('Out', f'Low Risk (<{limits["rule_out"]})')
    dot.node('Obs', 'Observe / Retest')
    dot.node('In', f'High Risk (>{limits["rule_in"]})')
    dot.node('Dest', f'DISCHARGE to {dest}', fillcolor='#4CAF50')
    dot.node('Cath', 'Cath Lab', fillcolor='#F44336')
    dot.edge('Start', 'Triage')
    dot.edge('Triage', 'Out')
    dot.edge('Triage', 'Obs')
    dot.edge('Triage', 'In')
    dot.edge('Out', 'Dest')
    dot.edge('In', 'Cath')
    return dot

# --- 4. REPORT GENERATOR ---

def generate_pdf(modality, dest, financials, cp_vol, limits):
    if not HAS_REPORTLAB: return None
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
    p.drawString(40, y, "EXECUTIVE SUMMARY")
    y -= 25
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Strategy: {modality}")
    y -= 15
    p.drawString(50, y, f"Volume: {cp_vol} Chest Pain Pts/Day")
    y -= 15
    p.drawString(50, y, f"Discharge To: {dest}")
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "FINANCIAL IMPACT (DAILY)")
    y -= 25
    p.drawString(50, y, f"Total Cost: £{financials['total_cost']:.2f}")
    y -= 15
    p.drawString(50, y, f"Bed Blocks: {financials['beds_blocked']} patients")
    
    p.save()
    buffer.seek(0)
    return buffer

# --- 5. MAIN APP INTERFACE ---

st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/f/fa/NHS-Logo.svg", width=80)
st.sidebar.title("Operations Control")

st.sidebar.subheader("1. Volume")
daily_census = st.sidebar.number_input("Daily ED Census", value=250, step=10)
chest_pain_pct = st.sidebar.slider("% Chest Pain", 0, 25, 10)
acs_prevalence = st.sidebar.slider("% True ACS", 0, 30, 15)

st.sidebar.subheader("2. Strategy")
modality_name = st.sidebar.radio("Modality:", ("Central Lab", "Point of Care (POC)"))
if modality_name == "Point of Care (POC)":
    strat_settings = {'cost': 30.00, 'time': 20, 'availability': 0.85}
else:
    strat_settings = {'cost': 5.00, 'time': 90, 'availability': 0.35}

st.sidebar.subheader("3. Limits & Staff")
rule_out = st.sidebar.slider("Rule Out (<)", 0, 20, 5)
rule_in = st.sidebar.slider("Rule In (>)", 20, 1000, 52)
discharge_dest = st.sidebar.selectbox("Safety Net:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))
consultant_cost = st.sidebar.slider("Consultant Cost (£/hr)", 100, 200, 135)
nurse_cost = st.sidebar.slider("Nurse Cost (£/hr)", 20, 50, 30)

current_sig = f"{daily_census}-{modality_name}-{rule_out}-{discharge_dest}"

# TABS
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📐 Pathway", "📄 Report"])

with tab1:
    col_head, col_btn = st.columns([3, 1])
    col_head.markdown("### 🫀 Real-time Capacity Simulator (MACROS2/ESC)")
    
    if col_btn.button("▶ RUN SIMULATION"):
        with st.spinner("Processing..."):
            df, fins, vol = run_shift(daily_census, chest_pain_pct, acs_prevalence, strat_settings, {'rule_out': rule_out, 'rule_in': rule_in}, discharge_dest)
            
            # Finalize Costs
            staff_cost_per_min = (consultant_cost + nurse_cost) / 60
            fins['waiting_cost'] = fins['waiting_minutes'] * staff_cost_per_min
            fins['total_cost'] = fins['waiting_cost'] + (fins['test_count'] * fins['test_unit_cost'])
            
            st.session_state['simulation_results'] = df
            st.session_state['financials'] = fins
            st.session_state['last_run_settings'] = current_sig
            st.success("Done!")

    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        fin = st.session_state['financials']
        
        # KPI Cards
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""<div class="metric-card"><h3>£{fin['total_cost']:,.0f}</h3><p>Daily Cost</p></div>""", unsafe_allow_html=True)
        
        missed_ua = len(df[(df['Condition'] == "Unstable Angina") & (df['Action'].str.contains("Discharge"))])
        k2.markdown(f"""<div class="metric-card" style="border-left: 5px solid {'red' if missed_ua > 0 else '#005EB8'};"><h3>{missed_ua}</h3><p>Missed UA (Safety)</p></div>""", unsafe_allow_html=True)
        
        k3.markdown(f"""<div class="metric-card"><h3>{len(df[df['Condition']=='NSTEMI'])}</h3><p>True NSTEMI</p></div>""", unsafe_allow_html=True)
        k4.markdown(f"""<div class="metric-card"><h3>{len(df[df['Condition']=='Chronic Injury'])}</h3><p>Chronic Injury</p></div>""", unsafe_allow_html=True)
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(plot_sankey(df), use_container_width=True)
        with c2: st.plotly_chart(plot_scatter(df), use_container_width=True)

with tab2:
    col_g, col_txt = st.columns([3, 2])
    with col_g: st.graphviz_chart(render_flowchart(modality_name, {'rule_out': rule_out, 'rule_in': rule_in}, discharge_dest))
    with col_txt:
        st.info("Auto-generated GP Letter:")
        st.text_area("Draft:", f"Dear GP,\nPatient discharged to {discharge_dest}.\nTrop < {rule_out}ng/L.\nRegards, ED", height=200)

with tab3:
    st.header("Director's Report")
    if st.session_state['simulation_results'] is None: st.warning("Run simulation first.")
    elif st.session_state['last_run_settings'] != current_sig: st.error("Settings changed. Please re-run simulation.")
    else:
        fin = st.session_state['financials']
        st.metric("Proj. Annual Cost", f"£{fin['total_cost']*365:,.0f}")
        pdf_data = generate_pdf(modality_name, discharge_dest, fin, fin['test_count'], {})
        if pdf_data: st.download_button("Download PDF", pdf_data, "Report.pdf", "application/pdf")
        else: st.error("PDF Library Missing")
