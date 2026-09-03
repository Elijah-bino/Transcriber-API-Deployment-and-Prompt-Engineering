"""Side-by-side view: one row per transcript, one column per model's output.

  python compare.py --out ../results            # -> results/comparison.csv
  python compare.py --out ../results/local

Reads results/raw/*.csv. Adds a "  (X)" suffix per cell where the output did
not exactly match the expected label, so misses are easy to scan.
"""
import argparse
import csv
import pathlib


def norm(s: str) -> str:
    return " ".join((s or "").strip().rstrip(".,!?;:").split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out).resolve()
    raw = sorted((out_dir / "raw").glob("*.csv"))
    if not raw:
        print(f"no raw files in {out_dir/'raw'}")
        return 1

    models = [p.stem for p in raw]
    rows: dict[str, dict] = {}
    for p in raw:
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            rid = r["id"]
            rows.setdefault(rid, {"id": rid, "dataset": r["dataset"],
                                  "transcript": r["transcript"],
                                  "expected": r["expected"]})
            out = r.get("output", "") or (f"[ERR {r.get('error','')[:40]}]" if r.get("error") else "")
            mark = "" if norm(out) == norm(r["expected"]) else "   <MISS>"
            rows[rid][p.stem] = out + mark

    dest = out_dir / "comparison.csv"
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "dataset", "transcript", "expected"] + models)
        w.writeheader()
        for rid in sorted(rows, key=int):
            w.writerow(rows[rid])

    # also a readable text dump
    txt = out_dir / "comparison.txt"
    with open(txt, "w", encoding="utf-8") as f:
        for rid in sorted(rows, key=int):
            r = rows[rid]
            f.write(f"\n[{r['id']}] ({r['dataset']}) {r['transcript']}\n")
            f.write(f"      expected : {r['expected']}\n")
            for m in models:
                f.write(f"  {m:28} : {r.get(m, '-')}\n")

    print(f"wrote {dest}\n      {txt}\n{len(rows)} transcripts x {len(models)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
