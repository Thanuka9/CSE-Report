"""Accounting constraint graph (§19)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from cse_financial_etl.compiler.canonical_statement import CanonicalFinancialStatement

EDGE_TYPES = (
    "ABOVE",
    "BELOW",
    "CHILD_OF",
    "SIBLING_OF",
    "SUBTOTAL_OF",
    "SAME_COLUMN",
    "SAME_ENTITY",
    "SAME_PERIOD",
    "SAME_DURATION",
    "SAME_UNIT",
    "CANDIDATE_CONCEPT",
    "RECONCILES_WITH",
    "CONTRADICTS",
)


@dataclass
class ConstraintGraph:
    graph: nx.MultiDiGraph = field(default_factory=nx.MultiDiGraph)

    def add_node(self, node_id: str, **attrs: Any) -> None:
        self.graph.add_node(node_id, **attrs)

    def add_edge(self, source: str, target: str, edge_type: str, **attrs: Any) -> None:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {edge_type}")
        self.graph.add_edge(source, target, edge_type=edge_type, **attrs)

    def ambiguity_components(self) -> list[set[str]]:
        undirected = self.graph.to_undirected()
        return [set(component) for component in nx.connected_components(undirected)]


def build_constraint_graph(statements: list[CanonicalFinancialStatement]) -> ConstraintGraph:
    cg = ConstraintGraph()
    for statement in statements:
        stmt_id = f"stmt:{statement.statement_type}:{statement.page_start}"
        cg.add_node(stmt_id, kind="statement", statement_type=statement.statement_type)
        for column in statement.columns:
            col_node = f"{stmt_id}:col:{column.column_id}"
            cg.add_node(
                col_node,
                kind="column",
                entity=column.entity,
                duration=column.duration_months,
                role=column.comparison_role,
            )
            cg.add_edge(stmt_id, col_node, "SAME_PERIOD")
        prev_row: str | None = None
        for row in statement.rows:
            row_node = f"{stmt_id}:row:{row.row_id}"
            cg.add_node(row_node, kind="row", label=row.raw_label)
            if prev_row:
                cg.add_edge(prev_row, row_node, "BELOW")
                cg.add_edge(row_node, prev_row, "ABOVE")
            prev_row = row_node
            for hyp in row.hypotheses:
                hyp_node = f"{row_node}:concept:{hyp.concept}"
                cg.add_node(hyp_node, kind="concept", score=hyp.total_score)
                cg.add_edge(row_node, hyp_node, "CANDIDATE_CONCEPT", score=hyp.total_score)
            for col_id, cell in row.cells.items():
                cell_node = f"{row_node}:cell:{col_id}"
                cg.add_node(
                    cell_node,
                    kind="cell",
                    raw=cell.raw_text,
                    value=str(cell.normalized_value) if cell.normalized_value is not None else None,
                )
                cg.add_edge(row_node, cell_node, "SAME_COLUMN")
                cg.add_edge(f"{stmt_id}:col:{col_id}", cell_node, "SAME_COLUMN")
    return cg
