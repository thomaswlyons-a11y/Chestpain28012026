import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import graphviz

NHS_BLUE = "#005EB8"

def load_css():
    st.markdown("""
    <style>
        .metric-card {
            background-color: #F0F2F6;
            border-left: 5px solid #005EB8;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        }
        .metric-card h3 { color: #005EB8; margin: 0; }
        .metric-card p { color: #555; margin: 0; font-size: 0.9em; }
        .stButton>button { width: 100%; border-radius: 5px; background-color: #005EB8; color: white; }
    </style>
    """, unsafe_allow_html=True)

def plot_sankey(df):
    labels = ["Arrival"] + list(df['Condition'].unique()) + list(df['Outcome'].unique()) + list(df['Action'].unique())
    labels = list(dict.fromkeys(labels))
    label_map = {label: i for i, label in enumerate(labels)}
    
    sources, targets, values, colors = [], [], [], []
    
    # Link 1: Arrival -> Condition
    for cond in df['Condition'].unique():
        count = len(df[df['Condition'] == cond])
        sources.append(label_map["Arrival"])
        targets.append(label_map[cond])
        values.append(count)
        colors.append("#E0E0E0") 
        
    # Link 2: Condition -> Outcome
    flow_1 = df.groupby(['Condition', 'Outcome']).size().reset_index(name='Count')
    for _, row in flow_1.iterrows():
        sources.append(label_map[row['Condition']])
        targets.append(label_map[row['Outcome']])
        values.append(row['Count'])
        if "Rule Out" in row['Outcome']: colors.append("#4CAF50")
        elif "Rule In" in row['Outcome']: colors.append("#F44336")
        else: colors.append("#FF9800")
        
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
    fig.update_layout(height=400, margin=dict(l=0,r=0,t=20,b=20))
    return fig

def plot_scatter(df):
    fig = px.scatter(
        df, x="Patient ID", y="Trop", color="Outcome",
        color_discrete_map={"Rule Out": "green", "Rule In": "red", "Grey Zone": "orange", "Pending": "grey"},
        log_y=True, hover_data=["Condition", "Action"]
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
