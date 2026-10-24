# 龙芯架构指令速查表

按助记符字典序排列的 LoongArch 指令速查表。A4 PDF，**137 页**，收录 **357 条**指令，覆盖 A–Z 中所有有指令的字母。

**PDF：[`loongarch-quickref.pdf`](loongarch-quickref.pdf)**

## 特点

- 严格按完整助记符的 ASCII 字典序排列，每个字母独立成章
- 每条指令包含：语法、语义、格式/版本、说明、编码方框位图、编码值、汇编示例、语义伪代码
- 封面、两栏目录、PDF 书签（封面 / 目录 / 17 个字母章 / 357 条指令）
- 目录页码自动回填，正文连续排版
- 构建时校验固定位域与基值

## 构建

需要 Python 3、Chromium、`qpdf`、`pdfinfo`（poppler）。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make pdf
```

也可以直接运行：

```bash
.venv/bin/python build.py
```

生成：

- `loongarch-quickref.pdf`：最终 PDF
- `build/manual.html`：中间 HTML
- `build/toc_pages.json`：目录页码缓存

`build/` 已被 `.gitignore` 忽略。

## 校验

需要 `loongarch64-linux-gnu-as` 与 `loongarch64-linux-gnu-objdump` 在 `PATH` 中。

```bash
make check
```

校验内容：

- 章内指令严格排序、首字母与章一致、无重复
- 每条指令固定位域与 `base` 一致
- 357 条指令逐条汇编，机器码与 `encoding_value` 公式一致

当前结果：**357 条、0 处不一致**。

## 目录结构

```text
.
├── content.yaml             # 唯一内容源：357 条指令
├── build.py                 # 生成封面/目录/正文/PDF/书签
├── validate.py              # 内容与编码校验
├── style.css                # A4 版式
├── Makefile
├── requirements.txt
├── loongarch-quickref.pdf   # 发布产物
└── README.md
```

## 维护 `content.yaml`

文档级字段：

```yaml
document:
  title: 龙芯架构指令速查表
  subtitle: 卷一 · 基础架构
  scope: A – Z 字母
```

章与指令：

```yaml
chapters:
  - letter: A
    title: A · 算术、逻辑、原子与边界检查指令
    note: 本章约定……
    section_notes:
      amadd.b:
        title: 原子指令通用规则
        html: <p>……</p>
    instructions:
      - mnemonic: add.w
        operands: rd, rj, rk
        cn_name: 字整数加法
        en_name: Add Word
        format: 3R 型
        isa: [LA32, LA64]
        equation: GR[rd] = SignExtend(...)
        description: 将……写入 `rd`。
        example: add.w $a0, $a1, $a2
        example_comment: "# $a0 = $a1 + $a2"
        pseudocode: |
          tmp = GR[rj][31:0] + GR[rk][31:0]
          GR[rd] = SignExtend(tmp[31:0], GRLEN)
        encoding:
          - {bits: [31, 25], value: "0000000", kind: fixed}
          - {bits: [24, 20], value: "00001", kind: fixed}
          - {bits: [19, 15], value: "00000", kind: fixed}
          - {bits: [14, 10], value: rk, kind: reg}
          - {bits: [9, 5], value: rj, kind: reg}
          - {bits: [4, 0], value: rd, kind: reg}
        base: "0x00100000"
        encoding_value: 0x00100000 | (rk << 10) | (rj << 5) | rd
```

约定：

- `encoding` 字段必须从 bit 31 连续覆盖到 bit 0。
- `kind: fixed` 的 `value` 为二进制串；`reg`/`imm`/`shift` 为字段名。
- `base` 为固定位域拼出的基值，`build.py` 和 `validate.py` 都会检查。
- 指令按助记符排序；新增指令后运行 `make check`，再运行 `make pdf`。

## 排序规则

按完整助记符的 ASCII 字典序，`.` 在 `_` 之前：

```text
amadd.b < amadd.d < amadd.h < amadd.w < amadd_db.b ...
asrtgt.d < asrtle.d
sc.d < sc.q < sc.w < screl.d ...
```

G、H、K、Q、U、V、W、Y、Z 在官方 Appendix B 中没有对应指令，因此不设章。

## 说明

- `fcmp.cond.s` / `fcmp.cond.d` 作为参数化指令收录，22 种比较条件列在条目注中。
- 官方 Appendix B 中 `AMCAS.*`、`AMSWAP`/`AMADD` 的 B/H 变体，以及 `LLACQ`/`SCREL` 把目的寄存器字段写作 `fd`；本表按语义统一记为 `rd`，位域位置不变。
- TLB、缓存、CSR、页表遍历等复杂系统指令采用速查级描述 + 主要伪代码；需要完整规范描述时可继续细化。

## 数据来源

- LoongArch Reference Manual, Volume 1: Basic Architecture（英文版）Appendix B 指令编码表，以及第 2.2、3.2、4.2 节。

指令编码与语义整理自龙芯官方文档，相关内容的版权归原文档作者所有；本仓库仅做排版与检索整理。
