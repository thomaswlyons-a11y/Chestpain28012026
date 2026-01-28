from io import BytesIO
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

def generate_pdf(modality, dest, financials, cp_vol, limits):
    if not HAS_REPORTLAB:
        return None

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Header
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
    
    y -= 40
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, "CLINICAL THRESHOLDS")
    y -= 25
    p.drawString(50, y, f"Rule Out: < {limits['rule_out']} ng/L")
    p.drawString(250, y, f"Rule In: > {limits['rule_in']} ng/L")

    p.save()
    buffer.seek(0)
    return buffer
