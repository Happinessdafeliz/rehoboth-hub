import streamlit as st
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

st.set_page_config(page_title="DECIDR by Felix GRC", page_icon="✅", layout="centered")

st.markdown("# DECIDR by Felix GRC")
st.caption("Customer-facing net-zero investment decisioning • Pilot: Solar + Battery optimisation (GBP).")

with st.expander("What this does", expanded=False):
    st.write(
        "Enter a few details and DECIDR will produce an investment recommendation with key metrics "
        "(CAPEX, annual savings, payback, CO₂ impact proxy) and a downloadable PDF report."
    )

st.markdown("## Inputs")
with st.form("inputs"):
    org_name = st.text_input("Organisation / Client name", value="")
    location = st.selectbox("Location (UK)", ["England", "Scotland", "Wales", "Northern Ireland"], index=0)
    annual_elec_kwh = st.number_input("Annual electricity consumption (kWh)", min_value=0.0, value=3500000.0, step=1000.0, format="%.0f")
    annual_bill_gbp = st.number_input("Annual electricity bill (£)", min_value=0.0, value=2000000.0, step=1000.0, format="%.0f")
    carbon_target_year = st.number_input("Target year for major reductions", min_value=2025, value=2030, step=1)
    budget_gbp = st.number_input("Available CAPEX budget (£)", min_value=0.0, value=4500000.0, step=1000.0, format="%.0f")
    roof_or_land = st.selectbox("Solar feasibility", ["High (good roof/land)", "Medium", "Low / constrained"], index=0)
    include_battery = st.checkbox("Include battery storage in options", value=True)
    submitted = st.form_submit_button("Calculate DECIDR Recommendation")

def fmt_gbp(x: float) -> str:
    return f"£{x:,.0f}"

def compute_options(annual_bill: float, annual_kwh: float, budget: float, feasibility: str, include_batt: bool):
    """
    Simple, transparent pilot logic.
    Replace later with the full optimisation engine (tariffs, profiles, constraints).
    """
    # Heuristics based on feasibility
    feas_mult = {"High (good roof/land)": 1.0, "Medium": 0.75, "Low / constrained": 0.45}[feasibility]

    # Solar+Battery assumed savings fraction of bill (pilot defaults)
    # High feasibility can save ~70% of bill; medium ~55%; low ~35%.
    save_frac = 0.70 * feas_mult
    if not include_batt:
        save_frac = 0.55 * feas_mult

    # CAPEX scaling: rough proxy: £1.15 per annual kWh offset (for large estates) * feasibility adjustment.
    # Clamp within a sensible pilot range.
    capex_solar_batt = max(500000.0, min(8000000.0, (annual_kwh * 1.15) * feas_mult / 1000.0))
    # If user budget is lower, assume phased deployment
    phased = False
    if budget > 0 and capex_solar_batt > budget:
        phased = True
        capex_solar_batt = budget

    annual_savings = annual_bill * save_frac
    payback = (capex_solar_batt / annual_savings) if annual_savings > 0 else float("inf")

    # CO2 proxy: 0.20 kg CO2e per kWh (grid average varies; this is a placeholder)
    co2_factor = 0.20
    co2_saved_t = (annual_kwh * save_frac * co2_factor) / 1000.0  # tonnes

    # Option 2: Renewable PPA (low CAPEX, moderate savings)
    capex_ppa = 25000.0
    savings_ppa = annual_bill * (0.18 * feas_mult)
    payback_ppa = (capex_ppa / savings_ppa) if savings_ppa > 0 else float("inf")
    co2_saved_ppa_t = (annual_kwh * 0.30 * co2_factor) / 1000.0  # contractual green fraction proxy

    # Option 3: Offsets (no savings, but carbon compliance)
    capex_offsets = annual_kwh * co2_factor/1000.0 * 30.0  # £30/tonne proxy
    savings_offsets = 0.0
    payback_offsets = float("inf")
    co2_saved_offsets_t = (annual_kwh * co2_factor)/1000.0  # claimable offset tonnes

    options = [
        {
            "name": "Install Solar + Battery" if include_batt else "Install Solar (no battery)",
            "capex": capex_solar_batt,
            "annual_savings": annual_savings,
            "payback_years": payback,
            "co2_saved_t": co2_saved_t,
            "notes": "Phased to match budget." if phased else "On-site generation reduces bills and exposure to volatility."
        },
        {
            "name": "Renewable PPA (Power Purchase Agreement)",
            "capex": capex_ppa,
            "annual_savings": savings_ppa,
            "payback_years": payback_ppa,
            "co2_saved_t": co2_saved_ppa_t,
            "notes": "Low CAPEX; contractual green supply; depends on counterparty and terms."
        },
        {
            "name": "Buy Verified Offsets",
            "capex": capex_offsets,
            "annual_savings": savings_offsets,
            "payback_years": payback_offsets,
            "co2_saved_t": co2_saved_offsets_t,
            "notes": "Improves reporting but does not reduce energy costs; quality varies."
        },
    ]

    # Score: maximise savings, minimise payback, maximise CO2 saved, penalise CAPEX over budget already handled
    for o in options:
        pb = o["payback_years"]
        pb_score = 0 if math.isinf(pb) else max(0.0, 10.0 - pb)  # <=10 years better
        o["score"] = (o["annual_savings"]/max(annual_bill,1.0))*10.0 + pb_score + (o["co2_saved_t"]/max((annual_kwh*co2_factor/1000.0),1e-6))*5.0

    options_sorted = sorted(options, key=lambda x: x["score"], reverse=True)
    return options_sorted

