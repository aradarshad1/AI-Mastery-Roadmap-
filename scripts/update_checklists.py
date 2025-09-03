#!/usr/bin/env python3
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ---------- Config
LEVELS = ["junior-level", "mid-level", "senior-level"]
ROOT = Path(__file__).resolve().parents[1]

MARKER_START = "<!-- PROGRESS_START -->"
MARKER_END   = "<!-- PROGRESS_END -->"
PROGRESS_HEADER = "## 📊 Progress"

# Match markdown checkboxes: - [ ], - [x], * [x], + [x]
CHECKBOX_RE = re.compile(r"""^[\s]*[-*+]\s*\[
                             (?P<mark>x|X|\s)
                             \]\s+""", re.VERBOSE)

# Fenced code blocks: ignore everything inside
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Headings
H1_RE = re.compile(r"^\s{0,3}#\s+(?P<title>.+?)\s*$")          # top-level section (topic name)
H2_RE = re.compile(r"^\s{0,3}##\s+(?P<title>.+?)\s*$")         # subsections (Things to Do / Resources)

def normalize_title(t: str) -> str:
    # strip emojis and parens like "(6 milestones)"
    t = re.sub(r"\(.*?milestones?.*?\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^\w\s&:/\-#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def parse_section_counts(md_text: str) -> Dict[str, Dict[str, Tuple[int,int]]]:
    """
    Parse a combined milestones.md:
    Returns: { section_name: {'topics': (checked,total), 'todo': (checked,total), 'total': (checked,total)} }
    - Counts checkboxes under each H1 section (# ...).
    - Within a section, if inside 'Things to Do' H2, those checkboxes go to 'todo';
      otherwise (and not in 'Resources') they go to 'topics'.
    - Ignores fenced code blocks.
    """
    in_code = False
    current_sec: Optional[str] = None
    current_bucket: Optional[str] = None  # 'topics' | 'todo' | None

    results: Dict[str, Dict[str, List[int]]] = {}  # counts as lists to mutate: [checked,total]

    def ensure_section(name: str):
        if name not in results:
            results[name] = {
                "topics": [0, 0],
                "todo":   [0, 0],
                "total":  [0, 0],
            }

    for rawline in md_text.splitlines():
        line = rawline.rstrip("\n")

        # Toggle fence state
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue

        # New H1 section?
        m1 = H1_RE.match(line)
        if m1:
            current_sec = normalize_title(m1.group("title"))
            ensure_section(current_sec)
            current_bucket = "topics"  # default
            continue

        # H2 inside section?
        m2 = H2_RE.match(line)
        if m2 and current_sec:
            title = normalize_title(m2.group("title")).lower()
            if "things to do" in title or "tasks" in title or "to do" in title:
                current_bucket = "todo"
            elif "resources" in title:
                current_bucket = None  # ignore resources
            else:
                # any other H2 resets to generic topics bucket
                current_bucket = "topics"
            continue

        # Checkbox?
        m = CHECKBOX_RE.match(line)
        if m and current_sec:
            mark = m.group("mark").lower()
            # always count to section total
            results[current_sec]["total"][1] += 1
            if mark == "x":
                results[current_sec]["total"][0] += 1
            # to bucket if relevant
            if current_bucket in ("topics", "todo"):
                results[current_sec][current_bucket][1] += 1
                if mark == "x":
                    results[current_sec][current_bucket][0] += 1

    # Convert inner lists to tuples
    finalized: Dict[str, Dict[str, Tuple[int,int]]] = {}
    for sec, buckets in results.items():
        finalized[sec] = {
            "topics": tuple(buckets["topics"]),
            "todo":   tuple(buckets["todo"]),
            "total":  tuple(buckets["total"]),
        }
    return finalized

def make_table(rows: List[Tuple[str, int, int, int, int, int, int]]) -> str:
    """
    rows: [(name, t_done,t_all, d_done,d_all, g_done,g_all), ...]
    """
    out = ["| Milestone | Topics | Things to Do | Overall |",
           "|---|---:|---:|---:|"]
    for name, td, ta, dd, da, gd, ga in rows:
        t_pct = (td/ta*100) if ta else 0.0
        d_pct = (dd/da*100) if da else 0.0
        g_pct = (gd/ga*100) if ga else 0.0
        out.append(
            f"| `{name}` | {td}/{ta} ({t_pct:.0f}%) | {dd}/{da} ({d_pct:.0f}%) | {gd}/{ga} ({g_pct:.0f}%) |"
        )
    return "\n".join(out)

def insert_progress_block(readme_path: Path, block_md: str) -> None:
    if readme_path.exists():
        txt = readme_path.read_text(encoding="utf-8")
    else:
        txt = ""
    start = txt.find(MARKER_START)
    end = txt.find(MARKER_END)
    new_block = f"{PROGRESS_HEADER}\n\n{MARKER_START}\n{block_md}\n{MARKER_END}\n"
    if start != -1 and end != -1 and end > start:
        before = txt[:start]
        after = txt[end + len(MARKER_END):]
        updated = before + new_block + after
    else:
        sep = "\n\n" if txt and not txt.endswith("\n") else "\n"
        updated = txt + sep + new_block
    readme_path.write_text(updated, encoding="utf-8")

def parse_level(level: str) -> Dict[str, Dict[str, Tuple[int,int]]]:
    lvl_dir = ROOT / level
    # Prefer milestones.md; fallback to README.md
    candidates = [lvl_dir / "milestones.md", lvl_dir / "README.md"]
    src = next((p for p in candidates if p.exists()), None)
    if not src:
        return {}
    return parse_section_counts(src.read_text(encoding="utf-8"))

def main():
    # Parse all levels
    per_level: Dict[str, Dict[str, Dict[str, Tuple[int,int]]]] = {}
    for lvl in LEVELS:
        per_level[lvl] = parse_level(lvl)

    # Console summary
    print("Progress Report")
    print("---------------")
    overall_done = overall_all = 0
    for lvl in LEVELS:
        sections = per_level.get(lvl, {})
        print(f"\n=== {lvl} ===")
        for name, counts in sections.items():
            td, ta = counts["topics"]
            dd, da = counts["todo"]
            gd, ga = counts["total"]
            overall_done += gd
            overall_all  += ga
            print(f"{name}  topics[{td}/{ta}]  todo[{dd}/{da}]  overall[{gd}/{ga}]")

    # Root PROGRESS.md
    lines = ["# Repository Progress"]
    for lvl in LEVELS:
        secs = per_level.get(lvl, {})
        if not secs:
            continue
        rows = []
        for name, c in sorted(secs.items()):
            td, ta = c["topics"]
            dd, da = c["todo"]
            gd, ga = c["total"]
            rows.append((name, td, ta, dd, da, gd, ga))
        lines.append(f"\n## {lvl}")
        lines.append(make_table(rows))
    if overall_all:
        overall_pct = overall_done/overall_all*100
        lines.append(f"\n---\n**Overall**: {overall_done}/{overall_all} ({overall_pct:.0f}%)\n")
    (ROOT / "PROGRESS.md").write_text("\n".join(lines), encoding="utf-8")

    # Update each level README with a block
    for lvl in LEVELS:
        lvl_dir = ROOT / lvl
        readme = lvl_dir / "README.md"
        secs = per_level.get(lvl, {})
        if not secs:
            continue
        rows = []
        for name, c in sorted(secs.items()):
            td, ta = c["topics"]
            dd, da = c["todo"]
            gd, ga = c["total"]
            rows.append((name, td, ta, dd, da, gd, ga))
        block_md = make_table(rows)
        insert_progress_block(readme, block_md)

if __name__ == "__main__":
    main()
