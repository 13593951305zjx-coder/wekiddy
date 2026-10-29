const SAMPLE_CODE = `import os
import pickle
import yaml


def run_command(user_input, payload, settings):
    password = "admin123"
    os.system(user_input)
    config = yaml.load(settings)
    return pickle.loads(payload)
`;

const state = {
  findings: [],
  selectedFinding: -1,
  projects: [],
  scans: [],
  health: false,
  analysisResult: null,
  repair: null,
  appliedRepair: null,
  editorRevision: 0,
  repairRequestId: 0,
  analysisRequestId: 0,
  dashboardRequestId: 0,
  dashboardSummary: null,
  githubRequestId: 0,
  reviewSnapshot: null,
  historyItems: [],
  historyTotal: 0,
  historyOffset: 0,
  historyFilter: "",
  historyRequestId: 0,
  historyDetailRequestId: 0,
  historyDetail: null,
  findingSeverityFilter: "all",
  findingQuery: "",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function severityClass(severity) {
  const normalized = String(severity || "INFO").toLowerCase();
  if (normalized === "critical") return "severity-critical";
  if (normalized === "high") return "severity-high";
  if (normalized === "medium") return "severity-medium";
  return normalized === "low" ? "severity-low" : "severity-info";
}

function showToast(message, type = "") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast show ${type}`.trim();
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.detail || `请求失败（HTTP ${response.status}）`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg || "输入格式不正确").join("；") : detail);
  }
  return payload;
}

function jsonOptions(body) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function setButtonBusy(button, busy, label) {
  if (busy) {
    button.dataset.originalLabel = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.innerHTML = `<span class="button-loader" aria-hidden="true"></span>${escapeHtml(label)}`;
  } else {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.innerHTML = button.dataset.originalLabel || button.innerHTML;
  }
}

function updateEditorMeta() {
  const code = $("code-input").value;
  const lines = code ? code.split("\n").length : 0;
  const characters = code.length;
  $("line-count").textContent = `${lines} 行`;
  $("code-size").textContent = `${characters} 字符`;
}

function resetRepairPanel() {
  state.repairRequestId += 1;
  state.repair = null;
  $("repair-panel").hidden = true;
  $("repair-result").innerHTML = "";
  $("repair-state").textContent = "等待生成";
  $("repair-state").className = "analysis-state";
}

function updateReportButton() {
  $("download-report").disabled = !state.analysisResult;
}

function invalidateAnalysis(preserveAppliedRepair = false) {
  state.editorRevision += 1;
  state.analysisRequestId += 1;
  state.analysisResult = null;
  state.reviewSnapshot = null;
  renderReviewComparison(null);
  if (!preserveAppliedRepair) state.appliedRepair = null;
  resetRepairPanel();
  state.findings = [];
  state.selectedFinding = -1;
  renderSummary();
  renderCodeSummary();
  renderFindings();
  setAnalysisState("待分析");
  $("llm-panel").hidden = true;
  $("last-action").textContent = "代码已修改，等待重新分析";
  updateReportButton();
}

function setAnalysisState(label, kind = "") {
  const element = $("analysis-state");
  element.textContent = label;
  element.className = `analysis-state ${kind}`.trim();
}

function setSidebarStat(id, label, count, unavailableLabel) {
  const element = $(id);
  const available = Number.isSafeInteger(count) && count >= 0;
  element.textContent = available ? String(count) : "—";
  element.setAttribute("aria-label", `${label}：${available ? count : unavailableLabel}`);
}

function renderDashboardSummary() {
  const summary = state.dashboardSummary;
  setSidebarStat("sidebar-scan-finding-count", "项目扫描累计问题数", summary?.scan_finding_count, "暂不可用");
  setSidebarStat("sidebar-risk-high-count", "项目扫描高风险问题数", summary?.high_risk_count, "暂不可用");
  setSidebarStat("sidebar-risk-medium-count", "项目扫描中风险问题数", summary?.medium_risk_count, "暂不可用");
  setSidebarStat("sidebar-risk-other-count", "项目扫描其他问题数", summary?.other_finding_count, "暂不可用");
  setSidebarStat("sidebar-project-count", "项目总数", summary?.project_count, "暂不可用");
  setSidebarStat("sidebar-scan-count", "扫描任务总数", summary?.scan_count, "暂不可用");
}

function renderSummary(analyzer = "-", unavailableLabel = "尚未分析") {
  const total = state.findings.length;
  const high = state.findings.filter((finding) => ["HIGH", "CRITICAL"].includes(String(finding.severity).toUpperCase())).length;
  $("metric-total").textContent = String(total);
  $("metric-high").textContent = String(high);
  $("metric-analyzer").textContent = analyzer === "python-ast" ? "AST" : analyzer || "-";
  setSidebarStat("sidebar-finding-count", "当前代码问题数", state.analysisResult ? total : null, unavailableLabel);
  setSidebarStat("sidebar-high-count", "当前代码高风险数", state.analysisResult ? high : null, unavailableLabel);
  $("sidebar-review-state").textContent = state.analysisResult ? "已分析" : unavailableLabel === "正在分析" ? "分析中" : unavailableLabel === "分析失败" ? "分析失败" : "未分析";
}

function deriveCodePurpose(code, findings = []) {
  const imports = [...code.matchAll(/^\s*(?:import|from)\s+([A-Za-z_][\w.]*)/gm)].map((match) => match[1].split(".")[0]);
  const definitions = [...code.matchAll(/^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)/gm)].map((match) => match[1]);
  const classes = [...code.matchAll(/^\s*class\s+([A-Za-z_]\w*)/gm)].map((match) => match[1]);
  const roles = [];
  if (/\b(?:fastapi|flask|django)\b/i.test(code)) roles.push("提供 Web 接口或处理请求");
  if (/\b(?:os\.system|subprocess|Popen|run\s*\()/i.test(code)) roles.push("执行系统命令或外部进程");
  if (/\b(?:sqlite3|sqlalchemy|pymysql|psycopg|SELECT\s|INSERT\s|UPDATE\s|DELETE\s)/i.test(code)) roles.push("访问或操作数据库");
  if (/\b(?:yaml|json|pickle|loads?\s*\()/i.test(code)) roles.push("读取、解析或序列化数据");
  if (/\b(?:open\s*\(|Path\s*\(|read_text|write_text)\b/i.test(code)) roles.push("读写本地文件");
  if (/\b(?:requests|httpx|urllib)\b/i.test(code)) roles.push("调用网络接口");
  const parts = ["这是一段 Python 代码"];
  if (classes.length) parts.push(`，定义了 ${classes.slice(0, 3).join("、")} 等类`);
  if (definitions.length) parts.push(`，包含 ${definitions.slice(0, 4).join("、")} 等函数`);
  if (roles.length) parts.push(`，主要用于${roles.slice(0, 3).join("、")}`);
  if (!roles.length && !classes.length && !definitions.length && imports.length) parts.push(`，使用了 ${[...new Set(imports)].slice(0, 5).join("、")} 等模块完成处理`);
  if (findings.length) parts.push(`。本次静态分析发现 ${findings.length} 个需要关注的问题，建议结合下面的风险说明逐项修改`);
  else parts.push("，当前静态分析没有发现已配置规则覆盖的风险问题");
  return `${parts.join("")}。`.replace(/。。$/, "。");
}

function renderCodeSummary(code = $("code-input").value, candidateCode = null) {
  const panel = $("code-summary-panel");
  if (!state.analysisResult || !panel) {
    if (panel) panel.hidden = true;
    return;
  }
  const hasCandidate = typeof candidateCode === "string" && candidateCode.trim() && candidateCode !== code;
  const completeCode = hasCandidate ? candidateCode : code;
  $("code-purpose-summary").textContent = deriveCodePurpose(code, state.findings);
  $("summary-code").textContent = completeCode;
  $("summary-code-label").textContent = hasCandidate ? "候选修改后完整代码" : "当前完整代码";
  $("summary-code-note").textContent = hasCandidate
    ? "这是修复方案生成的候选代码，应用后请重新分析。"
    : state.appliedRepair
      ? "已应用修复方案，当前内容已完成复检。"
      : "尚未应用自动修复，下面是当前编辑器中的完整代码。";
  $("code-summary-note").textContent = `共 ${completeCode ? completeCode.split("\n").length : 0} 行；总结根据当前代码和静态分析结果生成。`;
  panel.hidden = false;
}

function renderFindings() {
  const list = $("findings-list");
  const normalizedQuery = state.findingQuery.trim().toLowerCase();
  const visibleFindings = state.findings
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => {
      const severity = String(finding.severity || "INFO").toLowerCase();
      const matchesSeverity = state.findingSeverityFilter === "all" || severity === state.findingSeverityFilter;
      const haystack = [finding.rule_id, finding.message, finding.file_path, finding.severity].join(" ").toLowerCase();
      return matchesSeverity && (!normalizedQuery || haystack.includes(normalizedQuery));
    });
  $("finding-visible-count").textContent = state.findings.length && visibleFindings.length !== state.findings.length
    ? `${visibleFindings.length} / ${state.findings.length} 个问题`
    : `${state.findings.length} 个问题`;
  if (!visibleFindings.some(({ index }) => index === state.selectedFinding)) {
    const previousSelection = state.selectedFinding;
    state.selectedFinding = visibleFindings.length ? visibleFindings[0].index : -1;
    if (state.selectedFinding !== previousSelection) resetRepairPanel();
  }
  if (!state.findings.length) {
    list.innerHTML = state.analysisResult
      ? `<div class="entity-empty"><strong>未发现静态问题</strong><span>当前代码未命中已配置的检测规则。</span></div>`
      : `<div class="entity-empty"><strong>暂无分析结果</strong><span>运行静态分析后，问题会按风险等级列出。</span></div>`;
    $("finding-detail").className = "finding-detail empty-detail";
    $("finding-detail").innerHTML = `<div class="detail-placeholder"><div class="placeholder-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3.5 20 7v5c0 4.2-3 7.5-8 8.8C7 19.5 4 16.2 4 12V7l8-3.5Z"/><path d="M12 8v4M12 15.5h.01"/></svg></div><strong>选择一个问题</strong><span>详情、位置和修复建议会显示在这里。</span></div>`;
    return;
  }

  if (!visibleFindings.length) {
    list.innerHTML = `<div class="entity-empty"><strong>没有匹配的问题</strong><span>调整风险等级或搜索关键词后再试。</span></div>`;
    $("finding-detail").className = "finding-detail empty-detail";
    $("finding-detail").innerHTML = `<div class="detail-placeholder"><div class="placeholder-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4M8.5 11h5"/></svg></div><strong>筛选结果为空</strong><span>当前条件没有匹配的问题。</span></div>`;
    return;
  }

  list.innerHTML = visibleFindings.map(({ finding, index }) => {
    const severity = String(finding.severity || "INFO").toUpperCase();
    return `<button class="finding-row ${index === state.selectedFinding ? "selected" : ""}" type="button" data-finding-index="${index}">
      <span class="finding-topline"><span class="finding-rule">${escapeHtml(finding.rule_id)}</span><span class="severity ${severityClass(severity)}">${escapeHtml(severity)}</span></span>
      <span class="finding-message">${escapeHtml(finding.message)}</span>
      <span class="finding-location">${escapeHtml(finding.file_path)}:${escapeHtml(finding.line)}:${escapeHtml(finding.column)}</span>
    </button>`;
  }).join("");

  list.querySelectorAll("[data-finding-index]").forEach((button) => {
    button.addEventListener("click", () => {
      resetRepairPanel();
      state.selectedFinding = Number(button.dataset.findingIndex);
      renderFindings();
    });
  });
  renderFindingDetail();
}

function applyFindingFilters() {
  state.findingSeverityFilter = $("finding-severity-filter").value;
  state.findingQuery = $("finding-search").value;
  renderFindings();
}

function renderFindingDetail() {
  const detail = $("finding-detail");
  const finding = state.findings[state.selectedFinding];
  if (!finding) return;
  const severity = String(finding.severity || "INFO").toUpperCase();
  detail.className = "finding-detail";
  detail.innerHTML = `<div class="detail-content">
    <span class="panel-label">FINDING DETAIL</span>
    <h4>${escapeHtml(finding.message)}</h4>
    <div class="detail-meta"><span class="severity ${severityClass(severity)}">${escapeHtml(severity)}</span><span>${escapeHtml(finding.rule_id)}</span><span>${escapeHtml(finding.file_path)}:${escapeHtml(finding.line)}:${escapeHtml(finding.column)}</span></div>
    <div class="detail-block"><div class="detail-block-label">问题说明</div><p>${escapeHtml(finding.message)}</p></div>
    <div class="detail-block"><div class="detail-block-label">处理建议</div><p>${escapeHtml(suggestionFor(finding.rule_id, finding.message))}</p></div>
    <div class="detail-actions"><button class="button button-secondary" type="button" id="generate-repair">生成修复方案</button><span>先查看候选代码，再决定是否应用。</span></div>
  </div>`;
  $("generate-repair").addEventListener("click", generateRepair);
}

function suggestionFor(ruleId, message) {
  const rule = String(ruleId || "");
  if (rule === "PY-SYNTAX") return "先修正语法错误，再重新运行静态分析。";
  if (rule.includes("CMD")) return "避免将外部输入直接传给系统命令。优先使用参数数组调用 subprocess，并对参数执行白名单校验。";
  if (rule.includes("EXEC")) return "移除动态代码执行，改为显式的数据解析或固定的函数映射。";
  if (rule === "PY-DESERIALIZE-001") return "不要反序列化不可信数据，改用 JSON 等不执行代码的格式，并校验输入结构。";
  if (rule === "PY-DESERIALIZE-002") return "使用 yaml.safe_load，并限制可接受的数据类型。";
  if (rule === "PY-SQL-001") return "使用数据库驱动提供的参数占位符传入外部数据，不要用 f-string 或字符串拼接构造 SQL。";
  if (rule === "PY-TLS-001") return "移除 verify=False，启用证书验证；若使用内部证书，请正确配置可信 CA。";
  if (rule.includes("SECRET")) return "将敏感配置移到环境变量或密钥管理服务，不要写入源代码和版本库。";
  return `请结合 ${message || "该规则"} 检查输入来源、调用边界和异常处理。`;
}

function renderRepair(response, originalCode) {
  const available = response.status === "available" && typeof response.candidate_code === "string";
  const status = available ? (response.target_resolved ? "静态复检通过" : "已生成，仍需检查") : "需要人工修复";
  $("repair-state").textContent = status;
  $("repair-state").className = `analysis-state ${available ? "ready" : ""}`.trim();
  const warnings = Array.isArray(response.warnings) ? response.warnings : [];
  const remaining = Array.isArray(response.remaining_findings) ? response.remaining_findings : [];
  $("repair-result").innerHTML = `
    <div class="repair-summary">
      <p>${escapeHtml(response.explanation || "暂无修复说明。")}</p>
      <div class="repair-facts"><span>修复前：${escapeHtml(response.before_count)} 个问题</span>${response.after_count === null || response.after_count === undefined ? "" : `<span>候选代码复检后：${escapeHtml(response.after_count)} 个问题</span>`}<span>目标问题：${response.target_resolved ? "已消除" : "尚未确认消除"}</span></div>
      ${warnings.length ? `<div class="repair-warnings"><strong>注意</strong><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : ""}
    </div>
    ${available ? `<div class="repair-comparison"><div><span class="detail-block-label">当前代码</span><pre class="repair-code">${escapeHtml(originalCode)}</pre></div><div><span class="detail-block-label">候选代码</span><pre class="repair-code">${escapeHtml(response.candidate_code)}</pre></div></div>
      <div class="repair-footer"><span>候选代码中仍有 ${remaining.length} 个静态问题，请逐项检查。</span><button class="button button-primary" type="button" id="apply-repair">应用到编辑器并复检</button></div>` : `<div class="repair-manual">该问题需要结合业务逻辑人工修改。请参考上面的说明修改编辑器代码，然后重新运行静态分析。</div>`}`;
  if (available) $("apply-repair").addEventListener("click", applyRepair);
  renderCodeSummary(originalCode, available ? response.candidate_code : null);
}

async function generateRepair() {
  const finding = state.findings[state.selectedFinding];
  if (!finding || !state.analysisResult) {
    showToast("请先运行静态分析并选择一个问题", "error");
    return;
  }
  const originalCode = $("code-input").value;
  const filePath = $("file-path").value.trim() || "<input>";
  const selectedFinding = state.selectedFinding;
  const editorRevision = state.editorRevision;
  const requestId = ++state.repairRequestId;
  const button = $("generate-repair");
  setButtonBusy(button, true, "生成中");
  $("repair-panel").hidden = false;
  $("repair-state").textContent = "生成中";
  $("repair-result").innerHTML = `<div class="entity-empty"><strong>正在生成并复检候选代码</strong></div>`;
  try {
    const response = await requestJson("/api/repair/python", jsonOptions({
      file_path: filePath,
      code: originalCode,
      rule_id: finding.rule_id,
      line: finding.line,
      column: finding.column,
    }));
    if (requestId !== state.repairRequestId || editorRevision !== state.editorRevision || selectedFinding !== state.selectedFinding || originalCode !== $("code-input").value || filePath !== ($("file-path").value.trim() || "<input>")) return;
    state.repair = { finding: { ...finding }, source_code: originalCode, analysis_before: state.analysisResult, result: response };
    renderRepair(response, originalCode);
    updateReportButton();
    showToast(response.status === "available" ? "修复方案已生成" : "已生成手动修复建议");
  } catch (error) {
    if (requestId !== state.repairRequestId || editorRevision !== state.editorRevision || selectedFinding !== state.selectedFinding) return;
    $("repair-state").textContent = "生成失败";
    $("repair-state").className = "analysis-state error";
    $("repair-result").innerHTML = `<div class="entity-empty"><strong>无法生成修复方案</strong><span>${escapeHtml(error.message)}</span></div>`;
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function applyRepair() {
  const repair = state.repair;
  if (!repair || repair.result.status !== "available" || typeof repair.result.candidate_code !== "string" || $("code-input").value !== repair.source_code) {
    showToast("原始代码已变化，请重新生成修复方案", "error");
    return;
  }
  $("code-input").value = repair.result.candidate_code;
  invalidateAnalysis(true);
  state.appliedRepair = { ...repair, applied_to_editor: true };
  updateEditorMeta();
  $("last-action").textContent = "修复方案已应用到编辑器，正在复检";
  runStaticAnalysis();
}

function downloadReport() {
  if (!state.analysisResult) return;
  const filePath = $("file-path").value.trim() || "input.py";
  const report = {
    generated_at: new Date().toISOString(),
    file_path: filePath,
    code: $("code-input").value,
    analysis: state.analysisResult,
    history_id: state.reviewSnapshot?.id || null,
    comparison: state.reviewSnapshot?.comparison || null,
    repair: state.repair || state.appliedRepair,
    code_summary: {
      purpose: $("code-purpose-summary")?.textContent || "",
      complete_code: $("summary-code")?.textContent || $("code-input").value,
    },
  };
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const baseName = filePath.split(/[\\/]/).pop().replace(/[^a-zA-Z0-9._-]/g, "_") || "review";
  link.href = url;
  link.download = `${baseName}-review-report.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast("审查报告已下载");
}

async function runStaticAnalysis() {
  const code = $("code-input").value;
  const filePath = $("file-path").value.trim() || "<input>";
  const button = $("static-analysis");
  if (!code.trim()) {
    showToast("请先输入或导入代码", "error");
    $("code-input").focus();
    return;
  }
  const analysisRequestId = ++state.analysisRequestId;
  resetRepairPanel();
  state.analysisResult = null;
  state.reviewSnapshot = null;
  renderReviewComparison(null);
  state.findings = [];
  state.selectedFinding = -1;
  renderSummary("-", "正在分析");
  renderFindings();
  updateReportButton();
  setButtonBusy(button, true, "分析中");
  setAnalysisState("分析中");
  $("last-action").textContent = "正在运行 Python AST 分析";
  try {
    const snapshot = await requestJson("/api/reviews", jsonOptions({ file_path: filePath, code }));
    if (analysisRequestId !== state.analysisRequestId || code !== $("code-input").value || filePath !== ($("file-path").value.trim() || "<input>")) {
      $("last-action").textContent = "代码已修改，等待重新分析";
      return;
    }
    const result = snapshot.analysis;
    state.reviewSnapshot = snapshot;
    state.analysisResult = result;
    state.findings = result.findings || [];
    state.selectedFinding = state.findings.length ? 0 : -1;
    renderSummary(result.analyzer);
    renderFindings();
    renderCodeSummary(code, state.appliedRepair?.result?.candidate_code || null);
    renderReviewComparison(snapshot);
    setAnalysisState(state.findings.length ? `${state.findings.length} 个问题` : "未发现问题", "ready");
    updateReportButton();
    $("last-action").textContent = `静态分析完成 · ${state.findings.length} 个问题`;
    showToast(state.findings.length ? `发现 ${state.findings.length} 个潜在问题` : "未发现静态问题");
  } catch (error) {
    if (analysisRequestId !== state.analysisRequestId) return;
    state.analysisResult = null;
    state.findings = [];
    state.selectedFinding = -1;
    renderSummary("-", "分析失败");
    renderFindings();
    renderCodeSummary();
    setAnalysisState("分析失败", "error");
    $("last-action").textContent = "分析失败";
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function renderLlmResult(response) {
  const result = response.result || {};
  const unsafe = result.is_vulnerability === true || ["CRITICAL", "HIGH", "MEDIUM"].includes(String(result.severity || "").toUpperCase());
  const verdict = result.is_vulnerability === false ? "未确认漏洞" : unsafe ? "存在安全风险" : "需要进一步判断";
  const verdictClass = result.is_vulnerability === false ? "safe" : unsafe ? "unsafe" : "";
  const explanation = result.explanation || "模型没有返回可展示的解释。";
  const suggestion = result.suggestion || "模型没有返回具体修复建议。";
  $("llm-result").innerHTML = `<div class="llm-grid">
    <div class="llm-summary"><div class="llm-verdict ${verdictClass}"><span class="status-dot ${unsafe ? "error" : ""}"></span>${escapeHtml(verdict)}</div><p>${escapeHtml(response.provider)} · ${escapeHtml(response.model)}</p>${result.cwe ? `<p>${escapeHtml(result.cwe)}</p>` : ""}${result.confidence !== undefined ? `<p>置信度 ${(Number(result.confidence) * 100).toFixed(0)}%</p>` : ""}</div>
    <div class="llm-copy"><div><div class="detail-block-label">判断依据</div><p>${escapeHtml(explanation)}</p></div><div><div class="detail-block-label">修复建议</div><p>${escapeHtml(suggestion)}</p></div><details><summary>查看原始 JSON</summary><pre class="llm-json">${escapeHtml(JSON.stringify(result, null, 2))}</pre></details></div>
  </div>`;
}

async function runLlmReview() {
  const code = $("code-input").value;
  const filePath = $("file-path").value.trim() || "<input>";
  const button = $("llm-review");
  if (!code.trim()) {
    showToast("请先输入或导入代码", "error");
    $("code-input").focus();
    return;
  }
  $("llm-panel").hidden = false;
  $("llm-state").textContent = "请求中";
  setButtonBusy(button, true, "审查中");
  try {
    const response = await requestJson("/api/review/llm", jsonOptions({
      provider: $("llm-provider").value,
      file_path: filePath,
      code,
      context: $("review-context").value.trim(),
      static_findings: state.findings,
    }));
    renderLlmResult(response);
    $("llm-state").textContent = "已完成";
    $("llm-state").className = "analysis-state ready";
    $("last-action").textContent = "大模型审查完成";
    showToast("大模型审查已完成");
  } catch (error) {
    $("llm-state").textContent = "请求失败";
    $("llm-state").className = "analysis-state error";
    $("llm-result").innerHTML = `<div class="entity-empty"><strong>无法完成模型审查</strong><span>${escapeHtml(error.message)}</span></div>`;
    $("last-action").textContent = "大模型审查失败";
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function resetReview() {
  $("code-input").value = SAMPLE_CODE;
  $("file-path").value = "src/unsafe_command.py";
  $("review-context").value = "命令执行与不可信数据反序列化路径";
  state.analysisRequestId += 1;
  state.findings = [];
  state.selectedFinding = -1;
  state.analysisResult = null;
  state.reviewSnapshot = null;
  state.findingSeverityFilter = "all";
  state.findingQuery = "";
  $("finding-severity-filter").value = "all";
  $("finding-search").value = "";
  renderReviewComparison(null);
  state.appliedRepair = null;
  state.editorRevision += 1;
  resetRepairPanel();
  renderSummary();
  renderFindings();
  renderCodeSummary();
  setAnalysisState("待分析");
  $("llm-panel").hidden = true;
  $("last-action").textContent = "示例代码已载入";
  updateEditorMeta();
  updateReportButton();
}

function setHealth(healthy) {
  state.health = healthy;
  const dot = $("sidebar-status-dot");
  const text = $("sidebar-status-text");
  dot.className = `status-dot ${healthy ? "" : "error"}`.trim();
  text.textContent = healthy ? "服务在线" : "服务离线";
  document.querySelectorAll(".connection-pill .status-dot").forEach((item) => {
    item.className = `status-dot ${healthy ? "" : "error"}`.trim();
  });
}

async function refreshHealth(showMessage = false) {
  try {
    await requestJson("/api/health");
    setHealth(true);
    if (showMessage) showToast("API 服务正常");
  } catch (error) {
    setHealth(false);
    if (showMessage) showToast("无法连接 API 服务", "error");
  }
}

async function refreshDashboardSummary() {
  const requestId = ++state.dashboardRequestId;
  try {
    const summary = await requestJson("/api/dashboard/summary");
    if (requestId !== state.dashboardRequestId) return;
    state.dashboardSummary = {
      scan_finding_count: summary?.scan_finding_count,
      high_risk_count: summary?.high_risk_count,
      medium_risk_count: summary?.medium_risk_count,
      other_finding_count: summary?.other_finding_count,
      project_count: summary?.project_count,
      scan_count: summary?.scan_count,
    };
  } catch {
    if (requestId !== state.dashboardRequestId) return;
    state.dashboardSummary = null;
  }
  renderDashboardSummary();
}

function renderProjects() {
  const list = $("project-list");
  $("project-count").textContent = `${state.projects.length} 个项目`;
  if (!state.projects.length) {
    list.innerHTML = `<div class="entity-empty"><strong>还没有项目</strong><span>创建一个项目后，可以从扫描任务发起目录扫描。</span></div>`;
  } else {
    list.innerHTML = state.projects.map((project) => `<div class="entity-row"><div><div class="entity-name">${escapeHtml(project.name)}</div><div class="entity-meta"><span>${escapeHtml(project.language)}</span><span>${escapeHtml(project.source_path || "未绑定源码目录")}</span><span>${escapeHtml(formatDate(project.created_at))}</span></div></div><span class="entity-status">${escapeHtml(project.id.slice(0, 8))}</span></div>`).join("");
  }
  const select = $("scan-project");
  select.innerHTML = state.projects.length ? state.projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join("") : `<option value="">请先创建项目</option>`;
}

async function loadProjects() {
  try {
    state.projects = await requestJson("/api/projects");
    renderProjects();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function createProject(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  setButtonBusy(button, true, "创建中");
  try {
    const project = await requestJson("/api/projects", jsonOptions({
      name: $("project-name").value.trim(),
      language: $("project-language").value,
      source_path: $("project-source").value.trim() || null,
      description: $("project-description").value.trim() || null,
    }));
    state.projects.unshift(project);
    renderProjects();
    refreshDashboardSummary();
    form.reset();
    showToast("项目已创建");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function renderScans() {
  const list = $("scan-list");
  if (!state.scans.length) {
    list.innerHTML = `<div class="entity-empty"><strong>还没有扫描任务</strong><span>选择一个项目后创建同步扫描。</span></div>`;
    return;
  }
  list.innerHTML = state.scans.slice().reverse().map((scan) => {
    const project = state.projects.find((item) => item.id === scan.project_id);
    const status = String(scan.status || "created");
    return `<div class="entity-row"><div><div class="entity-name">${escapeHtml(project?.name || scan.project_id)}</div><div class="entity-meta"><span>${escapeHtml(formatDate(scan.created_at))}</span><span>${escapeHtml(scan.id.slice(0, 8))}</span><span>${scan.error ? escapeHtml(scan.error) : `${escapeHtml(scan.finding_count)} 个问题`}</span></div></div><div class="entity-actions"><span class="entity-status ${status}">${escapeHtml(status)}</span>${status === "completed" ? `<button class="text-button" type="button" data-scan-id="${escapeHtml(scan.id)}">查看问题</button>` : ""}</div></div>`;
  }).join("");
  list.querySelectorAll("[data-scan-id]").forEach((button) => {
    button.addEventListener("click", () => loadScanFindings(button.dataset.scanId));
  });
}

async function loadScanFindings(scanId) {
  const panel = $("scan-results");
  panel.hidden = false;
  $("scan-findings").innerHTML = `<div class="entity-empty"><strong>正在获取扫描结果</strong></div>`;
  try {
    const findings = await requestJson(`/api/scans/${encodeURIComponent(scanId)}/findings`);
    $("scan-results-count").textContent = `${findings.length} 个问题`;
    $("scan-findings").innerHTML = findings.length ? findings.map((finding) => {
      const severity = String(finding.severity || "INFO").toUpperCase();
      return `<div class="scan-finding"><div class="finding-topline"><span class="finding-rule">${escapeHtml(finding.rule_id)}</span><span class="severity ${severityClass(severity)}">${escapeHtml(severity)}</span></div><strong>${escapeHtml(finding.message)}</strong><span>${escapeHtml(finding.file_path)}:${escapeHtml(finding.line)}:${escapeHtml(finding.column)}</span></div>`;
    }).join("") : `<div class="entity-empty"><strong>未发现静态问题</strong><span>扫描任务已完成。</span></div>`;
  } catch (error) {
    $("scan-findings").innerHTML = `<div class="entity-empty"><strong>无法获取扫描结果</strong><span>${escapeHtml(error.message)}</span></div>`;
    showToast(error.message, "error");
  }
}

async function createScan(event) {
  event.preventDefault();
  const projectId = $("scan-project").value;
  if (!projectId) {
    showToast("请先创建并选择项目", "error");
    return;
  }
  const button = event.currentTarget.querySelector("button[type=submit]");
  setButtonBusy(button, true, "扫描中");
  try {
    const scan = await requestJson("/api/scans", jsonOptions({ project_id: projectId }));
    state.scans.push(scan);
    renderScans();
    refreshDashboardSummary();
    if (scan.status === "completed") loadScanFindings(scan.id);
    showToast(scan.status === "completed" ? `扫描完成，发现 ${scan.finding_count} 个问题` : "扫描任务已创建");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function renderGithubPRReview(response) {
  const stateLabel = response.finding_count ? `${response.finding_count} 个问题` : "未发现问题";
  $("github-pr-state").textContent = stateLabel;
  $("github-pr-state").className = `analysis-state ${response.finding_count ? "error" : "ready"}`.trim();
  const warnings = Array.isArray(response.warnings) ? response.warnings : [];
  $("github-pr-summary").innerHTML = `<div class="github-summary-card">
    <div class="github-summary-title"><a href="${escapeHtml(response.pr_url)}" target="_blank" rel="noreferrer">${escapeHtml(response.repository)}#${escapeHtml(response.number)}</a><strong>${escapeHtml(response.title)}</strong></div>
    <div class="github-summary-meta"><span>基准分支 ${escapeHtml(response.base_branch || "-")}</span><span>变更文件 ${escapeHtml(response.changed_file_count)}</span><span>已分析 ${escapeHtml(response.analyzed_file_count)}</span><span>问题 ${escapeHtml(response.finding_count)}</span></div>
    ${warnings.length ? `<div class="github-warnings">${warnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}</div>` : ""}
  </div>`;
  $("github-pr-files").innerHTML = response.files?.length ? response.files.map((file) => {
    const findings = Array.isArray(file.findings) ? file.findings : [];
    const findingMarkup = findings.length ? findings.map((finding) => `<div class="github-finding"><div class="finding-topline"><span class="finding-rule">${escapeHtml(finding.rule_id)}</span><span class="severity ${severityClass(finding.severity)}">${escapeHtml(finding.severity)}</span></div><strong>${escapeHtml(finding.message)}</strong><span>${escapeHtml(finding.file_path)}:${escapeHtml(finding.line)}:${escapeHtml(finding.column)}</span></div>`).join("") : `<div class="github-file-empty">${file.skipped_reason ? escapeHtml(file.skipped_reason) : "未发现静态问题"}</div>`;
    const llmMarkup = file.llm_review?.result ? `<div class="github-llm-note"><strong>大模型意见</strong><span>${escapeHtml(file.llm_review.result.explanation || file.llm_review.result.suggestion || "已返回审查结果")}</span></div>` : file.llm_error ? `<div class="github-file-empty">大模型审查失败：${escapeHtml(file.llm_error)}</div>` : "";
    return `<article class="github-file"><div class="github-file-heading"><div><strong>${escapeHtml(file.path)}</strong><span>${escapeHtml(file.status)} · +${escapeHtml(file.additions)} / -${escapeHtml(file.deletions)}</span></div><span class="entity-status ${file.analyzed ? "completed" : ""}">${file.analyzed ? `${findings.length} 个问题` : "已跳过"}</span></div><div class="github-file-findings">${findingMarkup}${llmMarkup}</div></article>`;
  }).join("") : `<div class="entity-empty"><strong>没有可展示的文件</strong></div>`;
}

async function runGithubPRReview(event) {
  event.preventDefault();
  const url = $("github-pr-url").value.trim();
  if (!url) {
    showToast("请输入 GitHub Pull Request 地址", "error");
    return;
  }
  const button = event.currentTarget.querySelector("button[type=submit]");
  const requestId = ++state.githubRequestId;
  setButtonBusy(button, true, "审查中");
  $("github-pr-state").textContent = "读取中";
  $("github-pr-state").className = "analysis-state";
  $("github-pr-summary").innerHTML = `<div class="entity-empty"><strong>正在读取 Pull Request</strong><span>下载变更文件并运行静态分析，请稍候。</span></div>`;
  $("github-pr-files").innerHTML = "";
  try {
    const response = await requestJson("/api/github/pr/review", jsonOptions({
      pr_url: url,
      provider: $("github-pr-provider").value,
      include_llm: $("github-pr-llm").checked,
    }));
    if (requestId !== state.githubRequestId) return;
    renderGithubPRReview(response);
    showToast(response.finding_count ? `PR 审查完成，发现 ${response.finding_count} 个问题` : "PR 审查完成，未发现静态问题");
  } catch (error) {
    if (requestId !== state.githubRequestId) return;
    $("github-pr-state").textContent = "审查失败";
    $("github-pr-state").className = "analysis-state error";
    $("github-pr-summary").innerHTML = `<div class="entity-empty"><strong>无法审查该 Pull Request</strong><span>${escapeHtml(error.message)}</span></div>`;
    showToast(error.message, "error");
  } finally {
    setButtonBusy(button, false);
  }
}

function comparisonMarkup(comparison) {
  const available = comparison.available;
  const counts = [
    ["新增问题", comparison.new_count, "new"],
    ["仍然存在", comparison.persistent_count, "persistent"],
    ["未再检出", comparison.absent_count, "absent"],
  ];
  const statusNames = { new: "新增", persistent: "仍存在", absent: "未再检出" };
  const changes = Array.isArray(comparison.changes) ? comparison.changes : [];
  return `<div class="comparison-body">
    <div class="comparison-metrics">${counts.map(([label, count, kind]) => `<div class="comparison-metric ${kind}"><span>${label}</span><strong>${available ? escapeHtml(count) : "—"}</strong></div>`).join("")}</div>
    <p class="comparison-explanation">${escapeHtml(comparison.explanation)}</p>
    ${comparison.baseline_created_at ? `<p class="comparison-baseline">对比版本：${escapeHtml(formatDate(comparison.baseline_created_at))}</p>` : ""}
    ${changes.length ? `<details class="comparison-changes"><summary>查看 ${changes.length} 条问题对比记录</summary><div>${changes.map(({ status, finding }) => `<div class="comparison-change"><span class="change-badge ${escapeHtml(status)}">${statusNames[status] || ""}</span><div><strong>${escapeHtml(finding.message)}</strong><span>${escapeHtml(finding.rule_id)} · ${status === "absent" ? "上次位置" : "当前位置"} ${escapeHtml(finding.line)}:${escapeHtml(finding.column)}</span></div></div>`).join("")}</div></details>` : ""}
  </div>`;
}

function renderReviewComparison(snapshot) {
  $("review-comparison-panel").hidden = !snapshot;
  $("review-comparison").innerHTML = snapshot ? comparisonMarkup(snapshot.comparison) : "";
  if (snapshot) $("comparison-save-state").textContent = `已保存 · ${formatDate(snapshot.created_at)}`;
}

function renderReviewHistory() {
  $("history-count").textContent = `共 ${state.historyTotal} 个已保存版本`;
  $("history-page").textContent = state.historyTotal
    ? `${state.historyOffset + 1}–${state.historyOffset + state.historyItems.length} / ${state.historyTotal}` : "0 / 0";
  $("history-prev").disabled = state.historyOffset === 0;
  $("history-next").disabled = state.historyOffset + state.historyItems.length >= state.historyTotal;
  $("history-list").innerHTML = state.historyItems.length ? state.historyItems.map((item) => `<button class="history-row ${item.id === state.historyDetail?.id ? "selected" : ""}" type="button" data-review-id="${escapeHtml(item.id)}">
    <span class="history-row-top"><strong>${escapeHtml(item.file_path)}</strong><span class="severity ${item.high_risk_count ? "severity-high" : "severity-info"}">${item.finding_count} 个问题</span></span>
    <span class="history-row-meta">${escapeHtml(formatDate(item.created_at))} · ${item.line_count} 行 · 高风险 ${item.high_risk_count}</span>
    <span class="history-row-changes">${item.new_count === null ? "基线版本 / 暂无可用对比" : `新增 ${item.new_count} · 仍存在 ${item.persistent_count} · 未再检出 ${item.absent_count}`}</span>
  </button>`).join("") : `<div class="entity-empty"><strong>暂无审查记录</strong><span>${state.historyFilter ? "没有匹配该文件路径的记录。" : "回到代码审查，运行一次静态分析即可保存。"}</span></div>`;
  $("history-list").querySelectorAll("[data-review-id]").forEach((button) => {
    button.addEventListener("click", () => loadHistoryDetail(button.dataset.reviewId));
  });
}

async function loadReviewHistory() {
  const requestId = ++state.historyRequestId;
  $("history-prev").disabled = true;
  $("history-next").disabled = true;
  $("history-list").innerHTML = `<div class="entity-empty"><strong>正在读取审查历史</strong></div>`;
  const query = new URLSearchParams({ limit: "30", offset: String(state.historyOffset) });
  if (state.historyFilter) query.set("file_path", state.historyFilter);
  try {
    const response = await requestJson(`/api/reviews?${query}`);
    if (requestId !== state.historyRequestId) return;
    state.historyItems = response.items;
    state.historyTotal = response.total;
    renderReviewHistory();
  } catch (error) {
    if (requestId !== state.historyRequestId) return;
    $("history-count").textContent = "历史暂不可用";
    $("history-list").innerHTML = `<div class="entity-empty"><strong>无法读取审查历史</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

async function loadHistoryDetail(reviewId) {
  const requestId = ++state.historyDetailRequestId;
  state.historyDetail = null;
  $("history-restore").disabled = true;
  $("history-detail").innerHTML = `<div class="entity-empty"><strong>正在读取历史版本</strong></div>`;
  try {
    const snapshot = await requestJson(`/api/reviews/${encodeURIComponent(reviewId)}`);
    if (requestId !== state.historyDetailRequestId) return;
    state.historyDetail = snapshot;
    renderReviewHistory();
    const findings = snapshot.analysis.findings;
    $("history-detail").innerHTML = `<div class="history-detail-meta"><strong>${escapeHtml(snapshot.file_path)}</strong><span>${escapeHtml(formatDate(snapshot.created_at))} · ${snapshot.finding_count} 个问题</span></div>
      ${comparisonMarkup(snapshot.comparison)}
      <div class="history-source"><div class="detail-block-label">当时的完整代码</div><pre class="summary-code">${escapeHtml(snapshot.code)}</pre></div>
      <div class="history-source"><div class="detail-block-label">当时的静态分析结果</div>${findings.length ? findings.map((finding) => `<div class="scan-finding"><div class="finding-topline"><span class="finding-rule">${escapeHtml(finding.rule_id)}</span><span class="severity ${severityClass(finding.severity)}">${escapeHtml(finding.severity)}</span></div><strong>${escapeHtml(finding.message)}</strong><span>第 ${escapeHtml(finding.line)} 行，第 ${escapeHtml(finding.column)} 列</span></div>`).join("") : `<p class="history-help">未发现静态问题。</p>`}</div>`;
    $("history-restore").disabled = false;
  } catch (error) {
    if (requestId !== state.historyDetailRequestId) return;
    $("history-detail").innerHTML = `<div class="entity-empty"><strong>无法读取该版本</strong><span>${escapeHtml(error.message)}</span></div>`;
  }
}

function restoreHistoryReview() {
  const snapshot = state.historyDetail;
  if (!snapshot) return;
  invalidateAnalysis();
  $("code-input").value = snapshot.code;
  $("file-path").value = snapshot.file_path;
  $("review-context").value = "";
  state.reviewSnapshot = snapshot;
  state.analysisResult = snapshot.analysis;
  state.findings = snapshot.analysis.findings;
  state.selectedFinding = state.findings.length ? 0 : -1;
  updateEditorMeta();
  renderSummary(snapshot.analysis.analyzer);
  renderFindings();
  renderCodeSummary(snapshot.code);
  renderReviewComparison(snapshot);
  updateReportButton();
  setAnalysisState("历史版本", "ready");
  $("last-action").textContent = `已载入 ${formatDate(snapshot.created_at)} 的记录；可修改后重新分析`;
  switchView("review");
  showToast("历史代码和分析结果已载入");
}

function switchView(view) {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== view;
    panel.classList.toggle("active", panel.dataset.viewPanel === view);
  });
  const titles = {
    review: ["代码审查工作台", "将静态规则与大语言模型审查放在同一条工作流中。"],
    github: ["GitHub PR 审查", "读取 Pull Request 变更，并复用本地静态分析和大语言模型审查。"],
    projects: ["项目空间", "管理源码目录和扫描范围。"],
    scans: ["扫描任务", "查看同步扫描任务的状态和结果。"],
    history: ["审查历史", "回看已保存的代码与分析结果，追踪每次修改后的问题变化。"],
    knowledge: ["代码知识图谱", "解释函数的作用，沿着调用与依赖关系理解项目。"],
  };
  $("page-title").textContent = titles[view][0];
  $("page-description").textContent = titles[view][1];
  refreshDashboardSummary();
  if (view === "projects" || view === "scans") loadProjects();
  if (view === "scans") renderScans();
  if (view === "history") loadReviewHistory();
}

function bindEvents() {
  $("code-input").addEventListener("input", () => { updateEditorMeta(); invalidateAnalysis(); });
  $("file-path").addEventListener("input", invalidateAnalysis);
  $("static-analysis").addEventListener("click", runStaticAnalysis);
  $("llm-review").addEventListener("click", runLlmReview);
  $("download-report").addEventListener("click", downloadReport);
  $("copy-summary-code").addEventListener("click", async () => {
    const code = $("summary-code").textContent || "";
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      showToast("完整代码已复制");
    } catch {
      showToast("浏览器未允许复制，请手动选择代码", "error");
    }
  });
  $("reset-code").addEventListener("click", resetReview);
  $("clear-code").addEventListener("click", () => {
    $("code-input").value = "";
    invalidateAnalysis();
    updateEditorMeta();
  });
  $("file-input").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    $("code-input").value = await file.text();
    $("file-path").value = file.name;
    updateEditorMeta();
    invalidateAnalysis();
    showToast(`已导入 ${file.name}`);
  });
  $("refresh-health").addEventListener("click", () => { refreshHealth(true); refreshDashboardSummary(); });
  $("project-form").addEventListener("submit", createProject);
  $("refresh-projects").addEventListener("click", () => { loadProjects(); refreshDashboardSummary(); });
  $("scan-form").addEventListener("submit", createScan);
  $("github-pr-form").addEventListener("submit", runGithubPRReview);
  $("history-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.historyOffset = 0;
    state.historyFilter = $("history-file-filter").value.trim();
    state.historyDetailRequestId += 1;
    state.historyDetail = null;
    $("history-restore").disabled = true;
    $("history-detail").innerHTML = `<div class="entity-empty"><strong>选择一条审查记录</strong></div>`;
    loadReviewHistory();
  });
  $("history-prev").addEventListener("click", () => { state.historyOffset = Math.max(0, state.historyOffset - 30); loadReviewHistory(); });
  $("history-next").addEventListener("click", () => { state.historyOffset += 30; loadReviewHistory(); });
  $("history-restore").addEventListener("click", restoreHistoryReview);
  $("finding-severity-filter").addEventListener("change", applyFindingFilters);
  $("finding-search").addEventListener("input", applyFindingFilters);
  document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));
}

function init() {
  $("service-address").textContent = window.location.host;
  bindEvents();
  resetReview();
  renderProjects();
  renderScans();
  renderDashboardSummary();
  refreshHealth();
  refreshDashboardSummary();
  loadProjects();
  window.setInterval(() => refreshHealth(), 30000);
}

init();
