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

# ==========================================
# 🛑 SPLASH SCREEN / DISCLAIMER SECTION 🛑
# ==========================================
if 'terms_accepted' not in st.session_state:
    st.session_state['terms_accepted'] = False

if not st.session_state['terms_accepted']:
    st.markdown("""
    <style>
        .splash-container {
            text-align: center;
            padding: 50px;
            background-color: #f8d7da;
            border: 2px solid #f5c6cb;
            border-radius: 10px;
            color: #721c24;
            margin-top: 100px;
        }
        .splash-btn {
            margin-top: 20px;
            width: 50%;
        }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="splash-container">
            <h1>⚠️ CLINICAL SAFETY WARNING</h1>
            <p><strong>THIS IS A DEMO APPLICATION ONLY.</strong></p>
            <p>Users are NOT to interpret the data produced by this simulation as clinical guidance.</p>
            <p>Do NOT take this simulation as a realistic interpretation of suspected ACS pathways within the NHS or any other healthcare system.</p>
            <p>This tool is for educational gameplay purposes only.</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("") # Spacer
        if st.button("I UNDERSTAND & ACCEPT", key="accept_btn", type="primary", use_container_width=True):
            st.session_state['terms_accepted'] = True
            st.rerun()
            
    st.stop() # <--- This prevents the rest of the app from running until accepted
# ==========================================
# END OF SPLASH SCREEN
# ==========================================

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

if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}
if 'last_run_settings' not in st.session_state:
    st.session_state['last_run_settings'] = ""

# --- 2. SIMULATION LOGIC (WATERFALL) ---

def generate_patient_profile(i, acs_prevalence):
    rand = random.random() * 100
    if rand < acs_prevalence: 
        condition = "NSTEMI"
        heart_score = random.randint(5, 10)
        base_trop = random.randint(20, 800)
        delta = random.randint(10, 100)
    elif rand < (acs_prevalence + 5):
        condition = "Unstable Angina"
        heart_score = random.randint(4, 9)
        base_trop = random.randint(0, 10) 
        delta = random.randint(0, 2)
    elif rand < (acs_prevalence + 15):
        condition = "Chronic Injury"
        heart_score = random.randint(3, 8)
        base_trop = random.randint(20, 60)
        delta = random.randint(0, 3)
    else:
        condition = "Non-Cardiac"
        heart_score = random.choices([0,1,2,3,4,5], weights=[30,30,20,10,5,5])[0]
        base_trop = random.randint(0, 6)
        delta = random.randint(0, 1)

    return {
        "Patient ID": i, "Condition": condition, "HEART Score": heart_score,
        "T0": base_trop, "T1": base_trop + delta
    }

def run_shift(volume, chest_pain_pct, acs_prevalence, platform_type, use_single_sample, limits, discharge_dest):
    """
    WATERFALL LOGIC:
    1. Everyone gets T0.
    2. Check Single Sample Exit.
    3. Remainder get T1 (0/1h).
    """
    results_log = []
    beds_blocked_count = 0
    total_wait_minutes = 0
    daily_cp_volume = int(volume * (chest_pain_pct / 100))
    
    # Platform Settings
    if platform_type == "Point of Care (POC)":
        COST_PER_TEST = 30.00
        TIME_PER_TEST = 20
        AVAILABILITY = 0.90 
    else:
        COST_PER_TEST = 5.00
        TIME_PER_TEST = 90
        AVAILABILITY = 0.40 
        
    total_kit_cost = 0
    
    for i in range(1, daily_cp_volume + 1):
        p = generate_patient_profile(i, acs_prevalence)
        
        # --- STEP 1: T0 TEST (Everyone) ---
        total_kit_cost += COST_PER_TEST
        wait = TIME_PER_TEST
        
        # Bottleneck 1: Doctor availability
        if random.random() > AVAILABILITY:
            wait += 60 
            
        outcome = ""
        action = ""
        beds = 0
        pathway_step = "T0 Check"
        
        # --- STEP 2: SINGLE SAMPLE DECISION ---
        # Logic: Low Risk (HEART<=3) AND Low Trop (T0 < Limit)
        is_safe_single = p['T0'] < limits['rule_out'] and p['HEART Score'] <= 3
        
        if use_single_sample and is_safe_single:
            # EXIT HERE
            outcome = "Rule Out (Single Sample)"
            action = f"Rapid Discharge ({discharge_dest})"
            beds = 0
        
        else:
            # --- STEP 3: SERIAL TESTING (0/1h) ---
            pathway_step = "Serial 0h/1h"
            total_kit_cost += COST_PER_TEST # Second kit used
            wait += 60 # Time for 1h sample
            wait += TIME_PER_TEST # Time for result
            
            # 0/1h Logic
            if p['T0'] < limits['rule_out'] or (p['T0'] < 12 and (p['T1'] - p['T0']) < 3):
                # Unstable Angina Safety Net
                if p['Condition'] == "Unstable Angina" and p['HEART Score'] >= 4 and random.random() < 0.5:
                     outcome = "Clinical Rescue"
                     action = "Admit (High Risk)"
                     beds = 1
                else:
                     outcome = "Rule Out (Serial)"
                     action = f"Discharge ({discharge_dest})"
            
            elif p['T0'] > limits['rule_in'] or (p['T1'] - p['T0']) > 5:
                outcome = "Rule In"
                action = "Cath Lab"
            
            else:
                outcome = "Grey Zone"
                action = "Admit AMU (Observe)"
                beds = 1
        
        if "Admit" in action or "Block" in action:
            beds = 1
            
        beds_blocked_count += beds
        total_wait_minutes += wait
        
        p.update({"Outcome": outcome, "Action": action, "Wait": wait})
        results_log.append(p)

    df = pd.DataFrame(results_log)
    financials = {
        "waiting_minutes": total_wait_minutes,
        "test_count": daily_cp_volume,
        "test_kit_cost": total_kit_cost,
        "beds_blocked": beds_blocked_count,
        "total_cost": 0 
    }
    return df, financials, daily_cp_volume

# --- 3. VISUALS ---

def plot_sankey(df):
    labels = ["Arrival"] + ["Single Sample Check"] + ["Serial Testing (0h/1h)"] + list(df['Outcome'].unique()) + list(df['Action'].unique())
    labels = list(dict.fromkeys(labels))
    label_map = {label: i for i, label in enumerate(labels)}
    
    sources, targets, values, colors = [], [], [], []
    
    # 1. Arrival -> Single Sample Check
    sources.append(label_map["Arrival"])
    targets.append(label_map["Single Sample Check"])
    values.append(len(df))
    colors.append("#E0E0E0")
    
    # 2. Split
    single_outs = df[df['Outcome'] == "Rule Out (Single Sample)"]
    if len(single_outs) > 0:
        sources.append(label_map["Single Sample Check"])
        targets.append(label_map["Rule Out (Single Sample)"])
        values.append(len(single_outs))
        colors.append("#4CAF50") 
        
    serial_pts = df[df['Outcome'] != "Rule Out (Single Sample)"]
    if len(serial_pts) > 0:
        sources.append(label_map["Single Sample Check"])
        targets.append(label_map["Serial Testing (0h/1h)"])
        values.append(len(serial_pts))
        colors.append("#FF9800") 
        
    # 3. Serial Outcomes
    if len(serial_pts) > 0:
        flow = serial_pts.groupby(['Outcome']).size().reset_index(name='Count')
        for _, row in flow.iterrows():
            sources.append(label_map["Serial Testing (0h/1h)"])
            targets.append(label_map[row['Outcome']])
            values.append(row['Count'])
            if "Rule Out" in row['Outcome']: colors.append("#4CAF50")
            elif "Rule In" in row['Outcome']: colors.append("#F44336")
            else: colors.append("#FF9800")

    # 4. Action
    flow_act = df.groupby(['Outcome', 'Action']).size().reset_index(name='Count')
    for _, row in flow_act.iterrows():
        sources.append(label_map[row['Outcome']])
        targets.append(label_map[row['Action']])
        values.append(row['Count'])
        colors.append("rgba(200,200,200,0.5)")

    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=labels, color=NHS_BLUE),
        link=dict(source=sources, target=targets, value=values, color=colors)
    )])
    fig.update_layout(height=450, margin=dict(l=0,r=0,t=40,b=20), title="Patient Waterfall Flow")
    return fig

def render_flowchart(platform, use_single, limits, dest):
    dot = graphviz.Digraph(comment='Pathway')
    dot.attr(rankdir='TB')
    dot.attr('node', shape='box', style='filled', fillcolor=NHS_BLUE, fontcolor='white', fontname='Arial')
    
    dot.node('Start', 'Patient Arrives')
    dot.node('T0', f'T0 Test ({platform})')
    dot.edge('Start', 'T0')
    
    if use_single:
        dot.node('Decision1', f'Single Sample Check\n(Trop <{limits["rule_out"]} & Low Risk?)', shape='diamond', fillcolor='orange')
        dot.edge('T0', 'Decision1')
        
        dot.node('SS_Exit', f'Rapid Discharge\n{dest}', fillcolor='#4CAF50')
        dot.edge('Decision1', 'SS_Exit', label='Yes')
        
        dot.node('T1', f'Proceed to T1\n(Serial Test)')
        dot.edge('Decision1', 'T1', label='No')
    else:
        dot.node('T1', f'Proceed to T1\n(Traditional 0h/1h)')
        dot.edge('T0', 'T1', label='Standard Protocol')

    dot.node('Delta', 'Delta Analysis', shape='diamond', fillcolor='orange')
    dot.edge('T1', 'Delta')
    
    dot.node('Out', 'Rule Out\n(Discharge)', fillcolor='#4CAF50')
    dot.node('In', 'Rule In\n(Cath Lab)', fillcolor='#F44336')
    dot.node('Obs', 'Grey Zone\n(Admit)', fillcolor='#FF9800')
    
    dot.edge('Delta', 'Out')
    dot.edge('Delta', 'In')
    dot.edge('Delta', 'Obs')
    
    return dot

def generate_pdf(filename, platform, use_single, dest, financials, cp_vol):
    if not HAS_REPORTLAB: return None
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFillColorRGB(0, 0.36, 0.72) 
    p.rect(0, 750, 612, 50, fill=1, stroke=0)
    p.setFillColorRGB(1, 1, 1) 
    p.setFont("Helvetica-Bold", 18)
    p.drawString(40, 765, "NHS Trust - Chest Pain Pathway Strategy")
    
    p.setFillColorRGB(0,0,0)
    p.setFont("Helvetica", 10)
    p.drawString(400, 765, datetime.now().strftime("%Y-%m-%d %H:%M"))
    
    y = 700
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "CONFIGURATION")
    y -= 20
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"• Platform: {platform}")
    y -= 15
    p.drawString(50, y, f"• Single Sample Rule-Out: {'ENABLED' if use_single else 'DISABLED'}")
    y -= 15
    p.drawString(50, y, f"• Discharge Safety Net: {dest}")
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "FINANCIAL PROJECTION (Daily)")
    y -= 20
    p.drawString(50, y, f"• Total Ops Cost: £{financials['total_cost']:.2f}")
    y -= 15
    p.drawString(50, y, f"• Test Kit Spend: £{financials['test_kit_cost']:.2f}")
    y -= 15
    p.drawString(50, y, f"• Bed Blocks: {financials['beds_blocked']} patients")

    p.save()
    buffer.seek(0)
    return buffer

# --- 4. MAIN APP ---

st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/f/fa/NHS-Logo.svg", width=80)
st.sidebar.title("Operations Control")

st.sidebar.subheader("1. Testing Platform")
platform_type = st.sidebar.radio("Primary Diagnostic Tool:", ("Central Lab", "Point of Care (POC)"))

st.sidebar.subheader("2. Protocol Logic")
use_single_sample = st.sidebar.checkbox("Enable Single Sample Rule Out?", value=True, help="If ON, low risk patients leave after T0. If OFF, everyone waits for T1.")

rule_out = st.sidebar.slider("Rule Out (<)", 0, 20, 5)
rule_in = st.sidebar.slider("Rule In (>)", 20, 1000, 52)
discharge_dest = st.sidebar.selectbox("Safety Net:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))

st.sidebar.divider()
st.sidebar.subheader("3. Volume & Costs")
daily_census = st.sidebar.number_input("Daily Census", 250, step=10)
chest_pain_pct = st.sidebar.slider("% Chest Pain", 0, 25, 10)
consultant_cost = st.sidebar.slider("Consultant (£/hr)", 100, 200, 135)
nurse_cost = st.sidebar.slider("Nurse (£/hr)", 20, 50, 30)

current_sig = f"{platform_type}-{use_single_sample}-{rule_out}-{daily_census}"

# TABS
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📐 Pathway", "📄 Report"])

with tab1:
    col_head, col_btn = st.columns([3, 1])
    col_head.markdown("### 🫀 Chest Pain Workflow Simulator")
    
    if col_btn.button("▶ RUN SIMULATION"):
        with st.spinner("Processing Waterfall Logic..."):
            df, fins, vol = run_shift(daily_census, chest_pain_pct, 15, platform_type, use_single_sample, {'rule_out': rule_out, 'rule_in': rule_in}, discharge_dest)
            
            # Final Costs
            staff_cost_per_min = (consultant_cost + nurse_cost) / 60
            fins['waiting_cost'] = fins['waiting_minutes'] * staff_cost_per_min
            fins['total_cost'] = fins['waiting_cost'] + fins['test_kit_cost']
            
            st.session_state['simulation_results'] = df
            st.session_state['financials'] = fins
            st.session_state['last_run_settings'] = current_sig
            st.success("Done!")

    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        fin = st.session_state['financials']
        
        # KPI Cards
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""<div class="metric-card"><h3>£{fin['total_cost']:,.0f}</h3><p>Total Cost</p></div>""", unsafe_allow_html=True)
        
        early_dc = len(df[df['Outcome'] == "Rule Out (Single Sample)"])
        total_pts = len(df)
        pct_early = (early_dc / total_pts) * 100 if total_pts > 0 else 0
        
        k2.markdown(f"""<div class="metric-card"><h3>{pct_early:.1f}%</h3><p>Single Sample Discharge</p></div>""", unsafe_allow_html=True)
        k3.markdown(f"""<div class="metric-card"><h3>{fin['beds_blocked']}</h3><p>Bed Blocks</p></div>""", unsafe_allow_html=True)
        k4.markdown(f"""<div class="metric-card"><h3>{df['Wait'].mean():.0f} min</h3><p>Avg Length of Stay</p></div>""", unsafe_allow_html=True)

        st.divider()
        st.subheader("Patient Waterfall Flow")
        st.plotly_chart(plot_sankey(df), use_container_width=True)

