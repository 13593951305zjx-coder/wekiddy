# 含错代码测试集（code-errors-testcases）

> **12 个长代码文件 · 3 种语言 · 42 个已标注错误**：6 个语法错误 + 18 个运行时异常 + 18 个逻辑错误。
>
> 每个错误都带机器可校验的 ground truth（`manifest.json`），并配套 `verify_all.py` 对真实工具链一键复核。

---

## 1. 用途

这套代码是**故意写错**的测试语料，适合用来评估/回归：

- 静态分析、SAST、代码审查工具的缺陷检出能力；
- LLM / 代码 Agent 的找 bug、代码审查、修复能力（可计算检出率/修复率）；
- IDE、编译器、lint 规则的诊断结果与行列号回归测试；
- 程序分析课程或面试题库（含标准答案）。

> ⚠️ 文件故意包含错误，**不能**直接用于生产环境。语法错误文件无法编译/解析，
> 运行时与逻辑错误文件语法合法，但行为是错的。

## 2. 目录结构

```text
code-errors-testcases/
├── README.md            # 本说明
├── manifest.json        # ground truth（机器可读，42 条）
├── manifest.csv         # ground truth（Excel 可读，UTF-8 BOM）
├── verify_all.py        # 一键校验：结构 + 每个错误是否真实复现
├── python/
│   ├── syntax_01_missing_colon.py
│   ├── syntax_02_literal_assignment.py
│   ├── runtime_01_service_pipeline.py
│   └── logic_01_inventory_report.py
├── javascript/
│   ├── syntax_01_missing_paren.js
│   ├── syntax_02_invalid_operator.js
│   ├── runtime_01_order_pipeline.js
│   └── logic_01_cart_report.js
├── java/
│   ├── Syntax01MissingSemicolon.java
│   ├── Syntax02MissingParen.java
│   ├── Runtime01OrderPipeline.java
│   └── Logic01CartReport.java
```

## 3. 环境要求

| 工具 | 要求 | 本包实测版本 |
|---|---|---|
| Python | 3.8+ | 3.12.14 |
| Node.js | 18+（用于 JS 文件） | v24.21.0 |
| JDK | 8+（用于 Java 文件） | 1.8.0_461 |

`verify_all.py` 会从 `PATH` 自动探测工具链，也可以用环境变量覆盖：

```text
PYTHON_BIN / NODE_BIN / JAVAC_BIN / JAVA_BIN
```

只装了部分工具链时，可只校验对应语言（见下一节）。

## 4. 快速开始

```bash
cd code-errors-testcases
python verify_all.py --strict      # 校验全部 3 种语言，缺失工具链视为失败
python verify_all.py --lang python # 只校验 Python
python verify_all.py --verbose     # 打印每一条检查结果
```

校验通过时最后会输出：

```text
Summary: 57 passed, 0 failed, 0 skipped
RESULT: PASS
```

## 5. 统计

| 语言 | 文件数 | 语法错误 | 运行时异常 | 逻辑错误 | 合计 |
|---|---|---|---|---|---|
| Python | 4 | 2 | 6 | 6 | 14 |
| JavaScript | 4 | 2 | 6 | 6 | 14 |
| Java 8 | 4 | 2 | 6 | 6 | 14 |
| **合计** | **12** | **6** | **18** | **18** | **42** |

## 6. 使用方式

### Python

```bash
# 语法错误文件：预期在第 137 行报 SyntaxError（诊断包含 expected ':'）
python python/syntax_01_missing_colon.py

# 运行时异常：按用例 ID 触发，预期 IndexError（第 123 行）
python python/runtime_01_service_pipeline.py R1

# 逻辑错误：输出错误结果 1767.00（正确值应为 2067.00）
python python/logic_01_inventory_report.py L1

python python/runtime_01_service_pipeline.py   # 不带参数：打印 usage，退出码 0
```

> `R1..R6` 为运行时异常用例，`L1..L6` 为逻辑错误用例；不带参数打印 `usage`，
> 未知用例 ID 以退出码 2 结束。

### JavaScript

