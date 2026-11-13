#!/usr/bin/env python3
"""Fill Chinese/English names, descriptions, equations, pseudocode and notes
into content-vec.yaml (draft produced by extract_vector.py).

Names are composed from a per-family semantic dictionary (Chinese/English
action templates) plus suffix-derived element words; descriptions come from
per-family prose templates with register/immediate/element substitution.
Also fills the 24 memory-access pseudocode blocks the manual omits and
corrects a handful of known manual pseudocode typos.

Usage: python3 tools/fill_vector_text.py [-i content-vec.yaml]
"""

from __future__ import annotations

import argparse
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# element vocabulary

# letter -> (chinese, english, bits)
INT_ELEM = {
    "B": ("字节", "Byte", 8),
    "H": ("半字", "Halfword", 16),
    "W": ("字", "Word", 32),
    "D": ("双字", "Doubleword", 64),
    "Q": ("四字", "Quadword", 128),
}
FLT_ELEM = {
    "H": ("半精度", "Half-Precision", 16),
    "S": ("单精度", "Single-Precision", 32),
    "D": ("双精度", "Double-Precision", 64),
}

FLOAT_BASES = {
    "VFADD", "VFSUB", "VFMUL", "VFDIV", "VFMAX", "VFMIN", "VFMAXA", "VFMINA",
    "VFSQRT", "VFRECIP", "VFRECIPE", "VFRSQRT", "VFRSQRTE", "VFMADD", "VFMSUB",
    "VFNMADD", "VFNMSUB", "VFLOGB", "VFCLASS", "VFRINT", "VFRINTRM",
    "VFRINTRNE", "VFRINTRP", "VFRINTRZ", "VFCMP", "VFRSTP", "VFRSTPI",
    "VFCVT", "VFCVTH", "VFCVTL", "VFTINT", "VFTINTH", "VFTINTL",
    "VFTINTRM", "VFTINTRMH", "VFTINTRML", "VFTINTRNE", "VFTINTRNEH",
    "VFTINTRNEL", "VFTINTRP", "VFTINTRPH", "VFTINTRPL", "VFTINTRZ",
    "VFTINTRZH", "VFTINTRZL", "VFFINT", "VFFINTH", "VFFINTL",
}

# families whose dst.src suffix means "widen src to dst"
WIDEN_BASES = {
    "VHADDW", "VHSUBW", "VADDWEV", "VADDWOD", "VSUBWEV", "VSUBWOD",
    "VMULWEV", "VMULWOD", "VMADDWEV", "VMADDWOD",
    "VEXTH", "VEXTL", "VEXT2XV", "VSLLWIL",
}
# families whose dst.src suffix means "narrow src to dst" (shift-narrowing)
NARROW_BASES = {
    "VSRLN", "VSRAN", "VSRLRN", "VSRARN",
    "VSSRLN", "VSSRAN", "VSSRLRN", "VSSRARN",
    "VSRLNI", "VSRANI", "VSRLRNI", "VSRARNI",
    "VSSRLNI", "VSSRANI", "VSSRLRNI", "VSSRARNI",
}
# families whose dst.src suffix means "convert src precision to dst"
CVT_BASES = {"VFCVT", "VFCVTH", "VFCVTL", "VFFINT", "VFFINTH", "VFFINTL",
             "VFTINT", "VFTINTH", "VFTINTL", "VFTINTRM", "VFTINTRMH",
             "VFTINTRML", "VFTINTRNE", "VFTINTRNEH", "VFTINTRNEL",
             "VFTINTRP", "VFTINTRPH", "VFTINTRPL", "VFTINTRZ",
             "VFTINTRZH", "VFTINTRZL"}

# widen families with the three-part .dst.srcU.src mixed-sign suffix
MIXED_FAMS = {"VADDWEV", "VADDWOD", "VSUBWEV", "VSUBWOD",
              "VMULWEV", "VMULWOD", "VMADDWEV", "VMADDWOD"}

