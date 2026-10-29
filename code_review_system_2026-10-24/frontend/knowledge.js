(() => {
  "use strict";
  const kg = { mode: "paste", files: [], archive: null, graph: null, selected: "", revision: 0, building: false, explaining: false, stop: false, camera: { x: 0, y: 0, w: 1000, h: 560 } };
  const kindNames = { file: "文件", class: "类", function: "函数 / 方法", external: "外部 / 未解析" };
  const sourceNames = { static: "源码结构分析", docstring: "源码文档字符串", codex: "Codex 语义说明" };
  const ignored = new Set([".git", ".venv", "venv", "env", "__pycache__", "node_modules", "site-packages", "__MACOSX"]);
  const demo = [
    { path: "shop/api.py", code: 'from .service import create_order\n\ndef submit_order(user_id: int, items: list):\n    """接收订单请求，将用户与商品列表交给订单服务。"""\n    return create_order(user_id, items)\n' },
    { path: "shop/service.py", code: 'from .pricing import calculate_total\nfrom .repository import save_order\n\ndef create_order(user_id: int, items: list):\n    """计算订单总价并保存，返回创建的订单。"""\n    total = calculate_total(items)\n    return save_order(user_id, items, total)\n' },
    { path: "shop/pricing.py", code: 'def calculate_total(items: list) -> float:\n    """累加每种商品的单价乘数量，得到订单总价。"""\n    return sum(item["price"] * item["quantity"] for item in items)\n' },
    { path: "shop/repository.py", code: 'def save_order(user_id: int, items: list, total: float) -> dict:\n    """构建订单记录。示例只返回字典，并未写入数据库。"""\n    return {"user_id": user_id, "items": items, "total": total}\n' },
  ];

  function setStatus(message, kind = "") {
    $("kg-state").textContent = message;
    $("kg-state").className = `analysis-state ${kind}`.trim();
  }

  function invalidate() {
    kg.revision += 1;
    kg.stop = true;
    kg.graph = null;
    kg.selected = "";
    $("kg-results").hidden = true;
    $("kg-export").disabled = true;
    setStatus("输入已就绪，请生成图谱");
  }

  function setInput(mode, files = [], archive = null) {
    kg.mode = mode; kg.files = files; kg.archive = archive;
    $("kg-paste").hidden = mode !== "paste";
    $("kg-import-info").hidden = mode === "paste";
    $("kg-use-paste").hidden = mode === "paste";
    $("kg-import-info").textContent = mode === "zip" ? `已选择 ${archive.name}（${(archive.size / 1024).toFixed(1)} KB），点击生成后读取项目。` : `已导入 ${files.length} 个 Python 文件：${files.slice(0, 8).map(f => f.path).join("、")}${files.length > 8 ? " 等" : ""}`;
    invalidate();
  }

  async function readFiles(input) {
    try {
      const files = Array.from(input.files || []).filter(f => f.name.toLowerCase().endsWith(".py") && !(f.webkitRelativePath || f.name).split("/").some(p => ignored.has(p)));
      if (!files.length) throw new Error("没有找到 Python 文件，请选择 .py 文件或包含源码的文件夹。");
      if (files.length > 150 || files.some(f => f.size > 512000) || files.reduce((s, f) => s + f.size, 0) > 3000000) throw new Error("最多 150 个文件，单文件 512 KB，源码合计 3 MB。请只选择业务源码目录。");
      const loaded = await Promise.all(files.map(async f => ({ path: f.webkitRelativePath || f.name, code: await f.text() })));
      setInput("files", loaded);
    } catch (error) { showToast(error.message, "error"); }
    input.value = "";
  }

  async function buildGraph() {
    if (kg.building) return;
    const revision = kg.revision;
    const button = $("kg-build");
    kg.building = true;
    setButtonBusy(button, true, "正在建立关系…");
    setStatus("正在解析源码");
    try {
      let graph;
      if (kg.mode === "zip") {
        graph = await requestJson("/api/knowledge/archive", { method: "POST", headers: { "Content-Type": "application/zip" }, body: kg.archive });
      } else {
        const files = kg.mode === "paste" ? [{ path: $("kg-path").value.trim() || "main.py", code: $("kg-code").value }] : kg.files;
        if (!files.length || (kg.mode === "paste" && !files[0].code.trim())) throw new Error("请先粘贴代码或导入项目。");
        graph = await requestJson("/api/knowledge/graph", jsonOptions({ files }));
      }
      if (revision !== kg.revision) return;
      kg.graph = graph;
      kg.selected = graph.nodes.find(n => n.kind === "function")?.id || graph.nodes[0]?.id || "";
      $("kg-results").hidden = false;
      $("kg-export").disabled = false;
      $("kg-overview").textContent = structuralOverview(graph);
      $("kg-overview-source").textContent = "结构分析";
      $("kg-ai-state").textContent = "基础说明已生成；可用 Codex 补充业务作用和协作流程。解释会提交相关源码片段。";
      $("kg-search").value = "";
      $("kg-file-filter").innerHTML = '<option value="">全部文件</option>' + graph.files.map(f => `<option value="${escapeHtml(f.path)}">${escapeHtml(f.path)}</option>`).join("");
      $("kg-stats").innerHTML = [["Python 文件", graph.file_count], ["函数 / 方法", graph.function_count], ["类", graph.class_count], ["项目内调用关系", graph.edges.filter(e => e.kind === "calls" && e.resolution !== "unresolved").length]].map(([label, count]) => `<div class="kg-stat"><span>${label}</span><strong>${count}</strong></div>`).join("");
      $("kg-warnings").hidden = !graph.warnings.length;
      $("kg-warnings").innerHTML = graph.warnings.slice(0, 30).map(w => `<p>${escapeHtml(w)}</p>`).join("");
      setStatus(graph.warnings.length ? "已生成 · 部分文件需检查" : "图谱已生成", "ready");
      renderSymbols(); renderDetail(); renderMap();
      showToast(`已识别 ${graph.function_count} 个函数 / 方法`);
    } catch (error) {
      if (revision === kg.revision) { setStatus("建图失败", "error"); showToast(error.message, "error"); }
    } finally { kg.building = false; setButtonBusy(button, false); }
  }

  function structuralOverview(graph) {
    const names = new Map(graph.nodes.map(n => [n.id, n.name]));
    const calls = graph.edges.filter(e => e.kind === "calls" && e.resolution !== "unresolved");
    const incoming = new Set(calls.map(e => e.target));
    const roots = graph.nodes.filter(n => n.kind === "function" && !incoming.has(n.id));
    let content = graph.overview;
    if (roots.length) content += `\n图中没有项目内调用者的函数包括 ${roots.slice(0, 6).map(n => n.name).join("、")}；它们可能是入口、回调或尚未被引用的函数。`;
    if (calls.length) content += "\n主要协作关系：" + calls.slice(0, 6).map(e => `${names.get(e.source)} → ${names.get(e.target)}`).join("；") + "。";
    else content += "\n尚未识别出项目内的直接调用；可查看独立函数和外部调用，或导入相关模块补充上下文。";
    return content;
  }

  function selectNode(id) {
    kg.selected = id;
    renderSymbols(); renderDetail(); renderMap(false);
  }

  function renderSymbols() {
    if (!kg.graph) return;
    const query = $("kg-search").value.trim().toLowerCase();
    const nodes = kg.graph.nodes.filter(n => n.kind !== "external" && `${n.qualified_name} ${n.file_path} ${n.summary}`.toLowerCase().includes(query));
    $("kg-symbol-list").innerHTML = nodes.map(n => `<button class="kg-symbol ${kg.selected === n.id ? "selected" : ""}" type="button" data-node="${escapeHtml(n.id)}"><strong>${escapeHtml(n.name)}</strong><span>${kindNames[n.kind]} · ${escapeHtml(n.file_path)}:${n.line}</span><p>${escapeHtml(n.summary.slice(0, 110))}</p></button>`).join("") || '<div class="entity-empty"><strong>没有匹配的节点</strong></div>';
  }

  function renderDetail() {
    const graph = kg.graph;
    if (!graph) return;
    const node = graph.nodes.find(n => n.id === kg.selected);
    if (!node) return;
    $("kg-explain-node").disabled = kg.explaining || node.kind === "external";
    const related = graph.edges.filter(e => e.source === node.id || e.target === node.id);
    const rows = related.map(e => {
      const outgoing = e.source === node.id;
      const other = graph.nodes.find(n => n.id === (outgoing ? e.target : e.source));
      if (!other) return "";
      return `<button type="button" class="kg-relation-row" data-node="${escapeHtml(other.id)}">${outgoing ? "→" : "←"} ${escapeHtml(e.label)} · ${escapeHtml(other.name)}<span>${escapeHtml(other.file_path)} · 关系位置：${e.lines.join("、")} 行${e.resolution === "inferred" ? " · 根据实例绑定推断" : e.resolution === "unresolved" ? " · 目标尚未确定" : ""}</span></button>`;
    }).join("");
    $("kg-detail").innerHTML = `<div class="kg-detail-body"><div class="kg-detail-path">${escapeHtml(node.qualified_name)}<br>${escapeHtml(node.file_path)}:${node.line}–${node.end_line}</div><pre class="kg-detail-signature">${escapeHtml(node.signature || node.name)}</pre><span class="kg-detail-source">${sourceNames[node.summary_source] || "结构分析"}</span><p class="kg-detail-summary">${escapeHtml(node.summary)}</p>${node.kind === "function" ? `<div class="kg-detail-facts"><div><strong>参数</strong>${escapeHtml(node.parameters.join("、") || "无参数")}</div><div><strong>返回类型注解</strong>${escapeHtml(node.returns || "未声明；可参考源码 return 表达式")}</div></div>` : ""}<h4 class="kg-related-heading">与其他节点的联系</h4>${rows || '<p class="kg-relations-empty">没有已提取的关联。</p>'}${node.source ? `<details class="kg-source-details"><summary>查看对应完整源码</summary><pre class="summary-code">${escapeHtml(node.source)}</pre></details>` : ""}</div>`;
  }

  function visibleGraph() {
    const graph = kg.graph;
    if (!graph) return { nodes: [], edges: [], total: 0 };
    const mode = $("kg-relation").value;
    const external = $("kg-external").checked;
    const path = $("kg-file-filter").value;
    let edges = graph.edges.filter(e => mode === "all" || e.kind === mode);
    let allowed = new Set(graph.nodes.filter(n => (external || n.kind !== "external") && (!path || n.file_path === path)).map(n => n.id));
    if (mode === "imports") allowed = new Set(graph.nodes.filter(n => n.kind === "file" && allowed.has(n.id)).map(n => n.id));
    if (mode === "calls") {
      const fileCallers = new Set(edges.map(e => e.source));
      allowed = new Set(graph.nodes.filter(n => allowed.has(n.id) && (n.kind !== "file" || fileCallers.has(n.id) || !graph.function_count)).map(n => n.id));
    }
    if ($("kg-neighbors").checked && kg.selected) {
      const neighbors = new Set([kg.selected]);
      for (const edge of edges) if (edge.source === kg.selected || edge.target === kg.selected) { neighbors.add(edge.source); neighbors.add(edge.target); }
      allowed = new Set([...allowed].filter(id => neighbors.has(id)));
    }
    let nodes = graph.nodes.filter(n => allowed.has(n.id));
    const total = nodes.length;
    // 大项目仅绘制局部；索引仍保留全部节点。选择节点时优先绘制它及其邻居。
    if (nodes.length > 120) {
      const neighbors = new Set([kg.selected]);
      for (const edge of edges) if (edge.source === kg.selected || edge.target === kg.selected) { neighbors.add(edge.source); neighbors.add(edge.target); }
      nodes = [...nodes.filter(n => neighbors.has(n.id)), ...nodes.filter(n => !neighbors.has(n.id))].slice(0, 120);
    }
    allowed = new Set(nodes.map(n => n.id));
    edges = edges.filter(e => allowed.has(e.source) && allowed.has(e.target)).slice(0, 400);
    return { nodes, edges, total };
  }

  function renderMap(fit = true) {
    if (!kg.graph) return;
    const { nodes, edges, total } = visibleGraph();
    const positions = new Map();
    const incoming = new Map(nodes.map(n => [n.id, 0]));
    for (const edge of edges) if (edge.source !== edge.target) incoming.set(edge.target, incoming.get(edge.target) + 1);
    const rank = new Map();
    let roots = nodes.filter(n => !incoming.get(n.id));
    if (!roots.length && nodes.length) roots = [nodes[0]];
    const queue = roots.map(n => [n.id, 0]);
    for (let i = 0; i < queue.length; i += 1) {
      const [id, level] = queue[i];
      if (rank.has(id)) continue;
      rank.set(id, Math.min(level, 7));
      for (const e of edges) if (e.source === id && !rank.has(e.target)) queue.push([e.target, level + 1]);
    }
    for (const n of nodes) if (!rank.has(n.id)) rank.set(n.id, 0);
    const columns = new Map();
    for (const n of nodes) {
      const level = rank.get(n.id);
      if (!columns.has(level)) columns.set(level, []);
      columns.get(level).push(n);
    }
    const maxRows = Math.max(1, ...[...columns.values()].map(c => c.length));
    const height = Math.max(450, maxRows * 96 + 60);
    const width = Math.max(900, (Math.max(0, ...columns.keys()) + 1) * 290 + 70);
    for (const [level, column] of columns) column.forEach((n, i) => positions.set(n.id, { x: 40 + level * 290, y: 35 + i * 96 + (height - 60 - column.length * 96) / 2 }));
    const pathFor = edge => {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      if (edge.source === edge.target) return `M ${a.x + 180} ${a.y + 20} C ${a.x + 280} ${a.y - 40}, ${a.x + 280} ${a.y + 105}, ${a.x + 180} ${a.y + 50}`;
      if (a.x === b.x) return `M ${a.x + 205} ${a.y + 33} C ${a.x + 270} ${a.y + 33}, ${b.x + 270} ${b.y + 33}, ${b.x + 205} ${b.y + 33}`;
      const forward = b.x > a.x;
      const start = { x: a.x + (forward ? 205 : 0), y: a.y + 33 };
      const end = { x: b.x + (forward ? 0 : 205), y: b.y + 33 };
      const middle = (start.x + end.x) / 2;
      return `M ${start.x} ${start.y} C ${middle} ${start.y}, ${middle} ${end.y}, ${end.x} ${end.y}`;
    };
    const edgeMarkup = edges.map(e => { const a = positions.get(e.source), b = positions.get(e.target); return `<path class="kg-edge ${e.resolution}" d="${pathFor(e)}" marker-end="url(#kg-arrow)"/><text class="kg-edge-label" x="${a.x === b.x ? a.x + 230 : (a.x + b.x + 205) / 2}" y="${(a.y + b.y) / 2 + 26}" text-anchor="middle">${escapeHtml(e.label)}</text>`; }).join("");
    const short = (s, length) => s.length > length ? s.slice(0, length - 1) + "…" : s;
    const nodeMarkup = nodes.map(n => { const p = positions.get(n.id); return `<g class="kg-node ${n.kind} ${n.id === kg.selected ? "selected" : ""}" transform="translate(${p.x},${p.y})" tabindex="0" role="button" aria-label="${escapeHtml(n.name)}，${kindNames[n.kind]}" data-node="${escapeHtml(n.id)}"><title>${escapeHtml(n.qualified_name)}\n${escapeHtml(n.summary)}</title><rect width="205" height="66" rx="9"/><text class="kg-node-name" x="12" y="27">${escapeHtml(short(n.name, 23))}</text><text class="kg-node-meta" x="12" y="48">${escapeHtml(short(n.file_path, 25))}:${n.line}</text></g>`; }).join("");
    $("kg-svg").innerHTML = `<defs><marker id="kg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8ca6a0"/></marker></defs>${edgeMarkup}${nodeMarkup}${!nodes.length ? '<text x="500" y="240" text-anchor="middle" fill="#7b8791" font-size="16">当前筛选没有节点，请切换关系视图或文件。</text>' : ""}`;
    kg.bounds = { width, height };
    if (fit) fitMap();
    $("kg-map-note").textContent = `当前绘制 ${nodes.length} / ${total} 个符合筛选的节点、${edges.length} 条关系${total > 120 ? "；大图已限制显示，可按文件筛选或只看所选节点的联系" : ""}。箭头从发起方指向目标；空白区域按住拖动画布，滚轮以鼠标位置为中心缩放，右上角按钮也可缩放。`;
  }

  function updateCamera() { const c = kg.camera; $("kg-svg").setAttribute("viewBox", `${c.x} ${c.y} ${c.w} ${c.h}`); }
  function fitMap() {
    const bounds = kg.bounds || { width: 1000, height: 560 };
    const rect = $("kg-svg").getBoundingClientRect();
    const ratio = rect.width / (rect.height || 520) || 1.8;
    let w = bounds.width, h = bounds.height;
    if (w / h > ratio) h = w / ratio; else w = h * ratio;
    kg.camera = { x: -(w - bounds.width) / 2, y: -(h - bounds.height) / 2, w, h };
    updateCamera();
  }
  function zoom(factor) { const c = kg.camera; const w = Math.max(180, Math.min(15000, c.w * factor)); const h = c.h * w / c.w; kg.camera = { x: c.x + (c.w - w) / 2, y: c.y + (c.h - h) / 2, w, h }; updateCamera(); }
  function zoomAt(factor, clientX, clientY) {
    const svg = $("kg-svg");
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const c = kg.camera;
    const px = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const py = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    const worldX = c.x + px * c.w;
    const worldY = c.y + py * c.h;
    const w = Math.max(180, Math.min(15000, c.w * factor));
    const h = c.h * w / c.w;
    kg.camera = { x: worldX - px * w, y: worldY - py * h, w, h };
    updateCamera();
  }

  async function explain(ids) {
    if (kg.explaining || !kg.graph) return;
    const graph = kg.graph, revision = kg.revision;
    kg.explaining = true; kg.stop = false;
    $("kg-explain-all").disabled = true;
    $("kg-explain-node").disabled = true;
    $("kg-stop-explain").hidden = false;
    let completed = 0;
    const batchOverviews = [];
    try {
      for (let index = 0; index < ids.length; index += 8) {
        if (kg.stop || revision !== kg.revision) break;
        $("kg-ai-state").textContent = `Codex 正在解释第 ${index + 1}–${Math.min(index + 8, ids.length)} 个节点，共 ${ids.length} 个；可能需要稍候。`;
        const response = await requestJson("/api/knowledge/explain", jsonOptions({ files: graph.files, node_ids: ids.slice(index, index + 8) }));
        if (revision !== kg.revision || graph !== kg.graph) break;
        for (const item of response.explanations) { const node = graph.nodes.find(n => n.id === item.id); if (node) { node.summary = item.summary; node.summary_source = "codex"; } }
        completed += response.explanations.length;
        batchOverviews.push(response.overview);
        graph.semantic_overviews = batchOverviews;
        $("kg-overview").textContent = batchOverviews.map((overview, i) => `${batchOverviews.length > 1 ? `第 ${i + 1} 批节点：\n` : ""}${overview}`).join("\n\n");
        $("kg-overview-source").textContent = "Codex · 当前解释范围";
        renderSymbols(); renderDetail(); renderMap(false);
      }
      if (revision === kg.revision) $("kg-ai-state").textContent = `已解释 ${completed} / ${ids.length} 个节点${kg.stop ? "，已停止后续批次" : ""}。其余节点保留源码说明。`;
    } catch (error) {
      if (revision === kg.revision) { $("kg-ai-state").textContent = `已完成 ${completed} 个；本次解释失败：${error.message}。已生成的结构图谱仍可使用。`; showToast(error.message, "error"); }
    } finally {
      kg.explaining = false;
      $("kg-stop-explain").hidden = true;
      $("kg-explain-all").disabled = false;
      if (kg.graph) renderDetail();
    }
  }

  $("kg-build").addEventListener("click", buildGraph);
  $("kg-code").addEventListener("input", invalidate);
  $("kg-path").addEventListener("input", invalidate);
  $("kg-use-paste").addEventListener("click", () => setInput("paste"));
  $("kg-from-editor").addEventListener("click", () => { $("kg-code").value = $("code-input").value; const path = $("file-path").value.replaceAll("\\", "/"); $("kg-path").value = path.includes(":") || path.startsWith("/") ? path.split("/").pop() : path === "<input>" ? "main.py" : path; setInput("paste"); });
  for (const id of ["kg-files", "kg-folder"]) $(id).addEventListener("change", event => readFiles(event.target));
  $("kg-zip").addEventListener("change", event => { const file = event.target.files?.[0]; if (file) { if (file.size > 10000000) showToast("ZIP 不能超过 10 MB", "error"); else setInput("zip", [], file); } event.target.value = ""; });
  $("kg-demo").addEventListener("click", () => { setInput("files", demo.map(f => ({ ...f }))); buildGraph(); });
  $("kg-search").addEventListener("input", renderSymbols);
  for (const id of ["kg-relation", "kg-file-filter", "kg-external", "kg-neighbors"]) $(id).addEventListener("change", () => renderMap());
  for (const id of ["kg-symbol-list", "kg-detail", "kg-svg"]) $(id).addEventListener("click", event => { const target = event.target.closest("[data-node]"); if (target) selectNode(target.dataset.node); });
  $("kg-svg").addEventListener("keydown", event => { if (["Enter", " "].includes(event.key) && event.target.dataset.node) { event.preventDefault(); selectNode(event.target.dataset.node); } });
  $("kg-zoom-in").addEventListener("click", () => zoom(.8));
  $("kg-zoom-out").addEventListener("click", () => zoom(1.25));
  $("kg-fit").addEventListener("click", fitMap);
  let drag = null;
  $("kg-svg").addEventListener("pointerdown", event => { if (event.target.closest("[data-node]")) return; drag = { x: event.clientX, y: event.clientY, camera: { ...kg.camera } }; event.currentTarget.setPointerCapture(event.pointerId); event.currentTarget.classList.add("dragging"); });
  $("kg-svg").addEventListener("pointermove", event => { if (!drag) return; const r = event.currentTarget.getBoundingClientRect(); kg.camera.x = drag.camera.x - (event.clientX - drag.x) * kg.camera.w / r.width; kg.camera.y = drag.camera.y - (event.clientY - drag.y) * kg.camera.h / r.height; updateCamera(); });
  for (const name of ["pointerup", "pointercancel"]) $("kg-svg").addEventListener(name, event => { drag = null; event.currentTarget.classList.remove("dragging"); });
  $("kg-svg").addEventListener("wheel", event => {
    event.preventDefault();
    const factor = Math.exp(Math.max(-0.35, Math.min(0.35, event.deltaY * 0.0015)));
    zoomAt(factor, event.clientX, event.clientY);
  }, { passive: false });
  $("kg-explain-node").addEventListener("click", () => explain([kg.selected]));
  $("kg-explain-all").addEventListener("click", () => { if (!kg.graph) return; let ids = kg.graph.nodes.filter(n => n.kind === "function").map(n => n.id); if (!ids.length) ids = kg.graph.nodes.filter(n => n.kind === "file").map(n => n.id); explain(ids); });
  $("kg-stop-explain").addEventListener("click", () => { kg.stop = true; $("kg-ai-state").textContent = "当前批次完成后停止；已生成的解释会保留。"; });
  $("kg-export").addEventListener("click", () => { if (!kg.graph) return; const blob = new Blob([JSON.stringify(kg.graph, null, 2)], { type: "application/json;charset=utf-8" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "code-knowledge-graph.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
})();
