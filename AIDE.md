# AIDE — Context Document

> **Purpose of this document:** Ground any AI assistant working on AIDE tasks. If a question is not covered here, respond with "I don't have confirmed information on that — check with Noah (CEO)" rather than guessing. Do not fabricate statistics, quotes, product features, timelines, or regulatory details.

---

## What is AIDE?

AIDE is a Melbourne-based health-tech startup building a voice-powered patient request intelligence platform for hospital wards and aged care facilities. Patients speak requests into a bedside device. AI transcribes and rephrases each request into a concise, de-identified action item displayed on a shared nurse dashboard — so staff know what a patient needs before walking to the room.

Tagline: **"Know before you go."**

AIDE handles all patient requests: urgent and non-urgent. It sits alongside existing nurse call systems as a separate channel. The long-term intent is to replace the physical call button, with the button retained as a backup.

### The core problem

The traditional nurse call button tells staff that someone pressed a button. Nothing else. A nurse walks to the room blind, with no idea whether the patient needs water, pain relief, or help to the bathroom. This creates wasted trips, delayed prioritisation, and unnecessary interruption to other tasks.

No published study has directly quantified the rate of "blind trips." Hendrich et al. (2008) provides aggregate walking-waste data as the closest legitimate proxy (~5 km per shift). The 42 km/week figure that circulates online is not robustly sourced and should not be used. The 15 km upper bound comes from a single ICU study (Nahk & Frolova, 2009) and should be cited with that caveat.

### How AIDE solves it

AIDE gives nurses pre-arrival context on every call. Before a nurse walks to the room, they see a short, AI-rephrased summary of what the patient needs — displayed on a shared ward dashboard. This eliminates the blind trip.

---

## Product

### Patient-side flow (current MVP)

1. Patient opens the AIDE web app (currently accessed via browser on a personal or hospital-provided phone — no dedicated hardware).
2. Patient taps to record and speaks their request (e.g. "hello I need to go to the toilet").
3. Sensitive clinical details are handled before the AI sees the transcript. The AI receives coded variables (e.g. U105 where "U" denotes a medication category, without identifying the specific drug). For full details on the de-identification pipeline, refer to Noah.
4. AI rephrases the raw transcript into a concise action item (e.g. "assistance requested").
5. Patient sees the rephrased version on screen.
6. Patient can cancel (re-record functionality planned for the native app, not yet in web MVP).
7. The request appears on the nurse dashboard.

### Nurse-side flow (current MVP)

The nurse dashboard shows:

- Room number (e.g. 101)
- AI-rephrased request summary (e.g. "assistance requested," "water")
- Timestamp
- Badge count of new requests (e.g. "1 new")
- "Acknowledge" button per request

When a nurse acknowledges a request, it moves to the compliance log. The compliance log shows:

- "PATIENT SAID" — the original transcript
- "AI REPHRASED" — the shortened version
- "ACKNOWLEDGED" — with total response time (e.g. 28s)

Requests are currently visible to the whole ward. A profile-picture-based "tag" system for assigning requests to individual nurses is planned. [UNSPECIFIED — for details on the tag system, refer to Noah.]

### Communication direction

Currently one-directional: patient to nurse only. Bi-directional communication (e.g. "a nurse is on your way") is under consideration. [UNSPECIFIED — refer to Noah for current status.]

### Carer/family proxy

Most likely supported (allowing a carer or family member to submit a request on behalf of a patient who cannot use the device). [UNSPECIFIED — refer to Noah for confirmed scope.]

---

## What's built vs. what's planned

### Built and functional in web MVP

- Patient voice recording and playback
- AI transcription (Web Speech API)
- AI rephrasing (cloud AI via OpenRouter / Kimi K2.5)
- Nurse dashboard with room number, rephrased request, timestamp, new-request badge
- Acknowledge button and status tracking
- Compliance log with original transcript, rephrased version, response time
- Cancel functionality (web only)

### Planned / in development

