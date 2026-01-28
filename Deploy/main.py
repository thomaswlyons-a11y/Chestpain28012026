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
    
    for i in range(1, daily_
