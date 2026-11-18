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
OUT = PROJECT / "docs" / "PeriZone_Loyiha_Hisoboti_UZ.pdf"

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
    box(d, x_in, 185, cw, 58, "Ayol (oʻzi kiritadi)", "Telegram bot|Mobil veb-sahifa")
    box(d, x_in, 115, cw, 58, "Patronaj / klinika", "Hamshira va shifokor|veb-formalari")
    box(d, x_in, 45, cw, 58, "Laboratoriya / DMED", "2-bosqich: FHIR R5|integratsiya")
    box(d, x_obs, 120, cw, 80, "Kuzatuv", "manba: oʻzi / klinika /|laboratoriya / qurilma|ML uchun tayyor format",
        fill=colors.HexColor("#eef3fd"), stroke=ACC)
    box(d, x_obs, 10, cw, 75, "Eksport va qayta oʻqitish", "anonim CSV|+ natija yorliqlari|-> mahalliy ML modellar")
    box(d, x_mid, 150, cw, 75, "Qoidalar (YAML)", "chegaralar · xavf belgilari|kombinatsiyalar · trendlar|xavf omillari · MEOWS",
        fill=colors.HexColor("#eef3fd"), stroke=ACC)
    box(d, x_mid, 55, cw, 75, "ML (maslahat)", "Random Forest|yashil->sariq koʻtaradi|qizil yaratmaydi")
    # zone column
    d.add(Rect(x_out, 140, wo, 95, rx=6, ry=6, fillColor=colors.white, strokeColor=LINE))
    d.add(String(x_out + wo / 2, 220, "Zona", fontName="UI-B", fontSize=9, fillColor=INK, textAnchor="middle"))
    for i, (c, t) in enumerate([(RED, "QIZIL"), (YEL, "SARIQ"), (GRN, "YASHIL")]):
        d.add(Rect(x_out + 10, 196 - i * 20, 11, 11, rx=5.5, ry=5.5, fillColor=c, strokeColor=c))
        d.add(String(x_out + 27, 198 - i * 20, t, fontName="UI-B", fontSize=8.3, fillColor=INK))
    box(d, x_out, 10, wo, 105, "Xabarnoma", "Telegram · SMS|· panel|mutaxassis ->|bosh shifokor|-> viloyat · audit",
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
        c.drawString(2 * cm, A4[1] - 1.2 * cm, "PeriZone — Perinatal yuqori xavf guruhi registri · Loyiha hisoboti")
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{doc.page}")
        c.setStrokeColor(LINE)
        c.line(2 * cm, A4[1] - 1.35 * cm, A4[0] - 2 * cm, A4[1] - 1.35 * cm)
    c.restoreState()


def cover():
    d = Drawing(W, 40)
    for i, col in enumerate([RED, YEL, GRN]):
        d.add(Rect(i * 26, 8, 20, 20, rx=10, ry=10, fillColor=col, strokeColor=col))
    return [Spacer(1, 3 * cm), d, Spacer(1, 10), P("PeriZone", "title"),
            P("Perinatal yuqori xavf guruhi registri — homilador ayollar va chaqaloqlarni rangli zonalar orqali "
              "monitoring qilish va OvaBMU mutaxassislariga avtomatik xabarnoma yuborish tizimi", "subtitle"),
            Spacer(1, 1.2 * cm),
            table([["Hujjat", "Loyiha hisoboti: imkoniyatlar, arxitektura, ilmiy asos, ML, rivojlanish rejasi"],
                   ["Holati", "Ishlaydigan xakaton prototipi (v0.1)"],
                   ["Sana", "2026-yil 18-noyabr"],
                   ["Texnologiyalar", "Python · FastAPI · SQLite/SQLAlchemy · scikit-learn · Telegram Bot API · JavaScript, Chart.js, Leaflet"],
                   ["Joylashuv", "C:\\Users\\user\\Documents\\LangForge"]], [3.4 * cm, W - 3.4 * cm], header=False, zebra=False),
            Spacer(1, 1.5 * cm),
            P("Ushbu prototipdagi klinik chegara qiymatlari MEOWS, NEWTT2 va JSST xavf belgilari asosida olingan "
              "namunaviy qiymatlardir. Amalda qoʻllashdan oldin ular akusher-ginekologlar, neonatologlar va Oʻzbekiston "
              "Respublikasi Sogʻliqni saqlash vazirligi tomonidan tasdiqlanishi shart.", "warn"),
            PageBreak()]


def main():
    meta = json.loads((PROJECT / "ml" / "models" / "metrics.json").read_text(encoding="utf-8"))
    cv = meta["cv"]
    st = []
    st += cover()

    # 1
    st += [P("1. Qisqacha mazmun", "h1"),
           P("Homilador ayollar va chaqaloqlar salomatligi tuman darajasida real vaqtda monitoring qilinmaydi: "
             "tahlillar yomonlashsa, OvaBMU mutaxassislari kech xabar topadi, yuqori xavfli holatlar oʻz vaqtida "
             "aniqlanmaydi. <b>PeriZone</b> — har bir homilador ayol va chaqaloqni "
             "<font color='#d32f2f'><b>Qizil</b></font>, <font color='#b7791f'><b>Sariq</b></font> yoki "
             "<font color='#2e7d4f'><b>Yashil</b></font> zonaga joylashtiruvchi registr. Zona har bir yangi "
             "oʻlchovdan keyin qayta hisoblanadi; holat yomonlashsa, masʼul mutaxassisga avtomatik xabar boradi. "
             "Hech kim javob bermasa, xabarnoma bosh shifokorga, soʻngra viloyat darajasiga eskalatsiya qilinadi."),
           P("Prototip bugun nimalarni qila oladi:", "h2")]
    st += B([
        "Homilador ayollar va chaqaloqlarni anamnez xavf omillari bilan roʻyxatga olish; yosh, kam vazn va chala tugʻilish avtomatik aniqlanadi.",
        "Maʼlumotni uch manbadan qabul qilish: ayolning oʻzi (Telegram bot yoki mobil veb-sahifa), patronaj hamshirasi yoki klinika, laboratoriya. Har bir qiymat oʻz manbasini saqlaydi.",
        "Shifokorlar tahrir qila oladigan, shaffof qoidalar mexanizmi orqali zona belgilash: chegara qiymatlar, JSST xavf belgilari, xavfli kombinatsiyalar (preeklampsiya, sepsis), yomonlashish trendlari, xavf omillari va bir nechta sariq koʻrsatkich qizilga aylanadigan MEOWS qoidasi.",
        "Avtomatik xabarnoma: amal tugmalari bilan Telegram, SMS (zaxira kanal, hozircha namuna) va jonli boshqaruv paneli. Takroriy xabarlar birlashtiriladi, javob boʻlmasa eskalatsiya qilinadi, toʻliq audit jurnali yuritiladi.",
        "Har bir oʻzi kiritgan maʼlumotdan keyin ayolga darhol xavfsizlik maslahati berish; xavf belgisi boʻlsa — «103 ga qoʻngʻiroq qiling».",
        "Maʼlumot yubormay qoʻygan sariq va qizil zonadagi bemorlar uchun ogohlantirish yaratish.",
        "Qoidalar ustiga maslahat beruvchi ML xavf bahosini qoʻshish (UCI Maternal Health Risk maʼlumotlarida oʻqitilgan Random Forest).",
        "Modellarni mahalliy maʼlumotlarda qayta oʻqitish uchun natija yorliqlari bilan anonimlashtirilgan maʼlumotlar toʻplamini eksport qilish.",
    ])
    st += [P("<b>Asosiy xulosa:</b> ayolning oʻzi kiritgan maʼlumot <i>foydali</i>, lekin yagona manba sifatida emas, "
             "balki tizimning bir qatlami sifatida. Faqat ayolning oʻzi biladigan xavf belgilarini u oʻzi xabar qiladi; "
             "oʻzi oʻlchagan koʻrsatkichlar tekshiruvni boshlab beradi, klinika yoki laboratoriya esa ularni tasdiqlaydi. "
             "Dalillar 5-boʻlimda keltirilgan.", "callout")]

    # 2
    st += [P("2. Muammo va dalillar", "h1"),
           table([["Fakt", "Manba"],
                  ["Onalar oʻlimi 100 000 tirik tugʻilishga 38 tadan 30 taga kamaydi (2010–2020), lekin Yevropa va Markaziy Osiyo oʻrtacha koʻrsatkichidan hali ham yuqori.", "Gazeta.uz / OTB (ADB)"],
                  ["Soʻnggi oʻn yilda onalar oʻlimining 69 foizi qon ketish, eklampsiya va sepsis sabab boʻlgan — bularning odatda erta ogohlantiruvchi belgilari boʻladi.", "BMTTD «Vision 2030» dasturi hujjati"],
                  ["2024-yilgi UNFPA/UNICEF baholashiga koʻra, 230 ta perinatal oʻlimni oʻz vaqtida koʻrsatilgan yordam bilan oldini olish mumkin edi.", "UNFPA mamlakat dasturi (2025)"],
                  ["OTB 100 mln dollarlik perinatal kreditni maʼqulladi (2025-yil oktabr): xavfni erta aniqlash uchun elektron bemor kartalari va kuchliroq yoʻllanma tizimi moliyalashtiriladi.", "Kun.uz, Tashkent Times"],
                  ["Yagona elektron tibbiy tizim DMED 36 mln dan ortiq fuqaroni qamrab olgan; Raqamli sogʻliqni saqlash platformasi FHIR R5 integratsiya qoʻllanmalarini eʼlon qilgan.", "Yuz.uz, DHP FHIR IG"]],
                 [W - 4.4 * cm, 4.4 * cm]),
           Spacer(1, 8),
           P("<b>Taqdimot uchun ahamiyati:</b> davlat xavfni elektron kartalar orqali erta aniqlashni allaqachon "
             "moliyalashtirmoqda. PeriZone aynan shuning ishlaydigan prototipi boʻlib, maʼlumotlar modeli DMED bilan "
             "FHIR orqali ulanishga moslashtirilgan.", "callout")]
    st += [KeepTogether([P("Klinik asos", "h2")] + B([
        "<b>MEOWS</b> (akusherlikda erta ogohlantirish shkalasi): har bir hayotiy koʻrsatkich uchun yashil, sariq va qizil oraliqlar; bitta qizil yoki ikki va undan ortiq sariq koʻrsatkich shoshilinch koʻrikni talab qiladi.",
        "<b>NEWTT2</b> (Buyuk Britaniyaning chaqaloqlar uchun erta ogohlantirish jadvali): chaqaloq koʻrsatkichlarini kuzatadi va xavf guruhidagi chaqaloqlarni (sepsis xavfi, past Apgar, gipoglikemiya) eskalatsiya qiladi.",
        "<b>JSST xavf belgilari</b> (homiladorlik va chaqaloqlar, IMCI): qon ketish, tutqanoq, kuchli bosh ogʻrigʻi, homila harakatining kamayishi; chaqaloqlarda — emmaslik, tez nafas (daqiqasiga 60 dan ortiq), koʻkrak qafasining ichga tortilishi, holsizlik.",
        "<b>Oʻxshash tizimlar:</b> Falastinning DHIS2 asosidagi ona va bola elektron registri (2016-yildan) shifokorlarga real vaqtda ogohlantirish beradi va xavf omili bor ayollarga SMS yuboradi.",
    ]))]
    st.append(Spacer(1, 10))

    # 3
    st += [P("3. Yechim va arxitektura", "h1"),
           P("Har qanday manbadan kelgan har bir yangi maʼlumot bir xil yoʻldan oʻtadi: u kuzatuv (Observation) "
             "sifatida saqlanadi, bemor qayta baholanadi, zona yomonlashsa (yoki yangi xavf belgisi paydo boʻlsa) "
             "xabarnoma yaratiladi va masʼul shaxslarga yuboriladi."),
           architecture(),
           P("1-rasm. Maʼlumot oqimi: manbalar → kuzatuv → qoidalar + ML → zona → xabarnoma va eskalatsiya; qayta oʻqitish uchun eksport.", "caption"),
           P("Foydalanuvchilar va rollar", "h2"),
           table([["Rol", "PeriZone tizimida nima qiladi"],
                  ["Homilador ayol / yosh ona", "Telegram botda telefonini ulaydi; har kuni xavf belgilari roʻyxatini va uyda oʻlchagan koʻrsatkichlarni (qon bosimi, harorat, qand, vazn) yuboradi; darhol maslahat va eslatmalar oladi."],
                  ["Patronaj hamshirasi / oilaviy shifokor", "Bemorlarni roʻyxatga oladi, klinik va laboratoriya oʻlchovlarini kiritadi, xavf omillari va natijalarni qayd etadi."],
                  ["OvaBMU tuman mutaxassisi", "Jonli panelni kuzatadi; xabarnomalarni oladi (Telegram + panel); ularni qabul qiladi va amallarni qayd etadi: qoʻngʻiroq, patronaj, yoʻllanma, xavf yoʻq."],
                  ["Tuman bosh shifokori", "Belgilangan vaqtda javob berilmagan xabarnomalarni oladi (1-daraja)."],
                  ["Viloyat perinatal markazi", "2-daraja eskalatsiyalarni oladi; tumanlar kesimidagi taqqoslash va javob vaqti koʻrsatkichlarini koʻradi."]],
                 [4.8 * cm, W - 4.8 * cm])]
    st.append(Spacer(1, 12))

    # 4
    st += [P("4. Imkoniyatlar batafsil", "h1"), P("4.1 Rangli zonalar qoidalar mexanizmi", "h2"),
           P("Python’da yozilgan mexanizm (<font face='Mono'>backend/app/rules/engine.py</font>) klinik qoidalarni "
             "YAML fayllardan oʻqiydi — shifokorlar ularni kodga tegmasdan koʻrib chiqishi va tahrirlashi mumkin. "
             "Zona quyidagilarning <b>eng yomoni</b> boʻyicha aniqlanadi:")]
    st += B([
        "<b>Koʻrsatkich chegaralari</b>: har bir oʻlchovning eng soʻnggi <i>dolzarb</i> qiymati (qon bosimi, yurak urishi, harorat, SpO2, nafas soni, gemoglobin, glyukoza, proteinuriya). Eski qiymatlar eskiradi (masalan, qon bosimi 14 kundan, gemoglobin 45 kundan keyin).",
        "<b>Xavf belgilari</b>: soʻnggi 72 soat ichida xabar qilingan belgilar (onalar uchun 13 ta, chaqaloqlar uchun 12 ta).",
        "<b>Kombinatsiyalar</b>: gipertenziya + proteinuriya yoki + bosh ogʻrigʻi / koʻrish buzilishi / shish → preeklampsiya (qizil); isitma + taxikardiya → sepsis (qizil); chaqaloqda tez nafas + holsizlik / emmaslik → neonatal sepsis.",
        "<b>Yomonlashish trendlari</b>: 21 kun ichida qon bosimining 15 mmHg va undan koʻp oshishi, gemoglobinning 15 g/L ga tushishi, tez vazn ortishi; chaqaloqda vazn yoʻqotish. Trendlar oʻrtacha qiymatlarni solishtiradi, shuning uchun uyda oʻlchangan bitta notoʻgʻri qiymat ularni ishga tushirmaydi.",
        "<b>Xavf omillari boʻyicha minimal zona</b>: masalan, egizak homila, oldin kesar kesish, surunkali gipertenziya → kamida sariq; juda kam vazn (&lt;1500 g) yoki juda chala tugʻilish (&lt;32 hafta) → qizil.",
        "<b>MEOWS jamlash qoidasi</b>: bir vaqtda 3 ta sariq koʻrsatkich → qizil (chaqaloqlarda 2 ta, chunki ularning ahvoli tezroq yomonlashadi).",
    ])
    st += [P("Har bir topilma shifokorga turi, maʼlumot manbasi va vaqti bilan koʻrsatiladi. Shu sababli tizim "
             "tushunarli: mutaxassis ayol <i>nima uchun</i> qizil zonada ekanini doim koʻradi.")]

    hdr = ["Koʻrsatkich (ona)", "Qizil", "Sariq", "Yashil"]
    st += [Spacer(1, 4), table([hdr,
        ["Sistolik bosim (mmHg)", "≥160 yoki &lt;90", "140–159 yoki 90–99", "100–139"],
        ["Diastolik bosim (mmHg)", "≥110", "90–109", "&lt;90"],
        ["Yurak urishi (daq.)", "≥120 yoki &lt;50", "100–119", "50–99"],
        ["Harorat (°C)", "≥38,5 yoki &lt;35", "37,6–38,4", "35–37,5"],
        ["SpO2 (%)", "&lt;94", "94–95", "≥96"],
        ["Gemoglobin (g/L)", "&lt;70", "70–99", "≥100"],
        ["Och qoringa glyukoza (mmol/L)", "≥11,1 yoki &lt;3,0", "5,1–11,0", "3,0–5,0"],
        ["Siydikda oqsil (test-poloska)", "≥2+", "1+", "manfiy / iz"],
        ["Xavf belgilari", "qon ketish, tutqanoq, qorinda kuchli ogʻriq, homila harakati kamayishi, qogʻonoq suvi ketishi, nafas qisishi",
         "kuchli bosh ogʻrigʻi, koʻz oldi xiralashishi, yuz/qoʻl shishi, isitma, siyishda ogʻriq, qusish, tushkunlik", "yoʻq"],
    ], [4.2 * cm, 4.5 * cm, 4.5 * cm, W - 13.2 * cm]),
        P("1-jadval. Onalar uchun chegaralar (namunaviy qiymatlar; fayl: backend/app/rules/maternal.yaml).", "caption"),
        KeepTogether([table([["Koʻrsatkich (chaqaloq, 0–28 kun)", "Qizil", "Sariq"],
               ["Harorat (°C)", "≥38,0 yoki &lt;35,5", "37,6–37,9 yoki 35,5–36,4"],
               ["Yurak urishi (daq.)", "≥180 yoki &lt;100", "160–179 yoki 100–109"],
               ["Nafas soni (daq.)", "≥60 yoki &lt;30", "50–59"],
               ["SpO2 (%) / glyukoza (mmol/L)", "&lt;92 / &lt;2,0", "92–94 / 2,0–2,5"],
               ["Xavf belgilari", "emmaslik, tutqanoq, holsizlik, tez nafas, koʻkrak qafasi ichga tortilishi, koʻkarish, erta sariqlik",
                "sariqlik, kindik qizarishi, qusish, ich ketishi, terida yiringli toshmalar"],
               ["Tugʻilish maʼlumotlari (avtomatik)", "&lt;1500 g, &lt;32 hafta", "&lt;2500 g, &lt;37 hafta, Apgar(5) &lt;7"]],
              [5.2 * cm, (W - 5.2 * cm) / 2, (W - 5.2 * cm) / 2]),
        P("2-jadval. Chaqaloqlar uchun chegaralar (fayl: backend/app/rules/newborn.yaml).", "caption")])]

    st += [P("4.2 Ayollarning oʻzi maʼlumot kiritishi", "h2")]
    st += B([
        "<b>Telegram bot</b>: /start → kontaktni yuborish (faqat oʻz raqami qabul qilinadi) → registrdagi yozuv(lar)iga ulanadi. Bitta telefonni ishlatadigan ona va chaqaloq ikkalasi ham ulanadi, bot esa maʼlumot kim uchun ekanini soʻraydi.",
        "<b>Bir bosishda xavf belgilari roʻyxati</b> (belgilanadigan tugmalar), shuningdek qon bosimi («120/80»), harorat, qand va vaznni kiritish tugmalari; kiritilgan qiymatlar tekshiriladi.",
        "<b>Mobil veb-sahifa</b> («Ona ilovasi») — brauzerni afzal koʻrgan ayollar uchun xuddi shu jarayon.",
        "<b>Darhol maslahat</b>: xavf belgisi boʻlsa — «Hoziroq 103 ga qoʻngʻiroq qiling yoki eng yaqin tugʻruq kompleksiga boring — mutaxassisingizga xabar yuborildi»; sariq boʻlsa — «Mutaxassis siz bilan bogʻlanadi»; yashil boʻlsa — minnatdorchilik va kuzatishni davom ettirish haqida eslatma.",
        "<b>Tasdiqlash halqasi</b>: faqat oʻzi kiritgan qiymatlar sabab boʻlgan qizil zona <i>verify_self_report</i> xabarnomasini yaratadi. Hamshiraning klinik oʻlchovi uni tasdiqlasa, bu audit jurnalida qayd etiladi.",
    ])
    st += [P("4.3 Xabarnomalar va eskalatsiya", "h2")]
    st += [table([["Xabarnoma turi", "Qachon yaratiladi"],
                  ["danger_sign", "Ayol yoki hamshira qizil xavf belgisini xabar qilganda; har doim yuboriladi, birlashtirilmaydi."],
                  ["verify_self_report", "Zona faqat oʻzi kiritgan qiymatlar sabab qizil boʻlganda: tekshirish uchun qoʻngʻiroq yoki uyga borish."],
                  ["zone_worsened", "Zona yomonlashganda (yashil→sariq, sariq→qizil…) yoki yangi qizil koʻrsatkich kelganda."],
                  ["missed_checkin", "Sariq yoki qizil zonadagi bemor belgilangan muddatda maʼlumot yubormaganda (sariq — 7 kun, qizil — 2 kun)."]],
                 [4.0 * cm, W - 4.0 * cm]), Spacer(1, 6)]
    st += B([
        "<b>Yoʻnaltirish</b>: 0-daraja → bemor tumanidagi OvaBMU mutaxassisi; 1-daraja → tuman bosh shifokori; 2-daraja → viloyat perinatal markazi.",
        "<b>Eskalatsiya taymerlari</b> qabul qilinmagan qizil xabarnomalar uchun (demo: 90 / 180 soniya; amalda masalan 30 / 60 daqiqa, ESCALATION_SECONDS orqali sozlanadi).",
        "<b>Amallar</b> Telegram tugmalari yoki paneldan: qabul qildim, qoʻngʻiroq qildim, patronaj, perinatal markazga yoʻllanma, tez yordam, tekshirildi — xavf yoʻq. Yoʻllanma yoki «xavf yoʻq» xabarnomani yopadi.",
        "<b>Ortiqcha xabarlarning oldini olish</b>: har bir bemor va muammo turi uchun bitta ochiq xabarnoma, MEOWS jamlash qoidasi, trendlarni tekislash va qizil xabarnomalarni birinchi koʻrsatish — maʼlumot kelmayotgani haqidagi ogohlantirishlar shoshilinch holatlarni hech qachon yashirmaydi.",
        "<b>Audit jurnali</b> har bir xabarnoma uchun: yaratildi, yuborildi (kimga, qaysi kanal orqali), eskalatsiya qilindi, qabul qilindi, amal, yopildi. Bu maʼlumotlar javob vaqti koʻrsatkichlarini hisoblash imkonini beradi.",
    ])
    st += [P("4.4 Boshqaruv paneli va registr (mutaxassislar uchun)", "h2")]
    st += B([
        "<b>Jonli monitoring paneli</b> (har 5 soniyada yangilanadi): onalar va chaqaloqlar boʻyicha qizil/sariq/yashil soni, ochiq va eskalatsiya qilingan xabarnomalar, oʻrtacha javob vaqti.",
        "<b>Diqqat talab qiluvchi bemorlar roʻyxati</b> zona va bemor turi boʻyicha filtrlanadi, har bir bemor uchun asosiy sabablar koʻrsatiladi.",
        "<b>Xarita</b> (Leaflet/OpenStreetMap) rangli belgilar bilan va <b>tumanlar kesimidagi</b> taqqoslash diagrammasi.",
        "<b>Xabarnomalar lentasi</b> bir bosishli amallar bilan, yangi qizil xabarnoma uchun ovozli va ekran ogohlantirishi, audit uchun foydalanuvchi ismi.",
        "<b>Registr</b>: ism yoki telefon boʻyicha qidiruv, filtrlar, yangi ona va chaqaloqlarni roʻyxatga olish.",
        "<b>Bemor kartasi</b>: «Nima uchun qizil zona?» izohi, qon bosimi / gemoglobin / glyukoza (chaqaloqda harorat, nafas va vazn) grafiklari (oʻzi kiritgan nuqtalar alohida belgilanadi), manba belgisi bilan toʻliq kuzatuvlar tarixi, yangi klinik oʻlchov kiritish, xavf omillarini tahrirlash, natija yorligʻi va xabarnomalar audit tarixi.",
        "<b>«Qoidalar va ML» sahifasi</b>: YAML fayldagi barcha chegaralar, ML koʻrsatkichlari, maʼlumotlarni eksport qilish, xodimlarning Telegram ulash kodlari.",
    ])
    st.append(PageBreak())

    # Screenshots
    st += [P("Ekran tasvirlari", "h1")]
    st += screenshot("dash.png", "2-rasm. Monitoring paneli: zonalar koʻrsatkichlari, diqqat talab qiluvchi bemorlar, amallar bilan xabarnomalar lentasi, xarita va tumanlar kesimi.")
    st.append(PageBreak())
    st += screenshot("patient.png", "3-rasm. Bemor kartasi: zona sabablari (maʼlumot manbasi bilan), ML bahosi, qon bosimi va gemoglobin/glyukoza trendlari, kuzatuvlar tarixi.")
    st.append(PageBreak())
    st += screenshot("registry.png", "4-rasm. Qidiruv va filtrlarga ega registr.", max_h=11 * cm)
    st += screenshot("rules.png", "5-rasm. «Qoidalar va ML» sahifasi — shaffof chegaralar, model koʻrsatkichlari, eksport, xodimlar kodlari.", max_h=11 * cm)
    st.append(PageBreak())

    # 5
    st += [P("5. Ayolning oʻzi kiritgan maʼlumoti samaralimi?", "h1"),
           P("<b>Qisqa javob: ha — gibrid tizimning bir qatlami sifatida, yagona manba sifatida emas.</b>", "callout"),
           table([["Dalil", "Natija", "Biz nima qildik"],
                  ["BUMP 1 va 2 randomizatsiyalangan tadqiqotlari (JAMA 2022, Buyuk Britaniya)", "Uyda qon bosimini oʻzi oʻlchash oʻz-oʻzidan gipertenziyani erta aniqlamadi va nazoratni yaxshilamadi. Lekin xavfsiz edi va gipertenziya rivojlangan ayollarning yarmidan koʻpida klinik tashxisdan taxminan bir oy oldin uyda yuqori qiymat qayd etilgan.",
                   "Signal bor edi, lekin unga hech kim javob bermagan — PeriZone uni avtomatik yoʻnaltiradi va eskalatsiya qiladi."],
                  ["Uyda oʻlchash aniqligi boʻyicha tadqiqotlar", "Tasdiqlangan qurilmalarda uyda oʻlchangan qon bosimi va vazn klinika natijalariga yaqin; zaif tomoni — muntazamlik (haftasiga ~1–1,5 marta).",
                   "Telegramda bir bosishli jarayon, eslatmalar, maʼlumot kelmaganda ogohlantirish; oʻzi kiritgan qiymatlar tekshiruvni boshlaydi."],
                  ["Past va oʻrta daromadli mamlakatlarda mHealth meta-tahlili", "mHealth tibbiyot muassasasida tugʻishni (OR 2,21), tugʻruqdan keyingi yordamni va xavf belgilarini bilishni yaxshiladi; dalillar sifati turlicha.",
                   "Xavf belgilari roʻyxati bir vaqtda taʼlim vositasi; har bir xabardan keyin darhol maslahat."]],
                 [3.8 * cm, 6.9 * cm, W - 10.7 * cm]),
           Spacer(1, 8), P("Dalillardan kelib chiqqan dizayn qoidalari", "h2")]
    st += B([
        "Oʻzi kiritish <b>belgilar</b> uchun eng kuchli: qon ketayotganini yoki boshi ogʻrayotganini hozir faqat ayolning oʻzi biladi.",
        "Oʻzi oʻlchagan hayotiy koʻrsatkichlar <b>tekshiruvni boshlaydi</b>, tashxis qoʻymaydi. Har bir kuzatuv manbasini saqlaydi, xabarnomalar esa qiymat oʻzi kiritilganmi yoki yoʻqligini koʻrsatadi.",
        "Klinika va laboratoriya maʼlumotlari asosiy tayanch boʻlib qoladi; keyinchalik ular DMED’dan avtomatik keladi, hamshiralar bir xil maʼlumotni ikki marta kiritmaydi.",
        "Manba <b>ML uchun ham belgi</b>: kelajakdagi modellar har bir manbaga qanchalik ishonish kerakligini oʻrganishi mumkin.",
    ])

    # 6
    st += [P("6. Mashinali oʻqitish (ML)", "h1"),
           P(f"<b>Boshlangʻich maʼlumotlar:</b> UCI Maternal Health Risk (Bangladeshning qishloq klinikalari): {meta['dataset']['rows_raw']} ta qator; "
             "belgilar: yosh, sistolik va diastolik bosim, qondagi qand, tana harorati, yurak urishi; yorliq — past/oʻrta/yuqori xavf. "
             f"<b>Faqat {meta['dataset']['rows_unique']} ta qator takrorlanmaydi.</b> Koʻplab ochiq loyihalar 85–90% aniqlik haqida xabar beradi, chunki "
             "bir xil qatorlar ham oʻqitish, ham test toʻplamiga tushib qolgan. Biz takrorlarni olib tashladik va 5 qismli stratifikatsiyalangan kross-validatsiyadan foydalandik:"),
           table([["Model", "Macro F1", "Yuqori xavfni topish (recall)", "Tanlangan"]] +
                 [[k, f"{v['macro_f1']:.2f}".replace(".", ","), f"{v['high_risk_recall']:.0%}", "Ha" if k == meta["model_name"] else ""]
                  for k, v in cv.items()], [5.5 * cm, 3.0 * cm, 5.0 * cm, W - 13.5 * cm]),
           P("3-jadval. Halol kross-validatsiya natijalari. Model birinchi navbatda yuqori xavfni topish koʻrsatkichi boʻyicha tanlangan, chunki yuqori xavfli ayolni oʻtkazib yuborish eng qimmat xato.", "caption"),
           P("ML qanday xavfsiz ishlatiladi", "h2")]
    st += B([
        "ML faqat <b>maslahat beradi</b>: yuqori xavf ehtimoli ≥ 0,6 boʻlsa, yashil bemorni sariqqa koʻtarishi mumkin («unga ertaroq qarang»). U hech qachon qizil xabarnoma yaratmaydi va zonani pasaytirmaydi. Qoidalar xavfsizlik toʻri boʻlib qoladi.",
        "Yetishmayotgan qiymatlar meʼyoriy qiymatlar bilan toʻldiriladi, bemor kartasida qaysilari toʻldirilgani koʻrsatiladi.",
        "Model faqat onalar uchun ishlaydi; chaqaloqlar uchun faqat qoidalar qoʻllanadi.",
    ])
    st += [P("Mahalliy modellar sari yoʻl xaritasi", "h2")]
    st += B([
        "Registr har bir kuzatuv uchun bitta anonimlashtirilgan qator eksport qiladi (<font face='Mono'>/api/export/ml-dataset.csv</font>): bemor maʼlumotlari, barcha oʻlchovlar, 25 ta belgi, maʼlumot manbasi, joriy zona va <b>natija yorligʻi</b> (preeklampsiya, eklampsiya, qon ketish, muddatidan oldin tugʻruq, oʻlik tugʻilish, reanimatsiya va h.k.).",
        "6–12 oylik mahalliy maʼlumotdan soʻng: vaqt qatori belgilariga (qon bosimi va gemoglobin oʻzgarish tezligi, belgilar chastotasi, maʼlumot yuborish muntazamligi) asoslangan natijani bashorat qiluvchi modellar (masalan, gradient boosting).",
        "Prospektiv validatsiya, ehtimollarni kalibrlash, tumanlar boʻyicha model barqarorligini kuzatish va ML zonalarga koʻproq taʼsir qilishidan oldin shifokorlar tomonidan koʻrib chiqish.",
    ])
    st.append(PageBreak())

    # 7
    st += [P("7. Texnik amalga oshirish", "h1"),
           table([["Qatlam", "Texnologiya", "Izoh"],
                  ["Backend API", "Python, FastAPI, Pydantic", "REST API va /docs manzilida OpenAPI hujjatlari; fiziologik oraliqlar boʻyicha kiritishni tekshirish."],
                  ["Maʼlumotlar bazasi", "SQLAlchemy 2, SQLite (PostgreSQL’ga tayyor)", "Modellar FHIR’ga mos: Patient, Observation, RiskAssessment (Assessment), Flag/Communication (Alert, AlertEvent)."],
                  ["Qoidalar", "YAML + Python mexanizmi", "Maʼlumotlar bazasiga bogʻliq emas; testlar bilan qoplangan; chegaralar versiyalanadi."],
                  ["Rejalashtiruvchi", "asyncio fon vazifasi", "Har 10 soniyada: eskalatsiyalar va maʼlumot kelmayotgani tekshiruvi."],
                  ["Xabar yuborish", "Telegram Bot API (httpx, long polling)", "Qoʻshimcha bot kutubxonasisiz; Eskiz / Play Mobile uchun SMS shlyuzi namunasi tayyor."],
                  ["ML", "scikit-learn, joblib", "Random Forest; halol baholash bilan oʻqitish skripti."],
                  ["Frontend", "HTML, JavaScript, Chart.js, Leaflet", "FastAPI orqali beriladi; yorugʻ/qorongʻi mavzu; oʻzbek (lotin) interfeysi; mobilga mos ona sahifasi."]],
                 [3.0 * cm, 5.2 * cm, W - 8.2 * cm]),
           P("Asosiy API manzillari", "h2"),
           table([["Manzil", "Vazifasi"],
                  ["GET /api/dashboard", "Zonalar soni, ochiq va eskalatsiya qilingan xabarnomalar, javob vaqti, tumanlar kesimi"],
                  ["GET / POST /api/patients", "Filtrli roʻyxat / ona yoki chaqaloqni roʻyxatga olish"],
                  ["GET / PATCH /api/patients/{id}", "Sabablar, tarix va xabarnomalar bilan toʻliq karta / xavf omillari va natijani tahrirlash"],
                  ["POST /api/patients/{id}/observations", "Klinika, laboratoriya yoki qurilma oʻlchovi → qayta baholash → yomonlashsa xabarnoma"],
                  ["POST /api/self-report", "Ayolning oʻz xabari (telefon yoki ID orqali) → zona va xavfsizlik maslahati"],
                  ["GET /api/alerts, POST /api/alerts/{id}/ack | action | resolve", "Xabarnomalar lentasi va amallar (audit bilan)"],
                  ["GET /api/rules/{kind}, /api/model, /api/meta", "Qoidalar, ML koʻrsatkichlari, formalar uchun maʼlumotnomalar"],
                  ["GET /api/export/ml-dataset.csv", "Natija yorliqlari bilan anonimlashtirilgan oʻqitish toʻplami"]],
                 [7.2 * cm, W - 7.2 * cm]),
           P("Loyiha tuzilmasi", "h2"),
           P("backend/app/rules/  maternal.yaml, newborn.yaml, engine.py<br/>"
             "backend/app/services/  assessment.py, alerts.py, notify.py, telegram_bot.py, intake.py, ml.py<br/>"
             "backend/app/api/routes.py · models.py · schemas.py · main.py<br/>"
             "frontend/  index.html, patients.html, patient.html, mother.html, rules.html, assets/<br/>"
             "ml/train.py · ml/models/ · ml/data/raw/<br/>"
             "scripts/seed.py · scripts/demo_scenario.py · tests/ · docs/RESEARCH.md", "code"),
           P("Sifat", "h2")]
    st += B([
        "<b>20 ta avtomatik test</b> (barchasi muvaffaqiyatli): qoidalar mexanizmi uchun 14 ta (chegaralar, kombinatsiyalar, eskirish, trendlar va shovqinga chidamlilik, MEOWS jamlash, chaqaloqlar mantigʻi) va API jarayoni uchun 6 ta (oʻzi kiritish → xabarnoma → eskalatsiya → amal, takrorlarni birlashtirish, eksportda anonimlik, notanish telefon).",
        "Demo maʼlumotlar generatori: klinik turlarga ega 160 ta ona (meʼyoriy, gestatsion gipertenziya, preeklampsiya, anemiya, gestatsion diabet, infeksiya) va Toshkentning 5 ta tumanidagi 40 ta chaqaloq. Barcha ismlar va raqamlar toʻqima.",
        "Taxminan 3 800 qator kod va sozlamalar.",
    ])
    st.append(Spacer(1, 12))

    # 8
    st += [P("8. Ishga tushirish va namoyish", "h1"),
           P("pip install -r requirements.txt<br/>python ml/train.py<br/>python scripts/seed.py<br/>"
             "uvicorn backend.app.main:app --port 8000<br/># brauzerda: http://127.0.0.1:8000", "code"),
           P("Telegram (ixtiyoriy): @BotFather orqali bot yarating va TELEGRAM_BOT_TOKEN ni .env fayliga yozing. "
             "Mutaxassislar botga <font face='Mono'>/staff KOD</font> yuboradi (kodlar «Qoidalar va ML» sahifasida); "
             "ayollar /start bosib, kontaktini yuboradi."),
           P("Jonli taqdimot ssenariysi (scripts/demo_scenario.py)", "h2"),
           table([["Qadam", "Nima sodir boʻladi", "Tizim javobi"],
                  ["1", "Malika (32 hafta) Telegram orqali uyda oʻlchagan bosimini yuboradi: 128/82", "Yashil; «Rahmat, koʻrsatkichlaringiz meʼyorda»"],
                  ["2", "Ertasi kuni: 148/94 + kuchli bosh ogʻrigʻi (oʻzi kiritgan)", "QIZIL (preeklampsiya belgilari). Ayolga 103 ga qoʻngʻiroq qilish aytiladi; mutaxassisga «tasdiqlang» xabarnomasi boradi."],
                  ["3", "Hamshira uyga keladi: 166/112, proteinuriya 2+", "Ogʻir preeklampsiya tasdiqlandi; oʻzi kiritgan maʼlumot boʻyicha xabarnoma «tasdiqlandi» deb belgilanadi; sabablar bilan yangi xabarnoma"],
                  ["4", "Hech kim javob bermaydi", "Bosh shifokorga (90 s), soʻngra viloyatga (180 s) eskalatsiya; hammasi audit jurnalida koʻrinadi"]],
                 [1.4 * cm, 6.8 * cm, W - 8.2 * cm]),
           Spacer(1, 6), P("Yakuniy jumla: «Bugun bu xavf belgilari kunlar oʻtib aniqlanadi. PeriZone bilan esa — soniyalar ichida.»", "callout")]

    # 9
    st += [P("9. Xavflar, cheklovlar va javoblar", "h1"),
           table([["Savol / xavf", "Javob"],
                  ["Klinik masʼuliyat", "Tizim faqat qaror qabul qilishga yordam beradi: zonalar eʼtiborni yoʻnaltiradi, qarorni shifokor qabul qiladi. Chegaralar SSV/OvaBMU tomonidan tasdiqlanishi kerak; ular versiyalanadigan YAML faylda."],
                  ["Shaxsiy maʼlumotlar", "Oʻzbekistonning shaxsga doir maʼlumotlar toʻgʻrisidagi qonuni fuqarolar maʼlumotlarini Oʻzbekistondagi serverlarda saqlashni talab qiladi: mahalliy server yoki mahalliy bulut, rollarga asoslangan kirish, anonimlashtirilgan eksport."],
                  ["Ortiqcha xabarnomalar", "Takrorlarni birlashtirish, jamlash qoidasi, trendlarni tekislash, qizilni birinchi koʻrsatish; sariq zona uchun kunlik hisobot (rejada)."],
                  ["Maʼlumotni ikki marta kiritish", "2-bosqichda tahlillar va tashriflar DMED’dan olinadi (FHIR Observation), zonalar esa DMED’ga qaytariladi (RiskAssessment / Flag)."],
                  ["Smartfoni yoʻq ayollar", "Maʼlumotni hamshira kiritadi; SMS/USSD kanali va oila aʼzosining Telegrami (rejada)."],
                  ["ML xorijiy maʼlumotda oʻqitilgan", "Faqat maslahat; halol koʻrsatkichlar; mahalliy natija yorliqlari asosida qayta oʻqitish jarayoni."],
                  ["Prototipdagi kamchiliklar", "Hozircha avtorizatsiya va rollar yoʻq; SMS — namuna; demo uchun SQLite; interfeys faqat oʻzbek tilida."]],
                 [4.4 * cm, W - 4.4 * cm]),
           P("Rivojlanish rejasi", "h2"),
           table([["Bosqich", "Qamrovi"],
                  ["Xakaton (bajarildi)", "Qoidalar mexanizmi, oʻzi kiritish uchun bot va veb, eskalatsiyali xabarnomalar, panel, bemor kartasi, boshlangʻich ML, eksport, testlar, demo maʼlumotlar"],
                  ["Pilot (1 tuman, 3 oy)", "Chegaralarni klinik tasdiqlash, avtorizatsiya va rollar, haqiqiy SMS shlyuzi, rus tilidagi interfeys, mahalliy serverga oʻrnatish, xodimlarni oʻqitish"],
                  ["Integratsiya", "DMED / Raqamli sogʻliqni saqlash platformasi bilan FHIR R5 orqali ulanish, laboratoriya analizatorlari, perinatal markazga yoʻllanma jarayoni"],
                  ["Kengaytirish va ML", "Mahalliy maʼlumotda natijaga asoslangan modellar, kalibrlash va barqarorlikni kuzatish, viloyat analitikasi, USSD kanali"]],
                 [4.4 * cm, W - 4.4 * cm]),
           P("Jamoa uchun ochiq savollar", "h2")]
    st += B([
        "OvaBMU’ning aniq maʼnosi va tumandagi shtati, tunda xabarnomalarni kim qabul qiladi.",
        "Perinatal xavf guruhlari boʻyicha amaldagi SSV buyrugʻi — chegaralar va xavf omillari roʻyxatini moslashtirish uchun.",
        "Poliklinikalar DMED’ga qaysi maʼlumotlarni allaqachon kiritadi.",
        "Pilot uchun SMS shlyuziga kirish.",
    ])

    st += [P("Manbalar", "h2"),
           P("Gazeta.uz (2024) OTB perinatal yordam · Kun.uz va Tashkent Times (2025) OTBning 100 mln dollarlik krediti · BMTTD «Vision 2030 Perinatal Care» hujjati (2023) · "
             "UNFPA Oʻzbekiston mamlakat dasturi loyihasi (2025) · Euronews (2026) Oʻzbekistonda raqamli sogʻliqni saqlash · Yuz.uz (2025) yagona elektron tibbiy karta / DMED · "
             "Raqamli sogʻliqni saqlash platformasi FHIR IG (build.fhir.org) · MEOWS: medicalalgorithms.com, PMC10040990, PMC5910060, PMC7028086 · "
             "NEWTT2 SOP, NHS Scotland · DHIS2 Falastin ona va bola e-registri · BUMP 1 va 2, JAMA 2022 (PubMed 35503346; Oksford universiteti) · "
             "Uyda monitoring: PMC5135734, PMC9049804 · mHealth meta-tahlili: PMC10257264 · "
             "Preeklampsiya uchun ML: PMC12158820, JMIR 2026 e78714 · UCI Maternal Health Risk maʼlumotlar toʻplami (archive.ics.uci.edu/dataset/863). "
             "Toʻliq havolalar: docs/RESEARCH.md.", "small")]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="PeriZone — Loyiha hisoboti",
                            author="PeriZone xakaton jamoasi", subject="Perinatal yuqori xavf guruhi registri")
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    print(OUT)


if __name__ == "__main__":
    main()
