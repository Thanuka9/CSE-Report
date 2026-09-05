from __future__ import annotations

from typing import Any

import networkx as nx

from cse_financial_etl.documents.document_ir import LineIR, TokenIR


def build_value_graph(
    *,
    label: str,
    value_token: TokenIR,
    entity: str,
    period_end: str,
    line: LineIR,
    column_scores: list[dict[str, Any]],
    cluster_centers: tuple[float, ...],
    components: dict[str, float],
    selected_score: float,
    runner_up_score: float,
    parent_header: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a transient spatial/evidence graph, then serialize the useful portion.

    Vectors and the live NetworkX object stay in RAM. Only nodes/edges/scores are kept.
    """

    graph = nx.MultiDiGraph()
    graph.add_node("metric", type="METRIC_LABEL", text=label)
    graph.add_node("value", type="VALUE", text=value_token.text)
    graph.add_node("entity", type="ENTITY", text=entity)
    graph.add_node("period", type="PERIOD", text=period_end)
    graph.add_node("row", type="ROW", text=line.text, line_id=line.line_id)
    graph.add_edge("metric", "value", relation="SAME_ROW")
    graph.add_edge("entity", "value", relation="ENTITY_FOR")
    graph.add_edge("entity", "value", relation="HEADER_FOR")
    graph.add_edge("period", "value", relation="PERIOD_FOR")
    graph.add_edge("period", "value", relation="NEAREST_HEADER")
    graph.add_edge("row", "value", relation="BELONGS_TO_REGION")
    if parent_header:
        graph.add_node(
            "parent_header",
            type="PARENT_HEADER",
            text=str(parent_header.get("phrase", "")),
            kind=parent_header.get("kind"),
        )
        graph.add_edge("parent_header", "value", relation="PARENT_HEADER")
        graph.add_edge("parent_header", "value", relation="BELONGS_TO_REGION")
    if value_token.bbox.center_x >= line.bbox.center_x:
        graph.add_edge("metric", "value", relation="RIGHT_OF")
    else:
        graph.add_edge("metric", "value", relation="LEFT_OF")
    for index, center in enumerate(cluster_centers):
        node_id = f"cluster_{index}"
        graph.add_node(node_id, type="COLUMN_CLUSTER", text=str(center))
        relation = "X_OVERLAP" if abs(center - value_token.bbox.center_x) <= 12 else "ALIGNABLE_WITH"
        graph.add_edge(node_id, "value", relation=relation)

    return {
        "nodes": [{"id": node_id, **dict(data)} for node_id, data in graph.nodes(data=True)],
        "edges": [
            {"from": source, "to": target, "relation": data.get("relation")}
            for source, target, data in graph.edges(data=True)
        ],
        "graph_metrics": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        },
        "column_scores": column_scores,
        "selected_score": round(selected_score, 4),
        "runner_up_score": round(runner_up_score, 4),
        "cluster_centers": list(cluster_centers),
        "components": components,
    }


def summarize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Approved facts keep summarized lineage; review keeps the full graph."""

    return {
        "nodes": [
            node
            for node in graph.get("nodes", [])
            if node.get("type")
            in {"METRIC_LABEL", "VALUE", "ENTITY", "PERIOD", "PARENT_HEADER"}
        ],
        "edges": [
            edge
            for edge in graph.get("edges", [])
            if edge.get("relation") in {
                "SAME_ROW",
                "HEADER_FOR",
                "ENTITY_FOR",
                "PERIOD_FOR",
                "PARENT_HEADER",
                "BELONGS_TO_REGION",
            }
        ],
        "selected_score": graph.get("selected_score"),
        "cluster_centers": graph.get("cluster_centers"),
    }