# family -> (cn template, en template, desc template)
# placeholders: {d} {j} {k} {a} {rd} {rj} {rk} {cd} registers (backticked),
# {e}/{E} result element, {s}/{S} other element, {n} element count,
# {i} immediate field name, {jsig}/{ksig}/{sig} signedness words,
# {ext} sign/zero extension word, {mix} mixed-sign phrase, {bits} element bits
FAMILIES: dict[str, tuple[str, str, str]] = {
    # ---- 1.2.1 arithmetic ----
    "VADD": ("向量{e}加法", "Vector Add {E}",
        "将 {j} 与 {k} 中对应{e}整数元素相加，结果写入 {d} 的对应{e}元素。"),
    "VSUB": ("向量{e}减法", "Vector Subtract {E}",
        "将 {j} 中{e}整数元素减去 {k} 中对应{e}元素，结果写入 {d} 的对应{e}元素。"),
    "VADDI": ("向量{mix}{e}立即数加法", "Vector Add Immediate Unsigned {E}",
        "将 {j} 中{e}元素与零扩展的立即数 {i} 相加，结果写入 {d} 的对应{e}元素。"),
    "VSUBI": ("向量{mix}{e}立即数减法", "Vector Subtract Immediate Unsigned {E}",
        "将 {j} 中{e}元素减去零扩展的立即数 {i}，结果写入 {d} 的对应{e}元素。"),
    "VNEG": ("向量{e}取负", "Vector Negate {E}",
        "将 {j} 中{e}元素取二进制补码相反数，结果写入 {d} 的对应{e}元素。"),
    "VSADD": ("向量{mix}{e}饱和加法", "Vector Saturating Add {MixE} {E}",
        "将 {j} 与 {k} 中对应{sig}{e}整数元素相加，结果饱和限制在该元素表示范围内后写入 {d}。"),
    "VSSUB": ("向量{mix}{e}饱和减法", "Vector Saturating Subtract {MixE} {E}",
        "将 {j} 中{jsig}{e}元素减去 {k} 中对应{ksig}{e}元素，结果饱和限制在该元素表示范围内后写入 {d}。"),
    "VHADDW": ("向量{mix}{s}加宽{e}加法", "Vector Add Widening {E} from {S}",
        "将 {j} 的奇数下标{jsig}{s}元素与 {k} 的偶数下标{ksig}{s}元素扩展到{e}宽度后相加，结果写入 {d}。"),
    "VHSUBW": ("向量{mix}{s}加宽{e}减法", "Vector Subtract Widening {E} from {S}",
        "将 {j} 的奇数下标{jsig}{s}元素扩展到{e}宽度，减去 {k} 的偶数下标{ksig}{s}元素，结果写入 {d}。"),
    "VADDWEV": ("向量{mix}{s}偶位加宽{e}加法", "Vector Even-Element Add Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为偶数（2i）的{jksig}{s}元素扩展到{e}宽度后相加，结果写入 {d} 的对应{e}元素。"),
    "VADDWOD": ("向量{mix}{s}奇位加宽{e}加法", "Vector Odd-Element Add Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为奇数（2i+1）的{jksig}{s}元素扩展到{e}宽度后相加，结果写入 {d} 的对应{e}元素。"),
    "VSUBWEV": ("向量{mix}{s}偶位加宽{e}减法", "Vector Even-Element Subtract Widening {E} from {S}",
        "将 {j} 中下标为偶数（2i）的{jsig}{s}元素扩展到{e}宽度，减去 {k} 中对应{ksig}{s}元素，结果写入 {d}。"),
    "VSUBWOD": ("向量{mix}{s}奇位加宽{e}减法", "Vector Odd-Element Subtract Widening {E} from {S}",
        "将 {j} 中下标为奇数（2i+1）的{jsig}{s}元素扩展到{e}宽度，减去 {k} 中对应{ksig}{s}元素，结果写入 {d}。"),
    "VAVG": ("向量{e}平均数", "Vector Average {E}",
        "将 {j} 与 {k} 中对应{sig}{e}元素相加后除以 2 并向下取整，结果写入 {d} 的对应{e}元素。"),
    "VAVGR": ("向量{e}平均数（向上取整）", "Vector Average Rounded {E}",
        "将 {j} 与 {k} 中对应{sig}{e}元素相加后加 1 再除以 2（向上取整），结果写入 {d} 的对应{e}元素。"),
    "VABSD": ("向量{e}绝对差", "Vector Absolute Difference {E}",
        "将 {j} 与 {k} 中对应{sig}{e}元素相减取绝对值，结果写入 {d} 的对应{e}元素。"),
    "VADDA": ("向量{e}绝对值和", "Vector Add Absolute {E}",
        "将 {j} 与 {k} 中对应{e}元素各自取绝对值后相加，结果写入 {d} 的对应{e}元素。"),
    "VMAX": ("向量{e}取最大", "Vector Maximum {E}",
        "取 {j} 与 {k} 中对应{sig}{e}元素的较大者，写入 {d} 的对应{e}元素。"),
    "VMIN": ("向量{e}取最小", "Vector Minimum {E}",
        "取 {j} 与 {k} 中对应{sig}{e}元素的较小者，写入 {d} 的对应{e}元素。"),
    "VMAXI": ("向量{e}立即数取最大", "Vector Maximum Immediate {E}",
        "取 {j} 中{sig}{e}元素与{exti}立即数 {i} 的较大者，写入 {d} 的对应{e}元素。"),
    "VMINI": ("向量{e}立即数取最小", "Vector Minimum Immediate {E}",
        "取 {j} 中{sig}{e}元素与{exti}立即数 {i} 的较小者，写入 {d} 的对应{e}元素。"),
    "VMUL": ("向量{e}乘法", "Vector Multiply {E}",
        "将 {j} 与 {k} 中对应{sig}{e}元素相乘，取乘积的低{bits}位写入 {d} 的对应{e}元素。"),
    "VMUH": ("向量{e}乘法取高半", "Vector Multiply High {E}",
        "将 {j} 与 {k} 中对应{sig}{e}元素相乘，取乘积的高{bits}位写入 {d} 的对应{e}元素。"),
    "VMULWEV": ("向量{mix}{s}偶位加宽乘法", "Vector Even-Element Multiply Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为偶数（2i）的{jksig}{s}元素相乘，取乘积的{e}（低）半写入 {d} 的对应{e}元素。"),
    "VMULWOD": ("向量{mix}{s}奇位加宽乘法", "Vector Odd-Element Multiply Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为奇数（2i+1）的{jksig}{s}元素相乘，取乘积的{e}（低）半写入 {d} 的对应{e}元素。"),
    "VMADD": ("向量{e}乘累加", "Vector Multiply-Add {E}",
        "将 {j} 与 {k} 中对应{e}元素相乘，乘积加到 {d} 原有{e}元素上，结果写回 {d}。"),
    "VMSUB": ("向量{e}乘减", "Vector Multiply-Subtract {E}",
        "将 {j} 与 {k} 中对应{e}元素相乘，从 {d} 原有{e}元素中减去乘积，结果写回 {d}。"),
    "VMADDWEV": ("向量{mix}{s}偶位加宽乘累加", "Vector Even-Element Multiply-Add Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为偶数（2i）的{jksig}{s}元素相乘，乘积累加到 {d} 的对应{e}元素上，结果写回 {d}。"),
    "VMADDWOD": ("向量{mix}{s}奇位加宽乘累加", "Vector Odd-Element Multiply-Add Widening {E} from {S}",
        "将 {j} 与 {k} 中下标为奇数（2i+1）的{jksig}{s}元素相乘，乘积累加到 {d} 的对应{e}元素上，结果写回 {d}。"),
    "VDIV": ("向量{e}除法", "Vector Divide {E}",
        "将 {j} 中{sig}{e}元素除以 {k} 中对应{sig}{e}元素（商向零取整），写入 {d}。"),
    "VMOD": ("向量{e}取模", "Vector Modulo {E}",
        "将 {j} 中{sig}{e}元素对 {k} 中对应{sig}{e}元素取模（余数与被除数同号），写入 {d}。"),
    "VSAT": ("向量{e}有效位饱和", "Vector Saturate to Valid Bits {E}",
        "将 {j} 中{sig}{e}元素饱和到立即数 {i} 指定的有效位范围，结果写入 {d}。"),
    "VEXTH": ("向量{mix}{s}取高半加宽{e}", "Vector Extend High {E} from {S}",
        "取 {j} 中高 {n} 个{jsig}{s}元素，扩展为{e}元素写入 {d}。"),
    "VEXTL": ("向量{mix}{s}取低半加宽{e}", "Vector Extend Low {E} from {S}",
        "取 {j} 低半部分的{jsig}{s}元素，扩展为{e}元素写入 {d}。"),
    "VEXT2XV": ("向量{mix}{s}加宽{e}扩展到 256 位", "Vector Extend to {E} in Extended Register",
        "取 {j} 低 128 位中的前 {ln} 个{jsig}{s}元素，扩展为{e}元素后写入 {d}（占满 {d} 全部 256 位）。"),
    "VMSKLTZ": ("向量{e}小于零掩码", "Vector Mask of Less Than Zero {E}",
        "逐个检查 {j} 中{e}元素是否小于零，生成位掩码写入 {d}：元素小于零的对应位为 1，否则为 0（写入前 {d} 清零）。"),
    "VMSKGEZ": ("向量{e}大于等于零掩码", "Vector Mask of Greater Than or Equal to Zero {E}",
        "逐个检查 {j} 中{e}元素是否大于等于零，生成位掩码写入 {d}：元素大于等于零的对应位为 1，否则为 0（写入前 {d} 清零）。"),
    "VMSKNZ": ("向量{e}非零掩码", "Vector Mask of Not Zero {E}",
        "逐个检查 {j} 中{e}元素是否非零，生成位掩码写入 {d}：元素非零的对应位为 1，否则为 0（写入前 {d} 清零）。"),
    "VLDI": ("向量立即数装载", "Vector Load Immediate",
        "按立即数 {i} 的编码规则生成 64 位数据，复制填充 {d} 的每个 64 位块（模式见节注）。"),

    "VCLO": ("向量{e}前导 1 计数", "Vector Count Leading Ones {E}",
        "统计 {j} 中{e}元素自最高位起连续 1 的个数，结果写入 {d} 的对应{e}元素。"),
    "VCLZ": ("向量{e}前导零计数", "Vector Count Leading Zeros {E}",
        "统计 {j} 中{e}元素自最高位起连续 0 的个数，结果写入 {d} 的对应{e}元素。"),
    "VPCNT": ("向量{e}位 1 计数", "Vector Population Count {E}",
        "统计 {j} 中{e}元素里值为 1 的位数，结果写入 {d} 的对应{e}元素。"),

    # ---- 1.2.2 bitwise ----
    "VAND": ("向量按位与", "Vector Bitwise AND",
        "将 {j} 与 {k} 按位与，结果写入 {d}。"),
    "VOR": ("向量按位或", "Vector Bitwise OR",
        "将 {j} 与 {k} 按位或，结果写入 {d}。"),
    "VXOR": ("向量按位异或", "Vector Bitwise XOR",
        "将 {j} 与 {k} 按位异或，结果写入 {d}。"),
    "VNOR": ("向量按位或非", "Vector Bitwise NOR",
        "将 {j} 与 {k} 按位或后取反，结果写入 {d}。"),
    "VANDN": ("向量按位与非", "Vector Bitwise AND-NOT",
        "将 {j} 取反后与 {k} 按位与，结果写入 {d}。"),
    "VORN": ("向量按位或非", "Vector Bitwise OR-NOT",
        "将 {k} 取反后与 {j} 按位或，结果写入 {d}。"),
    "VANDI": ("向量{e}立即数按位与", "Vector Bitwise AND Immediate {E}",
        "将 {j} 中{e}元素与零扩展的 {i} 位立即数 {i} 按位与，结果写入 {d}。"),
    "VORI": ("向量{e}立即数按位或", "Vector Bitwise OR Immediate {E}",
        "将 {j} 中{e}元素与零扩展的 {i} 位立即数 {i} 按位或，结果写入 {d}。"),
    "VXORI": ("向量{e}立即数按位异或", "Vector Bitwise XOR Immediate {E}",
        "将 {j} 中{e}元素与零扩展的 {i} 位立即数 {i} 按位异或，结果写入 {d}。"),
    "VNORI": ("向量{e}立即数按位或非", "Vector Bitwise NOR Immediate {E}",
        "将 {j} 中{e}元素与零扩展的 {i} 位立即数 {i} 按位或后取反，结果写入 {d}。"),
    "VSLL": ("向量{e}逻辑左移", "Vector Shift Left Logical {E}",
        "将 {j} 中{e}元素左移 {k} 对应{e}元素值的低若干位（移位量对 {bits} 取模），结果写入 {d}。"),
    "VSRL": ("向量{e}逻辑右移", "Vector Shift Right Logical {E}",
        "将 {j} 中{e}元素逻辑右移 {k} 对应{e}元素值的低若干位（移位量对 {bits} 取模），高位补零，结果写入 {d}。"),
    "VSRA": ("向量{e}算术右移", "Vector Shift Right Arithmetic {E}",
        "将 {j} 中{e}元素算术右移 {k} 对应{e}元素值的低若干位（移位量对 {bits} 取模），高位按符号位补齐，结果写入 {d}。"),
    "VSLLI": ("向量{e}立即数逻辑左移", "Vector Shift Left Logical Immediate {E}",
        "将 {j} 中{e}元素左移 {i} 位，结果写入 {d}。"),
    "VSRLI": ("向量{e}立即数逻辑右移", "Vector Shift Right Logical Immediate {E}",
        "将 {j} 中{e}元素逻辑右移 {i} 位，高位补零，结果写入 {d}。"),
    "VSRAI": ("向量{e}立即数算术右移", "Vector Shift Right Arithmetic Immediate {E}",
        "将 {j} 中{e}元素算术右移 {i} 位，高位按符号位补齐，结果写入 {d}。"),
    "VSRLR": ("向量{e}舍入逻辑右移", "Vector Shift Right Logical Rounded {E}",
        "将 {j} 中{e}元素逻辑右移 {k} 对应{e}元素值（对 {bits} 取模）位，并被移出的最低位加入舍入，结果写入 {d}。"),
    "VSRAR": ("向量{e}舍入算术右移", "Vector Shift Right Arithmetic Rounded {E}",
        "将 {j} 中{e}元素算术右移 {k} 对应{e}元素值（对 {bits} 取模）位，并被移出的最低位加入舍入，结果写入 {d}。"),
    "VSRLRI": ("向量{e}立即数舍入逻辑右移", "Vector Shift Right Logical Rounded Immediate {E}",
        "将 {j} 中{e}元素逻辑右移 {i} 位并加入被移出的最低位舍入，结果写入 {d}。"),
    "VSRARI": ("向量{e}立即数舍入算术右移", "Vector Shift Right Arithmetic Rounded Immediate {E}",
        "将 {j} 中{e}元素算术右移 {i} 位并加入被移出的最低位舍入，结果写入 {d}。"),
    "VROTR": ("向量{e}循环右移", "Vector Rotate Right {E}",
        "将 {j} 中{e}元素循环右移 {k} 对应{e}元素值（对 {bits} 取模）位，结果写入 {d}。"),
    "VROTRI": ("向量{e}立即数循环右移", "Vector Rotate Right Immediate {E}",
        "将 {j} 中{e}元素循环右移 {i} 位，结果写入 {d}。"),
    "VSLLWIL": ("向量{mix}{s}左移加宽{e}立即数", "Vector Shift Left Widening {E} from {S} Immediate",
        "将 {j} 中{jsig}{s}元素扩展到{e}宽度后左移 {i} 位，取低{bits}位写入 {d} 的对应{e}元素。"),
    "VSRLN": ("向量{mix}{s}逻辑右移窄化{e}", "Vector Narrowing Logical Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素逻辑右移 {k} 元素值（对 {sbits} 取模）位，取低{bits}位作为{e}元素写入 {d} 低半，{d} 高半清零。"),
    "VSRAN": ("向量{mix}{s}算术右移窄化{e}", "Vector Narrowing Arithmetic Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素算术右移 {k} 元素值（对 {sbits} 取模）位，取低{bits}位作为{e}元素写入 {d} 低半，{d} 高半清零。"),
    "VSRLRN": ("向量{mix}{s}舍入逻辑右移窄化{e}", "Vector Narrowing Rounding Logical Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素逻辑右移 {k} 元素值（对 {sbits} 取模）位（含舍入），取低{bits}位写入 {d} 低半，{d} 高半清零。"),
    "VSRARN": ("向量{mix}{s}舍入算术右移窄化{e}", "Vector Narrowing Rounding Arithmetic Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素算术右移 {k} 元素值（对 {sbits} 取模）位（含舍入），取低{bits}位写入 {d} 低半，{d} 高半清零。"),
    "VSSRLN": ("向量{mix}{s}逻辑右移{ssat}饱和窄化{e}", "Vector Narrowing Saturating Logical Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素逻辑右移 {k} 元素值（对 {sbits} 取模）位，取低{bits}位并饱和到{ssat}{e}元素范围写入 {d} 低半，{d} 高半清零。"),
    "VSSRAN": ("向量{mix}{s}算术右移{ssat}饱和窄化{e}", "Vector Narrowing Saturating Arithmetic Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素算术右移 {k} 元素值（对 {sbits} 取模）位，取低{bits}位并饱和到{ssat}{e}元素范围写入 {d} 低半，{d} 高半清零。"),
    "VSSRLRN": ("向量{mix}{s}舍入逻辑右移{ssat}饱和窄化{e}", "Vector Narrowing Saturating Rounding Logical Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素舍入逻辑右移后取低{bits}位，饱和到{ssat}{e}元素范围写入 {d} 低半，{d} 高半清零。"),
    "VSSRARN": ("向量{mix}{s}舍入算术右移{ssat}饱和窄化{e}", "Vector Narrowing Saturating Rounding Arithmetic Right Shift {E} from {S}",
        "将 {j} 与 {k} 中对应{sig}{s}元素舍入算术右移后取低{bits}位，饱和到{ssat}{e}元素范围写入 {d} 低半，{d} 高半清零。"),
    "VSRLNI": ("向量{mix}{s}逻辑右移窄化{e}立即数", "Vector Narrowing Logical Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素逻辑右移 {i} 位，取低{bits}位写入 {d} 低半；{d} 高半原{s}元素同样右移后写入 {d} 高半。"),
    "VSRANI": ("向量{mix}{s}算术右移窄化{e}立即数", "Vector Narrowing Arithmetic Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素算术右移 {i} 位，取低{bits}位写入 {d} 低半；{d} 高半原{s}元素同样右移后写入 {d} 高半。"),
    "VSRLRNI": ("向量{mix}{s}舍入逻辑右移窄化{e}立即数", "Vector Narrowing Rounding Logical Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素舍入逻辑右移 {i} 位写入 {d} 低半；{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VSRARNI": ("向量{mix}{s}舍入算术右移窄化{e}立即数", "Vector Narrowing Rounding Arithmetic Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素舍入算术右移 {i} 位写入 {d} 低半；{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VSSRLNI": ("向量{mix}{s}逻辑右移{ssat}饱和窄化{e}立即数", "Vector Narrowing Saturating Logical Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素逻辑右移 {i} 位并饱和到{ssat}{e}元素范围写入 {d} 低半；{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VSSRANI": ("向量{mix}{s}算术右移{ssat}饱和窄化{e}立即数", "Vector Narrowing Saturating Arithmetic Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素算术右移 {i} 位并饱和到{ssat}{e}元素范围写入 {d} 低半；{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VSSRLRNI": ("向量{mix}{s}舍入逻辑右移{ssat}饱和窄化{e}立即数", "Vector Narrowing Saturating Rounding Logical Right Shift Immediate {E} from {S}",
        "将 {j} 低半部分的{s}元素舍入逻辑右移 {i} 位并饱和写入 {d} 低半；{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VSSRARNI": ("向量{mix}{s}舍入算术右移{ssat}饱和窄化{e}立即数", "Vector Narrowing Saturating Rounding Arithmetic Right Shift Immediate {E} from {S}",
        "将 {j} 低半{s}元素舍入算术右移 {i} 位并饱和写入 {d} 低半，{d} 高半原{s}元素同样处理写入 {d} 高半。"),
    "VBITCLR": ("向量{e}位清除", "Vector Bit Clear {E}",
        "将 {j} 中{e}元素的第（{k} 对应{e}元素值对 {bits} 取模）位清零，结果写入 {d}。"),
    "VBITCLRI": ("向量{e}立即数位清除", "Vector Bit Clear Immediate {E}",
        "将 {j} 中{e}元素的第 {i} 位（对 {bits} 取模）清零，结果写入 {d}。"),
    "VBITSET": ("向量{e}位置位", "Vector Bit Set {E}",
        "将 {j} 中{e}元素的第（{k} 对应{e}元素值对 {bits} 取模）位置 1，结果写入 {d}。"),
    "VBITSETI": ("向量{e}立即数位置位", "Vector Bit Set Immediate {E}",
        "将 {j} 中{e}元素的第 {i} 位（对 {bits} 取模）置 1，结果写入 {d}。"),
    "VBITREV": ("向量{e}位反转", "Vector Bit Reverse {E}",
        "将 {j} 中{e}元素的第（{k} 对应{e}元素值对 {bits} 取模）位取反，结果写入 {d}。"),
    "VBITREVI": ("向量{e}立即数位反转", "Vector Bit Reverse Immediate {E}",
        "将 {j} 中{e}元素的第 {i} 位（对 {bits} 取模）取反，结果写入 {d}。"),
    "VBITSEL": ("向量按位选择", "Vector Bit Select",
        "以 {a} 中的位为选择子逐位选择：位为 1 取 {k} 对应位，为 0 取 {j} 对应位，结果写入 {d}。"),
    "VBITSELI": ("向量{e}立即数按位选择", "Vector Bit Select Immediate {E}",
        "以 {d} 原值为选择子逐位选择：位为 1 时取立即数 {i} 的对应位（0 或 1），位为 0 时取 {j} 的对应位，结果写回 {d}。"),

    # ---- 1.2.3 string ----
    "VBSLL": ("向量字节块左移", "Vector Byte Shift Left",
        "将 {j} 的全部数据按字节左移 {iraw}[3:0] 个字节（`idx = {iraw}[3:0] × 8`），空出的低位补零，结果写入 {d}。"),
    "VBSRL": ("向量字节块右移", "Vector Byte Shift Right",
        "将 {j} 的全部数据按字节右移 {iraw}[3:0] 个字节（`idx = {iraw}[3:0] × 8`），空出的高位补零，结果写入 {d}。"),

    # ---- 1.2.4 floating-point ----
    "VFADD": ("向量{e}浮点加法", "Vector Floating-Point Add {E}",
        "将 {j} 与 {k} 中对应{e}浮点元素相加，结果写入 {d} 的对应{e}元素。"),
    "VFSUB": ("向量{e}浮点减法", "Vector Floating-Point Subtract {E}",
        "将 {j} 中{e}浮点元素减去 {k} 中对应{e}元素，结果写入 {d} 的对应{e}元素。"),
    "VFMUL": ("向量{e}浮点乘法", "Vector Floating-Point Multiply {E}",
        "将 {j} 与 {k} 中对应{e}浮点元素相乘，结果写入 {d} 的对应{e}元素。"),
    "VFDIV": ("向量{e}浮点除法", "Vector Floating-Point Divide {E}",
        "将 {j} 中{e}浮点元素除以 {k} 中对应{e}元素，结果写入 {d} 的对应{e}元素。"),
    "VFMAX": ("向量{e}浮点取最大", "Vector Floating-Point Maximum {E}",
        "取 {j} 与 {k} 中对应{e}浮点元素的较大者（IEEE maxNum：有 NaN 时返回数值一方），写入 {d}。"),
    "VFMIN": ("向量{e}浮点取最小", "Vector Floating-Point Minimum {E}",
        "取 {j} 与 {k} 中对应{e}浮点元素的较小者（IEEE minNum：有 NaN 时返回数值一方），写入 {d}。"),
    "VFMAXA": ("向量{e}浮点取绝对值最大", "Vector Floating-Point Maximum of Absolute Values {E}",
        "取 {j} 与 {k} 中对应{e}浮点元素绝对值的较大者，保留其原符号写入 {d}。"),
    "VFMINA": ("向量{e}浮点取绝对值最小", "Vector Floating-Point Minimum of Absolute Values {E}",
        "取 {j} 与 {k} 中对应{e}浮点元素绝对值的较小者，保留其原符号写入 {d}。"),
    "VFSQRT": ("向量{e}浮点平方根", "Vector Floating-Point Square Root {E}",
        "对 {j} 中{e}浮点元素求精确平方根，结果写入 {d} 的对应{e}元素。"),
    "VFRECIP": ("向量{e}浮点倒数", "Vector Floating-Point Reciprocal {E}",
        "对 {j} 中{e}浮点元素求精确倒数（1/x），结果写入 {d} 的对应{e}元素。"),
    "VFRECIPE": ("向量{e}浮点倒数估计", "Vector Floating-Point Reciprocal Estimate {E}",
        "对 {j} 中{e}浮点元素求倒数近似估计值，结果写入 {d} 的对应{e}元素。"),
    "VFRSQRT": ("向量{e}浮点平方根倒数", "Vector Floating-Point Reciprocal Square Root {E}",
        "对 {j} 中{e}浮点元素求精确平方根倒数（1/√x），结果写入 {d} 的对应{e}元素。"),
    "VFRSQRTE": ("向量{e}浮点平方根倒数估计", "Vector Floating-Point Reciprocal Square Root Estimate {E}",
        "对 {j} 中{e}浮点元素求平方根倒数近似估计值，结果写入 {d} 的对应{e}元素。"),
    "VFMADD": ("向量{e}浮点乘加", "Vector Floating-Point Fused Multiply-Add {E}",
        "计算 `{j} × {k} + {a}`（融合乘加，仅末尾一次舍入），结果写入 {d} 的对应{e}元素。"),
    "VFMSUB": ("向量{e}浮点乘减", "Vector Floating-Point Fused Multiply-Subtract {E}",
        "计算 `{j} × {k} − {a}`（融合乘加，仅末尾一次舍入），结果写入 {d} 的对应{e}元素。"),
    "VFNMADD": ("向量{e}浮点负乘加", "Vector Floating-Point Negate Fused Multiply-Add {E}",
        "计算 `−({j} × {k} + {a})`（融合乘加后取负，仅末尾一次舍入），结果写入 {d} 的对应{e}元素。"),
    "VFNMSUB": ("向量{e}浮点负乘减", "Vector Floating-Point Negate Fused Multiply-Subtract {E}",
        "计算 `−({j} × {k} − {a})`，即 `{a} − {j} × {k}`（仅末尾一次舍入），结果写入 {d} 的对应{e}元素。"),
    "VFLOGB": ("向量{e}浮点指数提取", "Vector Floating-Point Exponent Extract {E}",
        "提取 {j} 中{e}浮点元素的指数（logB），结果写入 {d} 的对应{e}元素。"),
    "VFCLASS": ("向量{e}浮点分类", "Vector Floating-Point Class {E}",
        "对 {j} 中{e}浮点元素分类（NaN、无穷、零、正规数、次正规数及其符号），10 位分类码写入 {d} 的对应{e}元素。"),
    "VFRINT": ("向量{e}浮点按当前舍入模式取整", "Vector Floating-Point Round to Integer {E}",
        "将 {j} 中{e}浮点元素按 `FCSR.RM` 当前舍入模式取整为浮点整数，结果写入 {d}。"),
    "VFRINTRM": ("向量{e}浮点向负无穷取整", "Vector Floating-Point Round to Integer toward Minus Infinity {E}",
        "将 {j} 中{e}浮点元素向负无穷取整，结果写入 {d}。"),
    "VFRINTRNE": ("向量{e}浮点就近取整（偶）", "Vector Floating-Point Round to Integer Nearest-Even {E}",
        "将 {j} 中{e}浮点元素按最近偶数舍入取整，结果写入 {d}。"),
    "VFRINTRP": ("向量{e}浮点向正无穷取整", "Vector Floating-Point Round to Integer toward Plus Infinity {E}",
        "将 {j} 中{e}浮点元素向正无穷取整，结果写入 {d}。"),
    "VFRINTRZ": ("向量{e}浮点向零取整", "Vector Floating-Point Round to Integer toward Zero {E}",
        "将 {j} 中{e}浮点元素向零取整，结果写入 {d}。"),
    "VFCMP": ("向量{e}浮点比较", "Vector Floating-Point Compare {E}",
        "按 {i} 指定的条件比较 {j} 与 {k} 中对应{e}浮点元素，条件成立写全 1、否则写 0 到 {d} 的对应{e}元素（条件码见节注）。"),
    "VFRSTP": ("向量{e}首个负元素查找", "Vector Find First Sign-Masked {E}",
        "从 {j} 的{e}元素中找第一个小于 0 的元素下标 idx（无负元素则 idx 为元素总数），将 idx 写入 {d} 的第（{k} 首元素值对 {ln} 取模）个{e}元素。"),
    "VFRSTPI": ("向量{e}首个负元素查找立即数", "Vector Find First Sign-Masked Immediate {E}",
        "从 {j} 的{e}元素中找第一个小于 0 的元素下标 idx（无负元素则 idx 为元素总数），将 idx 写入 {d} 的第（{i} 对 {ln} 取模）个{e}元素。"),
    "VSIGNCOV": ("向量{e}符号复制", "Vector Sign Copy {E}",
        "符号复制：{j} 元素为正取 {k} 对应元素、为负取其相反数、为零取 0，结果写入 {d} 的对应{e}元素。"),

    # ---- 1.2.5 floating-point conversion ----
    "VFCVT": ("向量{s}转{e}浮点转换", "Vector Floating-Point Convert {S} to {E}",
        "将 {j} 与 {k} 中的{s}浮点元素分别转换为{e}浮点元素{cvt_split}。"),
    "VFCVTH": ("向量{s}取高半{e}浮点转换", "Vector Floating-Point Convert High-Half {S} to {E}",
        "将 {j} 中高半部分的{s}浮点元素转换为{e}浮点元素，写入 {d}。"),
    "VFCVTL": ("向量{s}取低半{e}浮点转换", "Vector Floating-Point Convert Low-Half {S} to {E}",
        "将 {j} 中低半部分的{s}浮点元素转换为{e}浮点元素，写入 {d}。"),
    "VFTINT": ("向量{s}浮点转{e}整数", "Vector Floating-Point to Integer {S} to {E}",
        "将 {j}{src2}中的{s}浮点元素按 `FCSR.RM` 当前舍入模式转换为{e}整数元素{cvt_split}，结果写入 {d}；溢出行为受 `FCSR.Enables.I` 控制。"),
    "VFTINTH": ("向量{s}取高半浮点转{e}整数", "Vector Floating-Point to Integer High-Half {S} to {E}",
        "将 {j} 高半部分的{s}浮点元素按 `FCSR.RM` 舍入为{e}整数元素，写入 {d}。"),
    "VFTINTL": ("向量{s}取低半浮点转{e}整数", "Vector Floating-Point to Integer Low-Half {S} to {E}",
        "将 {j} 低半部分的{s}浮点元素按 `FCSR.RM` 舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRM": ("向量{s}浮点向负无穷转{e}整数", "Vector Floating-Point to Integer toward Minus Infinity {S} to {E}",
        "将 {j}{src2}中的{s}浮点元素向负无穷舍入为{e}整数元素，结果写入 {d}{cvt_split}。"),
    "VFTINTRMH": ("向量{s}取高半浮点向负无穷转{e}整数", "Vector Floating-Point to Integer toward Minus Infinity High-Half {S} to {E}",
        "将 {j} 高半{s}浮点元素向负无穷舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRML": ("向量{s}取低半浮点向负无穷转{e}整数", "Vector Floating-Point to Integer toward Minus Infinity Low-Half {S} to {E}",
        "将 {j} 低半{s}浮点元素向负无穷舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRNE": ("向量{s}浮点就近取整（偶）转{e}整数", "Vector Floating-Point to Integer Nearest-Even {S} to {E}",
        "将 {j}{src2}中的{s}浮点元素按最近偶数舍入为{e}整数元素，结果写入 {d}{cvt_split}。"),
    "VFTINTRNEH": ("向量{s}取高半浮点就近取整（偶）转{e}整数", "Vector Floating-Point to Integer Nearest-Even High-Half {S} to {E}",
        "将 {j} 高半{s}浮点元素按最近偶数舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRNEL": ("向量{s}取低半浮点就近取整（偶）转{e}整数", "Vector Floating-Point to Integer Nearest-Even Low-Half {S} to {E}",
        "将 {j} 低半{s}浮点元素按最近偶数舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRP": ("向量{s}浮点向正无穷转{e}整数", "Vector Floating-Point to Integer toward Plus Infinity {S} to {E}",
        "将 {j}{src2}中的{s}浮点元素向正无穷舍入为{e}整数元素，结果写入 {d}{cvt_split}。"),
    "VFTINTRPH": ("向量{s}取高半浮点向正无穷转{e}整数", "Vector Floating-Point to Integer toward Plus Infinity High-Half {S} to {E}",
        "将 {j} 高半{s}浮点元素向正无穷舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRPL": ("向量{s}取低半浮点向正无穷转{e}整数", "Vector Floating-Point to Integer toward Plus Infinity Low-Half {S} to {E}",
        "将 {j} 低半{s}浮点元素向正无穷舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRZ": ("向量{s}浮点向零转{e}整数", "Vector Floating-Point to Integer toward Zero {S} to {E}",
        "将 {j}{src2}中的{s}浮点元素向零舍入为{e}整数元素，结果写入 {d}{cvt_split}。"),
    "VFTINTRZH": ("向量{s}取高半浮点向零转{e}整数", "Vector Floating-Point to Integer toward Zero High-Half {S} to {E}",
        "将 {j} 高半{s}浮点元素向零舍入为{e}整数元素，写入 {d}。"),
    "VFTINTRZL": ("向量{s}取低半浮点向零转{e}整数", "Vector Floating-Point to Integer toward Zero Low-Half {S} to {E}",
        "将 {j} 低半{s}浮点元素向零舍入为{e}整数元素，写入 {d}。"),
    "VFFINT": ("向量{mix}{s}整数转{e}浮点", "Vector Integer to Floating-Point {S} to {E}",
        "将 {j}{src2}中{jsig}{s}整数元素转换为{e}浮点元素，结果写入 {d}{cvt_split}。"),
    "VFFINTH": ("向量{mix}高半{s}整数转{e}浮点", "Vector Integer to Floating-Point High-Half {S} to {E}",
        "将 {j} 高半部分的{jsig}{s}整数元素转换为{e}浮点元素，写入 {d}。"),
    "VFFINTL": ("向量{mix}低半{s}整数转{e}浮点", "Vector Integer to Floating-Point Low-Half {S} to {E}",
        "将 {j} 低半部分的{jsig}{s}整数元素转换为{e}浮点元素，写入 {d}。"),

    # ---- 1.2.6 compare / select ----
    "VSEQ": ("向量{e}相等比较", "Vector Compare Equal {E}",
        "逐{e}元素比较 {j} 与 {k}：相等写全 1、不等写 0 到 {d} 的对应{e}元素。"),
    "VSLE": ("向量{e}小于等于比较", "Vector Compare Less Than or Equal {E}",
        "逐{e}元素比较 {j} 与 {k}（按{sig}数）：小于等于写全 1、否则写 0 到 {d} 的对应{e}元素。"),
    "VSLT": ("向量{e}小于比较", "Vector Compare Less Than {E}",
        "逐{e}元素比较 {j} 与 {k}（按{sig}数）：小于写全 1、否则写 0 到 {d} 的对应{e}元素。"),
    "VSEQI": ("向量{e}立即数相等比较", "Vector Compare Equal Immediate {E}",
        "逐{e}元素比较 {j} 与{exti}立即数 {i}：相等写全 1、不等写 0 到 {d}。"),
    "VSLEI": ("向量{e}立即数小于等于比较", "Vector Compare Less Than or Equal Immediate {E}",
        "逐{e}元素比较 {j}（按{sig}数）与{exti}立即数 {i}：小于等于写全 1、否则写 0 到 {d}。"),
    "VSLTI": ("向量{e}立即数小于比较", "Vector Compare Less Than Immediate {E}",
        "逐{e}元素比较 {j}（按{sig}数）与{exti}立即数 {i}：小于写全 1、否则写 0 到 {d}。"),
    "VSETEQZ": ("向量全零判断", "Vector Test All Elements Zero",
        "判断 {j} 整个寄存器是否为 0，结果（1/0）写入条件标志寄存器 {cd}。"),
    "VSETNEZ": ("向量非全零判断", "Vector Test Not All Elements Zero",
        "判断 {j} 整个寄存器是否非 0，结果（1/0）写入条件标志寄存器 {cd}。"),
    "VSETANYEQZ": ("向量存在零元素判断", "Vector Test Any Element Zero",
        "判断 {j} 中是否存在值为 0 的{e}元素，结果（1/0）写入条件标志寄存器 {cd}。"),
    "VSETALLNEZ": ("向量全部非零判断", "Vector Test All Elements Non-Zero",
        "判断 {j} 中{e}元素是否全部非零，结果（1/0）写入条件标志寄存器 {cd}。"),

    # ---- 1.2.7 shuffle / mix / insert ----
    "VINSGR2VR": ("通用寄存器插入向量{e}元素", "Insert General Register into Vector Element {E}",
        "将 {rj} 的低{bits}位写入 {d} 的第 {i} 个{e}元素，其余元素不变。"),
    "VPICKVE2GR": ("向量{e}元素抽取到通用寄存器", "Pick Vector Element to General Register {E}",
        "将 {j} 的第 {i} 个{e}元素{ext}到{bits}位后写入 {rd}。"),
    "VREPLGR2VR": ("通用寄存器值广播{e}元素", "Broadcast General Register to Vector {E}",
        "将 {rj} 的低{bits}位复制到 {d} 的全部 {n} 个{e}元素。"),
    "VREPLVE": ("按通用寄存器索引广播{e}元素", "Broadcast Selected Element to Vector {E}",
        "取 {j} 的第（{rk} 值对 {ln} 取模）个{e}元素，广播到 {d} 的全部 {n} 个{e}元素。"),
    "VREPLVEI": ("按立即数索引广播{e}元素", "Broadcast Selected Element to Vector Immediate {E}",
        "取 {j} 的第 {i} 个{e}元素，广播到 {d} 的全部 {n} 个{e}元素。"),
    "VREPL128VEI": ("128 位 lane 内按立即数广播{e}元素", "Broadcast Selected Element within 128-bit Lane Immediate {E}",
        "分别在 {j} 的每个 128 位 lane 内取第 {i} 个{e}元素，广播到该 lane 全部 {ln} 个{e}元素，写入 {d}。"),
    "VREPLVE0": ("广播 0 号{e}元素", "Broadcast Element 0 to Vector {E}",
        "取 {j} 的 0 号{e}元素，广播到 {d} 的全部 {n} 个{e}元素。"),
    "VINSVE0": ("插入 0 号{e}元素到指定位置", "Insert Element 0 into Vector {E}",
        "将 {j} 的 0 号{e}元素写入 {d} 的第 {i} 个{e}元素，其余元素保持不变。"),
    "VPICKVE": ("抽取{e}元素到 0 号位", "Pick Vector Element to Position 0 {E}",
        "取 {j} 的第 {i} 个{e}元素写入 {d} 的 0 号{e}元素，{d} 其余位置清零。"),
    "VPACKEV": ("向量{e}偶元素打包", "Vector Pack Even Elements {E}",
        "取 {k} 与 {j} 中下标为偶数（2i）的{e}元素：{k} 的写入 {d} 的第 2i 位、{j} 的写入第 2i+1 位（交织排列），构成新的{e}元素序列写入 {d}。"),
    "VPACKOD": ("向量{e}奇元素打包", "Vector Pack Odd Elements {E}",
        "取 {k} 与 {j} 中下标为奇数（2i+1）的{e}元素：{k} 的写入 {d} 的第 2i 位、{j} 的写入第 2i+1 位（交织排列），构成新的{e}元素序列写入 {d}。"),
    "VPICKEV": ("抽取偶{e}元素", "Vector Pick Even Elements {E}",
        "取 {j} 与 {k} 中下标为偶数（2i）的{e}元素：{j} 的依次放入 {d} 高半、{k} 的放入 {d} 低半，写入 {d}。"),
    "VPICKOD": ("抽取奇{e}元素", "Vector Pick Odd Elements {E}",
        "取 {j} 与 {k} 中下标为奇数（2i+1）的{e}元素：{j} 的依次放入 {d} 高半、{k} 的放入 {d} 低半，写入 {d}。"),
    "VILVL": ("向量{e}低半交织", "Vector Interleave Low {E}",
        "将 {j} 与 {k} 低半部分的{e}元素逐个交织（vk[0], vj[0], vk[1], vj[1], …），写入 {d}。"),
    "VILVH": ("向量{e}高半交织", "Vector Interleave High {E}",
        "将 {j} 与 {k} 高半部分的{e}元素逐个交织（vk[n], vj[n], vk[n+1], vj[n+1], …），写入 {d}。"),
    "VSHUF": ("向量{e}任意重排", "Vector Shuffle {E}",
        "将 {j}（高 128 位）与 {k}（低 128 位）拼接，按 {a} 中每{e}元素给出的索引选取元素写入 {d} 对应{e}元素。"),
    "VSHUF4I": ("向量{e} 4 元素组内重排", "Vector 4-Element Shuffle Immediate {E}",
        "在 {j} 的每 4 个连续{e}元素组内，按 {i} 中对应的 4 个 2 位一组索引重排元素，写入 {d}。"),
    "VPERM": ("向量 256 位跨 lane 字重排", "Vector Permute Word across 256-bit",
        "以 {k} 中第 i 个字元素值（对 8 取模）为索引，从 {j} 的 8 个字元素中选取写入 {d} 的第 i 个字元素。"),
    "VPERMI": ("向量{e}立即数重排", "Vector Permute Immediate {E}",
        "按 {i} 中每{e}对应的 2 位一组索引重排：第 0、1 个{e}元素从 {j} 选取（{i}[1:0]、{i}[3:2]），第 2、3 个{e}元素从 {d} 原值选取（{i}[5:4]、{i}[7:6]），结果写入 {d}{permextra}。"),
    "VEXTRINS": ("向量{e}元素插入", "Vector Extract and Insert {E}",
        "用 {i} 高位字段指定的下标从 {j} 取{e}元素，写入 {d} 中 {i} 低位字段指定的{e}元素位置（其余元素不变）。"),
    "VHSELI": ("向量双字立即数选择插入（语义待补）", "Vector Half Shuffle Insert Immediate Doubleword",
        "官方手册正文未描述该指令语义（见勘误清单），编码与助记符已按附录 B 核对。"),

    # ---- 1.2.8 memory ----
    "VLD": ("向量装载 128 位", "Vector Load 128-bit",
        "从 `GR[rj] + 符号扩展 {iraw}` 的地址连续装载 16 字节写入 {d}。不触发地址非对齐异常。"),
    "VLDX": ("向量装载 128 位（寄存器偏移）", "Vector Load 128-bit Indexed",
        "从 `GR[rj] + GR[rk]` 的地址连续装载 16 字节写入 {d}。不触发地址非对齐异常。"),
    "VST": ("向量存储 128 位", "Vector Store 128-bit",
        "将 {d} 的 16 字节连续存储到 `GR[rj] + 符号扩展 {iraw}` 的地址。不触发地址非对齐异常。"),
    "VSTX": ("向量存储 128 位（寄存器偏移）", "Vector Store 128-bit Indexed",
        "将 {d} 的 16 字节连续存储到 `GR[rj] + GR[rk]` 的地址。不触发地址非对齐异常。"),
    "VLDREPL": ("装载{e}并广播", "Vector Load and Broadcast Element {E}",
        "从 `GR[rj] + 符号扩展 {iraw} × 元素宽度` 的地址读取一个{e}元素，广播填充 {d} 的全部 {n} 个{e}元素。汇编中的偏移立即数以字节为单位。"),
    "VSTELM": ("存储指定{e}元素", "Vector Store Selected Element {E}",
        "将 {d} 的第 {idx} 个{e}元素存储到 `GR[rj] + 符号扩展 {iraw} × 元素宽度` 的地址。汇编中的偏移立即数以字节为单位。"),
}

# per-mnemonic template overrides (family entry does not fit every variant)
FAMILY_OVERRIDES: dict[str, tuple[str, str, str]] = {
    # XVPERMI.D selects all four doublewords from xj (unlike [X]VPERMI.W)
    "xvpermi.d": ("向量双字立即数重排", "Vector Permute Immediate Doubleword",
        "按 `ui8` 中每双字对应的 2 位一组索引，从 `xj` 的 4 个双字元素中选取依次写入 `xd` 的 4 个双字元素。"),
}

# ---------------------------------------------------------------------------
# memory-access pseudocode the manual omits (addr helpers, per element)


def _mem_pseudo() -> dict[str, str]:
    out = {}
    grlen = "GRLEN"
    out["vld"] = "VR[vd] = Mem[GR[rj] + SignExtend(si12, %s)]" % grlen
    out["vst"] = "Mem[GR[rj] + SignExtend(si12, %s)] = VR[vd]" % grlen
    out["vldx"] = "VR[vd] = Mem[GR[rj] + GR[rk]]"
    out["vstx"] = "Mem[GR[rj] + GR[rk]] = VR[vd]"
    out["xvld"] = "XR[xd] = Mem[GR[rj] + SignExtend(si12, %s)]" % grlen
    out["xvst"] = "Mem[GR[rj] + SignExtend(si12, %s)] = XR[xd]" % grlen
    out["xvldx"] = "XR[xd] = Mem[GR[rj] + GR[rk]]"
    out["xvstx"] = "Mem[GR[rj] + GR[rk]] = XR[xd]"
    repl = {
        "b": ("si12", 0, "B"), "h": ("si11", 1, "H"),
        "w": ("si10", 2, "W"), "d": ("si9", 3, "D"),
    }
    for suf, (imm, sh, elem) in repl.items():
        n_v = {"B": 16, "H": 8, "W": 4, "D": 2}[elem]
        n_x = n_v * 2  # 256-bit register
        addr = "GR[rj] + SignExtend(%s, %s)" % (imm, grlen) if sh == 0 else \
            "GR[rj] + SignExtend(%s << %d, %s)" % (imm, sh, grlen)
        out["vldrepl." + suf] = (
            "addr = %s\nfor i in range(%d):\n    VR[vd].%s[i] = Mem[addr][%d:0]"
            % (addr, n_v, elem, INT_ELEM[elem][2] - 1))
        out["xvldrepl." + suf] = (
            "addr = %s\nfor i in range(%d):\n    XR[xd].%s[i] = Mem[addr][%d:0]"
            % (addr, n_x, elem, INT_ELEM[elem][2] - 1))
        # VSTELM/XVSTELM always use si8, scaled by the element position
        saddr = ("GR[rj] + SignExtend(si8, %s)" % grlen) if sh == 0 else \
            ("GR[rj] + SignExtend(si8 << %d, %s)" % (sh, grlen))
        out["vstelm." + suf] = (
            "addr = %s\nMem[addr][%d:0] = VR[vd].%s[idx]"
            % (saddr, INT_ELEM[elem][2] - 1, elem))
        out["xvstelm." + suf] = (
            "addr = %s\nMem[addr][%d:0] = XR[xd].%s[idx]"
            % (saddr, INT_ELEM[elem][2] - 1, elem))
    return out


MEM_PSEUDO = _mem_pseudo()

# pseudocode lines with known manual typos -> corrected text (per mnemonic)
PSEUDO_FIXES = {
    # 1.2.1 xvclz.w: printed as "XR[xj].W[i] = CLZ(XR[i].W[xj])"
    "xvclz.w": "for i in range(8):\nXR[xd].W[i] = CLZ(XR[xj].W[i])",
    # 1.2.1.18: loop bound 16 copies the whole register; W has 4 / D has 2 elements
    "vsat.w": "for i in range(4):\nVR[vd].W[i] = Sat_S(VR[vj].W[i], ui5)",
    "vsat.d": "for i in range(2):\nVR[vd].D[i] = Sat_S(VR[vj].D[i], ui6)",
    "vsat.wu": "for i in range(4):\nVR[vd].W[i] = Sat_U(VR[vj].W[i], ui5)",
    "vsat.du": "for i in range(2):\nVR[vd].D[i] = Sat_U(VR[vj].D[i], ui6)",
    "xvsat.w": "for i in range(8):\nXR[xd].W[i] = Sat_S(XR[xj].W[i], ui5)",
    "xvsat.d": "for i in range(4):\nXR[xd].D[i] = Sat_S(XR[xj].D[i], ui6)",
    "xvsat.wu": "for i in range(8):\nXR[xd].W[i] = Sat_U(XR[xj].W[i], ui5)",
    "xvsat.du": "for i in range(4):\nXR[xd].D[i] = Sat_U(XR[xj].D[i], ui6)",
    # 1.2.3.1: manual merges two statements per line (m = ... VR[vd].B[m] = idx)
    "vfrstpi.b": "idx = 0\nfor i in range(16):\n    if VR[vj].B[i] < 0: break\n    idx = idx + 1\nm = ui5 % 16\nVR[vd].B[m] = idx",
    "vfrstpi.h": "idx = 0\nfor i in range(8):\n    if VR[vj].H[i] < 0: break\n    idx = idx + 1\nm = ui5 % 8\nVR[vd].H[m] = idx",
    "xvfrstpi.b": ("idx0 = 0\nfor i in range(16):\n    if XR[xj].B[i] < 0: break\n    idx0 = idx0 + 1\nm = ui5 % 16\nXR[xd].B[m] = idx0\n"
                   "idx1 = 0\nfor i in range(16, 32, 1):\n    if XR[xj].B[i] < 0: break\n    idx1 = idx1 + 1\nXR[xd].B[m] = idx1"),
    "xvfrstpi.h": ("idx0 = 0\nfor i in range(8):\n    if XR[xj].H[i] < 0: break\n    idx0 = idx0 + 1\nm = ui5 % 8\nXR[xd].H[m] = idx0\n"
                   "idx1 = 0\nfor i in range(8, 16, 1):\n    if XR[xj].H[i] < 0: break\n    idx1 = idx1 + 1\nXR[xd].H[m] = idx1"),
    # XVFRSTP.*: "XR[xd].B[m0] = idx0 idx1 = 0" also merged on one line
    "xvfrstp.b": ("idx0 = 0\nfor i in range(16):\n    if XR[xj].B[i] < 0: break\n    idx0 = idx0 + 1\nm0 = XR[xk].B[0] % 16\nXR[xd].B[m0] = idx0\n"
                  "idx1 = 0\nfor i in range(16, 32, 1):\n    if XR[xj].B[i] < 0: break\n    idx1 = idx1 + 1\nm1 = XR[xk].B[16] % 16\nXR[xd].B[m1] = idx1"),
    "xvfrstp.h": ("idx0 = 0\nfor i in range(8):\n    if XR[xj].H[i] < 0: break\n    idx0 = idx0 + 1\nm0 = XR[xk].H[0] % 8\nXR[xd].H[m0] = idx0\n"
                  "idx1 = 0\nfor i in range(8, 16, 1):\n    if XR[xj].H[i] < 0: break\n    idx1 = idx1 + 1\nm1 = XR[xk].H[8] % 8\nXR[xd].H[m1] = idx1"),
}

# systematic misprints applied to every pseudocode block
PSEUDO_GLOBAL_FIXES = [
    ("XR[vd]", "XR[xd]"),
    ("XR[vj]", "XR[xj]"),
    ("XR[vk]", "XR[xk]"),
    ("XR[va]", "XR[xa]"),
    ("XR[x_j]", "XR[xd]"),
    ("VR[xd]", "VR[vd]"),
    ("VR[xj]", "VR[vj]"),
    ("VR[xk]", "VR[vk]"),
    ("VR[xa]", "VR[va]"),
    ("VR[v_j]", "VR[vj]"),
    ("FCSR. RM", "FCSR.RM"),
    ("FCSR. Enables", "FCSR.Enables"),
]

# per-mnemonic notes (html) for tricky families
SECTION_NOTES: dict[str, dict[str, str]] = {}


def _build_section_notes() -> dict[str, dict[str, str]]:
    cond_list = ("CAF、CUN、CEQ、CUEQ、CLT、CULT、CLE、CULE、CNE、COR、CUNE、"
                 "SAF、SUN、SEQ、SUEQ、SLT、SULT、SLE、SULE、SNE、SOR、SUNE")
    cmp_html = (
        "<p><code>cond</code> 为 5 位立即数，可取 22 种比较条件（汇编时替换 "
        "<code>.cond.</code> 为对应条件助记符，如 <code>vfcmp.ceq.s</code>）："
        f"{cond_list}。前缀 C 表示有序比较（NaN 时结果为假），S 表示无序比较"
        "（NaN 时结果为真）；后缀 F=假、UN=无序、EQ=相等、LT=小于、LE=小于等于、"
        "NE=不等、OR=无序或相等、UNE=无序或不等、ULT=无序或小于、ULE=无序或小于等于。</p>")
    for mn in ("vfcmp.cond.s", "vfcmp.cond.d", "xvfcmp.cond.s", "xvfcmp.cond.d"):
        SECTION_NOTES[mn] = {"title": "浮点比较条件码", "html": cmp_html}
    mem_html = (
        "<p>地址偏移以字节为单位的立即数在指令码中按元素宽度缩放编码："
        "<code>vldrepl.h</code>/<code>xvldrepl.h</code> 汇编偏移对应 "
        "<code>si11 &lt;&lt; 1</code>；<code>.w</code> 对应 <code>si10 &lt;&lt; 2</code>；"
        "<code>.d</code> 对应 <code>si9 &lt;&lt; 3</code>；"
        "<code>vstelm.h</code>/<code>xvstelm.h</code> 对应 <code>si8 &lt;&lt; 1</code>，"
        "<code>.w</code> 对应 <code>si8 &lt;&lt; 2</code>，"
        "<code>.d</code> 对应 <code>si8 &lt;&lt; 3</code>（<code>.b</code> 无缩放）。</p>"
        "<p>这些访存指令不触发地址非对齐异常。</p>")
    for mn in ("vldrepl.b", "vldrepl.h", "vldrepl.w", "vldrepl.d",
               "xvldrepl.b", "xvldrepl.h", "xvldrepl.w", "xvldrepl.d",
               "vstelm.b", "vstelm.h", "vstelm.w", "vstelm.d",
               "xvstelm.b", "xvstelm.h", "xvstelm.w", "xvstelm.d"):
        SECTION_NOTES[mn] = {"title": "访存地址计算", "html": mem_html}
    ldi_html = (
        "<p>13 位立即数 <code>i13</code> 的最高位选择数据生成模式：</p>"
        "<ul><li><code>i13[12]=0</code>：低 10 位按 2 位模式位复制填充——"
        "<code>00</code>=8 位重复 8 次、<code>01</code>=10 位符号扩展为 16 位重复 4 次、"
        "<code>10</code>=符号扩展为 32 位重复 2 次、<code>11</code>=符号扩展为 64 位。</li>"
        "<li><code>i13[12]=1</code>：按 4 位模式位生成 32/64 位数据，共 13 种模式"
        "（字节重复、字节移位、位掩码广播、浮点零/单/双精度零等，详见手册附录 A "
        "<code>Set_Value</code> 定义）。</li></ul>"
        "<p>生成的 64 位数据复制填充目标寄存器的每个 64 位块。</p>")
    for mn in ("vldi", "xvldi"):
        SECTION_NOTES[mn] = {"title": "立即数模式", "html": ldi_html}
    sat_html = (
        "<p>本指令为 LA Vector V1.1 新增语义：按<strong>有效位</strong>饱和，而非按元素宽度饱和。"
        "对有符号元素 <code>Sat_S(x, y)</code>：若 <code>x &gt; 2^y−1</code> 结果为 "
        "<code>2^y−1</code>，若 <code>x &lt; −2^y</code> 结果为 <code>−2^y</code>；"
        "无符号元素 <code>Sat_U(x, y)</code>：若 <code>x &gt; 2^y−1</code> 结果为 "
        "<code>2^y−1</code>。立即数 <code>ui3/ui4/ui5/ui6</code> 给出有效位宽 y。</p>")
    for mn in ("vsat.b", "vsat.h", "vsat.w", "vsat.d",
               "vsat.bu", "vsat.hu", "vsat.wu", "vsat.du",
               "xvsat.b", "xvsat.h", "xvsat.w", "xvsat.d",
               "xvsat.bu", "xvsat.hu", "xvsat.wu", "xvsat.du"):
        SECTION_NOTES[mn] = {"title": "按有效位饱和", "html": sat_html}
    rm_html = (
        "<p>舍入模式取自 <code>FCSR.RM</code>：0=就近舍入（偶）、1=向零、"
        "2=向正无穷、3=向负无穷。转换结果的溢出/无效标志写入 "
        "<code>FCSR</code> 对应 cause/flag 位。</p>")
    for mn in ("vfrint.s", "vfrint.d", "xvfrint.s", "xvfrint.d",
               "vftint.w.s", "vftint.w.d", "vftint.l.d", "vftint.wu.s",
               "vftint.lu.d", "vftinth.l.s", "vftintl.l.s",
               "xvftint.w.s", "xvftint.w.d", "xvftint.l.d", "xvftint.wu.s",
               "xvftint.lu.d", "xvftinth.l.s", "xvftintl.l.s"):
        SECTION_NOTES[mn] = {"title": "舍入模式", "html": rm_html}
    q_html = (
        "<p>结果 <code>Q[0]</code> 由 <code>ui8[1:0]</code> 从拼接向量（低 lane 的 2 个四字、"
        "高 lane 的 2 个四字）中选取，<code>Q[1]</code> 由 <code>ui8[5:4]</code> 选取；"
        "<code>ui8[3:2]</code> 与 <code>ui8[7:6]</code> 必须为 0，否则结果未定义。</p>")
    SECTION_NOTES["xvpermi.q"] = {"title": "索引约束", "html": q_html}
    return SECTION_NOTES


SECTION_NOTES = _build_section_notes()


# ---------------------------------------------------------------------------
# per-instruction analysis


def is_float_base(base: str) -> bool:
    return base in FLOAT_BASES


def parse_variant(mnemonic: str) -> dict:
    """Split a mnemonic into base + suffix segments and per-segment info."""
    upper = mnemonic.upper()
    base = upper
    xv = False
    if base.startswith("XV"):
        xv = True
        base = "V" + base[2:]
    parts = base.split(".")
    fam = parts[0]
    sufs = upper.split(".")[1:]  # original (keeps COND etc.)
    return {"xv": xv, "fam": fam, "sufs": sufs, "base": base}


def elem_info(code: str, flt: bool) -> tuple[str, str, int, bool]:
    """code like 'B', 'BU', 'HU' -> (cn, en, bits, unsigned)."""
    unsigned = code.endswith("U")
    letter = code[0] if code else ""
    if letter == "V":  # whole-register suffix (VAND.V, VSETEQZ.V, ...)
        return ("128 位", "128-bit", 128, unsigned)
    tables = [FLT_ELEM, INT_ELEM] if flt else [INT_ELEM, FLT_ELEM]
    for tbl in tables:
        if letter in tbl:
            cn, en, bits = tbl[letter]
            return cn, en, bits, unsigned
    if letter == "L":  # "long": 64-bit integer element (= D)
        return ("双字", "Doubleword", 64, unsigned)
    raise KeyError(letter)


def build_vars(mnemonic: str, operands: str) -> dict:
    v = parse_variant(mnemonic)
    fam = v["fam"]
    xv = v["xv"] or fam == "VEXT2XV"  # VEXT2XV operates on XR registers
    flt = is_float_base(fam)
    R = ("x" if xv else "v")
    vars = {
        "d": f"`{R}d`", "j": f"`{R}j`", "k": f"`{R}k`", "a": f"`{R}a`",
        "rd": "`rd`", "rj": "`rj`", "rk": "`rk`", "cd": "`cd`",
    }
    s_bits = 0
    s_flt = False
    sufs = v["sufs"]
    # drop 'COND' marker for vfcmp
    sufs_clean = [s for s in sufs if s != "COND"]

    # determine result / source elements
    e_cn = e_en = ""
    s_cn = s_en = ""
    e_bits = 0
    e_uns = s_uns = False
    if flt and fam in CVT_BASES and len(sufs_clean) == 2:
        # e.g. VFCVT.H.S: dst H from src S; VFFINT: int src; VFTINT: float src
        e_cn, e_en, e_bits, _ = elem_info(sufs_clean[0], flt=True)
        src_flt = not fam.startswith("VFF")
        s_cn, s_en, _, s_uns = elem_info(sufs_clean[1], flt=src_flt)
        s_flt = src_flt
    elif fam in WIDEN_BASES and len(sufs_clean) == 2:
        e_cn, e_en, e_bits, e_uns = elem_info(sufs_clean[0], flt=False)
        s_cn, s_en, s_bits, s_uns = elem_info(sufs_clean[1], flt=False)
        s_flt = False
    elif fam in MIXED_FAMS and len(sufs_clean) == 3:
        # dst.srcU.src (e.g. VADDWOD.W.HU.H)
        e_cn, e_en, e_bits, e_uns = elem_info(sufs_clean[0], flt=False)
        s_cn, s_en, s_bits, s_uns = elem_info(sufs_clean[1].rstrip("U"), flt=False)
        s_flt = False
    elif fam in NARROW_BASES and len(sufs_clean) == 2:
        e_cn, e_en, e_bits, e_uns = elem_info(sufs_clean[0], flt=False)
        s_cn, s_en, s_bits, s_uns = elem_info(sufs_clean[1], flt=False)
        s_flt = False
    elif sufs_clean:
        e_cn, e_en, e_bits, e_uns = elem_info(sufs_clean[-1], flt=flt)
        s_flt = False
    else:
        # whole-register ops (VAND.V, VLD...) or no suffix
        e_bits = 256 if xv else 128
        e_cn, e_en = ("256 位", "256-bit") if xv else ("128 位", "128-bit")
        s_flt = False
    if not s_bits:
        s_bits = e_bits

    # immediate name = first operand that is a numeral field
    imms = [op for op in (o.strip() for o in operands.split(","))
            if re.fullmatch(r"([su]i[0-9]+|i13|cond|idx)", op)]
    vars["i"] = f"`{imms[0]}`" if imms else ""
    vars["iraw"] = imms[0] if imms else ""
    if fam == "VFCMP":  # cond is part of the mnemonic, not the operand list
        vars["i"] = "`cond`"
        vars["iraw"] = "cond"
    vars["idx"] = "`idx`"
    vars["e"] = e_cn
    vars["E"] = e_en
    vars["s"] = s_cn
    vars["S"] = s_en
    vars["bits"] = e_bits
    vars["sbits"] = s_bits
    lane = 256 if xv else 128
    vars["n"] = lane // e_bits if e_bits else 1
    vars["ln"] = 128 // e_bits if e_bits else 1

    # signedness words
    def sigw(u):
        return "无符号" if u else "有符号"

    if fam in MIXED_FAMS and len(sufs_clean) == 3:
        # dst.srcU.src: j unsigned, k signed
        jsig, ksig = sigw(sufs_clean[1].endswith("U")), sigw(sufs_clean[2].endswith("U"))
    elif fam in WIDEN_BASES | NARROW_BASES and len(sufs_clean) == 2:
        src_uns = sufs_clean[1].endswith("U")
        jsig = ksig = sigw(src_uns)
    elif fam in CVT_BASES and s_flt:
        jsig = ksig = ""  # float source: no signedness wording
    else:
        jsig = ksig = sigw(e_uns)
    vars["sig"] = jsig
    vars["jsig"], vars["ksig"] = jsig, ksig
    vars["jksig"] = jsig if jsig == ksig else f"{jsig}/{ksig}"

    # mixed-sign phrase for cn/en names
    if jsig != ksig:
        mix, mixE = "无符号·有符号", "Mixed-Sign "
    elif jsig == "无符号":
        mix, mixE = "无符号", "Unsigned "
    else:
        mix, mixE = "", ""
    vars["mix"], vars["MixE"] = mix, mixE

    # saturating narrow families: saturation kind follows the dst (e) element
    vars["ssat"] = "无符号" if e_uns else "有符号"

    # extension word (only used where unambiguous: VPICKVE2GR)
    vars["ext"] = "零扩展" if e_uns else "符号扩展"
    # immediate extension wording (VSLEI.BU zero-extends, VSLEI.B sign-extends)
    vars["exti"] = "零扩展" if e_uns else "符号扩展"

    # second-source phrase and split-destination phrase for two-register converts
    ops = [o.strip() for o in operands.split(",")]
    has_k = "vk" in ops or "xk" in ops
    vars["src2"] = f"（及 {vars['k']}）" if has_k else ""
    vars["cvt_split"] = (
        f"（{vars['j']} 的结果写入 {vars['d']} 高半，{vars['k']} 的写入 {vars['d']} 低半）"
        if has_k else "")
    # VPERMI extra lane text (only the .W variants read the destination)
    vars["permextra"] = (
        "；每个 128 位 lane 独立进行，第 4–7 个元素的下标加 4"
        if xv and fam == "VPERMI" and (sufs_clean and sufs_clean[-1] == "W") else "")
    return vars


def fill_names(mnemonic: str, operands: str) -> tuple[str, str, str]:
    v = parse_variant(mnemonic)
    fam = v["fam"]
    if mnemonic in FAMILY_OVERRIDES:
        cn_t, en_t, desc_t = FAMILY_OVERRIDES[mnemonic]
    elif fam not in FAMILIES:
        raise KeyError(f"no family entry for {fam} ({mnemonic})")
    else:
        cn_t, en_t, desc_t = FAMILIES[fam]
    vars = build_vars(mnemonic, operands)

    def fmt(template: str) -> str:
        out = template
        for _ in range(3):
            try:
                out = out.format(**vars)
                break
            except (KeyError, IndexError, ValueError):
                # strip unknown placeholder groups progressively
                out = re.sub(r"\{[a-zA-Z]+\}", "", out)
        return out

    cn = fmt(cn_t)
    en = fmt(en_t)
    if vars["jsig"] != vars["ksig"] and v["fam"] in MIXED_FAMS:
        en = en.replace("Vector ", "Vector Mixed-Sign ", 1)
    return cn, en, fmt(desc_t)


def pick_equation(pseudo: str) -> str:
    lines = pseudo.splitlines()
    cands = [l.strip() for l in lines if "=" in l and not l.strip().startswith("#")]

    def score(l: str) -> int:
        s = 0
        if re.match(r"^(VR|XR)\[[a-z]+\]\.\w", l) or re.match(r"^(VR|XR)\[[a-z]+\]\s*=", l):
            s += 6
        elif re.match(r"^(CFR|GR)\[[a-z]+\]", l):
            s += 6
        if re.search(r"SignExtend|ZeroExtend|Abs_|Abs\(|Max_|Min_|Sat_|ROTR|SLL|SRL|SRA|"
                     r"CLZ|CLO|PCNT|Bit_|Extend|FP|\+|-|\*|/|&|\||\^|==|!=|<<|>>", l):
            s += 2
        if re.match(r"^(vec|t0|t1|t\b|idx|product|m\b|data|bool_res|shft_res|shft_res)", l):
            s -= 6
        if re.match(r"^(VR|XR)\[[a-z]+\]\s*=\s*0*$", l):
            s -= 6
        return s

    if cands:
        return max(cands, key=score)
    return lines[0] if lines else ""


def simplify_comment(equation: str, mnemonic: str) -> str:
    """Turn an equation into a short `# ...` assembly comment."""
    if not equation:
        return ""
    c = equation.strip()
    # innermost-first: collapse element index brackets (handles [ui8[1:0]])
    for _ in range(3):
        new = re.sub(r"\.(\w+)\[[^()\[\]]*\]", r".\1", c)
        if new == c:
            break
        c = new
    c = re.sub(r"\b(VR|XR)\[(v[djka]|x[djka])\]", lambda m: "$" + (
        "vr" if m.group(1) == "VR" else "xr") + {"vd": "0", "xd": "0", "vj": "1",
        "xj": "1", "vk": "2", "xk": "2", "va": "3", "xa": "3"}[m.group(2)], c)
    c = re.sub(r"GR\[rd\]", "$a0", c)
    c = re.sub(r"CFR\[cd\]", "$fcc0", c)
    c = re.sub(r"(SignExtend|ZeroExtend)\(([^,()]+),\s*\w+\)", r"\2", c)
    c = re.sub(r"(?<!un)signed\(([^()]+)\)", r"\1", c)
    c = re.sub(r"unsigned\(([^()]+)\)", r"\1", c)
    c = re.sub(r"\s+", " ", c).strip()
    if len(c) > 60:
        c = ""
    return ("# " + c) if c else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--input", type=pathlib.Path,
                        default=ROOT.parent / "content-vec.yaml")
    args = parser.parse_args()

    content = yaml.safe_load(args.input.read_text(encoding="utf-8"))
    for chapter in content["chapters"]:
        for insn in chapter["instructions"]:
            mnem = insn["mnemonic"]
            # 1) pseudocode fixes / gaps
            pseudo = insn["pseudocode"]
            for bad, good in PSEUDO_GLOBAL_FIXES:
                pseudo = pseudo.replace(bad, good)
            if mnem in PSEUDO_FIXES:
                pseudo = PSEUDO_FIXES[mnem]
            elif mnem in MEM_PSEUDO:
                pseudo = MEM_PSEUDO[mnem]
            insn["pseudocode"] = pseudo
            # 2) names & description
            cn, en, desc = fill_names(mnem, insn["operands"])
            insn["cn_name"] = cn
            insn["en_name"] = en
            insn["description"] = desc
            # 3) equation + comment
            insn["equation"] = pick_equation(pseudo)
            insn["example_comment"] = simplify_comment(insn["equation"], mnem)

        # chapter notes
        if chapter["letter"] == "V":
            chapter["note"] = (
                "本章收录全部以 V 开头的 LSX（128 位向量）指令。约定：`VR[x]` 表示第 x 号 "
                "128 位向量寄存器（汇编名 `$vr0`～`$vr31`）；`GR[x]` 为通用寄存器，"
                "`CFR[x]` 为条件标志寄存器（`$fcc0`～`$fcc7`）；`GRLEN` 在 LA32 中为 32、"
                "LA64 中为 64。逐元素操作的元素个数按 128 位除以元素宽度计算。"
                "位图中固定编码字段以浅灰底标示。")
        else:
            chapter["note"] = (
                "本章收录全部以 X 开头的 LASX（256 位向量）指令。约定：`XR[x]` 表示第 x 号 "
                "256 位向量寄存器（汇编名 `$xr0`～`$xr31`）。除个别特有指令（如 "
                "`xvperm.w`、`xvrepl128vei.*`）外，XV 指令与同编号 V 指令语义相同，"
                "只是把 128 位换成 256 位（每 lane 仍为 128 位，lane 数加倍）。"
                "逐元素操作的元素个数按 256 位除以元素宽度计算。")

        # section notes (V-prefixed notes go to the V chapter, X-prefixed to X)
        notes = chapter.setdefault("section_notes", {})
        xchap = chapter["letter"] == "X"
        for mn, block in SECTION_NOTES.items():
            if mn.startswith("x") != xchap:
                continue
            notes.setdefault(mn, {"title": block["title"], "html": block["html"]})

    args.input.write_text(
        yaml.safe_dump(content, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=100),
        encoding="utf-8")
    total = sum(len(c["instructions"]) for c in content["chapters"])
    print(f"filled {total} instructions -> {args.input}")


if __name__ == "__main__":
    main()