```bash
# 语法错误文件：node --check 预期报 SyntaxError（第 154 行）
node --check javascript/syntax_01_missing_paren.js

# 运行时异常：预期 TypeError（第 184 行）
node javascript/runtime_01_order_pipeline.js R1

# 逻辑错误：输出错误结果 106.72（正确值应为 149.02）
node javascript/logic_01_cart_report.js L1

node javascript/runtime_01_order_pipeline.js   # 不带参数：打印 usage，退出码 0
```

> `R1..R6` 为运行时异常用例，`L1..L6` 为逻辑错误用例；不带参数打印 `usage`，
> 未知用例 ID 以退出码 2 结束。

### Java 8

Java 源文件是纯 ASCII；建议显式指定 `-encoding UTF-8`。语法错误文件**预期编译失败**。

```bash
# 语法错误文件：javac 预期在第 224 行报错（诊断包含 ';' expected）
javac -encoding UTF-8 -d /tmp/cases java/Syntax01MissingSemicolon.java

# 运行时/逻辑错误文件：编译到临时目录后按类名运行
mkdir -p /tmp/cases
javac -encoding UTF-8 -d /tmp/cases java/Runtime01OrderPipeline.java java/Logic01CartReport.java
java -cp /tmp/cases Runtime01OrderPipeline R1   # 预期 NullPointerException
java -cp /tmp/cases Logic01CartReport L1   # 输出错误结果 8298（正确值应为 8298.25）
```

> Windows 下把 `/tmp/cases` 换成任意可写目录（如 `%TEMP%\cases`），
> 并把 `mkdir -p` 换成 `New-Item -ItemType Directory -Force`。

> `R1..R6` 为运行时异常用例，`L1..L6` 为逻辑错误用例；不带参数打印 `usage`，
> 未知用例 ID 以退出码 2 结束。

## 7. 错误清单

### Python

| ID | 类型 | 文件 | 位置 | 错误说明 | Ground truth |
|---|---|---|---|---|---|
| `py-syn-01` | 语法错误 | `syntax_01_missing_colon.py` | L137 | summarize_batches 中 if 语句头部缺少结尾冒号，解析器在 if 行报 expected ':' | `expected ':'` |
| `py-syn-02` | 语法错误 | `syntax_02_literal_assignment.py` | L141 | allocate_supplier_budget 把字符串字面量 "reorder_total" 当作赋值目标，应为变量 reorder_total | `cannot assign to literal` |
| `py-run-R1` | 运行时异常 | `runtime_01_service_pipeline.py` | R1 @ L123 | 订单路由索引等于仓库行数，pick_primary_warehouse 访问 rows[index] 越界 | `IndexError` |
| `py-run-R2` | 运行时异常 | `runtime_01_service_pipeline.py` | R2 @ L150 | 新上架 SKU-1005 未登记进定价表，resolve_price_band 查表触发 KeyError | `KeyError` |
| `py-run-R3` | 运行时异常 | `runtime_01_service_pipeline.py` | R3 @ L190 | 订单行列表为空，average_line_value 用 0 做除数触发浮点除零 | `ZeroDivisionError` |
| `py-run-R4` | 运行时异常 | `runtime_01_service_pipeline.py` | R4 @ L220 | 客户 display_name 为 None，format_customer_name 直接调用 .strip() | `AttributeError` |
| `py-run-R5` | 运行时异常 | `runtime_01_service_pipeline.py` | R5 @ L238 | describe_quantity 把字符串前缀与整数数量直接相加，str + int 触发 TypeError | `TypeError` |
| `py-run-R6` | 运行时异常 | `runtime_01_service_pipeline.py` | R6 @ L263 | 渠道数量串带千分位逗号，parse_quantity 执行 int('12,500') 失败 | `ValueError` |
| `py-logic-L1` | 逻辑错误 | `logic_01_inventory_report.py` | L1 | 循环上界写成 len(items) - 1，漏算最后一件商品 F-600 的 300.00 库存价值 | 实际 `1767.00` ≠ 期望 `2067.00` |
| `py-logic-L2` | 逻辑错误 | `logic_01_inventory_report.py` | L2 | 求平均单价时用整除 // 截断，正确结果应为 2067/6 = 344.5 | 实际 `344.00` ≠ 期望 `344.50` |
| `py-logic-L3` | 逻辑错误 | `logic_01_inventory_report.py` | L3 | accumulate_ledger 使用可变默认参数 ledger=[]，第二次调用累积了第一批流水 37.50 | 实际 `42.00` ≠ 期望 `4.50` |
| `py-logic-L4` | 逻辑错误 | `logic_01_inventory_report.py` | L4 | 包邮/折扣边界用 > 而非 >=，小计恰好 500.00 时没有享受 10% 批量折扣 | 实际 `500.00` ≠ 期望 `450.00` |
| `py-logic-L5` | 逻辑错误 | `logic_01_inventory_report.py` | L5 | best_margin 以 0 作为 max 初值，而所有清仓毛利均为负数，结果错误地返回 0 | 实际 `0.00` ≠ 期望 `-12.00` |
| `py-logic-L6` | 逻辑错误 | `logic_01_inventory_report.py` | L6 | 小计计算漏乘数量，只累加单价 25+40+10，未得到 3*25+2*40+5*10 | 实际 `75.00` ≠ 期望 `205.00` |

