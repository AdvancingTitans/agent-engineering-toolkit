"""Generate and optionally serve the fully offline Evidence Atlas Viewer."""

from __future__ import annotations

import json
import mimetypes
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MERMAID_VERSION = "11.16.0"
_ASSET_ROOT = Path(__file__).with_name("assets")


def viewer_files(
    graph: dict[str, Any],
    projections: dict[str, dict[str, Any]],
) -> dict[str, bytes]:
    """Return the complete no-network Viewer file set."""
    payload = {
        "graph": graph,
        "projections": projections,
        "viewer": {
            "name": "AET Evidence Atlas",
            "version": "1.0",
            "mermaid_version": MERMAID_VERSION,
            "security_level": "strict",
        },
    }
    mermaid = _required_asset("mermaid.min.js")
    license_text = _required_asset("MERMAID-LICENSE")
    encoded = _encoded_payload(payload)
    return {
        "index.html": _html_document(payload, inline_mermaid=False).encode("utf-8"),
        "assets/atlas-data.js": (
            f"globalThis.__AET_ATLAS_DATA__={encoded};\n"
        ).encode("utf-8"),
        "assets/atlas.js": _VIEWER_JS.encode("utf-8"),
        "assets/atlas.css": _VIEWER_CSS.encode("utf-8"),
        "assets/mermaid.min.js": mermaid,
        "assets/MERMAID-LICENSE": license_text,
    }


def single_html(
    graph: dict[str, Any],
    projections: dict[str, dict[str, Any]],
) -> bytes:
    """Return one self-contained HTML file suitable for double-click viewing."""
    return _html_document(
        {
            "graph": graph,
            "projections": projections,
            "viewer": {
                "name": "AET Evidence Atlas",
                "version": "1.0",
                "mermaid_version": MERMAID_VERSION,
                "security_level": "strict",
            },
        },
        inline_mermaid=True,
    ).encode("utf-8")


