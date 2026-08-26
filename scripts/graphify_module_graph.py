"""Collapse graphify-out/graph.json to module (file) granularity, app/ only,
and render it with graphify's own exporters - no new dependencies, this
just constructs a coarser networkx.Graph and hands it to the same to_html/
to_graphml functions `graphify export` already uses.

Why this exists: graphify's own commands operate at function/class
granularity (1848 nodes for this repo) or at community granularity (its
own clustering, not module boundaries). Neither is "one node per app/
module" - the view that shows package-level structure without the
per-function noise. This is a one-off dev script, not part of the app;
requires graphifyy (see requirements-dev.txt), consistent with every other
generated file under graphify-out/ (gitignored).

Usage: venv/Scripts/python.exe scripts/graphify_module_graph.py
Output: graphify-out/module_graph.html, graphify-out/module_graph.graphml
"""
import collections
import json
from pathlib import Path

import networkx as nx

from graphify.exporters.html import to_html
from graphify.export import to_graphml

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_JSON = REPO_ROOT / "graphify-out" / "graph.json"
OUT_HTML = REPO_ROOT / "graphify-out" / "module_graph.html"
OUT_GRAPHML = REPO_ROOT / "graphify-out" / "module_graph.graphml"


def module_label(source_file: str) -> str:
    """app/jobs/routes.py -> jobs/routes.py (drop the app/ prefix, it's implied)."""
    return source_file[len("app/"):] if source_file.startswith("app/") else source_file


def subpackage(source_file: str) -> str:
    """app/jobs/routes.py -> jobs; app/extensions.py -> (root)."""
    rel = module_label(source_file)
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else "(app root)"


def main() -> None:
    data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    links = data["links"]

    id_to_file = {n["id"]: n.get("source_file") or "" for n in nodes}
    id_to_type = {n["id"]: n.get("file_type") for n in nodes}

    def is_app_code(nid: str) -> bool:
        f = id_to_file.get(nid, "")
        return f.startswith("app/") and id_to_type.get(nid) == "code"

    # Aggregate edges between distinct app/ modules.
    agg: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    modules_seen: set[str] = set()
    for e in links:
        src, tgt = e["source"], e["target"]
        if not (is_app_code(src) and is_app_code(tgt)):
            continue
        mod_src = id_to_file[src]
        mod_tgt = id_to_file[tgt]
        if mod_src == mod_tgt:
            continue  # same-module edges (mostly "contains") aren't module-level structure
        modules_seen.add(mod_src)
        modules_seen.add(mod_tgt)
        key = tuple(sorted((mod_src, mod_tgt)))
        agg[key][e.get("relation", "?")] += 1

    # Also include modules that exist but have zero cross-module edges, so
    # they still show up as isolated dots rather than silently vanishing.
    for nid, f in id_to_file.items():
        if is_app_code(nid):
            modules_seen.add(f)

    G = nx.Graph()
    subpkgs = sorted({subpackage(m) for m in modules_seen})
    subpkg_to_cid = {name: i for i, name in enumerate(subpkgs)}
    communities: dict[int, list[str]] = collections.defaultdict(list)
    community_labels = {i: name for name, i in subpkg_to_cid.items()}

    for m in sorted(modules_seen):
        cid = subpkg_to_cid[subpackage(m)]
        G.add_node(m, label=module_label(m), source_file=m, file_type="module")
        communities[cid].append(m)

    for (a, b), relcount in agg.items():
        total = sum(relcount.values())
        top_rel = ", ".join(f"{c} {r}" for r, c in relcount.most_common(3))
        G.add_edge(
            a, b,
            relation=f"{total}x ({top_rel})",
            confidence="EXTRACTED",
            _src=a, _tgt=b,
            weight=total,
        )

    print(f"Collapsed to {G.number_of_nodes()} modules, {G.number_of_edges()} inter-module edges "
          f"(from {len(nodes)} nodes / {len(links)} edges in the full graph).")

    written = to_html(G, dict(communities), str(OUT_HTML), community_labels=community_labels)
    print(f"module_graph.html {'written' if written else 'SKIPPED (to_html declined)'} -> {OUT_HTML}")

    to_graphml(G, dict(communities), str(OUT_GRAPHML))
    print(f"module_graph.graphml written -> {OUT_GRAPHML}")

    # Quick text summary too, for anyone who just wants the list.
    print("\nModules by subpackage:")
    for name in subpkgs:
        mods = sorted(module_label(m) for m in communities[subpkg_to_cid[name]])
        print(f"  {name} ({len(mods)}): {', '.join(mods)}")


if __name__ == "__main__":
    main()
