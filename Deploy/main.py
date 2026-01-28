import streamlit as st
import simulation
import visuals
import reports
import time

# --- SETUP ---
st.set_page_config(page_title="NHS Clinical Director Sim", layout="wide", page_icon="🫀")
visuals.load_css()

# Initialize State
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None
if 'financials' not in st.session_state:
    st.session_state['financials'] = {}
if 'last_run_settings' not in st.session_state:
    st.session_state['last_run_settings'] = ""

# --- SIDEBAR ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/f/fa/NHS-Logo.svg", width=80)
st.sidebar.title("Operations Control")

st.sidebar.subheader("1. Volume")
daily_census = st.sidebar.number_input("Daily ED Census", value=250, step=10)
chest_pain_pct = st.sidebar.slider("% Chest Pain", 0, 25, 10)
acs_prevalence = st.sidebar.slider("% True ACS", 0, 30, 15)

st.sidebar.subheader("2. Strategy")
modality_name = st.sidebar.radio("Modality:", ("Central Lab", "Point of Care (POC)"))

# Pack settings for simulation
if modality_name == "Point of Care (POC)":
    strat_settings = {'cost': 30.00, 'time': 20, 'availability': 0.85}
else:
    strat_settings = {'cost': 5.00, 'time': 90, 'availability': 0.35}

st.sidebar.subheader("3. Limits & Staff")
rule_out = st.sidebar.slider("Rule Out (<)", 0, 20, 5)
rule_in = st.sidebar.slider("Rule In (>)", 20, 1000, 52)
limits = {'rule_out': rule_out, 'rule_in': rule_in}

discharge_dest = st.sidebar.selectbox("Safety Net:", ("GP Surgery", "Virtual Ward", "RACPC Clinic"))

consultant_cost = st.sidebar.slider("Consultant Cost (£/hr)", 100, 200, 135)
nurse_cost = st.sidebar.slider("Nurse Cost (£/hr)", 20, 50, 30)

# Signature to detect changes
current_sig = f"{daily_census}-{modality_name}-{rule_out}-{discharge_dest}"

# --- MAIN TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📐 Pathway", "📄 Report"])

# TAB 1: DASHBOARD
with tab1:
    col_head, col_btn = st.columns([3, 1])
    col_head.markdown("### 🫀 Real-time Capacity Simulator")
    
    if col_btn.button("▶ RUN SIMULATION"):
        with st.spinner("Processing..."):
            # CALL THE SIMULATION MODULE
            df, fins, vol = simulation.run_shift(
                daily_census, chest_pain_pct, acs_prevalence, 
                strat_settings, limits, discharge_dest
            )
            
            # Add staff costs (logic stays in main or moves to sim, usually fine here)
            staff_cost_per_min = (consultant_cost + nurse_cost) / 60
            fins['waiting_cost'] = fins['waiting_minutes'] * staff_cost_per_min
            fins['total_cost'] = fins['waiting_cost'] + (fins['test_count'] * fins['test_unit_cost'])
            
            # Save to state
            st.session_state['simulation_results'] = df
            st.session_state['financials'] = fins
            st.session_state['last_run_settings'] = current_sig
            st.success("Done!")

    # Display Visuals
    if st.session_state['simulation_results'] is not None:
        df = st.session_state['simulation_results']
        fin = st.session_state['financials']
        
        # KPI Cards
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""<div class="metric-card"><h3>£{fin['total_cost']:,.0f}</h3><p>Daily Cost</p></div>""", unsafe_allow_html=True)
        k2.markdown(f"""<div class="metric-card"><h3>{fin['beds_blocked']}</h3><p>Bed Blocks</p></div>""", unsafe_allow_html=True)
        k3.markdown(f"""<div class="metric-card"><h3>{len(df[df['Condition']=='ACS (True)'])}</h3><p>True ACS</p></div>""", unsafe_allow_html=True)
        k4.markdown(f"""<div class="metric-card"><h3>{df['Wait'].mean():.0f} min</h3><p>Avg Wait</p></div>""", unsafe_allow_html=True)
        
        st.divider()
        
        # Charts from visuals.py
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(visuals.plot_sankey(df), use_container_width=True)
        with c2:
            st.plotly_chart(visuals.plot_scatter(df), use_container_width=True)

# TAB 2: PATHWAY
with tab2:
    col_g, col_txt = st.columns([3, 2])
    with col_g:
        st.graphviz_chart(visuals.render_flowchart(modality_name, limits, discharge_dest))
    with col_txt:
        st.info("Auto-generated GP Letter:")
        st.text_area("Draft:", f"Dear GP,\nPatient discharged to {discharge_dest}.\nTrop < {rule_out}ng/L.\nRegards, ED", height=200)

# TAB 3: REPORT
with tab3:
    st.header("Director's Report")
    if st.session_state['simulation_results'] is None:
        st.warning("Run simulation first.")
    elif st.session_state['last_run_settings'] != current_sig:
        st.error("Settings changed. Please re-run simulation.")
    else:
        fin = st.session_state['financials']
        st.metric("Proj. Annual Cost", f"£{fin['total_cost']*365:,.0f}")
        
        pdf_data = reports.generate_pdf(modality_name, discharge_dest, fin, fin['test_count'], limits)
        if pdf_data:
            st.download_button("Download PDF", pdf_data, "Report.pdf", "application/pdf")
        else:
            st.error("PDF Library Missing")