- Native app (iOS/Android) — in development
- Admin portal
- Login and authentication
- Nurse tag/assignment system (profile-picture-based)
- AI triage and batching (post-MVP) — urgency classification and grouping of related requests
- Re-record functionality (native app)
- Analytics dashboard for hospital administrators
- Bi-directional patient communication [UNSPECIFIED]
- On-premise AI inference (replacing cloud API)

---

## Tech stack

### Current (web MVP)

- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **Hosting:** Vercel
- **Database:** Upstash Redis
- **AI rephrasing:** OpenRouter (Kimi K2.5)
- **Transcription:** Web Speech API (browser-native)
- **Repo:** github.com/deltaromeomngo-create/nurse-call
- **Live MVP:** nurse-call-pi.vercel.app

### Planned (local inference)

- Ollama + Llama 3.2 3B (Q4_K_M quantisation) on Raspberry Pi 5
- Hybrid keyword classifier to reduce model invocations
- Purpose: eliminate cloud AI privacy exposure for patient data

---

## Data handling and privacy

- Sensitive clinical details are coded before AI processing. The AI never sees specific medication names, diagnoses, or identifying health information. It receives coded category variables only.
- Compliance logs store original verbatim transcripts short-term (approximately one month).
- After the retention window, logs are exported and stored locally by the hospital. AIDE's copies are then deleted.
- On-premise inference is the planned long-term architecture to avoid cloud API privacy exposure under Australian Privacy Act 1988 and Victorian Health Records Act 2001.
- Current cloud AI pipeline (OpenRouter) carries compliance risk due to logging, retention, and cross-border transfer. This is a known gap being addressed.

---

## Regulatory position

- **TGA:** The core product (voice transcription, rephrasing, dashboard display) is likely not a regulated medical device. However, AI-based clinical symptom triage (planned post-MVP) likely constitutes Class IIa Software as a Medical Device (SaMD), requiring ARTG inclusion.
- **TGA notification:** Required within 30 working days of first supply if the triage feature is active at launch.
- **Privacy:** Australian Privacy Act 1988, Victorian Health Records Act 2001, My Health Records Act 2012, OAIC guidance all apply.
- **APP 1.7:** Automated decision-making disclosure deadline is 10 December 2026.
- **Applicable standards (for triage feature):** ISO 13485, IEC 62304, ISO 14971.
- A legal documentation roadmap (26 documents across six categories) has been generated with phased sequencing.

Do not speculate on AIDE's regulatory status beyond what is stated here. For current regulatory questions, refer to Noah.

---

## Business

### Company status

- Pre-incorporation. No ABN yet.
- Approximately $800 in total funding to date.
- $0 revenue. 0 customers.
- No patent filings. IP is trade secrets and code only.

### Team (four founders)

- **Noah** — CEO and Co-Founder. Product vision, strategy, stakeholder relations.
- **Two co-founders (CTO titles)** — Full-stack development, AI integration, platform infrastructure.
- **One co-founder (CFO and Head of Brand)** — Financial planning, brand strategy, go-to-market.

Contact: aide.medtech@gmail.com

### Business model

SaaS, priced per bed per month. Specific pricing not yet determined. [UNSPECIFIED — refer to Noah.]

Secondary revenue stream planned: aggregated, de-identified analytics data licensed to hospital administrators.

### Origin

AIDE originated as "NurseCall" during a Monash Generator Startup Sprint (passed Gate 1 and Gate 2). It was rebranded to AIDE during the program.

---

## Market position

### Stakeholder groups

1. **Patients** — want their requests heard and acted on quickly.
2. **Nurses / PCAs** — want to know what a patient needs before walking to the room, reducing wasted trips and enabling prioritisation.
3. **Hospital administrators (payers)** — want operational efficiency data and reduced staff burden metrics.

### Aged care distinction

In aged care, Personal Care Assistants (PCAs) are the primary non-urgent call responders, not nurses. AIDE's value in that setting centres on giving PCAs pre-call context and surfacing clinical concerns to Registered Nurses, directly supporting care-minutes compliance.