### JavaScript

| ID | 类型 | 文件 | 位置 | 错误说明 | Ground truth |
|---|---|---|---|---|---|
| `js-syn-01` | 语法错误 | `syntax_01_missing_paren.js` | L154 | 轮库分仓规划中多行调用 pickWarehouse(...) 的最后一个实参后缺少右括号，解析器在实参行报错 | `missing ) after argument list` |
| `js-syn-02` | 语法错误 | `syntax_02_invalid_operator.js` | L196 | 退货结算中把加号与乘号连写成 +* 非法运算符序列，解析器在星号处报错 | `Unexpected token '*'` |
| `js-run-R1` | 运行时异常 | `runtime_01_order_pipeline.js` | R1 @ L184 | 迁移订单缺少 customer 字段，解析客户姓名时读取 undefined 的属性 | `TypeError` |
| `js-run-R2` | 运行时异常 | `runtime_01_order_pipeline.js` | R2 @ L189 | 积分抵扣计算引用了未声明的标识符 loyaltyCreditCents（正确变量名为 loyaltyCreditsCents） | `ReferenceError` |
| `js-run-R3` | 运行时异常 | `runtime_01_order_pipeline.js` | R3 @ L196 | 仓容 40 已占用 41，空闲槽位算出 -1 后用于 new Array(-1)，触发非法数组长度 | `RangeError` |
| `js-run-R4` | 运行时异常 | `runtime_01_order_pipeline.js` | R4 @ L202 | 折扣策略字段由配置误写成数字 42，作为函数调用时抛出 TypeError | `TypeError` |
| `js-run-R5` | 运行时异常 | `runtime_01_order_pipeline.js` | R5 @ L207 | 旧系统导入的出货清单 JSON 带尾随逗号，JSON.parse 抛出 SyntaxError | `SyntaxError` |
| `js-run-R6` | 运行时异常 | `runtime_01_order_pipeline.js` | R6 @ L214 | 仓库配置对象缺失，解构 undefined 上的 zoneCode 触发 TypeError | `TypeError` |
| `js-logic-L1` | 逻辑错误 | `logic_01_cart_report.js` | L1 | 合计循环上界写成 lines.length - 1，漏算最后一件商品（显示器支架） | 实际 `106.72` ≠ 期望 `149.02` |
| `js-logic-L2` | 逻辑错误 | `logic_01_cart_report.js` | L2 | 促销价解析用 parseInt 丢弃小数分位，12.75 变成 12、8.40 变成 8 | 实际 `28.00` ≠ 期望 `29.55` |
| `js-logic-L3` | 逻辑错误 | `logic_01_cart_report.js` | L3 | 循环中用 var 声明 rate 并被回调闭包捕获，所有行都按最后一档 10% 折扣计算 | 实际 `72.00` ≠ 期望 `76.50` |
| `js-logic-L4` | 逻辑错误 | `logic_01_cart_report.js` | L4 | 价格字符串使用 Array.prototype.sort() 默认字典序排序，取末位得到 9.99 而非真实最高价 100.00 | 实际 `9.99` ≠ 期望 `100.00` |
| `js-logic-L5` | 逻辑错误 | `logic_01_cart_report.js` | L5 | 0.1 + 0.2 的浮点求和无四舍五入，输出 IEEE-754 精度误差结果 | 实际 `0.30000000000000004` ≠ 期望 `0.3` |
| `js-logic-L6` | 逻辑错误 | `logic_01_cart_report.js` | L6 | 松散比较 value == false 把字符串 "0" 当作假值，误套用 15% 默认折扣 | 实际 `170.00` ≠ 期望 `200.00` |