with tab2:
    c1, c2 = st.columns([3, 2])
    with c1: st.graphviz_chart(render_flowchart(platform_type, use_single_sample, {'rule_out': rule_out, 'rule_in': rule_in}, discharge_dest))
    with c2:
        st.info("Protocol Logic:")
        if use_single_sample:
            st.success("✅ **Single Sample Rule-Out ENABLED**\n\nPatients with T0 < Limit and Low Risk are discharged immediately. The rest proceed to T1.")
        else:
            st.warning("⚠️ **Traditional Pathway ONLY**\n\nSingle sample rule-out is DISABLED. Every patient must wait for the second test (0/1h).")

with tab3:
    st.header("Director's Report")
    if st.session_state['simulation_results'] is None: st.warning("Run sim first.")
    elif st.session_state['last_run_settings'] != current_sig: st.error("Settings changed.")
    else:
        fin = st.session_state['financials']
        user_filename = st.text_input("Report Filename:", "Strategy_Report.pdf")
        
        pdf_data = generate_pdf(user_filename, platform_type, use_single_sample, discharge_dest, fin, fin['test_count'])
        if pdf_data: 
            st.download_button("Download PDF", pdf_data, user_filename, "application/pdf")
        else:
            st.error("PDF Library Missing (reportlab).")
