#!/usr/bin/env python3

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "character-briefs" / "source"
ASSIGNMENTS_FILE = ROOT / "character-briefs" / "Character Assignments.txt"
OUTPUT_SVG = ROOT / "character-briefs" / "Character Connection Graph.svg"
OUTPUT_PNG = ROOT / "character-briefs" / "Character Connection Graph.png"
OUTPUT_MD = ROOT / "character-briefs" / "Character Connection Graph.md"

VIEW_WIDTH = 2400
VIEW_HEIGHT = 1600
GRAPH_LEFT = 110
GRAPH_TOP = 240
GRAPH_RIGHT = 1720
GRAPH_BOTTOM = 1400
LEGEND_LEFT = 1810
PNG_RENDER_SIZE = 2400
NODE_MARGIN = 36

FIELD_KEYS = [
    "Name",
    "Agent Code Name",
    "Cover Name",
    "Undercover Name",
]

NODE_FILL = {
    "brief": "#d8ebff",
    "assignment_only": "#fde7b0",
    "mentioned_only": "#e5e7eb",
}
NODE_STROKE = {
    "brief": "#0f4c81",
    "assignment_only": "#8a5a00",
    "mentioned_only": "#4b5563",
}

MANUAL_ROLE_MATCHES = {
    "Agent Bartender": "The Bartender",
}

MANUAL_ALIASES = {
    "Agent Red": ["Your new girlfriend", "Evelyn Price"],
    "Agent Blue": ["The Courier", "Jack Grace", "The asset"],
    "The Successor": ["The SCSR recipient"],
    "The Retiring Diplomat": ["Ambassador"],
    "The Bartender": ["Agent Bartender", "Tom the Bartender", "Tom"],
    "Thing 1 Secret Service": ["Thing 1", "Ray Kessler", "Raymond Kessler"],
    "Thing 2 Secret Service": ["Thing 2", "Marcus Donnelly"],
}

# Keep undercover support roles out of the public-facing connection graph even when
# they maintain private intel notes in their own brief.
HIDDEN_GRAPH_NODES = {"The Bartender"}


@dataclass
class Node:
    key: str
    kind: str
    source_title: str | None = None
    assignment_role: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    aliases: set[str] = field(default_factory=set)
    degree: int = 0

    def role_label(self) -> str:
        if self.assignment_role:
            return self.assignment_role
        if self.source_title:
            return self.source_title
        return self.key

    def primary_label(self) -> str:
        if self.key == "Agent Red":
            return "Agent Red"
        if self.key == "Agent Blue":
            return "Agent Blue"
        if self.key == "Thing 1 Secret Service":
            return "Thing 1"
        if self.key == "Thing 2 Secret Service":
            return "Thing 2"
        if self.key == "The Bartender":
            return "The Bartender"
        if self.fields.get("Name"):
            return self.fields["Name"]
        if self.fields.get("Agent Code Name"):
            return self.fields["Agent Code Name"]
        if self.assignment_role:
            return self.assignment_role
        if self.source_title:
            return self.source_title
        return self.key

    def secondary_label(self) -> str | None:
        if self.key == "Agent Red":
            return self.fields.get("Cover Name")
        if self.key == "Agent Blue":
            parts = [self.source_title or "The Courier", self.fields.get("Undercover Name", "")]
            return " / ".join(part for part in parts if part)
        if self.key in {"Thing 1 Secret Service", "Thing 2 Secret Service"}:
            name = self.fields.get("Name", "")
            return re.sub(r"^Special Agent\s+", "", name).strip() or None
        if self.key == "The Bartender":
            return self.fields.get("Name")
        if self.fields.get("Name") and self.role_label() != self.fields.get("Name"):
            return self.role_label()
        if self.source_title and self.source_title != self.primary_label():
            return self.source_title
        return None

    def tooltip(self) -> str:
        alias_list = sorted(alias for alias in self.aliases if alias != self.primary_label())
        parts = [self.primary_label()]
        if self.secondary_label():
            parts.append(self.secondary_label() or "")
        parts.append(f"type: {self.kind.replace('_', ' ')}")
        if alias_list:
            parts.append("aliases: " + ", ".join(alias_list))
        return " | ".join(part for part in parts if part)


