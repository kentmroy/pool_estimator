import streamlit as st
import math
import googlemaps
import re
from fpdf import FPDF
import smtplib
from email.message import EmailMessage
import os

# Load Google Maps API key securely
gmaps = googlemaps.Client(key=st.secrets["googlemaps"]["api_key"])

# ─── Constants ──────────────────────────────────────────────────────────

COST_TABLE = {
    'Small': {
        'Easy': {'Excavation': 3791, 'Pool Work': 5391, 'Liner': 1178},
        'Moderate': {'Excavation': 4140, 'Pool Work': 6860, 'Liner': 1178},
        'Difficult': {'Excavation': 4488, 'Pool Work': 8269, 'Liner': 1535}
    },
    'Medium': {
        'Easy': {'Excavation': 3132, 'Pool Work': 5391, 'Liner': 1608},
        'Moderate': {'Excavation': 4140, 'Pool Work': 7890, 'Liner': 1981},
        'Difficult': {'Excavation': 4894, 'Pool Work': 10842, 'Liner': 2354}
    },
    'Large': {
        'Easy': {'Excavation': 7016, 'Pool Work': 7935, 'Liner': 1567},
        'Moderate': {'Excavation': 7016, 'Pool Work': 7935, 'Liner': 1567},
        'Difficult': {'Excavation': 7016, 'Pool Work': 7935, 'Liner': 1567}
    }
}

INSTALL_COST = {'Small': 281.69, 'Medium': 388.49, 'Large': 495.29}

PERMIT_COSTS = {
    'burlington': 1000, 'oakville': 1000,
    'mississauga': 500, 'toronto': 500, 'brampton': 500,
    'etobicoke': 500, 'hamilton': 500
}

FIXED_COSTS = {
    'Plumbing': 1800.00,
    'Filter': 1192.50,
    'SaltSystem': 1348.35 + 100.00,  # + $100 for salt
    'Transformer': 140.33,
    'DrainKit': 362.80,
    'WinterCoverLabour': 300.00
}

PUMP_OPTIONS = {
    "Jandy VSFHP165AUT, VS FloPro Variable Speed Pump W/O JEP-R": 1217.14,
    "Jandy VS FloPro 1.65 HP Variable-Speed Pump, 115/230 VAC, w/SpeedSet Control": 1490.69,
    "Jandy VS FloPro 1.85 HP Variable-Speed Pump 115/230 VAC, 2 AUX Relays": 1380.21,
    "Jandy VS FloPro 2.7 HP Variable-Speed Pump, 115/230 Vac, 2 Aux Relays, w/o": 1870.46,
}

HEATER_OPTIONS = {
    "Jandy JXIQ Pool Heater, 200, Natural Gas, Copper Hx, Versaflo, Poly Header": 3067.73,
    "Jandy JXI Pool Heater 200 Propane/ Natural": 2718.61,
    "Jandy JXIQ Pool Heater, 260, Natural Gas, Copper Hx, Versaflo, Poly Header": 3294.29,
    "Jandy JXI Pool Heater 260 Propane/ Natural": 2936.09,
    "Jandy JXIQ Pool Heater, 400, Natural Gas, Copper Hx, Versaflo, Poly Header": 3549.77,
    "Jandy JXI Pool Heater 400 Natural/ Propane": 3212.75,
}

# ─── Helper Functions ───────────────────────────────────────────────────

def sanitize_filename(address: str) -> str:
    clean = re.sub(r'[^\w\s]', '', address)
    return "_".join(clean.strip().split())

def get_city(address: str) -> str:
    match = re.search(r'([\w\s\-]+?),\s*(ON|Ontario)', address, re.IGNORECASE)
    return match.group(1).strip().lower() if match else ''

def get_permit_cost(address: str) -> float:
    city = get_city(address)
    for key in PERMIT_COSTS:
        if key in city:
            return PERMIT_COSTS[key]
    return 0

def calculate_difficulty(distance_ft, access_in):
    dist_factor = 1 if distance_ft <= 70 else 2 if distance_ft <= 120 else 3
    acc_factor = 2 if access_in < 70 else 1
    score = dist_factor * acc_factor
    if score == 1:
        return "Easy"
    elif score == 2:
        return "Moderate"
    else:
        return "Difficult"