### Java 8

| ID | 类型 | 文件 | 位置 | 错误说明 | Ground truth |
|---|---|---|---|---|---|
| `java-syn-01` | 语法错误 | `Syntax01MissingSemicolon.java` | L224 | 仓库补货计划中，Product.getDailyDemand() 的 return 语句末尾缺少分号；javac 1.8 报 "Syntax01MissingSemicolon.java:224: error: ';' expected"，补上分号后整个文件可正常编译 | `';' expected` |
| `java-syn-02` | 语法错误 | `Syntax02MissingParen.java` | L199 | 发票审批流程 requiresManagerApproval() 的 if 条件缺少右括号；javac 1.8 报 "Syntax02MissingParen.java:199: error: ')' expected"，补上右括号后整个文件可正常编译 | `')' expected` |
| `java-run-R1` | 运行时异常 | `Runtime01OrderPipeline.java` | R1 @ L67 | 订单 ORD-9001 的 customer 引用丢失，requireCustomer 在计算总价时对空客户抛 NullPointerException，异常未被捕获 | `NullPointerException` |
| `java-run-R2` | 运行时异常 | `Runtime01OrderPipeline.java` | R2 @ L96 | 订单行只有 3 个字段却按 4 个字段解析（normalizeField 访问 fields[3]）触发数组越界；Java 8 的异常消息就是越界下标 3 | `ArrayIndexOutOfBoundsException` |
| `java-run-R3` | 运行时异常 | `Runtime01OrderPipeline.java` | R3 @ L112 | 数量字段带千分位 "12,500"，自制整数解析器 parseQuantity 在遇到逗号时抛 NumberFormatException | `NumberFormatException` |
| `java-run-R4` | 运行时异常 | `Runtime01OrderPipeline.java` | R4 @ L147 | 夜间订单快照为空，averageOrderQuantity 用有效订单数 0 做整数除法，抛 ArithmeticException: / by zero | `ArithmeticException` |
| `java-run-R5` | 运行时异常 | `Runtime01OrderPipeline.java` | R5 @ L193 | 异构属性表里 priority 存的是字符串 "HIGH"，resolvePriority 却强转为 Integer，抛 ClassCastException | `ClassCastException` |
| `java-run-R6` | 运行时异常 | `Runtime01OrderPipeline.java` | R6 @ L228 | 装运计划假定待处理队列有 4 个订单，实际只有 2 个，nextPending 在迭代器耗尽时抛 NoSuchElementException | `NoSuchElementException` |
| `java-logic-L1` | 逻辑错误 | `Logic01CartReport.java` | L1 | 平均单价用整数除法计算，33193/4 的小数部分被截断，应为 8298.25 却输出 8298 | 实际 `8298` ≠ 期望 `8298.25` |
| `java-logic-L2` | 逻辑错误 | `Logic01CartReport.java` | L2 | 优惠码用 == 比较两个运行时构造的字符串（StringBuilder 与 new String 生成），引用不同导致匹配失败，折扣 350 分变成 0 | 实际 `0` ≠ 期望 `350` |
| `java-logic-L3` | 逻辑错误 | `Logic01CartReport.java` | L3 | 批发订单 4999 分 * 500000 件用 int 相乘，超出 2^31 溢出成负数，正确总额为 2499500000 分 | 实际 `-1795467296` ≠ 期望 `2499500000` |
| `java-logic-L4` | 逻辑错误 | `Logic01CartReport.java` | L4 | legacyReportSubtotalCents 循环上界写成 items.size() - 1，漏算最后一行 Mouse（1899 分），合计少了 1899 | 实际 `31294` ≠ 期望 `33193` |
| `java-logic-L5` | 逻辑错误 | `Logic01CartReport.java` | L5 | shippingCents 的 switch 中 STANDARD 分支缺少 break，落穿到 EXPRESS 分支，运费从 499 分变成 999 分 | 实际 `999` ≠ 期望 `499` |
| `java-logic-L6` | 逻辑错误 | `Logic01CartReport.java` | L6 | sortCheapestFirst 的 Comparator 参数顺序写反，按单价降序排序，首元素变成最贵的 Monitor 而不是最便宜的 Cable | 实际 `Monitor` ≠ 期望 `Cable` |