def clean_text(value: str) -> str:
    value = value.replace("\ufeff", "")
    value = value.replace("\u2028", "\n")
    value = value.replace("\u2029", "\n")
    return value


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def dom_id(prefix: str, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{prefix}-{slug or 'item'}"


def parse_assignments() -> list[str]:
    roles: list[str] = []
    for raw_line in ASSIGNMENTS_FILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or " - " not in line:
            continue
        _, role = line.split(" - ", 1)
        cleaned_role = re.sub(r"\s*\((?:unwritten|written)\)\s*$", "", role.strip(), flags=re.I)
        roles.append(cleaned_role)
    return roles


def parse_briefs() -> dict[str, Node]:
    nodes: dict[str, Node] = {}

    for path in sorted(SOURCE_DIR.glob("*.txt")):
        text = clean_text(path.read_text())
        title_match = re.search(r"^Character Brief:\s*(.+)$", text, re.M)
        if not title_match:
            continue
        source_title = title_match.group(1).strip()
        key = MANUAL_ROLE_MATCHES.get(source_title, source_title)

        fields: dict[str, str] = {}
        for field_name in FIELD_KEYS:
            match = re.search(rf"^{re.escape(field_name)}:\s*(.+)$", text, re.M)
            if match:
                fields[field_name] = match.group(1).strip()

        node = Node(key=key, kind="brief", source_title=source_title, fields=fields)
        node.aliases.update({source_title, path.stem, key})
        node.aliases.update(value for value in fields.values() if value)

        primary_name = fields.get("Name", "")
        if primary_name.startswith("Special Agent "):
            node.aliases.add(primary_name.removeprefix("Special Agent ").strip())

        nodes[key] = node

    for key, aliases in MANUAL_ALIASES.items():
        if key in nodes:
            nodes[key].aliases.update(aliases)

    for role in parse_assignments():
        if role in nodes:
            nodes[role].assignment_role = role
            nodes[role].aliases.add(role)
            continue

        matched_node = None
        for node in nodes.values():
            if role in node.aliases:
                matched_node = node
                break
        if matched_node:
            matched_node.assignment_role = role
            matched_node.aliases.add(role)
        else:
            placeholder = Node(key=role, kind="assignment_only", assignment_role=role)
            placeholder.aliases.add(role)
            nodes[role] = placeholder

    return nodes


def ensure_mentioned_node(nodes: dict[str, Node], label: str) -> None:
    if label in nodes:
        return
    for node in nodes.values():
        if label in node.aliases:
            return
    node = Node(key=label, kind="mentioned_only")
    node.aliases.add(label)
    nodes[label] = node


def extend_with_mentioned_only(nodes: dict[str, Node]) -> None:
    for label in ["Josh Roberson", "The Journalist"]:
        ensure_mentioned_node(nodes, label)


def alias_patterns(nodes: dict[str, Node]) -> list[tuple[str, str, re.Pattern[str]]]:
    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for key, node in nodes.items():
        for alias in node.aliases:
            alias = alias.strip()
            if not alias:
                continue
            patterns.append((alias, key, re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.I)))
    patterns.sort(key=lambda item: len(item[0]), reverse=True)
    return patterns


