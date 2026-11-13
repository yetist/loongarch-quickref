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

### 5. 1.2.1.18 节：`[X]VSAT.{W/WU/D/DU}` 伪代码循环上界全部误为 `range(16)`

- **位置**：1.2.1.18 节（[X]VSAT.{B/H/W/D}[U]），印刷页 43–44（PDF 第 51–52 页）
- **原文**（节选）：

  ```text
      VSAT.W:
           for i in range(16):
                     VR[vd].W[i] = Sat_S(VR[vj].W[i], ui5)

      VSAT.D:
           for i in range(16):
                     VR[vd].D[i] = Sat_S(VR[vj].D[i], ui6)
  ```

- **问题**：循环上界应等于目标寄存器中该宽度元素的个数：`VSAT.W`/`VSAT.WU`
  应为 `range(4)`、`VSAT.D`/`VSAT.DU` 应为 `range(2)`、`XVSAT.W`/`XVSAT.WU`
  应为 `range(8)`、`XVSAT.D`/`XVSAT.DU` 应为 `range(4)`。同节的
  `VSAT.B`/`VSAT.H`/`XVSAT.B`（16）、`VSAT.HU`（8）等均正确，仅这 8 条
  印错。`range(16)` 会把 128 位寄存器的 W/D 元素循环越界，无法与
  附录 B 元素宽度对应。
- **建议**：按元素个数更正上述 8 条的循环上界。

- **附带**：同节 `XVSAT.B` 伪代码首行目的寄存器印为 `XR[x_j]`，应为
  `XR[xd]`（与其余 7 条一致）。

### 6. 1.2.2.14 节：`XVCLZ.W` 伪代码寄存器交叉印错

- **位置**：1.2.2.14 节（[X]VCLO/[X]VCLZ），印刷页 88（PDF 第 96 页）
- **原文**：

  ```text
      XVCLZ.W:
          for i in range(8):
                      XR[xj].W[i] = CLZ(XR[i].W[xj])
  ```

- **问题**：目的寄存器与源寄存器写反，且 `XR[i]` 中的 `i`（循环变量）被
  误用作寄存器下标。同节 `XVCLZ.D` 正确为
  `XR[xd].D[i] = CLZ(XR[xj].D[i])`。
- **建议**：更正为 `XR[xd].W[i] = CLZ(XR[xj].W[i])`。

### 7. XV（256 位）家族伪代码中寄存器名系统性印为 V 系列（230 处）

- **位置**：1.2.1.6、1.2.1.7、1.2.1.8（[X]VADDW/VSUBW 加宽，120 处）、
  1.2.1.14（[X]VMULW 加宽，48 处）、1.2.1.16（[X]VMADDW，48 处）、
  1.2.2.4（[X]VSLLWIL，4 处）、1.2.7.4（XVREPLVE0，10 处）
- **原文**（示例，1.2.1.6 `XVADDW.H.B`）：

  ```text
      XVADDW.H.B:
          for i in range(8):
                      XR[vd].H[i] = SignExtend(XR[vj].B[2i], 16) + SignExtend(XR[vj].B[2i+1], 16)
  ```

- **问题**：256 位向量寄存器应为 `XR[xd]`/`XR[xj]`/`XR[xk]`/`XR[xa]`，
  但这些 XV 家族的伪代码把 x 系列寄存器印成了 `XR[vd]`/`XR[vj]`/`XR[vk]`
  （个别地方还出现 `VR[xd]`/`VR[xj]`/`VR[xk]`/`VR[v_j]` 的反向混淆）。
  全书共约 230 处，明显是从 V 版伪代码复制时未替换寄存器名。
- **建议**：批量更正上述小节伪代码中的寄存器名。

## 二、正文与伪代码不一致

### 8. 1.2.5.4 节：`[X]VFFINT.S.L` 正文说 signed，伪代码用 UINT64

- **位置**：1.2.5.4 节（[X]VFFINT.{S.W/D.L}[U], [X]VFFINT.S.L,
  [X]VFFINT{L/H}.D.W），印刷页 113（PDF 第 121 页）
- **原文**（正文与伪代码节选）：

  ```text
  The [X]VFFINT.S.L instruction converts each signed integer double-word element
  in every 128 bits of vector registers vj/xj into a single-precision floating-point
  number. ...

      VFFINT.S.L:
           for i in range(2):
                     VR[vd].S[i+2] = FP32_convertFromInt(VR[vj].L[i], UINT64)
                     VR[vd].S[i+0] = FP32_convertFromInt(VR[vk].L[i], UINT64)
  ```

- **问题**：正文两处说 "signed integer double-word"，伪代码却用 `UINT64`
  （无符号）。二者必有一处错误：同节 `VFFINT.D.L` 用 `SINT64`、
  `VFFINT.D.LU` 用 `UINT64`，从命名规律看 `.S.L` 应为有符号（伪代码应为
  `SINT64`）。
- **附带**：同段正文还说 vk 的结果 "writing the results sequentially to the
  upper half of each 128 bits"，但伪代码写的是低半（`S[i+0]`），正文
  "upper half" 应为 "lower half"（与 vj 的 "upper half" 相对）。
- **疑问**：请确认 `.S.L` 的符号语义，并统一正文与伪代码。

## 三、遗漏

### 9. `XVHSELI.D` 只出现在附录 B，正文（第 1 章）完全没有条目

- **位置**：附录 B，印刷页 186（PDF 第 194 页）：

  ```text
  XVHSELI.D   xd, xj, ui5   0 1 1 1 0 1 1 0 1 0 0 1 1 1 1 1 1   ui5   xj   xd
  ```

