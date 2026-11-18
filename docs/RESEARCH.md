# Research notes — Perinatal high-risk registry (colour-zone monitoring)

## 1. The problem in numbers (Uzbekistan)

| Fact | Source |
|---|---|
| Maternal mortality fell 38 → 30 per 100,000 live births (2010–2020), still high vs. Europe & Central Asia | [Gazeta.uz / ADB](https://gazeta.uz/en/2024/07/17/adb) |
| 69% of maternal deaths in the last decade: bleeding, eclampsia, sepsis — all have early warning signs | [UNDP Vision 2030 prodoc](https://mptf.undp.org/sites/default/files/documents/2023-09/prodoc_vision_2030_perinatal_care_signed_20230913_redacted.pdf) |
| 230 perinatal deaths judged preventable with timely care (UNFPA/UNICEF 2024 assessment) | [UNFPA country programme](https://aa.unfpa.org/sites/default/files/board-documents/main-document/DP.FPA_.CPD_.UZB_.6%20-%20Uzbekistan%20-%20DRAFT%20final%20-%202June25.pdf) |
| ADB $100M perinatal loan (Oct 2025) explicitly funds *electronic patient records to identify risks early* and a stronger referral system | [Kun.uz](https://kun.uz/en/49696907), [Tashkent Times](https://www.tashkenttimes.uz/finances/13363-adb-to-help-improve-perinatal-care-in-uzbekistan) |
| DMED unified EHR: 36M+ citizens, 20+ modules; Digital Health Platform publishes FHIR R5 integration guides | [Yuz.uz](https://yuz.uz/en/news/v-uzbekistane-sozdana-edinaya-elektronnaya-meditsinskaya-karta-naseleniya), [DHP FHIR IG](https://build.fhir.org/ig/vadi2/DHP-integrations-temp/en/) |

**Pitch line:** the government is already funding "early risk identification with electronic records" — PeriZone is a working prototype of exactly that, built to plug into DMED via FHIR.

## 2. Clinical basis for the colour zones

* **MEOWS** (Modified Early Obstetric Warning Score) — the standard maternal track-and-trigger chart. Green/yellow/red bands per vital sign; **1 red or 2+ yellow → urgent review**. Thresholds vary by hospital (consensus-based), so ours are configurable YAML. ([medicalalgorithms](https://www.medicalalgorithms.com/obstetric-early-warning-score), [PMC10040990](https://pmc.ncbi.nlm.nih.gov/articles/PMC10040990), [PMC7028086](https://pmc.ncbi.nlm.nih.gov/articles/PMC7028086))
* **NEWTT2** (BAPM newborn early warning) — scores 0/1/2 per observation, escalation by total; target groups: sepsis risk, hypoglycaemia risk, low Apgar, resuscitation. ([NHS Scotland SOP](https://www.rightdecisions.scot.nhs.uk/shared-content/ggc-women-and-children/neonatology/sop-for-implementation-of-neonatal-early-warning-track-trigger-newtt2-in-rah))
* **WHO danger signs** (pregnancy & young infant/IMCI) — bleeding, convulsions, severe headache/blurred vision, fever, reduced fetal movement; newborn: not feeding, convulsions, fast breathing ≥60, chest indrawing, lethargy, temperature instability.
* **Similar systems:** Palestine's MCH e-Registry on DHIS2 (since 2016) gives clinicians real-time decision-support alerts and sends targeted SMS to women with risk factors. ([DHIS2](https://dhis2.org/palestine-tracker-user-story/))

## 3. Is self-reported data from women effective? — **Yes, as one layer, not alone**

### What the evidence says
* **BUMP 1 & 2 RCTs (JAMA 2022, UK, ~3,000 women):** home BP self-monitoring + telemonitoring did **not** detect hypertension earlier or control it better than usual care *on its own*. But: it was **safe**, and **>50% of women who developed hypertension had a raised home reading ~1 month before clinic diagnosis** — the signal is there, the problem was that nobody acted on it automatically. ([Oxford](https://www.ox.ac.uk/news/2022-05-03-neither-detection-nor-control-high-blood-pressure-improved-self-monitoring-during), [PubMed](https://pubmed.ncbi.nlm.nih.gov/35503346/))
* **Accuracy:** home BP and weight readings agree closely with clinic readings when validated devices are used; adherence is the weak point (≈1–1.5 readings/week in a 6-month study). ([PMC5135734](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5135734/), [PMC9049804](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9049804/))
* **mHealth in low/middle-income countries:** meta-analysis of RCTs — mHealth improved facility delivery (OR 2.21), postnatal care uptake and **knowledge of obstetric danger signs**. Evidence quality is mixed; ~43% of older studies negative/unclear. ([PMC10257264](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10257264/), [PMC8830260](https://pmc.ncbi.nlm.nih.gov/articles/PMC8830260))

### Design conclusions (implemented in PeriZone)
1. **Self-report is best for symptoms (danger signs)** — only the woman knows she is bleeding or has a headache *right now*. Danger signs trigger an immediate alert + "call 103" advice.
2. **Self-reported vitals are a trigger for verification, not a diagnosis.** Every observation carries `source` (self/clinic/lab/device). A red zone driven only by self-reported values creates a `verify_self_report` alert ("send nurse / call her"); a clinic reading then confirms it and closes the loop.
3. **BUMP failed because data wasn't acted on** → our core value is the *automatic routing + escalation* (specialist → head physician → region, with acknowledgement timers and an audit log).
4. **Adherence is the weak point** → Telegram (already on everyone's phone), one-tap checklist, reminders, and *missed check-in alerts* for yellow/red women.
5. **Hybrid data** — clinic + lab data from nurses (and later DMED/analyser integration) + self-report. That's also what makes the ML dataset trustworthy: `source` is a feature, and models can learn how much to trust each source.

## 4. ML — what is realistic

* Literature: preeclampsia/risk ML models commonly use **age, parity, BMI, diabetes, hypertension, BP**; ML tends to beat logistic regression but evidence is mostly retrospective and interpretability matters. ([PMC12158820](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12158820/), [JMIR 2026 meta-analysis](https://www.jmir.org/2026/1/e78714/PDF))
* **Baseline model in this repo:** UCI *Maternal Health Risk* dataset (1,012 rows, Bangladesh; age, BP, glucose, temperature, heart rate → low/mid/high). **Only 451 rows are unique** — many public notebooks report 85–90% accuracy because duplicates leak into the test set. Honest 5-fold CV on de-duplicated rows: **random forest macro-F1 0.60, high-risk recall 0.77**.
* **Therefore:** ML is *advisory* (can raise green → yellow, never creates red, never lowers a zone). Rules are the safety net.
* **Roadmap:** the registry exports a pseudonymised per-observation dataset with **outcome labels** (preeclampsia, preterm birth, haemorrhage, NICU…) → after 6–12 months of local data, train outcome-prediction models (e.g. gradient boosting on time-series features: BP slope, Hb slope, symptom frequency, adherence), validate prospectively, calibrate, and monitor drift per district.

## 5. Risks & answers for judges

| Question | Answer |
|---|---|
| Who is responsible for decisions? | Decision *support*: zones and alerts route attention; doctors decide. Thresholds must be approved by MoH/OvaBMU specialists (YAML, versioned). |
| Personal data? | Uzbek personal-data law requires citizens' data to be stored on servers in Uzbekistan → on-prem/local cloud deployment, role-based access, export is pseudonymised. |
| Alert fatigue? | De-duplication (one open alert per problem), MEOWS aggregation, trend logic instead of single noisy points, red-first feed, daily digest for yellow (roadmap). |
| Double data entry for nurses? | Phase 2: pull labs and visits from DMED (FHIR Observation), push zones back as FHIR RiskAssessment/Flag. |
| Women without smartphones? | Patronage nurse enters data; SMS/USSD channel (roadmap); family member's Telegram. |
| Is self-report reliable? | See §3: used for danger signs + triggering verification; source is tracked everywhere. |

## 6. Open questions for the team / mentors
1. Exact meaning and staffing of **OvaBMU** at district level — who is on call at night?
2. Current MoH order on perinatal risk groups (to align YAML thresholds and risk-factor list).
3. Which data the polyclinic already enters into DMED (to avoid duplicate entry).
4. SMS gateway access (Eskiz / Play Mobile) for the pilot.
