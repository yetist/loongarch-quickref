#!/usr/bin/env python3
"""Extract a draft vector quick-reference content YAML from the LoongArch manual PDF.

Parses:
  - Appendix B "Instruction Code List" -> mnemonic, operands, encoding fields
  - Chapter 1.2 instruction sections   -> per-instruction pseudocode blocks

Usage:
  python3 tools/extract_vector.py <manual.pdf> [-o content-vec.yaml]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

import yaml


def yaml_dump(content: dict) -> str:
    return yaml.safe_dump(
        content,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )

FIELD_KINDS = {
    "vd": "reg", "vj": "reg", "vk": "reg", "va": "reg",
    "xd": "reg", "xj": "reg", "xk": "reg", "xa": "reg",
    "rj": "reg", "rk": "reg", "rd": "reg",
    "cond": "imm", "idx": "imm",
}


def tokens_with_cols(line: str) -> list[tuple[int, int, str]]:
    out = []
    for m in re.finditer(r"\S+", line):
        out.append((m.start(), m.end(), m.group()))
    return out


def parse_appendix_b(text: str) -> dict[str, dict]:
    """Parse the Appendix B instruction code list.

    Rows are `MNEMONIC operands... <bit area>`.  Bit-area tokens are assigned
    widths structurally instead of geometrically: fixed '0'/'1' tokens cover
    one bit each, si*/ui* immediates carry their width in the name, general
    and vector register fields cover 5 bits, and any leftover bits belong to
    variable-width fields (idx) which are inserted at the widest column gap.
    """
    FIELD_WIDTHS = {
        "vd": 5, "vj": 5, "vk": 5, "va": 5,
        "xd": 5, "xj": 5, "xk": 5, "xa": 5,
        "rj": 5, "rk": 5, "rd": 5,
        "cond": 5, "cd": 3,
        "idx": None,
    }
    entries: dict[str, dict] = {}

    def classify(mnemonic: str, operand_names: list[str], bit_toks: list[tuple[int, int, str]]) -> list[dict]:
        toks = []
        for lo, hi, txt in bit_toks:
            txt = {"XD": "xd", "XJ": "xj", "XK": "xk", "XA": "xa",
                   "VD": "vd", "VJ": "vj", "VK": "vk", "VA": "va"}.get(txt, txt)
            if txt in ("0", "1"):
                width = 1
            elif m := re.fullmatch(r"([su]?i)([0-9]+)", txt):
                width = int(m.group(2))
            elif txt in FIELD_WIDTHS:
                width = FIELD_WIDTHS[txt]
            else:
                width = None
            toks.append([lo, hi, txt, width])

        known = sum(t[3] for t in toks if t[3] is not None)
        unknowns = [t for t in toks if t[3] is None]
        leftover = 32 - known
        if unknowns and leftover >= len(unknowns):
            # one variable-width field gets all leftover bits
            if len(unknowns) == 1:
                unknowns[0][3] = leftover
            else:
                raise ValueError(f"{mnemonic}: cannot split {leftover} bits over {len(unknowns)} unknown fields")
        elif not unknowns and leftover != 0:
            # a field named in the operands is missing from the bit area
            # (split label); insert it at the widest gap between tokens
            missing = [op for op in operand_names
                       if op not in {t[2] for t in toks} and op not in ("0", "1")]
            if len(missing) != 1 or leftover <= 0:
                raise ValueError(f"{mnemonic}: {leftover:+d} bits, missing fields {missing}")
            gaps = []
            for a, b in zip(toks, toks[1:]):
                gaps.append((b[0] - a[1], a))
            if not toks:
                raise ValueError(f"{mnemonic}: empty bit area")
            gaps.append((leftover * 6, toks[-1]))  # trailing gap
            width = leftover
            best_gap, after = max(gaps, key=lambda g: g[0])
            idx = toks.index(after) + 1
            toks.insert(idx, [after[1] + 1, after[1] + 2, missing[0], width])

        total = sum(t[3] for t in toks)
        if total != 32:
            raise ValueError(f"{mnemonic}: bit widths sum to {total}")

        fields = []
        bit = 31
        for lo, hi, txt, width in toks:
            low = bit - width + 1
            if txt in ("0", "1"):
                if width != 1:
                    raise ValueError(f"{mnemonic}: bit token {txt!r} spans {width} bits")
                fields.append({"bits": [bit, low], "value": txt, "kind": "fixed"})
            else:
                kind = FIELD_KINDS.get(txt)
                if kind is None:
                    kind = "imm" if re.fullmatch(r"([su]?i)[0-9]+", txt) else "reg"
                fields.append({"bits": [bit, low], "value": txt, "kind": kind})
            bit = low - 1
        if bit != -1:
            raise ValueError(f"{mnemonic}: fields do not end at bit 0 (at {bit})")

        # merge contiguous fixed runs
        merged = []
        for f in fields:
            if merged and merged[-1]["kind"] == "fixed" and f["kind"] == "fixed" \
                    and merged[-1]["bits"][0] == f["bits"][1] + 1:
                merged[-1]["bits"] = [merged[-1]["bits"][0], f["bits"][1]]
                merged[-1]["value"] += f["value"]
            else:
                merged.append(f)
        return merged

    # restrict to Appendix B region (last occurrence of its title)
    starts = [i for i, line in enumerate(text.splitlines())
              if re.search(r"^3\s+Appendix B: Instruction Code List", line.strip())]
    if not starts:
        raise SystemExit("Appendix B not found in text")
    body = "\n".join(text.splitlines()[starts[-1]:])

    for line in body.splitlines():
        toks = line.split()
        if not toks or not re.fullmatch(r"(XV|V)[A-Za-z0-9.]+", toks[0]):
            continue
        mnemonic = toks[0]
        # operands: tokens until the first fixed-bit token
        i = 1
        operand_names = []
        while i < len(toks) and toks[i] not in ("0", "1"):
            operand_names.append(toks[i].rstrip(","))
            i += 1
        bit_toks = []
        pos = 0
        for j, tok in enumerate(toks[i:], start=i):
            col = line.index(tok, pos)
            pos = col + len(tok)
            bit_toks.append((col, col + len(tok), tok))
        try:
            fields = classify(mnemonic, operand_names, bit_toks)
        except ValueError as exc:
            print(f"SKIP: {exc}", file=sys.stderr)
            continue
        if mnemonic in entries:
            print(f"DUP: {mnemonic}", file=sys.stderr)
            continue
        base = 0
        for f in fields:
            if f["kind"] == "fixed":
                base |= int(f["value"], 2) << f["bits"][1]
        # the lowest-bit field is the destination register; the manual
        # occasionally misprints the first operand (e.g. xvmaddwod.* rows
        # list "xk, xj, xk") — trust the encoding and fix the operand list
        dest = fields[-1]["value"]
        if operand_names and operand_names[0] != dest and dest in ("vd", "xd", "rd", "fd"):
            print(f"FIXED operands: {mnemonic}: {operand_names[0]} -> {dest}", file=sys.stderr)
            operand_names[0] = dest
        entries[mnemonic] = {
            "mnemonic": mnemonic.lower(),
            "upper": mnemonic,
            "operands": ", ".join(operand_names),
            "encoding": fields,
            "base": f"0x{base:08x}",
        }

    return entries


SECTION_RE = re.compile(r"^1\.2\.\d+\.\d+\s+(.*)$")
LABEL_RE = re.compile(r"^\s*((?:X)?V[A-Z0-9]+(?:\.[A-Za-z0-9]+)*|VSET[A-Z0-9.]*)\s*:?\s*$")


def parse_sections(text: str) -> dict[str, dict]:
    """Extract per-mnemonic pseudocode blocks and section prose from chapter 1.2."""
    lines = text.splitlines()
    sections: list[dict] = []
    current: dict | None = None

    for i, line in enumerate(lines):
        m = SECTION_RE.match(line.strip())
        if m and "Appendix" not in line:
            current = {"title": m.group(1).strip(), "prose": [], "pseudo": {}, "syntax": {}}
            sections.append(current)
            continue
        if current is None:
            continue
        if line.strip().startswith(("2 Appendix", "3 Appendix")):
            current = None
            continue
        lm = LABEL_RE.match(line.rstrip())
        if lm:
            label = lm.group(1).rstrip(":")
            if label in current["pseudo"]:
                # manual typo: duplicate label; rename by the element type in
                # its code body (e.g. second "VPICKVE2GR.B" uses VR[vj].H[ui3])
                peek = []
                for later in lines[i + 1 : i + 4]:
                    if not later.strip():
                        continue
                    peek.append(later.strip())
                    if len(peek) >= 1:
                        break
                elem = re.search(r"\.([BHWD])\[", " ".join(peek))
                if elem:
                    fixed = label.rsplit(".", 1)[0] + "." + elem.group(1)
                    print(f"FIXED label: {label} -> {fixed}", file=sys.stderr)
                    label = fixed
            current["pseudo"].setdefault(label, [])
            current["_label"] = label
            continue
        if current.get("_label") is not None:
            if line.strip() and not re.match(r"^\s*$", line):
                stripped = line.strip()
                if re.match(r"^[0-9.]*\s*(Appendix|Table|LoongArch Reference)", stripped):
                    current["_label"] = None
                else:
                    current["pseudo"][current["_label"]].append(stripped)
        else:
            prose = line.strip()
            if prose and not re.match(r"^(1\.2\.|Table|LoongArch Reference Manual Volume|\s*$)", prose):
                current["prose"].append(prose)

    result: dict[str, dict] = {}
    for sec in sections:
        pseudo = {}
        for label, code_lines in sec["pseudo"].items():
            # drop trailing page-footers/manual headers
            clean = [l for l in code_lines if not re.match(r"^(LoongArch Reference|\d+ )", l)]
            pseudo[label] = "\n".join(clean).strip()
        result[sec["title"]] = {"pseudo": pseudo, "prose": "\n".join(sec["prose"])}
    return result


def derive_isa(mnemonic: str) -> list[str]:
    if mnemonic.startswith("x"):
        return ["LSX", "LASX"]
    return ["LSX"]


def derive_format(operands: str) -> str:
    n = len([op for op in operands.split(",") if op.strip()])
    return f"{n}R 型" if n else ""


REG_EXAMPLE = {
    "vd": "$vr0", "vj": "$vr1", "vk": "$vr2", "va": "$vr3",
    "xd": "$xr0", "xj": "$xr1", "xk": "$xr2", "xa": "$xr3",
    "rj": "$a1", "rk": "$a2", "rd": "$a0",
    "cd": "$fcc0", "cond": "0", "idx": "0",
}


def make_example(mnemonic: str, operands: str) -> str:
    args = []
    for op in (o.strip() for o in operands.split(",")):
        if not op:
            continue
        if op in REG_EXAMPLE:
            args.append(REG_EXAMPLE[op])
        elif re.fullmatch(r"([su]?i)[0-9]+", op):
            args.append("1" if op == "si16" else "0")
        else:
            args.append("0")
    return mnemonic + ((" " + ", ".join(args)) if args else "")


def make_encoding_value(base: str, encoding: list[dict]) -> str:
    parts = [base]
    for f in encoding:
        if f["kind"] == "fixed":
            continue
        low = f["bits"][1]
        if low == 0:
            parts.append(f["value"])
        else:
            parts.append(f"({f['value']} << {low})")
    return " | ".join(parts)


def label_to_mnemonic(label: str) -> str:
    return label.lower().rstrip(":")


def build_content(entries: dict, sections: dict) -> dict:
    # map each lowercase mnemonic to its pseudocode block
    pseudo: dict[str, str] = {}
    conflicts = []
    for title, sec in sections.items():
        for label, code in sec["pseudo"].items():
            mnem = label_to_mnemonic(label)
            if mnem in pseudo and pseudo[mnem] != code:
                conflicts.append(mnem)
                continue
            pseudo.setdefault(mnem, code)
    if conflicts:
        print(f"note: {len(conflicts)} pseudocode label conflicts, kept first", file=sys.stderr)

    instructions: dict[str, dict] = {}
    missing_pseudo = []
    for upper, e in entries.items():
        mnem = e["mnemonic"]
        code = pseudo.get(mnem, "")
        insn = {
            "mnemonic": mnem,
            "operands": e["operands"],
            "cn_name": "（待编）",
            "en_name": "（待编）",
            "format": derive_format(e["operands"]),
            "isa": derive_isa(mnem),
            "equation": code.splitlines()[0].strip() if code else "（待编）",
            "description": "（待编）",
            "example": make_example(mnem, e["operands"]),
            "example_comment": "",
            "pseudocode": code or "（待补）",
            "encoding": e["encoding"],
            "base": e["base"],
            "encoding_value": make_encoding_value(e["base"], e["encoding"]),
        }
        if not code:
            missing_pseudo.append(mnem)
        instructions[mnem] = insn

    chapters = []
    for letter, chapter_title in (("V", "V · LSX 向量指令"), ("X", "X · LASX 扩展向量指令")):
        members = sorted(m for m in instructions if m[0].upper() == letter)
        if not members:
            continue
        chapters.append({
            "letter": letter,
            "title": chapter_title,
            "note": "（待编）",
            "instructions": [instructions[m] for m in members],
        })
    total = sum(len(c["instructions"]) for c in chapters)
    print(f"pseudocode coverage: {total - len(missing_pseudo)}/{total}", file=sys.stderr)
    return {
        "document": {
            "title": "龙芯架构指令速查表",
            "subtitle": "卷二 · 向量扩展",
            "scope": "V / X 字母（LSX 与 LASX）",
        },
        "chapters": chapters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=pathlib.Path, help="manual PDF path")
    parser.add_argument("-o", "--output", type=pathlib.Path, default=pathlib.Path("content-vec.yaml"))
    parser.add_argument("--dump", type=pathlib.Path, help="dump parsed JSON for inspection")
    args = parser.parse_args()

    txt = subprocess.run(
        ["pdftotext", "-layout", str(args.pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout

    entries = parse_appendix_b(txt)
    sections = parse_sections(txt)

    if args.dump:
        import json
        args.dump.write_text(
            json.dumps({"appendix": entries, "sections": sections}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    content = build_content(entries, sections)
    args.output.write_text(yaml_dump(content), encoding="utf-8")
    total = sum(len(c["instructions"]) for c in content["chapters"])
    print(f"appendix entries: {len(entries)}")
    print(f"sections: {len(sections)}")
    print(f"wrote {args.output}: {total} instructions")


if __name__ == "__main__":
    main()