- **问题**：全文检索 "HSELI" 在第 1 章命中 0 次——该指令既无 1.2.x 小节、
  无功能描述、也无伪代码；版本历史（V1.10 新增指令列表）中也没有提到它。
  全书 1367 条指令中仅此一条有编码无正文。
- **疑问**：请确认 `XVHSELI.D` 的语义（推测与 `XVSHUF4I`/`VEXTRINS` 系列的
  元素选择相关？），或补充相应正文小节。

### 10. 访存类指令没有逐条伪代码（24 条）

- **位置**：1.2.8.1 节（印刷页 140）、1.2.8.2 节（印刷页 141）
- **范围**：`[X]VLD[X]`、`[X]VST[X]`（8 条）、`[X]VLDREPL.{B/H/W/D}`
  （8 条）、`[X]VSTELM.{B/H/W/D}`（8 条）
- **问题**：这些小节只有文字描述（地址计算规则写在段落里），没有像其他
  指令那样给出逐条 `VLD:` / `VSTELM.B:` 形式的伪代码块。
- **疑问**：是有意省略还是遗漏？若能补充逐条伪代码（含
  `Mem[GR[rj] + SignExtend(si12)]` 类地址表达式），与其他章节风格更一致，
  也便于工具链实现者对齐语义。

## 四、轻微 / 格式问题

### 11. 1.2.3.1 节：VFRSTP[I] 伪代码两条语句挤在同一行

- **位置**：1.2.3.1 节（[X]VFRSTP[I].{B/H}），印刷页 93–94（PDF 第 101–102 页）
- **原文**（节选）：

  ```text
      VFRSTPI.B:
          ...
          m = ui5%16 VR[vd].B[m] = idx

      XVFRSTPI.B:
          m = ui5 % 16 idx0 = 0
          ...
          XR[xd].B[m] = idx0 idx1 = 0

      XVFRSTP.B:
          ...
          XR[xd].B[m0] = idx0 idx1 = 0
  ```

- **问题**：`m = ui5%16`、`idx0 = 0`、`idx1 = 0` 等独立语句与赋值语句粘连
  在同一行（`XVFRSTPI.H`、`XVFRSTP.H`、`XVFRSTPI.B`/`.H`、`XVFRSTP.B`/`.H`
  均如此），纯文本提取和机器解析都会把两条语句当成一条。
- **建议**：拆成独立行。

### 12. 1.2.1.5 节标题花括号内有多余空格

- **位置**：印刷页 8（PDF 第 16 页）

  ```text
  1.2.1.5 [X]VHADDW.{H.B/W.H/D.W/Q.D/HU.BU/WU.HU/DU.WU/QU.DU},
            [X]VHSUBW.{ H.B/W.H/D.W/Q.D/HU.BU/WU.HU/DU.WU/QU.DU }
  ```

- 第二行 `{ H.B/… }` 花括号内两侧多了空格，与全书其他标题的排版不一致。

### 13. 附录 B：`idx` 字段标号被竖排断行（VSTELM.* 行）

- **位置**：附录 B，印刷页 156–157（PDF 第 164–165 页）起
- `VSTELM.{B/H/W/D}`、`XVSTELM.{B/H/W/D}` 行的 `idx` 字段标号被拆成
  两行渲染（"id" 与 "x" 分离），纯文本提取时无法与所在行对齐。
  属排版/渲染问题，不影响编码正确性，但影响文本形态的工具消费。

### 14. `VLDI` 立即数命名 `i13` 与 `si*/ui*` 约定不一致

- **位置**：1.2.1.24 节（印刷页 50）与附录 B（印刷页 173）
- 全书立即数字段命名均为 `siN` / `uiN`（宽度自名），仅 `VLDI`/`XVLDI`
  使用 `i13`。若为有意区分（如带符号立即数与普通立即数），建议在
  附录 A 的算子说明中补充 `iN` 的定义；否则建议统一为 `si13`。

### 15. 伪代码中 `2i+1` 等连乘记号未在算子表中定义

- **位置**：如 1.2.1.5 节 `VR[vj].B[2i+1]`，以及 `2i`、`i+16` 等写法
- 附录 A 表 2-3 定义了 `*` 为乘法，但未说明"数字与变量相邻"即为相乘。
  `2i+1` 的含义（`2*i+1`）可推断，但按严格的伪代码规范宜显式写为
  `2*i+1`，或在附录 A 补充连乘记号的说明。

## 五、验证方法（供参考）

上述判断的依据：

1. 以附录 B 全部 1367 条指令行为数据源，提取助记符、操作数列与 32 位
   编码位域，逐一与 `loongarch64-linux-gnu-as`（GNU binutils 2.47）交叉
   汇编比对——除上文第 1 条（操作数列印错）外全部一致；
2. 将第 1 章 78 个小节的逐条伪代码标签与附录 B 助记符集合交叉比对，
   发现第 3、9、10 条问题；
3. 将各小节标题中的助记符模式（含 `[X]`、`{a/b/c}`、`[U]` 展开）与
   附录 B 集合比对，发现第 4 条问题；
4. 按元素宽度核对伪代码循环上界与寄存器元素个数（B/H/W/D =
   16/8/4/2，X 系列 32/16/8/4），发现第 5 条问题；
5. 按 XV 家族应使用 `XR[x*]` 寄存器的规则全文检查伪代码，统计出
   第 7 条的 230 处，同时发现第 6 条（`XVCLZ.W` 寄存器交叉印错）；
6. 核对附录 A 函数定义的分支结构，发现第 8 条（`Sat_S` 重复分支）。

除上列各项外，未发现其他编码层面（固定位域、字段位置、字段宽度）的
不一致。