@st.cache_data(show_spinner=False)
def get_drive_km_and_time(origin, destination):
    try:
        if not destination.strip():
            # Empty destination
            return 0, 0
        result = gmaps.distance_matrix(origins=origin, destinations=destination, mode="driving", units="metric")
        element = result['rows'][0]['elements'][0]
        if element['status'] != 'OK':
            st.warning(f"Google Distance Matrix API returned status: {element['status']}")
            return 0, 0
        km = element['distance']['value'] / 1000
        hrs = element['duration']['value'] / 3600
        return km, hrs
    except Exception as e:
        st.warning(f"Error calling Google Maps API: {e}")
        return 0, 0

def generate_pdf(data: dict, filename: str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Vinyl Pool Estimate", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    for k, v in data['summary'].items():
        pdf.cell(70, 8, f"{k}:", 0)
        pdf.cell(0, 8, str(v), ln=True)
        pdf.ln(6)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Cost Breakdown", ln=True)
    pdf.set_font("Arial", '', 12)
    for k, v in data['costs'].items():
        pdf.cell(90, 8, f"{k}:", 0)
        pdf.cell(0, 8, f"${v:,.2f}", ln=True, align="R")
        pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    total = data['costs'].get("Total", 0)
    pdf.cell(0, 10, f"Total Estimated Build Cost: ${total:,.2f}", ln=True)
    pdf.output(filename)

def send_email_with_attachment(sender_email, sender_password, recipient_email, subject, body, attachment_path):
    msg = EmailMessage()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.set_content(body)

    with open(attachment_path, 'rb') as f:
        file_data = f.read()
        file_name = os.path.basename(attachment_path)
    msg.add_attachment(file_data, maintype='application', subtype='pdf', filename=file_name)

    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Failed to send email: {e}"

# ─── Streamlit UI ───────────────────────────────────────────────────────

# Display your attached logo at the top
st.image("logo.png", width=300)

# Main title in bold
st.markdown("# **📐 Vinyl Pool Cost Estimator**")

with st.form("pool_form"):
    st.markdown("## **Pool Information**")
    address = st.text_input("Full Pool Address (e.g. 2168 Highway 54, Caledonia, ON)", "")
    width = st.number_input("Pool Width (ft)", min_value=1.0, value=16.0)
    length = st.number_input("Pool Length (ft)", min_value=1.0, value=32.0)
    dist_to_pool = st.number_input("Distance from driveway to pool (ft)", min_value=0.0, value=65.0)
    access_in = st.number_input("Pool Access Width (inches)", min_value=0.0, value=65.0)
    steps = st.radio("Fibreglass steps?", ["Yes", "No"])
    tracking = st.radio("Tracking Type", ["Side Mount Single Track", "Bullnose Single Track"])
    lights = st.number_input("Number of Lights", min_value=0, step=1)

    selected_pump = st.selectbox("Select Pump Model", options=list(PUMP_OPTIONS.keys()))
    selected_heater = st.selectbox("Select Heater Model", options=list(HEATER_OPTIONS.keys()))

    submit = st.form_submit_button("📄 Generate Estimate")

if submit:
    if not address.strip():
        st.error("Please enter a valid pool address before generating estimate.")
    else:
        linear_feet = 2 * (width + length)
        sqft = width * length
        category = 'Small' if linear_feet <= 76 else 'Medium' if linear_feet <= 104 else 'Large'
        difficulty = calculate_difficulty(dist_to_pool, access_in)
        permit_cost = get_permit_cost(address)
        drive_km, drive_hr = get_drive_km_and_time("5491 Appleby Line, Burlington, ON", address)
        drive_cost = drive_hr * 35 * 26 * 4  # labor cost estimate
        
        costs = COST_TABLE[category][difficulty]
        base_liner = INSTALL_COST[category]
        extra = (linear_feet * 22.12) if steps == "Yes" else (linear_feet * 22.12 + 300)
        rounded = math.ceil(linear_feet / 10) * 10
        track_rate = 4.27 if tracking == "Side Mount Single Track" else 8.39
        tracking_cost = rounded * track_rate
        hpb = linear_feet * 7.25
        steel = linear_feet * 50
        concrete = sqft * 5.25
        soft = sqft * 0.50
        winter_area = sqft * 3.50
        lights_total = lights * 366.65
        transformer = FIXED_COSTS["Transformer"] if lights > 0 else 0

        pump_cost = PUMP_OPTIONS[selected_pump]
        heater_cost = HEATER_OPTIONS[selected_heater]

        total = sum([
            costs["Excavation"], costs["Pool Work"], costs["Liner"],
            base_liner + extra, hpb, steel, tracking_cost,
            concrete, soft,
            lights_total, transformer,
            FIXED_COSTS["DrainKit"], FIXED_COSTS["Plumbing"],
            heater_cost,
            FIXED_COSTS["Filter"], pump_cost,
            FIXED_COSTS["SaltSystem"],
            FIXED_COSTS["WinterCoverLabour"], winter_area,
            permit_cost, drive_cost
        ])

        summary = {
            "Address": address,
            "Pool Size": f"{width} x {length} ft",
            "Linear Feet": f"{linear_feet:.0f}",
            "Square Ft": f"{sqft:.0f}",
            "Category": category,
            "Difficulty": difficulty,
            "City": get_city(address).title(),
            "Fibreglass Steps": steps,
            "Tracking Type": tracking,
            "Lights": lights,
            "Pump Model": selected_pump,
            "Heater Model": selected_heater,
            "Drive Distance": f"{drive_km:.2f} km",
            "Drive Time": f"{drive_hr*60:.0f} min"
        }

        breakdown = {
            "Excavation": costs["Excavation"],
            "Pool Work": costs["Pool Work"],
            "Liner Labor": costs["Liner"],
            "Liner Material + Steps": base_liner + extra,
            "HPB": hpb,
            "Steel": steel,
            "Tracking": tracking_cost,
            "Concrete": concrete,
            "Softbottom": soft,
            "Lights": lights_total,
            "Transformer": transformer,
            "Drain Kit": FIXED_COSTS["DrainKit"],
            "Plumbing": FIXED_COSTS["Plumbing"],
            "Heater": heater_cost,
            "Filter": FIXED_COSTS["Filter"],
            "Pump": pump_cost,
            "Salt System (+salt)": FIXED_COSTS["SaltSystem"],
            "Winter Cover Area": winter_area,
            "Winter Cover Labour": FIXED_COSTS["WinterCoverLabour"],
            "Permit": permit_cost,
            "Drive Time Labour": drive_cost,
            "Total": total
        }

        st.success("✅ Estimate Ready")
        st.markdown("## **Summary**")
        st.write(summary)
        st.markdown("## **Cost Breakdown**")
        st.write(breakdown)

        file_path = sanitize_filename(address) + "_Estimate.pdf"
        generate_pdf({'summary': summary, 'costs': breakdown}, file_path)

        with open(file_path, "rb") as f:
            st.download_button("📥 Download Estimate PDF", f, file_name=file_path, mime="application/pdf")

        st.markdown("---")
        st.markdown("## **📧 Email Estimate PDF**")
        recipient_email = st.text_input("Recipient Email Address", key="recipient_email")
        sender_email = st.text_input("Sender Email Address (e.g. your Gmail)", key="sender_email")
        sender_password = st.text_input("Sender Email Password or App Password", type="password", key="sender_password")
        send_email = st.button("Send Email")

        if send_email:
            if not recipient_email or not sender_email or not sender_password:
                st.error("Please enter recipient email, sender email and password.")
            else:
                with st.spinner("Sending email..."):
                    success, message = send_email_with_attachment(
                        sender_email=sender_email,
                        sender_password=sender_password,
                        recipient_email=recipient_email,
                        subject="Vinyl Pool Cost Estimate",
                        body=f"Please find attached the vinyl pool cost estimate for {address}.",
                        attachment_path=file_path
                    )
                if success:
                    st.success(message)
                else:
                    st.error(message)