def build_pdf(org, location, inputs, options_sorted, chosen):
    styles = getSampleStyleSheet()
    buff = BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []

    story.append(Paragraph("DECIDR Decision Report", styles["Title"]))
    story.append(Paragraph("DECIDR by Felix GRC", styles["Heading2"]))
    story.append(Spacer(1, 10))
    meta = f"Client: {org or '—'} | Location: {location} | Generated: {inputs['generated_at']}"
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Inputs", styles["Heading3"]))
    data = [
        ["Annual electricity (kWh)", f"{inputs['annual_elec_kwh']:,.0f}"],
        ["Annual bill (£)", fmt_gbp(inputs["annual_bill_gbp"])],
        ["Target year", str(inputs["carbon_target_year"])],
        ["Budget (£)", fmt_gbp(inputs["budget_gbp"])],
        ["Solar feasibility", inputs["feasibility"]],
    ]
    t = Table(data, colWidths=[220, 260])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Recommendation", styles["Heading3"]))
    rec = (
        f"<b>Best option:</b> {chosen['name']}<br/>"
        f"<b>CAPEX:</b> {fmt_gbp(chosen['capex'])}<br/>"
        f"<b>Annual savings:</b> {fmt_gbp(chosen['annual_savings'])}<br/>"
        f"<b>Payback:</b> {'—' if math.isinf(chosen['payback_years']) else f'{chosen['payback_years']:.2f} years'}<br/>"
        f"<b>CO₂ reduction (proxy):</b> {chosen['co2_saved_t']:.0f} tCO₂e/yr<br/>"
        f"<b>Notes:</b> {chosen['notes']}"
    )
    story.append(Paragraph(rec, styles["BodyText"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Top options (ranked)", styles["Heading3"]))
    table_data = [["Rank", "Option", "CAPEX", "Annual savings", "Payback (yrs)", "CO₂ saved (t/yr)"]]
    for i, o in enumerate(options_sorted[:3], start=1):
        table_data.append([
            str(i),
            o["name"],
            fmt_gbp(o["capex"]),
            fmt_gbp(o["annual_savings"]),
            "∞" if math.isinf(o["payback_years"]) else f"{o['payback_years']:.2f}",
            f"{o['co2_saved_t']:.0f}",
        ])
    tt = Table(table_data, colWidths=[40, 180, 85, 95, 75, 80])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("PADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(tt)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Disclaimer", styles["Heading3"]))
    story.append(Paragraph(
        "This pilot report uses simplified assumptions suitable for early-stage decisioning. "
        "For procurement, financing, and compliance submissions, DECIDR should be calibrated with site surveys, tariffs, "
        "half-hourly consumption profiles, and verified emissions factors.",
        styles["BodyText"]
    ))

    doc.build(story)
    buff.seek(0)
    return buff

if submitted:
    options_sorted = compute_options(annual_bill_gbp, annual_elec_kwh, budget_gbp, roof_or_land, include_battery)
    chosen = options_sorted[0]

    st.markdown("## Results")
    c1, c2, c3 = st.columns(3)
    c1.metric("Best option", chosen["name"])
    c2.metric("CAPEX", fmt_gbp(chosen["capex"]))
    c3.metric("Payback", "—" if math.isinf(chosen["payback_years"]) else f"{chosen['payback_years']:.2f} yrs")

    st.write("### Summary")
    st.write(f"- **Annual savings:** {fmt_gbp(chosen['annual_savings'])}")
    st.write(f"- **CO₂ reduction (proxy):** {chosen['co2_saved_t']:.0f} tCO₂e/year")
    st.write(f"- **Notes:** {chosen['notes']}")

    st.write("### Top 3 options")
    for i, o in enumerate(options_sorted[:3], start=1):
        st.write(f"**{i}. {o['name']}** — CAPEX {fmt_gbp(o['capex'])}, savings {fmt_gbp(o['annual_savings'])}, "
                 f"payback {'∞' if math.isinf(o['payback_years']) else f'{o['payback_years']:.2f} yrs'}")

    st.markdown("## Download report")
    inputs = {
        "annual_elec_kwh": float(annual_elec_kwh),
        "annual_bill_gbp": float(annual_bill_gbp),
        "carbon_target_year": int(carbon_target_year),
        "budget_gbp": float(budget_gbp),
        "feasibility": roof_or_land,
        "generated_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    pdf_bytes = build_pdf(org_name, location, inputs, options_sorted, chosen)
    st.download_button(
        label="Download DECIDR PDF (GBP)",
        data=pdf_bytes,
        file_name="decidr_report.pdf",
        mime="application/pdf",
        use_container_width=True
    )

st.markdown("---")
st.caption("© DECIDR by Felix GRC • Pilot build. Next: tariff profiles, multi-site portfolios, financing, audit logs.")
