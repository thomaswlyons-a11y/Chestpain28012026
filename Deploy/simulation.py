import random
import pandas as pd
import numpy as np

def generate_patient_profile(i, acs_prevalence):
    """
    Generates a realistic patient with:
    - Condition (NSTEMI, UA, Chronic Injury, Non-Cardiac)
    - HEART Score (0-10)
    - Troponin Profile (T0, T1, T3)
    """
    rand = random.random() * 100
    
    # 1. Determine Condition based on Real-World Prevalence
    # Approx: 10% NSTEMI, 5% UA, 10% Chronic Injury, 75% Non-Cardiac
    if rand < acs_prevalence: 
        condition = "NSTEMI"
        # NSTEMI: High score, High Trop OR Rising Trop
        heart_score = random.randint(5, 10)
        base_trop = random.randint(20, 800)
        delta = random.randint(10, 100) # Significant rise
    
    elif rand < (acs_prevalence + 5):
        condition = "Unstable Angina"
        # UA: High score, but NORMAL Trop (Ischaemia without necrosis)
        heart_score = random.randint(4, 9)
        base_trop = random.randint(0, 10) 
        delta = random.randint(0, 2)
        
    elif rand < (acs_prevalence + 15):
        condition = "Chronic Injury"
        # Chronic (e.g. CKD): Moderate score, ELEVATED but STABLE Trop
        heart_score = random.randint(3, 8)
        base_trop = random.randint(20, 60) # Grey zone elevation
        delta = random.randint(0, 3) # Minimal change
        
    else:
        condition = "Non-Cardiac"
        # Normal: Low score, Low Trop
        heart_score = random.choices([0,1,2,3,4,5], weights=[30,30,20,10,5,5])[0]
        base_trop = random.randint(0, 6)
        delta = random.randint(0, 1)

    return {
        "Patient ID": i,
        "Condition": condition,
        "HEART Score": heart_score,
        "T0": base_trop,
        "T1": base_trop + delta,
        "T3": base_trop + (delta * 2) # Rough extrapolation for 3h
    }

def apply_esc_guidelines(p, limits, result_ready):
    """
    Simulates ESC 0h/1h Algorithm logic
    """
    if not result_ready:
        return "Pending", "Bed Blocked (Wait)", 90 + 60

    # ESC Logic
    # Rule Out: T0 very low OR (T0 low AND No Delta)
    if p['T0'] < limits['rule_out'] or (p['T0'] < 12 and (p['T1'] - p['T0']) < 3):
        return "Rule Out", "Discharge", 20
        
    # Rule In: T0 very high OR High Delta
    elif p['T0'] > limits['rule_in'] or (p['T1'] - p['T0']) > 5:
        return "Rule In", "Cath Lab/Cardiology", 60
        
    # Grey Zone: Everything else -> Observe
    else:
        return "Observe", "Admit AMU (Serial Trop)", 180 # 3 hr wait

def apply_macros2_rule(p, limits, result_ready):
    """
    Simulates MACROS2 (Manchester) Rule
    Rule Out = HEART <= 3 AND T0 < Limit (usually 5ng/L)
    """
    if not result_ready:
        return "Pending", "Bed Blocked (Wait)", 90 + 60

    # MACROS2 Logic
    if p['HEART Score'] <= 3 and p['T0'] < limits['rule_out']:
        return "Rule Out (MACROS2)", "Early Discharge", 15 # Very fast
        
    elif p['T0'] > limits['rule_in']:
        return "Rule In", "Cath Lab/Cardiology", 60
        
    else:
        # MACROS2 fails to rule out -> defaults to standard observation
        return "Observe", "Admit AMU (Too High Risk)", 180

def run_shift(volume, chest_pain_pct, acs_prevalence, strategy_settings, limits, discharge_dest):
    """
    Main simulation loop
    """
    results_log = []
    beds_blocked_count = 0
    total_wait_minutes = 0
    
    daily_cp_volume = int(volume * (chest_pain_pct / 100))
    
    # Decide which clinical protocol to use (can be passed in arguments in future)
    # For now, we assume ESC is standard, but we could add a toggle in Main.py
    # Let's assume Standard ESC for this code block, or trigger MACROS if desired.
    protocol = "ESC" 

    for i in range(1, daily_cp_volume + 1):
        # 1. Generate Complex Patient
        p = generate_patient_profile(i, acs_prevalence)
        
        # 2. Check Resource Availability
        result_ready = random.random() < strategy_settings['availability']
        
        # 3. Apply Clinical Logic
        # We will use the limits passed from the sidebar. 
        # Note: If the user sets 'Rule Out' to 5ng/L, that fits MACROS2 perfectly.
        
        outcome, action, wait = apply_esc_guidelines(p, limits, result_ready)
        
        # Special Logic: If the patient has Unstable Angina (Normal Trop but High Risk)
        # The Troponin rules alone might Discharge them! 
        # We need a safety net (Clinical Judgement) simulation
        if p['Condition'] == "Unstable Angina" and outcome == "Rule Out":
            # 50% chance the doctor spots the high HEART score and admits anyway
            if p['HEART Score'] >= 4 and random.random() < 0.5:
                outcome = "Clinical Rescue"
                action = "Admit (High Risk Story)"
                wait = 120
            else:
                outcome = "Missed UA" # Dangerous discharge!
                action = f"Discharge ({discharge_dest})"

        if action.startswith("Bed") or action.startswith("Admit"):
            beds_blocked_count += 1
            
        total_wait_minutes += wait
        
        # Flatten dict for DataFrame
        p_data = p.copy()
        p_data.update({"Outcome": outcome, "Action": action, "Wait": wait})
        results_log.append(p_data)
        
    df = pd.DataFrame(results_log)
    
    financials = {
        "waiting_minutes": total_wait_minutes,
        "test_count": daily_cp_volume,
        "test_unit_cost": strategy_settings['cost'],
        "beds_blocked": beds_blocked_count,
        "total_cost": 0 
    }
    
    return df, financials, daily_cp_volume
