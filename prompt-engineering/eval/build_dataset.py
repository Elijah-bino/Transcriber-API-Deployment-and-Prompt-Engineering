"""Merge the 200-row eval set + the 25-row realistic set into one scored input.

Output: data/eval_set_225.csv  with columns  id,dataset,transcript,expected_shortened
  dataset in {general, personal_data_injected, realistic_messy}
Reproducible: safe to re-run.
"""
import csv
import pathlib

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
EVAL200 = DATA / "AIDE_200_row_LLM_evaluation_dataset.csv"
MESSY25 = DATA / "AIDE_training_data_with_expected_shortened.csv"
OUT = DATA / "eval_set_225.csv"


def main() -> None:
    rows = []

    with open(EVAL200, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["dataset"].strip(), r["transcript"].strip(),
                         r["expected_shortened"].strip()))

    with open(MESSY25, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(("realistic_messy", r["transcript"].strip(),
                         r["expected_shortened"].strip()))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "dataset", "transcript", "expected_shortened"])
        for i, (ds, t, e) in enumerate(rows, start=1):
            w.writerow([i, ds, t, e])

    counts: dict[str, int] = {}
    for ds, _, _ in rows:
        counts[ds] = counts.get(ds, 0) + 1
    print(f"wrote {OUT}  ({len(rows)} rows)")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