### Competitors and adjacent systems

- **Rauland** — incumbent nurse call hardware vendor in Australian hospitals. AIDE sits alongside, not inside, Rauland systems.
- **TigerConnect** — clinical communication platform (US-focused). Messaging and workflow, not voice-to-dashboard.
- Traditional nurse call systems — undifferentiated button press with no request context.

AIDE's differentiation: the AI layer that converts a voice request into a pre-arrival action item. Existing systems transmit a signal ("someone pressed a button"). AIDE transmits meaning ("patient in room 101 needs assistance to bathroom").

### Integration strategy

AIDE currently operates as a standalone channel alongside existing nurse call systems. Integration with existing infrastructure is a future consideration, contingent on competitive moat and the cost of integration for hospitals. [UNSPECIFIED — for integration roadmap, refer to Noah.]

---

## Deployment

### Pilot plan

- Targets: Alfred Hospital (nursing leadership connection), Regis Aged Care.
- Structure: 8-12 weeks, single ward, nil cost to hospital.
- Timeline: when development is ready. No hard dates set.

### Setup

AIDE team handles room number and ward configuration, with support from volunteers and hospital IT.

### Offline / connectivity

- AIDE requires an internet connection for full functionality.
- Dead-zone handling: cache current submissions and dashboard state (nurse side), notify users of faulty connection.
- Fully offline operation is not supported.

---

## Design system

- **Colours:** Ward Green #0B3630, Alert Amber #E8914A, Resolved Teal #5AC9A8, Linen #FAF6F0
- **Typography:** DM Serif Display (headings) + Inter (body)
- **Logo:** aide-logo.png (258 x 259 px)

---

## Research sources (verified)

These are the only statistics and studies that should be cited in AIDE materials. Do not invent or extrapolate figures beyond what these sources support.

| Source | What it supports | Caveat |
|---|---|---|
| Hendrich et al., Permanente Journal, 2008 | ~5 km walked per shift; aggregate nursing time-waste data | Closest proxy for blind-trip waste. Does not directly measure blind-trip rate. |
| Nahk & Frolova, Critical Care, 2009 | Up to 15 km per shift | Single ICU study. Upper bound, not typical. |
| Tzeng, BMC Health Services Research, 2010 | Patient call light patterns and reasons | — |
| Westbrook et al., BMC Health Services Research, 2011 | Nursing task interruption data | — |
| Meade et al., AJN, 2006 | Hourly rounding reduces call light use and falls | — |
| Digby et al., Nursing Older People, 2011 | Older patient communication barriers in hospital | — |
| NCSBN, 2024 National Nursing Workforce Study | Nursing workforce demographics and burnout | — |

The 42 km/week figure is not robustly sourced. Do not use it.

---

## Content and communication standards

- Short sentences. Plain language. No excessive hedging.
- No em-dashes in any AIDE content.
- Every claim must have a cited, verifiable source. Do not fabricate or composite quotes, statistics, or case studies.
- LinkedIn content should mix formats: data/insights, opinion/contrarian, expertise/framework, and community engagement. Not every post needs to be story-based.
- Pitch materials require inline academic citations (Author et al., Year) and real nurse quotes only. No illustrative composites.

---

## What to do when you don't know

If a question touches any of the following, respond with: **"I don't have confirmed information on that. Check with Noah (CEO) at aide.medtech@gmail.com."**

- Specific pricing figures
- Pilot dates or confirmed partner commitments
- The nurse tag/assignment system design
- Bi-directional communication scope
- Carer/family proxy feature details
- Integration roadmap with existing nurse call systems
- Details of the de-identification pipeline beyond what is documented here
- Regulatory interpretations beyond what is stated in this document
- Financial projections or runway
- Any feature not listed in the "built" or "planned" sections above
- Competitor capabilities beyond what is stated here

Do not guess. Do not extrapolate. Do not fill gaps with plausible-sounding information.
