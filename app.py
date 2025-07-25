import streamlit as st
import math
import googlemaps
import re
from fpdf import FPDF

# Load Google Maps API key securely
gmaps = googlemaps.Client(key=st.secrets["googlemaps"]["api_key"])

# ─── Constants ──────────────────────────────────────────────────────────
COST_TABLE = {
    'Small': {
        'Easy': {'Excavation': 3791, 'Pool Work': 5391, 'Liner': 821},
        'Moderate': {'Excavation': 4140, 'Pool Work': 6860, 'Liner': 1535},
        'Difficult': {'Excavation': 4488, 'Pool Work': 8269, 'Liner': 1178}
    },
    'Medium': {
        'Easy': {'Excavation': 3132, 'Pool Work': 4938, 'Liner': 1608},
        'Moderate': {'Excavation': 4013, 'Pool Work': 7890, 'Liner': 1981},
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
    'Plumbing': 1800.00, 'Heater': 3067.73, 'Filter': 1192.50,
    'Pump': 1490.69, 'SaltSystem': 1348.35 + 100.00,  # + $100 for salt
    'Transformer': 140.33, 'DrainKit': 362.80, 'WinterCoverLabour': 300.00
}

# ─── Helper Functions ───────────────────────────────────────────────────
def sanitize_filename(address: str) -> str:
    clean = re.sub(r'[^\w\s]', '', address)
    return "_".join(clean.strip().split())


def get_city(address: str) -> str:
    import re
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
    return "Easy" if score == 1 else "Moderate" if score == 2 else "Difficult"


@st.cache_data(show_spinner=False)
def get_drive_km_and_time(origin, destination):
    result = gmaps.distance_matrix(origins=origin, destinations=destination, mode="driving", units="metric")
    element = result['rows'][0]['elements'][0]
    km = element['distance']['value'] / 1000
    hrs = element['duration']['value'] / 3600
    return km, hrs


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

# ─── Streamlit UI ───────────────────────────────────────────────────────
st.title("📐 Vinyl Pool Cost Estimator")

with st.form("pool_form"):
    st.markdown("### Pool Information")
    address = st.text_input("Full Pool Address (e.g. 2168 Highway 54, Caledonia, ON)", "")
    width = st.number_input("Pool Width (ft)", min_value=1.0, value=16.0)
    length = st.number_input("Pool Length (ft)", min_value=1.0, value=32.0)
    dist_to_pool = st.number_input("Distance from driveway to pool (ft)", min_value=0.0, value=65.0)
    access_in = st.number_input("Pool Access Width (inches)", min_value=0.0, value=65.0)
    steps = st.radio("Fibreglass steps?", ["Yes", "No"])
    tracking = st.radio("Tracking Type", ["Side Mount Single Track", "Bullnose Single Track"])
    lights = st.number_input("Number of Lights", min_value=0, step=1)

    submit = st.form_submit_button("📄 Generate Estimate")

if submit:
    linear_feet = 2 * (width + length)
    sqft = width * length
    category = 'Small' if linear_feet <= 76 else 'Medium' if linear_feet <= 104 else 'Large'
    difficulty = calculate_difficulty(dist_to_pool, access_in)
    permit_cost = get_permit_cost(address)

    drive_km, drive_hr = get_drive_km_and_time("5491 Appleby Line, Burlington, ON", address)
    drive_cost = drive_hr * 35 * 26 * 4

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

    total = sum([
        costs["Excavation"], costs["Pool Work"], costs["Liner"],
        base_liner + extra, hpb, steel, tracking_cost,
        concrete, soft,
        lights_total, transformer,
        FIXED_COSTS["DrainKit"], FIXED_COSTS["Plumbing"], FIXED_COSTS["Heater"],
        FIXED_COSTS["Filter"], FIXED_COSTS["Pump"], FIXED_COSTS["SaltSystem"],
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
        "Drive Distance": f"{drive_km:.2f} km",
        "Drive Time": f"{drive_hr*60:.0f} min"
    }

    breakdown = {
        "Excavation": costs["Excavation"],
        "Pool Work": costs["Pool Work"],
        "Liner Labor": costs["Liner"],
        "Liner Material + Steps": base_liner + extra,
        "HPB": hpb, "Steel": steel, "Tracking": tracking_cost,
        "Concrete": concrete, "Softbottom": soft,
        "Lights": lights_total, "Transformer": transformer,
        "Drain Kit": FIXED_COSTS["DrainKit"], "Plumbing": FIXED_COSTS["Plumbing"],
        "Heater": FIXED_COSTS["Heater"], "Filter": FIXED_COSTS["Filter"],
        "Pump": FIXED_COSTS["Pump"], "Salt System (+salt)": FIXED_COSTS["SaltSystem"],
        "Winter Cover Area": winter_area,
        "Winter Cover Labour": FIXED_COSTS["WinterCoverLabour"],
        "Permit": permit_cost, "Drive Time Labour": drive_cost,
        "Total": total
    }

    st.success("✅ Estimate Ready")
    st.write("### Summary", summary)
    st.write("### Cost Breakdown", breakdown)

    file_path = sanitize_filename(address) + "_Estimate.pdf"
    generate_pdf({'summary': summary, 'costs': breakdown}, file_path)

    with open(file_path, "rb") as f:
        st.download_button("📥 Download Estimate PDF", f, file_name=file_path, mime="application/pdf")
