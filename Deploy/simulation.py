import random
import time
import pandas as pd

def run_shift(volume, chest_pain_pct, acs_prevalence, strategy_settings, limits, discharge_dest):
    """
    Runs the full day simulation logic.
    Returns: DataFrame of patients, Financial Dictionary
    """
    
    # Unpack settings
    test_cost = strategy_settings['cost']
    turnaround_time = strategy_settings['time']
    availability_chance = strategy_settings['availability']
    
    results_log = []
    beds_blocked_count = 0
    total_wait_minutes = 0
    
    # Calculate exact patient volume
    daily_cp_volume = int(volume * (chest_pain_pct / 100))
    
    for i in range(1, daily_cp_volume + 1):
        # 1. Condition Truth
        is_mi = random.random() < (acs_prevalence / 100)
        if is_mi:
            trop = random.randint(50, 5000)
            condition = "ACS (True)"
        else:
            trop = random.randint(0, 15)
            condition = "Non-Cardiac"

        # 2. Availability Check
        result_ready = random.random() < availability_chance
        
        # 3. Decision Logic
        if result_ready:
            wait_time = 20 # Fast track
            if trop < limits['rule_out']:
                outcome = "Rule Out"
                action = f"Discharge ({discharge_dest})"
                beds = 0
            elif trop > limits['rule_in']:
                outcome = "Rule In"
                action = "Cath Lab"
                beds = 0
            else:
                outcome = "Grey Zone"
                action = "Admit AMU"
                beds = 1
        else:
            wait_time = turnaround_time + 60 # Penalty for missed window
            outcome = "Pending"
            action = "Bed Blocked (Wait)"
            beds = 1
            
        beds_blocked_count += beds
        total_wait_minutes += wait_time
        
        results_log.append({
            "Patient ID": i, "Condition": condition, "Trop": trop,
            "Outcome": outcome, "Action": action, "Wait": wait_time
        })
        
    df = pd.DataFrame(results_log)
    
    # Financial Calculations
    # We return the raw data so the UI can format it
    financials = {
        "waiting_minutes": total_wait_minutes,
        "test_count": daily_cp_volume,
        "test_unit_cost": test_cost,
        "beds_blocked": beds_blocked_count,
        "total_cost": 0 # Will be calculated in main.py based on staff cost
    }
    
    return df, financials, daily_cp_volume