## 8. Ground truth 说明（manifest.json）

每个文件一条 `files[]` 记录，每个错误一条 `cases[]` 记录。字段：

| 字段 | 适用类型 | 含义 |
|---|---|---|
| `id` | 全部 | 稳定用例 ID，如 `py-run-R3` |
| `language` / `kind` / `file` | 全部 | 语言、错误类别、源文件相对路径 |
| `line` | syntax / runtime | 1-based 行号：解析器/编译器实际报告的行，或异常最内层栈帧所在行 |
| `error_type` / `diagnostic_pattern` | syntax | 错误类型与工具输出中的诊断子串 |
| `case` / `exception` / `message_pattern` | runtime | 触发的用例 ID、异常类型、异常消息子串 |
| `expected` / `actual` | logic | 正确结果 / 代码实际输出的错误结果（二者必然不同） |
| `description` | 全部 | 中文错误说明 |

行号以本包当前文件为准（生成时已用真实工具链逐条复核）。如果你修改了源文件，
行号可能变化，请重新运行 `verify_all.py` 并更新 manifest。

## 9. verify_all.py 校验内容

1. **结构**：12 个文件、42 个用例齐全；源文件纯 ASCII、无 BOM；长度达标（语法 ≥120 行、
   运行时 ≥200 行、逻辑 ≥170 行）；每个文件 ≥10 个函数/方法。
2. **语法错误**：`ast.parse`（Python）/ `node --check`（JS）/ `javac`（Java）必须在
   标注行报错，且输出包含标注的诊断子串。
3. **运行时异常**：按用例 ID 执行，必须抛出标注异常（未被捕获），最内层栈帧行号一致，
   异常消息子串匹配。
4. **逻辑错误**：按用例 ID 执行，stdout 必须恰好等于标注的错误值，且与 `expected` 不同。
5. **CLI 约定**：不带参数打印 usage 且退出码 0；未知用例退出码 2。
6. **产物干净**：包内不允许出现 `.class`、`.pyc`、`__pycache__` 等构建产物。

## 10. 生成环境与可复现性

| 项目 | 值 |
|---|---|
| 生成日期 | 2026-10-21 |
| Python | 3.12.14 |
| Node.js | v24.21.0 |
| JDK | 1.8.0_461（javac/java） |
| 源文件编码 | UTF-8（无 BOM），纯 ASCII 字符 |
| 依赖 | 全部仅用标准库 |

Java 源文件保持纯 ASCII，是为了兼容 Java 8 在非 UTF-8 默认字符集下的编译；
中文说明只出现在 README / manifest / 报告描述中。

## 11. 反馈与扩展

若要新增用例：

1. 在 `manifest.json` 的 `cases`（以及 `files`、`summary`）中登记；
2. 语法错误保证一个文件只有一处目标错误；运行时/逻辑错误按 `R*` / `L*` 用例 ID 扩展；
3. 运行 `python verify_all.py --strict` 全绿后再打包。

