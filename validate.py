#!/usr/bin/env python3
"""Validate content.yaml: coverage, order, encoding fields, and GNU as output."""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
AS = "loongarch64-linux-gnu-as"
OBJDUMP = "loongarch64-linux-gnu-objdump"


def validate_base(insn: dict) -> None:
    value = 0
    for field in insn["encoding"]:
        high, low = field["bits"]
        span = high - low + 1
        if field.get("kind") != "fixed":
            continue
        bits = str(field["value"])
        if len(bits) != span or set(bits) - {"0", "1"}:
            raise ValueError(
                f"{insn['mnemonic']}: fixed field {high}:{low} is not {span} binary digits"
            )
        value |= int(bits, 2) << low
    base = int(str(insn["base"]), 0)
    if value != base:
        raise ValueError(
            f"{insn['mnemonic']}: fixed fields form 0x{value:08x}, base is 0x{base:08x}"
        )


def asm_operand(op: str, insn: str) -> str:
    regs = {
        "rd": "$a0", "rj": "$a1", "rk": "$a2", "ra": "$a3",
        "fd": "$f0", "fj": "$f1", "fk": "$f2", "fa": "$f3",
        "cd": "$fcc0", "cj": "$fcc0", "ca": "$fcc0",
        "fcsr": "$fcsr0", "csr": "0x0",
    }
    if op in regs:
        return regs[op]
    if op.startswith("si"):
        return "1" if op == "si16" else "0"
    if op.startswith("ui"):
        return "1"
    if op == "sa2":
        return "2"
    if op == "sa3":
        return "5"
    if op == "sa":
        return "2"
    if op.startswith("offs"):
        return "8"
    if op == "msbw":
        return "15"
    if op == "msbd":
        return "39"
    if op in ("lsbw", "lsbd"):
        return "8"
    if op in ("code", "hint", "level", "seq", "op", "cond", "csr", "fcsr"):
        return "0"
    raise ValueError(f"{insn}: unsupported operand {op}")


def env_for(insn: dict) -> dict[str, int]:
    return {
        "rd": 4, "rj": 5, "rk": 6, "ra": 1,
        "fd": 0, "fj": 1, "fk": 2, "fa": 3,
        "cd": 0, "cj": 0, "ca": 0,
        "fcsr": 0, "csr": 0, "cond": 4,
        "code": 0, "hint": 0, "level": 0, "seq": 0, "op": 0,
        "si12": 0, "si14": 0, "si16": 1, "si20": 0,
        "ui5": 1, "ui6": 1, "ui12": 1,
        "sa": 2, "sa2": 2, "sa3": 5, "offs": 8,
        "msbw": 15, "lsbw": 8, "msbd": 39, "lsbd": 8,
    }


def main() -> None:
    for tool in (AS, OBJDUMP):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found in PATH")

    content = yaml.safe_load((ROOT / "content.yaml").read_text(encoding="utf-8"))
    chapters = content["chapters"]
    instructions = [insn for chapter in chapters for insn in chapter["instructions"]]

    seen: set[str] = set()
    for chapter in chapters:
        letter = chapter["letter"]
        names = [insn["mnemonic"] for insn in chapter["instructions"]]
        if names != sorted(names):
            raise SystemExit(f"chapter {letter} is not sorted")
        for insn in chapter["instructions"]:
            name = insn["mnemonic"]
            if name in seen:
                raise SystemExit(f"duplicate mnemonic: {name}")
            seen.add(name)
            if name[0].upper() != letter:
                raise SystemExit(f"{name} is in chapter {letter}")
            validate_base(insn)

    lines: list[str] = []
    meta: list[tuple[dict, dict[str, int]]] = []
    for insn in instructions:
        operands = [op.strip() for op in insn["operands"].split(",")] if insn["operands"] else []
        args = [asm_operand(op, insn["mnemonic"]) for op in operands]
        mnemonic = insn["mnemonic"]
        if mnemonic == "fcmp.cond.s":
            mnemonic = "fcmp.ceq.s"
        elif mnemonic == "fcmp.cond.d":
            mnemonic = "fcmp.ceq.d"
        lines.append(mnemonic + ((" " + ", ".join(args)) if args else ""))
        meta.append((insn, env_for(insn)))

    source = ROOT / "build" / "validate.s"
    source.parent.mkdir(exist_ok=True)
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    obj = source.with_suffix(".o")
    subprocess.run([AS, "-o", str(obj), str(source)], check=True)
    out = subprocess.run(
        [OBJDUMP, "-d", str(obj)], capture_output=True, text=True, check=True
    ).stdout
    words = [
        int(m.group(1), 16)
        for m in re.finditer(r"^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+", out, re.M)
    ]
    if len(words) != len(meta):
        raise SystemExit(f"assembled {len(words)} words for {len(meta)} instructions")

    bad = []
    for (insn, env), word in zip(meta, words):
        expected = eval(insn["encoding_value"], {}, env) & 0xFFFFFFFF
        if expected != word:
            bad.append((insn["mnemonic"], f"0x{expected:08x}", f"0x{word:08x}"))
    if bad:
        for row in bad:
            print("mismatch:", *row)
        raise SystemExit(f"{len(bad)} encoding mismatches")

    print(f"OK: {len(instructions)} instructions, {len(chapters)} chapters, 0 mismatches")


if __name__ == "__main__":
    main()
