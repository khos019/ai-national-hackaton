"""Build the PeriZone project report PDF."""
import json
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

PROJECT = Path(r"C:\Users\user\Documents\LangForge")
SHOTS = Path(sys.argv[1])
OUT = PROJECT / "docs" / "PeriZone_Project_Report.pdf"

F = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("UI", F + "segoeui.ttf"))
pdfmetrics.registerFont(TTFont("UI-B", F + "segoeuib.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "consola.ttf"))
pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI", boldItalic="UI-B")

RED, YEL, GRN = colors.HexColor("#d32f2f"), colors.HexColor("#f0b429"), colors.HexColor("#2e7d4f")
ACC, INK, MUTED = colors.HexColor("#2457c5"), colors.HexColor("#1b1f24"), colors.HexColor("#5d6673")
LINE, SOFT = colors.HexColor("#e2e5ea"), colors.HexColor("#f3f5f8")

S = {
    "title": ParagraphStyle("title", fontName="UI-B", fontSize=30, leading=36, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName="UI", fontSize=14, leading=20, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName="UI-B", fontSize=18, leading=23, textColor=INK, spaceBefore=4, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="UI-B", fontSize=12.5, leading=16, textColor=ACC, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="UI", fontSize=10, leading=14.5, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="UI", fontSize=8.5, leading=11.5, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="UI", fontSize=8.8, leading=11.8, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="UI-B", fontSize=8.8, leading=11.8, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="UI", fontSize=10, leading=14.5, textColor=INK, leftIndent=14,
                             bulletIndent=3, spaceAfter=2),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.6, leading=12, textColor=INK, backColor=SOFT,
                           borderPadding=(6, 8, 6, 8), spaceBefore=4, spaceAfter=10, leftIndent=8, rightIndent=8),
    "caption": ParagraphStyle("caption", fontName="UI", fontSize=8.5, leading=11, textColor=MUTED,
                              alignment=TA_CENTER, spaceBefore=3, spaceAfter=12),
    "callout": ParagraphStyle("callout", fontName="UI", fontSize=10, leading=14.5, textColor=INK,
                              backColor=colors.HexColor("#eef3fd"), borderPadding=(8, 10, 8, 10),
                              spaceBefore=6, spaceAfter=12, leftIndent=10, rightIndent=10),
    "warn": ParagraphStyle("warn", fontName="UI", fontSize=9.5, leading=13.5, textColor=INK,
                           backColor=colors.HexColor("#fdf5e3"), borderPadding=(8, 10, 8, 10),
                           spaceBefore=6, spaceAfter=12, leftIndent=10, rightIndent=10),
}
W = A4[0] - 4 * cm  # content width


def P(t, s="body"): return Paragraph(t, S[s])
def B(items): return [Paragraph(i, S["bullet"], bulletText="•") for i in items]


def table(rows, widths, header=True, zebra=True):
    data = [[c if not isinstance(c, str) else Paragraph(c, S["cellb" if (header and r == 0) else "cell"])
             for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    if zebra:
        for r in range(2 if header else 1, len(rows), 2):
            st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#fafbfc")))
    t.setStyle(TableStyle(st))
    return t


def zone_dot(z):
    c = {"red": RED, "yellow": YEL, "green": GRN}[z]
    d = Drawing(10, 10)
    d.add(Rect(1, 1, 8, 8, rx=4, ry=4, fillColor=c, strokeColor=c))
    return d


def screenshot(name, caption, max_h=17 * cm):
    p = SHOTS / name
    if not p.exists():
        return []
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(p)).getSize()
    w = W
    h = w * ih / iw
    if h > max_h:
        h, w = max_h, max_h * iw / ih
    img = Image(str(p), width=w, height=h)
    img.hAlign = "CENTER"
    frame = Table([[img]], colWidths=[w + 2])
    frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [KeepTogether([frame, P(caption, "caption")])]


def arrow(d, x1, y1, x2, y2, c=MUTED):
    d.add(Line(x1, y1, x2, y2, strokeColor=c, strokeWidth=1.2))
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    s = 5
    d.add(Polygon([x2, y2, x2 - s * math.cos(a - 0.4), y2 - s * math.sin(a - 0.4),
                   x2 - s * math.cos(a + 0.4), y2 - s * math.sin(a + 0.4)], fillColor=c, strokeColor=c))


def box(d, x, y, w, h, title, sub="", fill=SOFT, stroke=LINE, tc=INK):
    d.add(Rect(x, y, w, h, rx=6, ry=6, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
    d.add(String(x + w / 2, y + h - 15, title, fontName="UI-B", fontSize=8.8, fillColor=tc, textAnchor="middle"))
    for i, line in enumerate(sub.split("|") if sub else []):
        d.add(String(x + w / 2, y + h - 28 - i * 10.5, line, fontName="UI", fontSize=7.4, fillColor=MUTED,
                     textAnchor="middle"))


def architecture():
    d = Drawing(W, 255)
    cw = 110                      # column width
    x_in, x_obs, x_mid, x_out = 0, 135, 270, 400
    wo = W - x_out
    box(d, x_in, 185, cw, 58, "Ayol (self-report)", "Telegram bot|Mobile web page")
    box(d, x_in, 115, cw, 58, "Patronaj / klinika", "Nurse & doctor|web forms")
    box(d, x_in, 45, cw, 58, "Laboratoriya / DMED", "Phase 2: FHIR R5|integration")
    box(d, x_obs, 120, cw, 80, "Observation", "source = self / clinic /|lab / device|ML-ready format",
        fill=colors.HexColor("#eef3fd"), stroke=ACC)
    box(d, x_obs, 10, cw, 75, "Export & retraining", "pseudonymised CSV|+ outcome labels|-> local ML models")
    box(d, x_mid, 150, cw, 75, "Rules engine (YAML)", "bands · danger signs|combos · trends|risk floors · MEOWS",
        fill=colors.HexColor("#eef3fd"), stroke=ACC)
    box(d, x_mid, 55, cw, 75, "ML layer (advisory)", "Random forest|may raise green->yellow|never creates red")
    # zone column
    d.add(Rect(x_out, 140, wo, 95, rx=6, ry=6, fillColor=colors.white, strokeColor=LINE))
    d.add(String(x_out + wo / 2, 220, "Zone", fontName="UI-B", fontSize=9, fillColor=INK, textAnchor="middle"))
    for i, (c, t) in enumerate([(RED, "QIZIL"), (YEL, "SARIQ"), (GRN, "YASHIL")]):
        d.add(Rect(x_out + 10, 196 - i * 20, 11, 11, rx=5.5, ry=5.5, fillColor=c, strokeColor=c))
        d.add(String(x_out + 27, 198 - i * 20, t, fontName="UI-B", fontSize=8.3, fillColor=INK))
    box(d, x_out, 10, wo, 105, "Alert", "Telegram · SMS|· dashboard|specialist ->|head physician|-> region · audit",
        fill=colors.HexColor("#fdecec"), stroke=RED)
    arrow(d, x_in + cw, 214, x_obs, 175)
    arrow(d, x_in + cw, 144, x_obs, 160)
    arrow(d, x_in + cw, 74, x_obs, 135)
    arrow(d, x_obs + cw, 172, x_mid, 187)
    arrow(d, x_obs + cw, 140, x_mid, 100)
    arrow(d, x_mid + cw, 187, x_out, 187)
    arrow(d, x_mid + cw, 92, x_out, 150)
    arrow(d, x_out + wo / 2, 140, x_out + wo / 2, 115, RED)
    arrow(d, x_obs + cw / 2, 120, x_obs + cw / 2, 85)
    return d


def on_page(c, doc):
    c.saveState()
    if doc.page > 1:
        c.setFont("UI", 8)
        c.setFillColor(MUTED)
        c.drawString(2 * cm, A4[1] - 1.2 * cm, "PeriZone — Perinatal high-risk registry · Project report")
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{doc.page}")
        c.setStrokeColor(LINE)
        c.line(2 * cm, A4[1] - 1.35 * cm, A4[0] - 2 * cm, A4[1] - 1.35 * cm)
    c.restoreState()


def cover():
    d = Drawing(W, 40)
    for i, col in enumerate([RED, YEL, GRN]):
        d.add(Rect(i * 26, 8, 20, 20, rx=10, ry=10, fillColor=col, strokeColor=col))
    return [Spacer(1, 3 * cm), d, Spacer(1, 10), P("PeriZone", "title"),
            P("Perinatal yuqori xavf guruhi registri — colour-zone monitoring of pregnant women and newborns "
              "with automatic alerts to OvaBMU specialists", "subtitle"),
            Spacer(1, 1.2 * cm),
            table([["Document", "Project report: features, architecture, research basis, ML, roadmap"],
                   ["Status", "Working hackathon prototype (v0.1)"],
                   ["Date", "18 November 2026"],
                   ["Stack", "Python · FastAPI · SQLite/SQLAlchemy · scikit-learn · Telegram Bot API · vanilla JS, Chart.js, Leaflet"],
                   ["Location", "C:\\Users\\user\\Documents\\LangForge"]], [3.2 * cm, W - 3.2 * cm], header=False, zebra=False),
            Spacer(1, 1.5 * cm),
            P("Clinical thresholds in this prototype are demonstration values based on MEOWS, NEWTT2 and WHO danger "
              "signs. They must be validated by obstetricians, neonatologists and the Ministry of Health of Uzbekistan "
              "before any real-world use.", "warn"),
            PageBreak()]


def main():
    meta = json.loads((PROJECT / "ml" / "models" / "metrics.json").read_text(encoding="utf-8"))
    cv = meta["cv"]
    st = []
    st += cover()

    # 1 Executive summary
    st += [P("1. Executive summary", "h1"),
           P("In Uzbekistan, the health of pregnant women and newborns is not monitored in real time at district level. "
             "When test results get worse, OvaBMU specialists find out late and high-risk cases are missed. "
             "<b>PeriZone</b> is a registry that places every pregnant woman and newborn in a "
             "<font color='#d32f2f'><b>Red</b></font>, <font color='#b7791f'><b>Yellow</b></font> or "
             "<font color='#2e7d4f'><b>Green</b></font> zone. The zone is recalculated after every new measurement, "
             "and the right specialist is alerted automatically when it gets worse. If nobody responds, the alert "
             "escalates to the head physician and then to the regional level."),
           P("What the prototype can do today:", "h2")]
    st += B([
        "Register pregnant women and newborns with their background risk factors; age, low birth weight and prematurity are detected automatically.",
        "Take data from three sources: the woman herself (Telegram bot or mobile web page), the patronage nurse or clinic, and the laboratory. Every value records its source.",
        "Assign a colour zone with a transparent, doctor-editable rules engine: value thresholds, WHO danger signs, dangerous combinations (e.g. preeclampsia, sepsis), worsening trends, risk-factor floors, and the MEOWS rule that several yellow findings at once become red.",
        "Send alerts automatically: Telegram with action buttons, an SMS fallback (stub) and the live dashboard. Alerts are de-duplicated, escalate on timers and keep a full audit log.",
        "Give the woman immediate safety advice after every self-report; a danger sign tells her to call 103.",
        "Detect missed check-ins: yellow and red patients who stop sending data trigger an alert.",
        "Add an advisory ML risk score (random forest trained on the UCI Maternal Health Risk dataset) on top of the rules.",
        "Export a pseudonymised, ML-ready dataset with outcome labels so models can be retrained on local Uzbek data.",
    ])
    st += [P("<b>Key design answer:</b> self-reported data <i>is</i> useful, but as one layer, not the only source. "
             "Women report danger signs that only they can know. Self-reported vital signs trigger a verification "
             "step, and clinic or lab readings confirm them. Section 5 summarises the evidence.", "callout")]

    # 2 Problem
    st += [P("2. Problem and evidence", "h1"),
           table([["Fact", "Source"],
                  ["Maternal mortality fell from 38 to 30 per 100,000 live births (2010–2020), still high compared with Europe & Central Asia.", "Gazeta.uz / ADB"],
                  ["69% of maternal deaths in the last decade were caused by bleeding, eclampsia and sepsis, which usually show early warning signs.", "UNDP Vision 2030 programme document"],
                  ["A 2024 UNFPA/UNICEF assessment judged 230 perinatal deaths preventable with timely care.", "UNFPA country programme (2025)"],
                  ["ADB approved a $100M perinatal loan (Oct 2025) that funds electronic patient records to identify risks early, plus a stronger referral system.", "Kun.uz, Tashkent Times"],
                  ["DMED, the unified electronic health record, covers 36M+ citizens; the Digital Health Platform publishes FHIR R5 integration guides.", "Yuz.uz, DHP FHIR IG"]],
                 [W - 4.2 * cm, 4.2 * cm]),
           Spacer(1, 8),
           P("<b>Why it matters for the pitch:</b> the government is already funding early risk identification through "
             "electronic records. PeriZone is a working prototype of exactly that, and its data model is shaped to "
             "connect to DMED through FHIR.", "callout"),
           ]
    st += [KeepTogether([P("Clinical basis", "h2")] + B([
        "<b>MEOWS</b> (Modified Early Obstetric Warning Score): green, yellow and red bands for each vital sign; one red parameter or two or more yellow ones trigger urgent review.",
        "<b>NEWTT2</b> (UK newborn early warning chart): tracks newborn vital signs and escalates at-risk babies (sepsis risk, low Apgar, hypoglycaemia).",
        "<b>WHO danger signs</b> for pregnancy and young infants (IMCI): bleeding, convulsions, severe headache, reduced fetal movement; for newborns, not feeding, fast breathing ≥60/min, chest indrawing, lethargy.",
        "<b>Similar systems:</b> Palestine's MCH e-Registry on DHIS2 (since 2016) gives clinicians real-time decision-support alerts and sends SMS to women with risk factors.",
    ]))]
    st.append(Spacer(1, 10))

    # 3 Solution & architecture
    st += [P("3. Solution overview and architecture", "h1"),
           P("Every new piece of data, from whatever source, goes through the same pipeline: it is stored as an "
             "Observation, the patient is re-assessed, and if the zone gets worse (or a new danger sign appears) an "
             "alert is created and routed to the responsible people."),
           architecture(),
           P("Figure 1. Data flow: sources → observation → rules + ML → zone → alert and escalation; export for retraining.", "caption"),
           P("Users and roles", "h2"),
           table([["Role", "What they do in PeriZone"],
                  ["Pregnant woman / young mother", "Links her phone in the Telegram bot; sends a daily danger-sign checklist and home readings (BP, temperature, glucose, weight); receives instant advice and reminders."],
                  ["Patronage nurse / family doctor", "Registers patients, enters clinic and lab measurements, records risk factors and outcomes."],
                  ["OvaBMU district specialist", "Watches the live dashboard; receives alerts (Telegram + panel); acknowledges and records actions: called, home visit, referred, no risk."],
                  ["District head physician", "Receives alerts escalated after the acknowledgement timeout (level 1)."],
                  ["Regional perinatal centre", "Receives level-2 escalations; sees district comparison and response-time KPIs."]],
                 [4.6 * cm, W - 4.6 * cm])]
    st.append(PageBreak())

    # 4 Features
    st += [P("4. Features in detail", "h1"), P("4.1 Colour-zone rules engine", "h2"),
           P("A pure-Python engine (<font face='Mono'>backend/app/rules/engine.py</font>) reads clinical rules from "
             "YAML files that doctors can review and edit without touching code. The zone is the <b>worst</b> of:")]
    st += B([
        "<b>Parameter bands</b>: latest <i>fresh</i> value of each measurement (BP, heart rate, temperature, SpO2, respiratory rate, haemoglobin, glucose, proteinuria). Old values expire (e.g. BP after 14 days, Hb after 45).",
        "<b>Danger-sign symptoms</b> reported within the last 72 hours (13 maternal, 12 newborn signs).",
        "<b>Combinations</b>: hypertension + proteinuria or + headache/visual disturbance/oedema → preeclampsia (red); fever + tachycardia → sepsis (red); newborn fast breathing + lethargy/poor feeding → neonatal sepsis.",
        "<b>Worsening trends</b>: BP rising ≥15 mmHg within 21 days, Hb falling ≥15 g/L, rapid weight gain; newborn weight loss. Trends compare averages, so one noisy home reading cannot trigger them.",
        "<b>Risk-factor floors</b>: e.g. twins, previous caesarean, chronic hypertension → at least yellow; very low birth weight (&lt;1500 g) or very preterm (&lt;32 weeks) → red.",
        "<b>MEOWS aggregation</b>: 3 yellow findings at once → red (2 for newborns, who deteriorate faster).",
    ])
    st += [P("Every finding is shown to the doctor with its category, data source and timestamp, so the system is "
             "explainable: the specialist always sees <i>why</i> a woman is red.")]

    def zrow(label, red, yellow, green):
        return [label, red, yellow, green]

    hdr = ["Parameter (mother)", "Red", "Yellow", "Green"]
    st += [Spacer(1, 4), table([hdr,
        zrow("Systolic BP (mmHg)", "≥160 or &lt;90", "140–159 or 90–99", "100–139"),
        zrow("Diastolic BP (mmHg)", "≥110", "90–109", "&lt;90"),
        zrow("Heart rate (/min)", "≥120 or &lt;50", "100–119", "50–99"),
        zrow("Temperature (°C)", "≥38.5 or &lt;35", "37.6–38.4", "35–37.5"),
        zrow("SpO2 (%)", "&lt;94", "94–95", "≥96"),
        zrow("Haemoglobin (g/L)", "&lt;70", "70–99", "≥100"),
        zrow("Fasting glucose (mmol/L)", "≥11.1 or &lt;3.0", "5.1–11.0", "3.0–5.0"),
        zrow("Proteinuria (dipstick)", "≥2+", "1+", "negative / trace"),
        zrow("Danger signs", "bleeding, convulsions, severe abdominal pain, reduced fetal movement, waters breaking, breathlessness",
             "severe headache, blurred vision, face/hand swelling, fever, dysuria, vomiting, low mood", "none"),
    ], [4.0 * cm, 4.6 * cm, 4.6 * cm, W - 13.2 * cm]),
        P("Table 1. Maternal thresholds (demo values; file backend/app/rules/maternal.yaml).", "caption"),
        KeepTogether([table([["Parameter (newborn, 0–28 days)", "Red", "Yellow"],
               ["Temperature (°C)", "≥38.0 or &lt;35.5", "37.6–37.9 or 35.5–36.4"],
               ["Heart rate (/min)", "≥180 or &lt;100", "160–179 or 100–109"],
               ["Respiratory rate (/min)", "≥60 or &lt;30", "50–59"],
               ["SpO2 (%) / glucose (mmol/L)", "&lt;92 / &lt;2.0", "92–94 / 2.0–2.5"],
               ["Danger signs", "not feeding, convulsions, lethargy, fast breathing, chest indrawing, cyanosis, early jaundice",
                "jaundice, umbilical redness, vomiting, diarrhoea, skin pustules"],
               ["Birth data (automatic)", "&lt;1500 g, &lt;32 weeks", "&lt;2500 g, &lt;37 weeks, Apgar(5) &lt;7"]],
              [5.0 * cm, (W - 5.0 * cm) / 2, (W - 5.0 * cm) / 2]),
        P("Table 2. Newborn thresholds (file backend/app/rules/newborn.yaml).", "caption")])]

    st += [P("4.2 Self-reporting by women", "h2")]
    st += B([
        "<b>Telegram bot</b>: /start → share contact (only her own number is accepted) → linked to her registry record(s). A mother and her newborn sharing one phone are both linked, and the bot asks who the report is for.",
        "<b>One-tap danger-sign checklist</b> with toggle buttons, plus buttons to enter BP (\"120/80\"), temperature, glucose and weight, with input validation.",
        "<b>Mobile web page</b> (\"Ona ilovasi\") with the same flow for women who prefer a browser.",
        "<b>Instant advice</b>: a danger sign gives \"Call 103 now or go to the nearest maternity unit — your specialist has been notified\"; yellow gives \"A specialist will contact you\"; green gives a thank-you and a reminder to keep monitoring.",
        "<b>Verification loop</b>: a red zone caused only by self-reported values creates a <i>verify_self_report</i> alert. When the nurse's clinic reading confirms it, the alert is marked confirmed in its audit log.",
    ])
    st += [P("4.3 Alerts and escalation", "h2")]
    st += [table([["Alert type", "When it is created"],
                  ["danger_sign", "The woman or a nurse reports a red danger sign; always sent, never de-duplicated."],
                  ["verify_self_report", "Zone is red only because of self-reported values: call or visit to verify."],
                  ["zone_worsened", "Zone gets worse (green→yellow, yellow→red…) or a new red reading arrives."],
                  ["missed_checkin", "A yellow or red patient sends no data within the expected interval (yellow 7 days, red 2 days)."]],
                 [4.0 * cm, W - 4.0 * cm]), Spacer(1, 6)]
    st += B([
        "<b>Routing</b>: level 0 → OvaBMU specialist of the patient's district; level 1 → district head physician; level 2 → regional perinatal centre.",
        "<b>Escalation timers</b> for unacknowledged red alerts (demo 90 s / 180 s; production e.g. 30 / 60 min, set via ESCALATION_SECONDS).",
        "<b>Actions</b> from Telegram buttons or the dashboard: acknowledged, called, home visit, referred to perinatal centre, ambulance, verified – no risk. Referral or no-risk closes the alert.",
        "<b>Alert-fatigue controls</b>: one open alert per patient and problem type, MEOWS aggregation, trend smoothing, and red-first sorting so missed check-ins never hide emergencies.",
        "<b>Audit log</b> for every alert: created, notified (who, through which channel), escalated, acknowledged, action, resolved. The data supports response-time KPIs.",
    ])
    st += [P("4.4 Dashboard and registry (for specialists)", "h2")]
    st += B([
        "<b>Live monitoring panel</b> (refreshes every 5 s): red/yellow/green counts for mothers and newborns, open and escalated alerts, average response time.",
        "<b>Attention list</b> filtered by zone and patient type, with the top reasons for each patient.",
        "<b>Map</b> (Leaflet/OpenStreetMap) with colour-coded patient markers, and a <b>district comparison</b> bar chart.",
        "<b>Alert feed</b> with one-click actions, a sound and on-screen notice for new red alerts, and the name of the user for the audit log.",
        "<b>Registry</b>: search by name or phone, filters, registration of new mothers and newborns.",
        "<b>Patient card</b>: \"Why is she red?\" explanation, BP / Hb / glucose (or newborn temperature, breathing and weight) charts with self-reported points marked separately, full observation history with source badges, entry of new clinic readings, risk-factor editing, outcome labelling, and alert audit timeline.",
        "<b>Rules & ML page</b>: all thresholds rendered from YAML, ML metrics, dataset export, staff Telegram link codes.",
    ])
    st.append(PageBreak())

    # Screenshots
    st += [P("Screenshots", "h1")]
    st += screenshot("dash.png", "Figure 2. Monitoring dashboard: zone KPIs, attention list, alert feed with actions, map and district comparison.")
    st.append(PageBreak())
    st += screenshot("patient.png", "Figure 3. Patient card: reasons for the zone (with data source), ML score, BP and Hb/glucose trends, observation history.")
    st.append(PageBreak())
    st += screenshot("registry.png", "Figure 4. Registry with search and filters.", max_h=11 * cm)
    st += screenshot("rules.png", "Figure 5. Rules and ML page — transparent thresholds, model metrics, export, staff link codes.", max_h=11 * cm)
    st.append(PageBreak())

    # 5 Self-report evidence
    st += [P("5. Is self-reported data effective?", "h1"),
           P("<b>Short answer: yes, as one layer of a hybrid system, not as the only source.</b>", "callout"),
           table([["Evidence", "Finding", "What we did"],
                  ["BUMP 1 & 2 RCTs (JAMA 2022, UK)", "Home BP self-monitoring did not by itself detect hypertension earlier or improve control. It was safe, and >50% of women who developed hypertension had a raised home reading about a month before clinic diagnosis.",
                   "The signal exists but was not acted on, so PeriZone routes it automatically and escalates."],
                  ["Home measurement accuracy studies", "Home BP and weight agree closely with clinic readings with validated devices; adherence is the weak point (~1–1.5 readings/week).",
                   "Telegram one-tap flow, reminders, missed check-in alerts; self-reported values trigger verification."],
                  ["mHealth meta-analysis (LMICs)", "mHealth improved facility delivery (OR 2.21), postnatal care and knowledge of danger signs; overall evidence quality is mixed.",
                   "Danger-sign checklist doubles as education; immediate advice after every report."]],
                 [3.6 * cm, 7.0 * cm, W - 10.6 * cm]),
           Spacer(1, 8), P("Design rules derived from the evidence", "h2")]
    st += B([
        "Self-report is strongest for <b>symptoms</b>: only the woman knows she is bleeding or has a headache right now.",
        "Self-reported vital signs <b>start a check</b>; they don't diagnose. Every observation stores its source, and alerts say whether a value was self-reported.",
        "Clinic and lab data stay the backbone; later they come from DMED automatically, so nurses don't enter the same data twice.",
        "The source is also an <b>ML feature</b>: future models can learn how much to trust each source.",
    ])

    # 6 ML
    st += [P("6. Machine learning", "h1"),
           P(f"<b>Baseline dataset:</b> UCI Maternal Health Risk (rural clinics in Bangladesh): {meta['dataset']['rows_raw']} rows; "
             "features: age, systolic BP, diastolic BP, blood glucose, body temperature, heart rate; label low/mid/high risk. "
             f"<b>Only {meta['dataset']['rows_unique']} rows are unique.</b> Many public notebooks report 85–90% accuracy because duplicate rows "
             "appear in both training and test sets. We removed duplicates and used 5-fold stratified cross-validation:"),
           table([["Model", "Macro F1", "High-risk recall", "Selected"]] +
                 [[k, f"{v['macro_f1']:.2f}", f"{v['high_risk_recall']:.0%}", "Yes" if k == meta["model_name"] else ""]
                  for k, v in cv.items()], [6 * cm, 3.5 * cm, 4 * cm, W - 13.5 * cm]),
           P("Table 3. Honest cross-validated performance. The model is chosen by high-risk recall first, because missing a high-risk woman is the costliest error.", "caption"),
           P("How ML is used safely", "h2")]
    st += B([
        "ML is <b>advisory</b>: if P(high risk) ≥ 0.6 it can raise a green patient to yellow (\"look at her sooner\"). It never creates a red alert and never lowers a zone. Rules remain the safety net.",
        "Missing inputs are filled with normal values, and the patient card lists which ones were filled.",
        "The model runs only for mothers; newborns use rules only.",
    ])
    st += [P("Roadmap to useful local models", "h2")]
    st += B([
        "The registry exports one pseudonymised row per observation (<font face='Mono'>/api/export/ml-dataset.csv</font>): patient context, all measurements, 25 symptom flags, data source, current zone and <b>outcome label</b> (preeclampsia, eclampsia, haemorrhage, preterm birth, stillbirth, NICU admission, etc.).",
        "After 6–12 months of local data: outcome-prediction models (e.g. gradient boosting) on time-series features such as BP slope, Hb slope, symptom frequency and reporting adherence.",
        "Prospective validation, probability calibration, monitoring for drift by district, and clinician review before ML is allowed to influence zones further.",
    ])
    st.append(PageBreak())

    # 7 Technical
    st += [P("7. Technical implementation", "h1"),
           table([["Layer", "Technology", "Notes"],
                  ["Backend API", "Python, FastAPI, Pydantic", "REST API + OpenAPI docs at /docs; input validation with physiological ranges."],
                  ["Database", "SQLAlchemy 2, SQLite (PostgreSQL-ready)", "Models follow FHIR: Patient, Observation, RiskAssessment (Assessment), Flag/Communication (Alert, AlertEvent)."],
                  ["Rules", "YAML + pure-Python engine", "No database access; unit-tested; versioned thresholds."],
                  ["Scheduler", "asyncio background task", "Every 10 s: escalations and missed check-ins."],
                  ["Messaging", "Telegram Bot API over httpx (long polling)", "No extra bot framework; SMS gateway stub ready for Eskiz / Play Mobile."],
                  ["ML", "scikit-learn, joblib", "Random forest; training script with honest evaluation."],
                  ["Frontend", "Static HTML, vanilla JS, Chart.js, Leaflet", "Served by FastAPI; light/dark theme; Uzbek (Latin) UI; mobile-friendly mother page."]],
                 [2.8 * cm, 5.2 * cm, W - 8.0 * cm]),
           P("Main API endpoints", "h2"),
           table([["Endpoint", "Purpose"],
                  ["GET /api/dashboard", "Zone counts, open and escalated alerts, response time, district breakdown"],
                  ["GET / POST /api/patients", "List with filters / register mother or newborn"],
                  ["GET / PATCH /api/patients/{id}", "Full card with reasons, history, alerts / edit risk factors, outcome"],
                  ["POST /api/patients/{id}/observations", "Clinic, lab or device reading → re-assessment → alert if worse"],
                  ["POST /api/self-report", "Woman's own report (by phone or ID) → zone + safety advice"],
                  ["GET /api/alerts, POST /api/alerts/{id}/ack | action | resolve", "Alert feed and actions (audited)"],
                  ["GET /api/rules/{kind}, /api/model, /api/meta", "Rules, ML metrics, catalogs for forms"],
                  ["GET /api/export/ml-dataset.csv", "Pseudonymised training dataset with outcome labels"]],
                 [7.2 * cm, W - 7.2 * cm]),
           P("Project structure", "h2"),
           P("backend/app/rules/  maternal.yaml, newborn.yaml, engine.py<br/>"
             "backend/app/services/  assessment.py, alerts.py, notify.py, telegram_bot.py, intake.py, ml.py<br/>"
             "backend/app/api/routes.py · models.py · schemas.py · main.py<br/>"
             "frontend/  index.html, patients.html, patient.html, mother.html, rules.html, assets/<br/>"
             "ml/train.py · ml/models/ · ml/data/raw/<br/>"
             "scripts/seed.py · scripts/demo_scenario.py · tests/ · docs/RESEARCH.md", "code"),
           P("Quality", "h2")]
    st += B([
        "<b>20 automated tests</b> (all passing): 14 rules-engine tests (thresholds, combos, expiry, trends and noise robustness, MEOWS aggregation, newborn logic) and 6 API flow tests (self-report → alert → escalation → action, de-duplication, export pseudonymisation, unknown phone).",
        "Demo data generator: 160 mothers in clinical archetypes (normal, gestational hypertension, preeclampsia, anaemia, gestational diabetes, infection) plus 40 newborns across 5 Tashkent districts. All names and numbers are fictional.",
        "About 3,800 lines of code and configuration.",
    ])
    st.append(PageBreak())

    # 8 Run & demo
    st += [P("8. How to run and demo", "h1"),
           P("pip install -r requirements.txt<br/>python ml/train.py<br/>python scripts/seed.py<br/>"
             "uvicorn backend.app.main:app --port 8000<br/># open http://127.0.0.1:8000", "code"),
           P("Optional Telegram: create a bot with @BotFather and put TELEGRAM_BOT_TOKEN in .env. Specialists send "
             "<font face='Mono'>/staff CODE</font> (codes on the Rules page); women press /start and share their contact."),
           P("Live pitch scenario (scripts/demo_scenario.py)", "h2"),
           table([["Step", "What happens", "System response"],
                  ["1", "Malika (32 weeks) sends home BP 128/82 through Telegram", "Green; \"Thank you, values are normal\""],
                  ["2", "Next day: 148/94 + severe headache (self-reported)", "RED (preeclampsia signs). The woman is told to call 103; a \"verify\" alert goes to the specialist."],
                  ["3", "Nurse home visit: 166/112, proteinuria 2+", "Confirmed severe preeclampsia; the self-report alert is marked confirmed; new alert with reasons"],
                  ["4", "Nobody acknowledges", "Escalates to head physician (90 s), then region (180 s); everything visible in the audit log"]],
                 [1.2 * cm, 7 * cm, W - 8.2 * cm]),
           Spacer(1, 6), P("Closing line: \"Today these warning signs are found days late. With PeriZone, it takes seconds.\"", "callout")]

    # 9 Risks & roadmap
    st += [P("9. Risks, limitations and answers", "h1"),
           table([["Question / risk", "Answer"],
                  ["Clinical responsibility", "Decision support only: zones route attention, doctors decide. Thresholds need MoH/OvaBMU sign-off; they are versioned YAML."],
                  ["Personal data", "Uzbek personal-data law requires citizens' data to be stored on servers in Uzbekistan: on-premise or local cloud deployment, role-based access, pseudonymised export."],
                  ["Alert fatigue", "De-duplication, aggregation, trend smoothing, red-first sorting; daily digest for yellow (roadmap)."],
                  ["Double data entry", "Phase 2 pulls labs and visits from DMED (FHIR Observation) and pushes zones back (RiskAssessment / Flag)."],
                  ["Women without smartphones", "Nurse enters data; SMS/USSD channel and family-member Telegram (roadmap)."],
                  ["ML trained on foreign data", "Advisory only; honest metrics; retraining pipeline on local labelled outcomes."],
                  ["Prototype gaps", "No authentication or roles yet; SMS is a stub; SQLite for demo; UI in Uzbek only."]],
                 [4.2 * cm, W - 4.2 * cm]),
           P("Roadmap", "h2"),
           table([["Phase", "Scope"],
                  ["Hackathon (done)", "Rules engine, self-report bot & web, alerts with escalation, dashboard, patient card, baseline ML, export, tests, demo data"],
                  ["Pilot (1 district, 3 months)", "Clinical validation of thresholds, authentication and roles, real SMS gateway, Russian UI, on-prem deployment, staff training"],
                  ["Integration", "DMED / Digital Health Platform via FHIR R5, lab analyser feeds, perinatal-centre referral workflow"],
                  ["Scale & ML", "Outcome-based models on local data, calibration and drift monitoring, regional analytics, USSD channel"]],
                 [4.2 * cm, W - 4.2 * cm]),
           P("Open questions for the team", "h2")]
    st += B([
        "Exact meaning and district staffing of OvaBMU, and who receives alerts at night.",
        "The current Ministry of Health order on perinatal risk groups, to align the thresholds and risk-factor list.",
        "Which data polyclinics already enter into DMED.",
        "SMS gateway access for a pilot.",
    ])

    # Sources
    st += [P("Sources", "h2"),
           P("Gazeta.uz (2024) ADB perinatal care · Kun.uz & Tashkent Times (2025) ADB $100M loan · UNDP Vision 2030 Perinatal Care prodoc (2023) · "
             "UNFPA Uzbekistan Country Programme draft (2025) · Euronews (2026) Uzbekistan digital healthcare · Yuz.uz (2025) unified EMR / DMED · "
             "Uzbekistan Digital Health Platform FHIR IG (build.fhir.org) · MEOWS: medicalalgorithms.com, PMC10040990, PMC5910060, PMC7028086 · "
             "NEWTT2 SOP, NHS Scotland · DHIS2 Palestine MCH e-Registry · BUMP 1 & 2, JAMA 2022 (PubMed 35503346; Univ. of Oxford) · "
             "Home monitoring feasibility: PMC5135734, PMC9049804 · mHealth LMIC meta-analysis: PMC10257264 · "
             "ML for preeclampsia: PMC12158820, JMIR 2026 e78714 · UCI Maternal Health Risk dataset (archive.ics.uci.edu/dataset/863). "
             "Full links: docs/RESEARCH.md.", "small")]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="PeriZone — Project Report",
                            author="PeriZone hackathon team", subject="Perinatal high-risk registry")
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    print(OUT)


if __name__ == "__main__":
    main()