def split_connection_chunks(connection_text: str) -> list[str]:
    if not connection_text:
        return []
    chunks = re.split(r"\n\s*\n|\n(?=[A-Z0-9-])", connection_text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def subject_from_chunk(chunk: str) -> str:
    return re.split(r"\s+[\u2014-]\s+|:\s+", chunk, maxsplit=1)[0].strip()


def resolve_targets(subject: str, patterns: list[tuple[str, str, re.Pattern[str]]]) -> list[str]:
    matches: list[tuple[int, int, str, str]] = []
    seen_nodes: set[str] = set()

    for alias, key, pattern in patterns:
        match = pattern.search(subject)
        if not match or key in seen_nodes:
            continue
        seen_nodes.add(key)
        matches.append((match.start(), match.end(), alias, key))

    matches.sort()
    if len(matches) <= 1:
        return [item[3] for item in matches]

    keep_all = False
    for (_, first_end, _, _), (second_start, _, _, _) in zip(matches, matches[1:]):
        between = subject[first_end:second_start].lower()
        if " and " in between:
            keep_all = True
            break

    if keep_all:
        return [item[3] for item in matches]
    return [matches[-1][3]]


def parse_connections(nodes: dict[str, Node]) -> dict[frozenset[str], list[str]]:
    patterns = alias_patterns(nodes)
    pair_notes: dict[frozenset[str], list[str]] = defaultdict(list)

    for path in sorted(SOURCE_DIR.glob("*.txt")):
        text = clean_text(path.read_text())
        title_match = re.search(r"^Character Brief:\s*(.+)$", text, re.M)
        if not title_match or "Connections" not in text:
            continue

        source_title = title_match.group(1).strip()
        source_key = MANUAL_ROLE_MATCHES.get(source_title, source_title)
        if source_key in HIDDEN_GRAPH_NODES:
            continue
        connection_text = text.split("Connections", 1)[1].strip()

        for chunk in split_connection_chunks(connection_text):
            subject = subject_from_chunk(chunk)
            targets = resolve_targets(subject, patterns)
            for target_key in targets:
                if target_key == source_key or target_key in HIDDEN_GRAPH_NODES:
                    continue
                pair_key = frozenset((source_key, target_key))
                note = re.sub(r"\s+", " ", chunk.replace("\n", " ")).strip()
                pair_notes[pair_key].append(f"{nodes[source_key].primary_label()} -> {note}")

    for pair in pair_notes:
        for node_key in pair:
            nodes[node_key].degree += 1

    return pair_notes


def connected_nodes(nodes: dict[str, Node]) -> list[Node]:
    return sorted(
        (node for node in nodes.values() if node.degree > 0),
        key=lambda node: (-node.degree, node.primary_label()),
    )


def disconnected_assignment_roles(nodes: dict[str, Node]) -> list[str]:
    return sorted(
        node.role_label()
        for node in nodes.values()
        if node.kind == "assignment_only" and node.degree == 0
    )


def node_card_size(node: Node) -> tuple[float, float]:
    primary = node.primary_label()
    secondary = node.secondary_label() or ""
    longest = max(len(primary), len(secondary))
    width = clamp(130 + (longest * 10.0), 190, 370)
    height = 90 if secondary else 70
    return width, height


def force_layout(layout_nodes: list[Node], edges: list[tuple[str, str, int]]) -> dict[str, tuple[float, float]]:
    node_keys = [node.key for node in layout_nodes]
    if not node_keys:
        return {}

    sizes = {node.key: node_card_size(node) for node in layout_nodes}
    graph_width = GRAPH_RIGHT - GRAPH_LEFT
    graph_height = GRAPH_BOTTOM - GRAPH_TOP
    center_x = GRAPH_LEFT + graph_width / 2
    center_y = GRAPH_TOP + graph_height / 2
    radius_x = graph_width * 0.34
    radius_y = graph_height * 0.34

    positions: dict[str, tuple[float, float]] = {}
    for index, key in enumerate(node_keys):
        angle = (2 * math.pi * index) / len(node_keys)
        positions[key] = (
            center_x + radius_x * math.cos(angle),
            center_y + radius_y * math.sin(angle),
        )

    area = graph_width * graph_height
    spring_scale = math.sqrt(area / len(node_keys))
    temperature = 60.0

    for _ in range(280):
        disp = {key: [0.0, 0.0] for key in node_keys}

        for i, source in enumerate(node_keys):
            x1, y1 = positions[source]
            width1, height1 = sizes[source]
            for target in node_keys[i + 1:]:
                x2, y2 = positions[target]
                width2, height2 = sizes[target]
                dx = x1 - x2
                dy = y1 - y2
                dist = math.hypot(dx, dy) or 0.01
                min_dist = math.hypot((width1 + width2) / 2, (height1 + height2) / 2) + NODE_MARGIN
                force = (spring_scale * spring_scale) / max(dist, min_dist)
                rx = (dx / dist) * force
                ry = (dy / dist) * force
                disp[source][0] += rx
                disp[source][1] += ry
                disp[target][0] -= rx
                disp[target][1] -= ry

        for source, target, weight in edges:
            x1, y1 = positions[source]
            x2, y2 = positions[target]
            dx = x1 - x2
            dy = y1 - y2
            dist = math.hypot(dx, dy) or 0.01
            width1, height1 = sizes[source]
            width2, height2 = sizes[target]
            ideal_dist = max(260.0, ((width1 + width2) / 2) + ((height1 + height2) / 2) + 110.0)
            force = ((dist - ideal_dist) / dist) * (0.18 + weight * 0.04)
            ax = dx * force
            ay = dy * force
            disp[source][0] -= ax
            disp[source][1] -= ay
            disp[target][0] += ax
            disp[target][1] += ay

        for key in node_keys:
            dx, dy = disp[key]
            dist = math.hypot(dx, dy) or 0.01
            move = min(dist, temperature)
            x, y = positions[key]
            x += (dx / dist) * move
            y += (dy / dist) * move
            x += (center_x - x) * 0.004
            y += (center_y - y) * 0.004
            width, height = sizes[key]
            positions[key] = (
                clamp(x, GRAPH_LEFT + width / 2, GRAPH_RIGHT - width / 2),
                clamp(y, GRAPH_TOP + height / 2, GRAPH_BOTTOM - height / 2),
            )

        temperature *= 0.965

    for _ in range(220):
        moved = False
        for i, source in enumerate(node_keys):
            x1, y1 = positions[source]
            width1, height1 = sizes[source]
            for target in node_keys[i + 1:]:
                x2, y2 = positions[target]
                width2, height2 = sizes[target]
                dx = x2 - x1
                dy = y2 - y1
                overlap_x = (width1 + width2) / 2 + NODE_MARGIN - abs(dx)
                overlap_y = (height1 + height2) / 2 + NODE_MARGIN - abs(dy)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                moved = True
                if overlap_x < overlap_y:
                    shift_x = (overlap_x / 2 + 1) * (1 if dx >= 0 else -1)
                    x1 -= shift_x
                    x2 += shift_x
                else:
                    shift_y = (overlap_y / 2 + 1) * (1 if dy >= 0 else -1)
                    y1 -= shift_y
                    y2 += shift_y

                positions[source] = (
                    clamp(x1, GRAPH_LEFT + width1 / 2, GRAPH_RIGHT - width1 / 2),
                    clamp(y1, GRAPH_TOP + height1 / 2, GRAPH_BOTTOM - height1 / 2),
                )
                positions[target] = (
                    clamp(x2, GRAPH_LEFT + width2 / 2, GRAPH_RIGHT - width2 / 2),
                    clamp(y2, GRAPH_TOP + height2 / 2, GRAPH_BOTTOM - height2 / 2),
                )

        if not moved:
            break

    xs = [positions[key][0] for key in node_keys]
    ys = [positions[key][1] for key in node_keys]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    used_width = max(max_x - min_x, 1.0)
    used_height = max(max_y - min_y, 1.0)
    target_width = (GRAPH_RIGHT - GRAPH_LEFT) - 180
    target_height = (GRAPH_BOTTOM - GRAPH_TOP) - 180

    for key in node_keys:
        x, y = positions[key]
        width, height = sizes[key]
        scaled_x = GRAPH_LEFT + 90 + ((x - min_x) / used_width) * target_width
        scaled_y = GRAPH_TOP + 90 + ((y - min_y) / used_height) * target_height
        positions[key] = (
            clamp(scaled_x, GRAPH_LEFT + width / 2, GRAPH_RIGHT - width / 2),
            clamp(scaled_y, GRAPH_TOP + height / 2, GRAPH_BOTTOM - height / 2),
        )

    return positions


def render_svg(nodes: dict[str, Node], pair_notes: dict[frozenset[str], list[str]]) -> str:
    connected = connected_nodes(nodes)
    node_dom_ids = {node.key: dom_id("node", node.key) for node in connected}
    edges: list[dict[str, object]] = []
    neighbor_map: dict[str, set[str]] = defaultdict(set)
    edge_map: dict[str, list[str]] = defaultdict(list)

    for edge_index, (pair, notes) in enumerate(sorted(pair_notes.items(), key=lambda item: sorted(item[0]))):
        source, target = sorted(pair)
        edge_id = f"edge-{edge_index}"
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "weight": len(notes),
                "tooltip": " | ".join(notes),
            }
        )
        neighbor_map[source].add(target)
        neighbor_map[target].add(source)
        edge_map[source].append(edge_id)
        edge_map[target].append(edge_id)

    layout_edges = [(edge["source"], edge["target"], edge["weight"]) for edge in edges]
    positions = force_layout(connected, layout_edges) # type: ignore[arg-type]

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_WIDTH} {VIEW_HEIGHT}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Character Connection Graph</title>",
        "<desc id=\"desc\">Auto-generated graph of connected characters from the murder mystery character briefs.</desc>",
        "<defs>",
        '<filter id="cardShadow" x="-20%" y="-20%" width="140%" height="140%">',
        '<feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.10"/>',
        "</filter>",
        "</defs>",
        "<style>",
        "text { font-family: Helvetica, Arial, sans-serif; }",
        ".title { font-size: 42px; font-weight: 700; fill: #111827; }",
        ".subtitle { font-size: 22px; fill: #334155; }",
        ".edge { stroke: #64748b; stroke-linecap: round; opacity: 0.34; transition: opacity 160ms ease, stroke 160ms ease, stroke-width 160ms ease; }",
        ".node-label { font-size: 24px; font-weight: 700; fill: #0f172a; text-anchor: middle; }",
        ".node-subtitle { font-size: 18px; fill: #334155; text-anchor: middle; }",
        ".legend-label { font-size: 18px; fill: #334155; }",
        ".footer { font-size: 18px; fill: #475569; }",
        ".node-card { cursor: pointer; outline: none; transition: opacity 160ms ease; }",
        ".node-card rect { transition: opacity 160ms ease, stroke 160ms ease, stroke-width 160ms ease, filter 160ms ease; }",
        ".node-card text { transition: opacity 160ms ease, fill 160ms ease; pointer-events: none; }",
        "#graph-root.has-selection .edge { opacity: 0.08; }",
        "#graph-root.has-selection .node-card { opacity: 0.26; }",
        "#graph-root.has-selection .node-card.is-active, #graph-root.has-selection .node-card.is-related { opacity: 1; }",
        "#graph-root.has-selection .edge.is-active { stroke: #0f4c81; opacity: 0.96; }",
        ".node-card.is-active rect { stroke: #0b3b63; stroke-width: 7; }",
        ".node-card.is-related rect { stroke-width: 6; }",
        ".node-card.is-active .node-label, .node-card.is-related .node-label { fill: #0b3b63; }",
        "</style>",
        f'<rect width="{VIEW_WIDTH}" height="{VIEW_HEIGHT}" fill="#f8fafc"/>',
        '<text class="title" x="90" y="86">Cold War Character Connection Graph</text>',
        '<text class="subtitle" x="90" y="124">Generated from the Connections sections in character-brief source files.</text>',
    ]

    legend_items = [
        ("brief", "Character with a source brief"),
        ("assignment_only", "Assigned role referenced without a brief"),
        ("mentioned_only", "Mentioned-only external character"),
    ]
    for index, (kind, label) in enumerate(legend_items):
        y = 126 + index * 42
        svg_parts.append(
            f'<rect x="{LEGEND_LEFT}" y="{y - 14}" width="30" height="30" rx="10" fill="{NODE_FILL[kind]}" stroke="{NODE_STROKE[kind]}" stroke-width="3"/>'
        )
        svg_parts.append(f'<text class="legend-label" x="{LEGEND_LEFT + 48}" y="{y + 9}">{escape(label)}</text>')

    svg_parts.append('<g id="graph-root">')
    svg_parts.append('<g id="edge-layer">')
    for edge in edges:
        source = edge["source"] # type: ignore[assignment]
        target = edge["target"] # type: ignore[assignment]
        x1, y1 = positions[source] # type: ignore[index]
        x2, y2 = positions[target] # type: ignore[index]
        svg_parts.append(
            f'<line id="{edge["id"]}" class="edge" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke-width="{2.2 + (edge["weight"] * 1.5):.2f}" '
            f'data-source="{node_dom_ids[source]}" data-target="{node_dom_ids[target]}"><title>{escape(edge["tooltip"])}</title></line>'
        )
    svg_parts.append("</g>")

    svg_parts.append('<g id="node-layer">')
    for node in connected:
        x, y = positions[node.key]
        width, height = node_card_size(node)
        left = x - width / 2
        top = y - height / 2
        primary = node.primary_label()
        secondary = node.secondary_label()
        neighbor_ids = " ".join(sorted(node_dom_ids[key] for key in neighbor_map.get(node.key, set())))
        edge_ids = " ".join(sorted(edge_map.get(node.key, [])))

        svg_parts.append(
            f'<g id="{node_dom_ids[node.key]}" class="node-card" transform="translate({left:.2f} {top:.2f})" '
            f'data-node-id="{node_dom_ids[node.key]}" data-neighbor-ids="{neighbor_ids}" data-edge-ids="{edge_ids}" '
            f'focusable="true" tabindex="0" aria-label="{escape(primary)}">'
            f'<rect width="{width:.2f}" height="{height:.2f}" rx="24" '
            f'fill="{NODE_FILL[node.kind]}" stroke="{NODE_STROKE[node.kind]}" stroke-width="4" filter="url(#cardShadow)">'
            f'<title>{escape(node.tooltip())}</title></rect>'
        )
        primary_y = height / 2 + (-5 if secondary else 9)
        svg_parts.append(f'<text class="node-label" x="{width / 2:.2f}" y="{primary_y:.2f}">{escape(primary)}</text>')
        if secondary:
            svg_parts.append(f'<text class="node-subtitle" x="{width / 2:.2f}" y="{primary_y + 30:.2f}">{escape(secondary)}</text>')
        svg_parts.append("</g>")
    svg_parts.append("</g>")
    svg_parts.append("</g>")

    svg_parts.extend(
        [
            "<script><![CDATA[",
            "(function () {",
            "  const script = document.currentScript;",
            "  const svg = script && script.ownerSVGElement;",
            "  if (!svg) return;",
            "  const graphRoot = svg.getElementById('graph-root');",
            "  if (!graphRoot) return;",
            "  const nodeCards = Array.from(svg.querySelectorAll('.node-card'));",
            "  let hoveredNode = null;",
            "  let focusedNode = null;",
            "",
            "  function clearState() {",
            "    graphRoot.classList.remove('has-selection');",
            "    nodeCards.forEach((node) => {",
            "      node.classList.remove('is-active');",
            "      node.classList.remove('is-related');",
            "    });",
            "    svg.querySelectorAll('.edge').forEach((edge) => edge.classList.remove('is-active'));",
            "  }",
            "",
            "  function activate(node) {",
            "    clearState();",
            "    if (!node) return;",
            "    graphRoot.classList.add('has-selection');",
            "    node.classList.add('is-active');",
            "    const neighborIds = (node.getAttribute('data-neighbor-ids') || '').split(/\\s+/).filter(Boolean);",
            "    const edgeIds = (node.getAttribute('data-edge-ids') || '').split(/\\s+/).filter(Boolean);",
            "    neighborIds.forEach((id) => {",
            "      const neighbor = svg.getElementById(id);",
            "      if (neighbor) neighbor.classList.add('is-related');",
            "    });",
            "    edgeIds.forEach((id) => {",
            "      const edge = svg.getElementById(id);",
            "      if (edge) edge.classList.add('is-active');",
            "    });",
            "  }",
            "",
            "  function updateActiveNode() {",
            "    activate(hoveredNode || focusedNode);",
            "  }",
            "",
            "  nodeCards.forEach((node) => {",
            "    node.addEventListener('mouseenter', () => {",
            "      hoveredNode = node;",
            "      updateActiveNode();",
            "    });",
            "    node.addEventListener('mouseleave', () => {",
            "      if (hoveredNode === node) hoveredNode = null;",
            "      updateActiveNode();",
            "    });",
            "    node.addEventListener('focus', () => {",
            "      focusedNode = node;",
            "      updateActiveNode();",
            "    });",
            "    node.addEventListener('blur', () => {",
            "      if (focusedNode === node) focusedNode = null;",
            "      updateActiveNode();",
            "    });",
            "  });",
            "})();",
            "]]></script>",
            f'<text class="footer" x="90" y="{VIEW_HEIGHT - 76}">Edge thickness reflects how many briefs mention that relationship.</text>',
            f'<text class="footer" x="90" y="{VIEW_HEIGHT - 44}">Updated {date.today().isoformat()} by scripts/generate_character_connection_graph.py</text>',
            "</svg>",
        ]
    )
    return "\n".join(svg_parts)


