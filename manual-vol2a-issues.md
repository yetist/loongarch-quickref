# 《LoongArch 参考手册 卷 II-a：向量指令扩展》V1.11 勘误与疑问清单

本清单整理自对《LoongArch Reference Manual Volume II-a: Vector Instruction Extensions》V1.11
（197 页，PDF）做指令速查表整理时的发现，供与文档作者沟通核对使用。

页码同时给出**印刷页码**（正文页脚数字）与 **PDF 页码**，便于直接定位。
"已验证"表示该判断经交叉汇编器 `loongarch64-linux-gnu-as`（GNU binutils 2.47）
按手册编码位域逐条汇编比对确认。

## 一、确认的笔误

### 1. 附录 B：XVMADDWOD.W.HU.H / XVMADDWOD.Q.DU.D 操作数列印错

- **位置**：附录 B（Instruction Code List），印刷页 178（PDF 第 186 页）
- **原文**：

  ```text
  XVMADDWOD.W.HU.H   xk, xj, xk   0 1 1 1 0 1 0 0 1 0 1 1 1 1 1 0 1   xk  xj  xd
  XVMADDWOD.Q.DU.D   xk, xj, xk   0 1 1 1 0 1 0 0 1 0 1 1 1 1 1 1 1   xk  xj  xd
  ```

- **问题**：操作数列把目的寄存器印成了 `xk`，应为 `xd`（同一行的编码位图
  bits 4:0 正确地标为 `xd`；按位图汇编 `xvmaddwod.w.hu.h $xr0, $xr1, $xr2`
  得到机器码 `0x74be8820`，与位图一致）。
- **建议**：操作数列更正为 `xd, xj, xk`。

### 2. 附录 B：XVSAT.WU 目的寄存器字段标成了大写 `XD`

- **位置**：附录 B，印刷页 187（PDF 第 195 页）
- **原文**：

  ```text
  XVSAT.WU   xd, xj, ui5   0 1 1 1 0 1 1 1 0 0 1 0 1 0 0 0 1   ui5   xj   XD
  ```

- **问题**：bits 4:0 字段标号印为 `XD`，全表其余各行均为小写 `xd`。
  位域位置本身正确（汇编验证一致），仅为标号大小写笔误。
- **建议**：更正为 `xd`。

### 3. 1.2.7.1 节：伪代码标签 `VPICKVE2GR.B:` 重复出现

- **位置**：1.2.7.1 节（VINSGR2VR / VPICKVE2GR），印刷页 125（PDF 第 133 页）
- **原文**（节选）：

  ```text
  The VPICKVE2GR.{B/H/W/D} instruction writes the signed integer byte/...
  elements indexed by the immediate value ui4/ui3/ui2/ui1 ...

      VPICKVE2GR.B:
          GR[rd] = SignExtend(VR[vj].B[ui4])

      VPICKVE2GR.B:                     <-- 第二个标签
          GR[rd] = SignExtend(VR[vj].H[ui3])    <-- 代码体操作的是 H 元素

      VPICKVE2GR.W:
          GR[rd] = SignExtend(VR[vj].W[ui2])
  ```

- **问题**：第二个 `VPICKVE2GR.B:` 按其代码体（`VR[vj].H[ui3]`）应为
  `VPICKVE2GR.H:`。导致 `vpickve2gr.h` 在正文中没有对应的伪代码条目。
- **建议**：第二个标签更正为 `VPICKVE2GR.H:`。

### 4. 1.2.7.15 节标题：`VPREMI.W` / `XVPREMI.W` 应为 `VPERMI.W` / `XVPERMI.W`

- **位置**：1.2.7.15 节标题，印刷页 139（PDF 第 147 页）
- **原文**：

  ```text
  1.2.7.15 VPREMI.W, XVPREMI.W, XVPERMI.D, XVPERMI.Q
  ```

- **问题**：`VPREMI.W`、`XVPREMI.W` 是助记符拼写笔误。附录 B（印刷页 157 /
  165）、本节正文（"The [X]VPERMI.W instruction uses …"）、伪代码标签
  （`VPERMI.W:`）以及交叉汇编器（仅接受 `vpermi.w`，`vpremi.w` 报
  "no match insn"）均证实正确拼写为 `VPERMI.W` / `XVPERMI.W`。
- **建议**：标题更正为 `VPERMI.W, XVPERMI.W, XVPERMI.D, XVPERMI.Q`。

## 二、遗漏

