# Label Convention

Ground-truth format for every `expected_shortened` label and every model output
in the rephrasing stage. Keeps datasets consistent so exact-match scoring is fair.

## Rules

1. **2 to 5 words.**
2. **Title Case first word**, rest lowercase (labels contain no proper nouns by design).
3. **No punctuation** — no trailing period, comma, question mark.
4. **Topic first, category noun last.** "Water request", not "Requesting water".
5. **Category noun is one of a closed set:**
   | Noun | Use when the patient... | Examples |
   |---|---|---|
   | `request` | wants an item or an action delivered | Water request, Blanket request, Family contact request |
   | `assistance` | needs hands-on help, or reports a symptom / pain | Bathroom assistance, Sitting assistance, Headache assistance, Leg pain assistance |
   | `adjustment` | wants something in the room changed | Pillow adjustment, Light adjustment, Television volume adjustment |
   | `question` | asks something that needs an informational answer | Pain question, Medication dosage question, Monitor beeping question |
   | `update` | asks whether something has happened / wants a status | Doctor visit update, Family contact update, Test result update |
6. **No name, age, location, or other identifying detail** — ever, even if stated in the transcript.
7. **Compound topics allowed** when the patient genuinely states two related needs:
   "Dizziness and nausea assistance", "Blanket and pillow request". Keep within the 5-word cap.
8. **Symptoms and pain map to `assistance`**, not `question`, unless the patient is only
   asking whether it is normal ("Is this pain normal?" -> "Pain question").

## Normalization applied 2026-09-03

`AIDE_training_data_with_expected_shortened.csv` (25 rows) was the only file off-convention:

| Was | Now | Reason |
|---|---|---|
| Immediate assistance needed | Immediate assistance request | `needed` is not in the closed noun set |
| Pain medication dosage question | Medication dosage question | canon drops the redundant "pain" qualifier |
| Fresh blanket and pillow | Blanket and pillow request | had no category noun |

`AIDE_100_general_dataset.csv`, `AIDE_100_personal_data_dataset.csv`, and
`AIDE_200_row_LLM_evaluation_dataset.csv` were already clean and internally consistent
(the two 100-row files concatenate exactly into the 200-row eval set).