def serve_atlas(
    atlas_directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> None:
    """Serve one generated Viewer read-only on localhost until interrupted."""
    root = Path(atlas_directory).resolve(strict=True)
    if not (root / "index.html").is_file():
        raise ValueError(f"Atlas Viewer is missing index.html: {root}")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Atlas Viewer may only bind to localhost")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")

    class LocalHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' "
                "'unsafe-inline'; img-src 'self' data:; connect-src 'none'; "
                "font-src 'none'; object-src 'none'; frame-src 'none'; "
                "base-uri 'none'; form-action 'none'",
            )
            super().end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    mimetypes.add_type("text/javascript", ".js")
    with ThreadingHTTPServer((host, port), LocalHandler) as server:
        address, actual_port = server.server_address[:2]
        url = f"http://{address}:{actual_port}/"
        print(f"AET Evidence Atlas: {url}", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def _html_document(payload: dict[str, Any], *, inline_mermaid: bool) -> str:
    encoded = _encoded_payload(payload)
    if inline_mermaid:
        mermaid_script = _required_asset("mermaid.min.js").decode("utf-8")
        scripts = (
            f"<script>{mermaid_script}</script>"
            f"<script>globalThis.__AET_ATLAS_DATA__={encoded};</script>"
            f"<script>{_VIEWER_JS}</script>"
        )
        styles = f"<style>{_VIEWER_CSS}</style>"
    else:
        scripts = (
            '<script src="assets/atlas-data.js"></script>'
            '<script src="assets/mermaid.min.js"></script>'
            '<script src="assets/atlas.js"></script>'
        )
        styles = '<link rel="stylesheet" href="assets/atlas.css">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; font-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'">
<title>AET Evidence Atlas</title>
{styles}
</head>
<body>
<header>
  <div>
    <p class="eyebrow">AGENT ENGINEERING TOOLKIT</p>
    <h1>Evidence Atlas</h1>
  </div>
  <div class="identity">
    <span id="bundle-id"></span>
    <span class="strict">OFFLINE · STRICT · DETERMINISTIC</span>
  </div>
</header>
<main>
  <aside class="nav-panel">
    <label for="perspective">Perspective</label>
    <select id="perspective"></select>
    <label for="search">Search nodes</label>
    <input id="search" type="search" autocomplete="off" placeholder="Claim, evidence, source…">
    <div class="filters" aria-label="Status filters">
      <button data-filter="all" class="active">All</button>
      <button data-filter="conflicted">Conflict</button>
      <button data-filter="unknown">Unknown</button>
      <button data-filter="stale">Stale</button>
    </div>
    <nav id="node-tree" aria-label="Evidence nodes"></nav>
  </aside>
  <section class="diagram-panel">
    <div class="diagram-toolbar">
      <button id="back" disabled>← Parent</button>
      <span id="diagram-title"></span>
      <button id="drill" disabled>Expand node</button>
      <button id="fit">Fit</button>
    </div>
    <div id="diagram" role="img" aria-live="polite"></div>
    <pre id="fallback" hidden></pre>
    <p id="diagram-status" class="status"></p>
  </section>
  <aside class="detail-panel">
    <p class="eyebrow">NODE EVIDENCE</p>
    <h2 id="detail-title">Select a node</h2>
    <dl id="detail-fields"></dl>
    <h3>Summary</h3>
    <p id="detail-summary"></p>
    <h3>Source references</h3>
    <ul id="detail-sources"></ul>
    <h3>Limitations / unknowns</h3>
    <ul id="detail-related"></ul>
    <h3>Does not prove</h3>
    <ul id="detail-does-not-prove"></ul>
    <details>
      <summary>Raw JSON</summary>
      <pre id="detail-json"></pre>
    </details>
  </aside>
</main>
{scripts}
</body>
</html>
"""


def _encoded_payload(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).replace("</", "<\\/")


def _required_asset(name: str) -> bytes:
    path = _ASSET_ROOT / name
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"packaged Atlas Viewer asset is unavailable: {name}"
        ) from error
    if not raw:
        raise RuntimeError(f"packaged Atlas Viewer asset is empty: {name}")
    return raw


_VIEWER_JS = r"""
(() => {
  "use strict";
  const data = globalThis.__AET_ATLAS_DATA__;
  if (!data || typeof data !== "object") {
    throw new Error("Evidence Atlas data is unavailable");
  }
  const nodes = new Map(data.graph.nodes.map((node) => [node.id, node]));
  const projections = data.projections;
  let perspective = Object.keys(projections)[0];
  let diagramId = null;
  let selected = null;
  let filter = "all";
  let history = [];
  const byId = (id) => document.getElementById(id);
  const put = (element, value) => { element.textContent = value == null ? "" : String(value); };
  put(byId("bundle-id"), data.graph.bundle_id);

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    htmlLabels: false,
    deterministicIds: true,
    deterministicIDSeed: data.graph.generated_from.bundle_content_hash,
    theme: "dark",
    flowchart: { htmlLabels: false, useMaxWidth: true },
  });

  const select = byId("perspective");
  Object.entries(projections).forEach(([id, projection]) => {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = projection.perspective.title;
    select.appendChild(option);
  });

  function activeProjection() {
    const root = projections[perspective];
    return diagramId && root.diagrams[diagramId] ? root.diagrams[diagramId] : root;
  }

  function projectionNodes() {
    return activeProjection().ir.nodes
      .map((item) => nodes.get(item.canonical_id))
      .filter(Boolean);
  }

  function activeReferences() {
    return projections[perspective].references.filter(
      (reference) => reference.parent_diagram_id === diagramId,
    );
  }

  function visible(node) {
    const query = byId("search").value.trim().toLocaleLowerCase();
    const matchesQuery = !query || `${node.title} ${node.summary} ${node.id}`.toLocaleLowerCase().includes(query);
    const matchesFilter = filter === "all" || node.status === filter || node.freshness === filter || node.type === filter;
    return matchesQuery && matchesFilter;
  }

  function renderTree() {
    const root = byId("node-tree");
    root.replaceChildren();
    const projection = activeProjection();
    const rootIds = new Set(
      projection.root_node_id
        ? [projection.root_node_id]
        : projections[perspective].perspective.root_node_ids,
    );
    const references = new Map(
      activeReferences().map((reference) => [reference.node_id, reference]),
    );
    projectionNodes().filter(visible).forEach((node) => {
      const button = document.createElement("button");
      button.className = `tree-node status-${node.status}`;
      button.dataset.nodeId = node.id;
      button.setAttribute("aria-level", rootIds.has(node.id) ? "1" : "2");
      if (!rootIds.has(node.id)) button.classList.add("tree-child");
      const type = document.createElement("span");
      type.className = "node-type";
      type.textContent = `[${node.type.toUpperCase()}]`;
      const title = document.createElement("span");
      title.textContent = node.title;
      button.append(type, title);
      const graphTarget = projections[perspective].node_to_diagram[node.id];
      const referenceState = references.get(node.id);
      const target = referenceState?.target_diagram_id || graphTarget;
      if (referenceState || (target && target !== diagramId)) {
        const reference = document.createElement("span");
        reference.className = "node-reference";
        reference.textContent = referenceState
          ? referenceState.reason === "deduplicated"
            ? "↗ SEE SUBGRAPH"
            : referenceState.reason === "max_depth"
              ? "MAX DEPTH"
              : "CYCLE"
          : "↗ SUBGRAPH";
        button.appendChild(reference);
        if (target) button.dataset.referenceDiagram = target;
      }
      button.addEventListener("click", () => showNode(node.id));
      root.appendChild(button);
    });
  }

  function applyVisibilityToDiagram() {
    const projection = activeProjection();
    const hidden = new Set(
      projection.ir.nodes
        .filter((item) => {
          const node = nodes.get(item.canonical_id);
          return node && !visible(node);
        })
        .map((item) => item.id),
    );
    byId("diagram").querySelectorAll("g.node").forEach((group) => {
      const mapping = projection.ir.nodes.find((item) => group.id.includes(item.id));
      group.classList.toggle("filtered-out", Boolean(mapping && hidden.has(mapping.id)));
    });
    byId("diagram").querySelectorAll(".edgePath").forEach((element, index) => {
      const edge = projection.ir.edges[index];
      element.classList.toggle(
        "filtered-out",
        Boolean(edge && (hidden.has(edge.from) || hidden.has(edge.to))),
      );
    });
  }

  function addField(term, value) {
    const dl = byId("detail-fields");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = term;
    dd.textContent = value == null ? "UNKNOWN" : String(value);
    dl.append(dt, dd);
  }

  function showNode(id) {
    const node = nodes.get(id);
    if (!node) return;
    selected = id;
    put(byId("detail-title"), node.title);
    put(byId("detail-summary"), node.summary);
    byId("detail-fields").replaceChildren();
    addField("Type", node.type);
    addField("Status", node.status);
    addField("Authority", node.authority);
    addField("Freshness", node.freshness);
    addField("Complexity", `${node.complexity.classification} (${node.complexity.score})`);
    const referenceState = activeReferences().find(
      (reference) => reference.node_id === id,
    );
    if (referenceState) {
      addField("Reference", referenceState.reason.toUpperCase());
    }
    const sources = byId("detail-sources");
    sources.replaceChildren();
    node.source_refs.forEach((ref) => {
      const item = document.createElement("li");
      item.textContent = `${ref.collection} · ${ref.record_id}${ref.field ? ` · ${ref.field}` : ""}`;
      sources.appendChild(item);
    });
    const related = byId("detail-related");
    related.replaceChildren();
    data.graph.edges
      .filter((edge) => edge.from === id && ["LIMITED_BY", "LEAVES_UNKNOWN", "CONTRADICTED_BY", "INVALIDATED_BY"].includes(edge.type))
      .forEach((edge) => {
        const target = nodes.get(edge.to);
        if (!target) return;
        const item = document.createElement("li");
        item.textContent = `${edge.type}: ${target.summary}`;
        related.appendChild(item);
      });
    const doesNotProve = byId("detail-does-not-prove");
    doesNotProve.replaceChildren();
    const limitations = Array.isArray(node.attributes?.does_not_prove)
      ? node.attributes.does_not_prove
      : [];
    (limitations.length ? limitations : ["No explicit limitation is recorded."])
      .forEach((value) => {
        const item = document.createElement("li");
        item.textContent = value;
        doesNotProve.appendChild(item);
      });
    put(byId("detail-json"), JSON.stringify(node, null, 2));
    document.querySelectorAll(".tree-node").forEach((element) => {
      element.classList.toggle("selected", element.dataset.nodeId === id);
    });
    const target = (
      referenceState?.target_diagram_id
      || projections[perspective].node_to_diagram[id]
    );
    byId("drill").disabled = !target || target === diagramId;
    put(
      byId("drill"),
      target && target !== diagramId ? "Open subgraph ↗" : "Expand node",
    );
    highlightPaths(id);
    applyVisibilityToDiagram();
  }

  function highlightPaths(id) {
    const categories = new Map([[id, "selected"]]);
    const queue = [id];
    const counter = new Set(["CONTRADICTED_BY", "VIOLATES"]);
    const stale = new Set(["INVALIDATED_BY", "STALE_FOR"]);
    const support = new Set(["SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY", "PRODUCED_BY", "VALIDATES", "DERIVED_FROM", "FRESH_FOR", "OBSERVED_IN"]);
    while (queue.length) {
      const from = queue.shift();
      const inherited = categories.get(from);
      data.graph.edges.filter((edge) => edge.from === from).forEach((edge) => {
        const category = counter.has(edge.type) ? "counter" : stale.has(edge.type) ? "stale" : support.has(edge.type) ? (inherited === "counter" || inherited === "stale" ? inherited : "support") : inherited;
        if (!category || categories.has(edge.to)) return;
        categories.set(edge.to, category);
        queue.push(edge.to);
      });
    }
    document.querySelectorAll("#diagram g.node").forEach((group) => {
      group.classList.remove("path-selected", "path-support", "path-counter", "path-stale", "path-muted");
      const category = categories.get(group.dataset.canonicalId);
      group.classList.add(category ? `path-${category}` : "path-muted");
    });
    document.querySelectorAll("#diagram .edgePath").forEach((element, index) => {
      element.classList.remove("path-support", "path-counter", "path-stale", "path-muted");
      const edge = activeProjection().ir.edges[index];
      const targetNode = edge && activeProjection().ir.nodes.find((item) => item.id === edge.to);
      const category = targetNode && categories.get(targetNode.canonical_id);
      element.classList.add(category && category !== "selected" ? `path-${category}` : "path-muted");
    });
  }

  function enterDiagram(target) {
    if (!target || target === diagramId) return;
    history.push({ perspective, diagramId });
    diagramId = target;
    selected = null;
    byId("back").disabled = false;
    byId("drill").disabled = true;
    renderTree();
    renderDiagram();
  }

  async function renderDiagram() {
    const root = projections[perspective];
    const projection = activeProjection();
    put(byId("diagram-title"), diagramId ? `${root.perspective.title} · ${projection.title}` : root.perspective.title);
    const diagram = byId("diagram");
    const fallback = byId("fallback");
    const status = byId("diagram-status");
    diagram.replaceChildren();
    fallback.hidden = true;
    try {
      const renderId = `atlas_${perspective}_${diagramId || "root"}`.replace(/[^A-Za-z0-9_]/g, "_");
      const result = await mermaid.render(renderId, projection.mermaid);
      diagram.innerHTML = result.svg;
      diagram.querySelectorAll("g.node").forEach((group) => {
        const mapping = projection.ir.nodes.find((item) => group.id.includes(item.id));
        if (!mapping) return;
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.dataset.canonicalId = mapping.canonical_id;
        const open = () => showNode(mapping.canonical_id);
        group.addEventListener("click", open);
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") open();
        });
      });
      put(status, `${projection.ir.nodes.length} nodes · ${projection.ir.edges.length} edges${diagramId ? " · recursive subgraph" : ""}`);
      if (selected) highlightPaths(selected);
      applyVisibilityToDiagram();
    } catch (error) {
      fallback.hidden = false;
      fallback.textContent = projection.mermaid;
      put(status, `Mermaid fallback: ${error instanceof Error ? error.message : "render failed"}`);
    }
  }

  select.addEventListener("change", () => {
    history.push({ perspective, diagramId });
    perspective = select.value;
    diagramId = null;
    selected = null;
    byId("back").disabled = history.length === 0;
    byId("drill").disabled = true;
    renderTree();
    renderDiagram();
  });
  byId("back").addEventListener("click", () => {
    const prior = history.pop();
    if (!prior) return;
    perspective = prior.perspective;
    diagramId = prior.diagramId;
    selected = null;
    select.value = perspective;
    byId("back").disabled = history.length === 0;
    byId("drill").disabled = true;
    renderTree();
    renderDiagram();
  });
  byId("drill").addEventListener("click", () => {
    if (!selected) return;
    enterDiagram(projections[perspective].node_to_diagram[selected]);
  });
  byId("search").addEventListener("input", () => {
    renderTree();
    applyVisibilityToDiagram();
  });
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      filter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
      renderTree();
      applyVisibilityToDiagram();
    });
  });
  byId("fit").addEventListener("click", () => {
    const svg = byId("diagram").querySelector("svg");
    if (svg) {
      svg.removeAttribute("width");
      svg.removeAttribute("height");
      svg.style.maxWidth = "100%";
      svg.style.maxHeight = "100%";
    }
  });
  renderTree();
  renderDiagram();
  const first = projectionNodes()[0];
  if (first) showNode(first.id);
})();
"""


_VIEWER_CSS = r"""
:root{color-scheme:dark;--bg:#090b10;--panel:#10141c;--line:#283142;--text:#e8edf6;--muted:#8f9aad;--cyan:#4cd7e8;--amber:#f6bd60;--red:#f07178;--green:#7bd88f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
header{height:82px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:14px 22px;background:#0c1017}
h1,h2,h3,p{margin-top:0}h1{font-size:25px;margin-bottom:0;letter-spacing:-.04em}.eyebrow{font-size:10px;letter-spacing:.18em;color:var(--cyan);margin-bottom:3px}.identity{display:flex;gap:12px;align-items:center;color:var(--muted);font-size:11px}.strict{border:1px solid #305663;padding:5px 8px;color:var(--cyan)}
main{display:grid;grid-template-columns:280px minmax(420px,1fr) 340px;height:calc(100vh - 82px)}aside,.diagram-panel{min-width:0}.nav-panel,.detail-panel{background:var(--panel);padding:18px;overflow:auto}.nav-panel{border-right:1px solid var(--line)}.detail-panel{border-left:1px solid var(--line)}
label{display:block;color:var(--muted);font-size:11px;margin:12px 0 6px}select,input{width:100%;background:#0a0e14;border:1px solid var(--line);color:var(--text);padding:9px;border-radius:2px}
.filters{display:flex;gap:5px;margin:12px 0}.filters button,.diagram-toolbar button{background:#151c27;border:1px solid var(--line);color:var(--muted);padding:6px 8px;cursor:pointer}.filters button.active,.filters button:hover,.diagram-toolbar button:hover{color:var(--cyan);border-color:#396774}
#node-tree{display:flex;flex-direction:column;gap:4px}.tree-node{display:flex;flex-direction:column;align-items:flex-start;text-align:left;background:transparent;border:1px solid transparent;color:var(--text);padding:8px;cursor:pointer}.tree-node.tree-child{margin-left:14px;border-left-color:var(--line)}.tree-node:hover,.tree-node.selected{background:#151c27;border-color:var(--line)}.node-type,.node-reference{font-size:9px;color:var(--muted);letter-spacing:.08em}.node-reference{color:var(--cyan);margin-top:3px}.status-unknown .node-type{color:var(--amber)}.status-conflicted .node-type,.status-stale .node-type{color:var(--red)}.status-verified .node-type,.status-supported .node-type{color:var(--green)}
.diagram-panel{display:grid;grid-template-rows:48px 1fr auto;overflow:hidden}.diagram-toolbar{display:flex;align-items:center;gap:12px;padding:8px 14px;border-bottom:1px solid var(--line)}#diagram-title{flex:1;text-align:center;color:var(--muted)}#diagram{overflow:auto;padding:24px;display:flex;align-items:center;justify-content:center}#diagram svg{max-width:100%;max-height:100%}.status{padding:8px 14px;margin:0;border-top:1px solid var(--line);color:var(--muted);font-size:11px}#fallback{white-space:pre-wrap;padding:20px;overflow:auto}
.filtered-out{display:none!important}.path-muted{opacity:.2}.path-selected{opacity:1;filter:drop-shadow(0 0 5px var(--cyan))}.path-support{opacity:1;filter:drop-shadow(0 0 4px var(--green))}.path-counter{opacity:1;filter:drop-shadow(0 0 4px var(--red))}.path-stale{opacity:1;filter:drop-shadow(0 0 4px var(--amber))}
.detail-panel h2{font-size:18px}.detail-panel h3{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-top:20px}dl{display:grid;grid-template-columns:90px 1fr;gap:6px;margin:14px 0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}ul{padding-left:18px}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#b9c5d8;font-size:11px}
@media(max-width:1050px){main{grid-template-columns:240px 1fr}.detail-panel{grid-column:1/-1;border-left:0;border-top:1px solid var(--line);max-height:42vh}main{height:auto;min-height:calc(100vh - 82px)}.diagram-panel{min-height:650px}}
@media(max-width:720px){header{height:auto;align-items:flex-start;gap:12px}.identity{flex-direction:column;align-items:flex-end}main{display:block}.nav-panel,.detail-panel{border:0;border-bottom:1px solid var(--line)}.diagram-panel{min-height:560px}}
"""