### 5. `XVHSELI.D` 只出现在附录 B，正文（第 1 章）完全没有条目

- **位置**：附录 B，印刷页 186（PDF 第 194 页）：

  ```text
  XVHSELI.D   xd, xj, ui5   0 1 1 1 0 1 1 0 1 0 0 1 1 1 1 1 1   ui5   xj   xd
  ```

- **问题**：全文检索 "HSELI" 在第 1 章命中 0 次——该指令既无 1.2.x 小节、
  无功能描述、也无伪代码；版本历史（V1.10 新增指令列表）中也没有提到它。
  全书 1367 条指令中仅此一条有编码无正文。
- **疑问**：请确认 `XVHSELI.D` 的语义（推测与 `XVSHUF4I`/`VEXTRINS` 系列的
  元素选择相关？），或补充相应正文小节。

### 6. 访存类指令没有逐条伪代码（24 条）

- **位置**：1.2.8.1 节（印刷页 140）、1.2.8.2 节（印刷页 141）
- **范围**：`[X]VLD[X]`、`[X]VST[X]`（8 条）、`[X]VLDREPL.{B/H/W/D}`
  （8 条）、`[X]VSTELM.{B/H/W/D}`（8 条）
- **问题**：这些小节只有文字描述（地址计算规则写在段落里），没有像其他
  指令那样给出逐条 `VLD:` / `VSTELM.B:` 形式的伪代码块。
- **疑问**：是有意省略还是遗漏？若能补充逐条伪代码（含
  `Mem[GR[rj] + SignExtend(si12)]` 类地址表达式），与其他章节风格更一致，
  也便于工具链实现者对齐语义。

## 三、轻微 / 格式问题

### 7. 1.2.1.5 节标题花括号内有多余空格

- **位置**：印刷页 8（PDF 第 16 页）

  ```text
  1.2.1.5 [X]VHADDW.{H.B/W.H/D.W/Q.D/HU.BU/WU.HU/DU.WU/QU.DU},
            [X]VHSUBW.{ H.B/W.H/D.W/Q.D/HU.BU/WU.HU/DU.WU/QU.DU }
  ```

- 第二行 `{ H.B/… }` 花括号内两侧多了空格，与全书其他标题的排版不一致。

### 8. 附录 B：`idx` 字段标号被竖排断行（VSTELM.* 行）

- **位置**：附录 B，印刷页 156–157（PDF 第 164–165 页）起
- `VSTELM.{B/H/W/D}`、`XVSTELM.{B/H/W/D}` 行的 `idx` 字段标号被拆成
  两行渲染（"id" 与 "x" 分离），纯文本提取时无法与所在行对齐。
  属排版/渲染问题，不影响编码正确性，但影响文本形态的工具消费。

### 9. `VLDI` 立即数命名 `i13` 与 `si*/ui*` 约定不一致

- **位置**：1.2.1.24 节（印刷页 50）与附录 B（印刷页 173）
- 全书立即数字段命名均为 `siN` / `uiN`（宽度自名），仅 `VLDI`/`XVLDI`
  使用 `i13`。若为有意区分（如带符号立即数与普通立即数），建议在
  附录 A 的算子说明中补充 `iN` 的定义；否则建议统一为 `si13`。

### 10. 伪代码中 `2i+1` 等连乘记号未在算子表中定义

- **位置**：如 1.2.1.5 节 `VR[vj].B[2i+1]`，以及 `2i`、`i+16` 等写法
- 附录 A 表 2-3 定义了 `*` 为乘法，但未说明"数字与变量相邻"即为相乘。
  `2i+1` 的含义（`2*i+1`）可推断，但按严格的伪代码规范宜显式写为
  `2*i+1`，或在附录 A 补充连乘记号的说明。

## 四、验证方法（供参考）

上述判断的依据：

1. 以附录 B 全部 1367 条指令行为数据源，提取助记符、操作数列与 32 位
   编码位域，逐一与 `loongarch64-linux-gnu-as`（GNU binutils 2.47）交叉
   汇编比对——除上文第 1 条（操作数列印错）外全部一致；
2. 将第 1 章 78 个小节的逐条伪代码标签与附录 B 助记符集合交叉比对，
   发现第 3、5、6 条问题；
3. 将各小节标题中的助记符模式（含 `[X]`、`{a/b/c}`、`[U]` 展开）与
   附录 B 集合比对，发现第 4 条问题。

除上列各项外，未发现其他编码层面（固定位域、字段位置、字段宽度）的
不一致。
