"""Check every label file against LABEL_CONVENTION.md. Run before any eval."""
import csv
import pathlib

DATA = pathlib.Path(__file__).parent / "data"
CATEGORY_NOUNS = {"request", "assistance", "adjustment", "question", "update"}

FILES = [
    "AIDE_100_general_dataset.csv",
    "AIDE_100_personal_data_dataset.csv",
    "AIDE_200_row_LLM_evaluation_dataset.csv",
    "AIDE_training_data_with_expected_shortened.csv",
]


def problems(label: str) -> list[str]:
    out = []
    words = label.split()
    if not (2 <= len(words) <= 5):
        out.append(f"wordcount={len(words)}")
    if label != label[0].upper() + label[1:]:
        out.append("not-Titlecase-first")
    if any(c in label for c in ".,!?;:"):
        out.append("punctuation")
    if words and words[-1].lower() not in CATEGORY_NOUNS:
        out.append(f"end='{words[-1]}'")
    return out


def main() -> int:
    bad = 0
    for name in FILES:
        rows = list(csv.DictReader(open(DATA / name, newline="", encoding="utf-8")))
        viol = [(r["transcript"], r["expected_shortened"], problems(r["expected_shortened"]))
                for r in rows if problems(r["expected_shortened"])]
        print(f"{name}: {len(rows)} rows, {len(viol)} violations")
        for t, l, pr in viol:
            print(f"  [{','.join(pr)}] {l!r} <- {t!r}")
        bad += len(viol)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