def wrap_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "None"


def render_markdown(nodes: dict[str, Node], pair_notes: dict[frozenset[str], list[str]]) -> str:
    connected = connected_nodes(nodes)
    disconnected = disconnected_assignment_roles(nodes)

    neighbor_map: dict[str, set[str]] = defaultdict(set)
    for pair in pair_notes:
        source, target = sorted(pair)
        neighbor_map[source].add(target)
        neighbor_map[target].add(source)

    lines = [
        "# Character Connection Graph",
        "",
        "Auto-generated from the `Connections` sections in `character-briefs/source/*.txt`.",
        "",
        "![Character Connection Graph](Character Connection Graph.png)",
        "",
        "## Legend",
        "",
        "- Blue nodes are characters with a source brief.",
        "- Gold nodes are assigned roles referenced in other briefs but not yet written.",
        "- Gray nodes are mentioned-only external characters.",
        "- Thicker lines mean the relationship is mentioned in more briefs.",
        "",
        "## Connected Characters",
        "",
    ]

    for node in connected:
        neighbors = sorted(
            (nodes[key].primary_label() for key in neighbor_map.get(node.key, set())),
            key=str.casefold,
        )
        heading = node.primary_label()
        if node.secondary_label():
            heading += f" ({node.secondary_label()})"
        lines.append(f"- **{heading}**: {', '.join(neighbors)}")

    lines.extend(
        [
            "",
            "## Not Currently Connected",
            "",
            f"- Assigned but not referenced in any current `Connections` section: {wrap_list(disconnected)}",
            "",
            "## Notes",
            "",
            "- The PNG preview is rendered from the generated SVG when `qlmanage` is available on macOS.",
            "- `The SCSR recipient` is normalized to John Brightmann based on the matching espionage handoff described in the briefs.",
            "- `Your new girlfriend` is normalized to Agent Red based on Victor Hale's and Agent Red's paired cover story.",
            "- `The Journalist` remains a separate gray node because the current briefs describe that identity ambiguously.",
            "",
        ]
    )
    return "\n".join(lines)


def write_png_preview() -> None:
    if not shutil.which("qlmanage"):
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            ["qlmanage", "-t", "-s", str(PNG_RENDER_SIZE), "-o", temp_dir, str(OUTPUT_SVG)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        preview_path = Path(temp_dir) / f"{OUTPUT_SVG.name}.png"
        if preview_path.exists():
            shutil.copyfile(preview_path, OUTPUT_PNG)


def main() -> None:
    nodes = parse_briefs()
    extend_with_mentioned_only(nodes)
    pair_notes = parse_connections(nodes)
    OUTPUT_SVG.write_text(render_svg(nodes, pair_notes))
    write_png_preview()
    OUTPUT_MD.write_text(render_markdown(nodes, pair_notes))
    print(f"Wrote {OUTPUT_SVG}")
    if OUTPUT_PNG.exists():
        print(f"Wrote {OUTPUT_PNG}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
