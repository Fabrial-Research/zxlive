import pytest
from pytestqt.qtbot import QtBot
from pyzx.utils import EdgeType, VertexType, get_triangle_partner

from zxlive.commands import AddTriangleNode, ChangeNodeType
from zxlive.common import GraphT, find_unknown_tikz_styles, new_graph
from zxlive.graphscene import GraphScene
from zxlive.vitem import DEFAULT_COLOR_KEY_BY_TYPE, PRESSED_COLOR_KEY_BY_TYPE


def test_triangle_styles_are_known() -> None:
    tikz = r"\node [style=triangle] (0) at (0, 0) {};" + "\n" + \
           r"\node [style=triangle input] (1) at (0, 1) {};"
    assert find_unknown_tikz_styles(tikz) == []


# ---------------------------------------------------------------------------
# Task 6: AddTriangleNode command
# ---------------------------------------------------------------------------

class _FakeGraphScene:
    def __init__(self) -> None:
        self.g = new_graph()


class _FakeGraphView:
    """Minimal stub satisfying BaseCommand's interface."""

    def __init__(self) -> None:
        self.graph_scene = _FakeGraphScene()
        self._last_graph = None

    def update_graph(self, g: GraphT, select_new: bool = False) -> None:  # type: ignore[override]
        self._last_graph = g


def test_add_triangle_creates_pair() -> None:
    gv = _FakeGraphView()
    cmd = AddTriangleNode(gv, 2.0, 1.0)  # type: ignore[arg-type]
    cmd.redo()
    g = cmd.g
    tys = sorted(int(g.type(v)) for v in g.vertices())
    assert tys == [int(VertexType.TRIANGLE_INPUT), int(VertexType.TRIANGLE_OUTPUT)]
    body = next(v for v in g.vertices() if g.type(v) == VertexType.TRIANGLE_OUTPUT)
    assert g.type(get_triangle_partner(g, body)) == VertexType.TRIANGLE_INPUT
    cmd.undo()
    assert len(list(g.vertices())) == 0


# ---------------------------------------------------------------------------
# Task 7: Triangle rendering (vitem)
# ---------------------------------------------------------------------------

def test_triangle_color_keys() -> None:
    assert DEFAULT_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_OUTPUT] == "hadamard"
    assert DEFAULT_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INPUT] == "w_input"
    assert PRESSED_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_OUTPUT] == "hadamard_pressed"
    assert PRESSED_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INPUT] == "w_input_pressed"


def test_triangle_renders(qtbot: QtBot) -> None:
    """Triangle pair added directly to a graph must appear in scene.vertex_map
    after set_graph and must not raise during refresh / shape path creation."""
    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    scene = GraphScene()
    scene.set_graph(g)

    assert tip in scene.vertex_map, "TRIANGLE_INPUT must be in vertex_map"
    assert body in scene.vertex_map, "TRIANGLE_OUTPUT must be in vertex_map"

    # _make_shape_path and refresh must not raise
    body_vitem = scene.vertex_map[body]
    body_vitem.refresh()

    # Body is at a different row from tip, so rotation should be non-zero
    assert body_vitem.rotation() != 0.0, "Body should auto-rotate toward tip"


# ---------------------------------------------------------------------------
# Task 8: Triangle palette entry
# ---------------------------------------------------------------------------

def test_triangle_in_palette() -> None:
    from zxlive.editor_base_panel import vertices_data
    data = vertices_data()
    assert VertexType.TRIANGLE_OUTPUT in data
    assert data[VertexType.TRIANGLE_OUTPUT]["text"] == "Triangle"


# ---------------------------------------------------------------------------
# Task 9: Copy/paste + undo integration test
# ---------------------------------------------------------------------------

def test_triangle_graph_json_roundtrip() -> None:
    """Triangle pair must survive JSON serialization round-trip (copy/paste + save/load)."""
    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, 0, 1)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, 0, 2)
    g.add_edge((tip, body), EdgeType.W_IO)
    g2 = GraphT.from_json(g.to_json())
    tys = sorted(int(g2.type(v)) for v in g2.vertices())
    assert tys == [int(VertexType.TRIANGLE_INPUT), int(VertexType.TRIANGLE_OUTPUT)]
    assert any(g2.edge_type(e) == EdgeType.W_IO for e in g2.edges())


# ---------------------------------------------------------------------------
# Final review: lifecycle guard fixes  (items 1-5 from final-review-findings)
# ---------------------------------------------------------------------------

# Shared minimal fakes for calling EditorBasePanel helper methods as unbound
# functions without instantiating the full Qt widget hierarchy.

class _FakeUndoStackExec:
    """Executes commands immediately so the graph mutation is visible."""
    def push(self, cmd: object) -> None:  # type: ignore[override]
        cmd.redo()  # type: ignore[attr-defined]


class _FakeGScene2:
    """Minimal graph-scene stub."""
    def __init__(self, g: GraphT, selected_verts: list, selected_edges: list | None = None) -> None:
        self.g = g
        self.selected_vertices = selected_verts
        self.selected_edges = selected_edges or []


class _FakeGView2:
    """Minimal graph-view stub."""
    def __init__(self, scene: _FakeGScene2) -> None:
        self.graph_scene = scene
        self.last_graph: GraphT = scene.g

    def update_graph(self, g: GraphT, select_new: bool = False) -> None:
        self.last_graph = g

    def set_graph(self, g: GraphT) -> None:
        self.last_graph = g


class _FakePanel2:
    """Minimal EditorBasePanel substitute for unbound-method calls."""
    def __init__(self, g: GraphT, selected_verts: list) -> None:
        self._scene = _FakeGScene2(g, selected_verts)
        self.graph_scene: _FakeGScene2 = self._scene
        self.graph_view: _FakeGView2 = _FakeGView2(self._scene)
        self.undo_stack = _FakeUndoStackExec()

    @property
    def graph(self) -> GraphT:
        return self.graph_scene.g


# Fix 1: delete_selection cascade ----------------------------------------

def test_delete_cascade_removes_triangle_partner() -> None:
    """Selecting the body must cascade to remove the tip as well, leaving the
    graph empty and preventing orphan-vertex AssertionError from
    get_triangle_partner."""
    from zxlive.editor_base_panel import EditorBasePanel

    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    # Select only the body; after the fix the tip must cascade into the delete set.
    panel = _FakePanel2(g, [body])
    EditorBasePanel.delete_selection(panel)  # type: ignore[arg-type]

    remaining = list(panel.graph_view.last_graph.vertices())
    assert len(remaining) == 0, (
        f"Expected 0 vertices (cascade-delete); got {len(remaining)}: {remaining}"
    )


def test_delete_cascade_tip_selects_removes_body() -> None:
    """Selecting the tip must cascade to remove the body as well."""
    from zxlive.editor_base_panel import EditorBasePanel

    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    # Select only the tip.
    panel = _FakePanel2(g, [tip])
    EditorBasePanel.delete_selection(panel)  # type: ignore[arg-type]

    remaining = list(panel.graph_view.last_graph.vertices())
    assert len(remaining) == 0, (
        f"Expected 0 vertices (tip cascade-delete); got {len(remaining)}: {remaining}"
    )


# Fix 2 & 3: _is_invalid_edge triangle guards -----------------------------

def test_is_invalid_edge_blocks_triangle_partners() -> None:
    """An edge between existing triangle partners must be rejected."""
    from zxlive.editor_base_panel import EditorBasePanel

    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    # _is_invalid_edge uses no `self` state — passing None is safe.
    result = EditorBasePanel._is_invalid_edge(None, g, tip, body)  # type: ignore[arg-type]
    assert result is True, "Edge between triangle partners must be invalid"


def test_is_invalid_edge_caps_triangle_input_degree() -> None:
    """A second external edge to TRIANGLE_INPUT must be blocked (cap = 1 external)."""
    from zxlive.editor_base_panel import EditorBasePanel

    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)
    external = g.add_vertex(VertexType.Z, qubit=2, row=-1)
    g.add_edge((external, tip))  # first external edge — now tip has 2 neighbours

    extra = g.add_vertex(VertexType.Z, qubit=3, row=-1)
    result = EditorBasePanel._is_invalid_edge(None, g, tip, extra)  # type: ignore[arg-type]
    assert result is True, "Third edge to TRIANGLE_INPUT must be invalid"


def test_is_invalid_edge_caps_triangle_output_degree() -> None:
    """A second external edge to TRIANGLE_OUTPUT must be blocked (cap = 1 external)."""
    from zxlive.editor_base_panel import EditorBasePanel

    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)
    external = g.add_vertex(VertexType.Z, qubit=2, row=2)
    g.add_edge((external, body))  # first external edge — now body has 2 neighbours

    extra = g.add_vertex(VertexType.Z, qubit=3, row=2)
    result = EditorBasePanel._is_invalid_edge(None, g, body, extra)  # type: ignore[arg-type]
    assert result is True, "Third edge to TRIANGLE_OUTPUT must be invalid"


# Fix 3: vert_double_clicked phase guard ----------------------------------

def test_phase_guard_rejects_triangle(monkeypatch: pytest.MonkeyPatch) -> None:
    """vert_double_clicked must return early for triangle vertices without
    opening a phase-input dialog (which would raise ValueError on triangle)."""
    from zxlive.editor_base_panel import EditorBasePanel

    dialog_called: list[bool] = []

    class _MockQInputDialog:
        @staticmethod
        def getText(*args: object, **kwargs: object) -> tuple[str, bool]:
            dialog_called.append(True)
            return ("", False)

    monkeypatch.setattr("zxlive.editor_base_panel.QInputDialog", _MockQInputDialog)

    g = new_graph()
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    g.add_edge((tip, body), EdgeType.W_IO)

    panel = _FakePanel2(g, [])
    EditorBasePanel.vert_double_clicked(panel, body)  # type: ignore[arg-type]

    assert dialog_called == [], (
        "QInputDialog.getText must NOT be called for triangle body vertex"
    )

    EditorBasePanel.vert_double_clicked(panel, tip)  # type: ignore[arg-type]
    assert dialog_called == [], (
        "QInputDialog.getText must NOT be called for triangle tip vertex"
    )


# Fix 4: drag-sync _collect_moved_vertices --------------------------------

def test_drag_sync_collects_triangle_partner(qtbot: QtBot) -> None:
    """Moving the triangle body must include the tip in the moved-vertex set
    so both halves translate together."""
    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    scene = GraphScene()
    scene.set_graph(g)

    body_vitem = scene.vertex_map[body]
    body_vitem.setSelected(True)

    moved = body_vitem._collect_moved_vertices(scene)
    vs = {it.v for it in moved}

    assert body in vs, f"body {body} missing from moved set {vs}"
    assert tip in vs, f"tip {tip} must be collected when body is moved; got {vs}"


# Fix 5: ChangeNodeType no-op for triangle --------------------------------

def test_change_node_type_noop_for_triangle() -> None:
    """ChangeNodeType on a triangle vertex must be a no-op: both the vertex
    type and its partner must remain unchanged after redo."""
    gv = _FakeGraphView()
    g = gv.graph_scene.g
    tip = g.add_vertex(VertexType.TRIANGLE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    cmd = ChangeNodeType(gv, [body], VertexType.Z)  # type: ignore[arg-type]
    cmd.redo()

    # After fix: body type unchanged, partner not orphaned.
    assert cmd.g.type(body) == VertexType.TRIANGLE_OUTPUT, (
        f"Expected TRIANGLE_OUTPUT after redo; got {cmd.g.type(body)}"
    )
    assert cmd.g.type(tip) == VertexType.TRIANGLE_INPUT, (
        f"tip type should be TRIANGLE_INPUT; got {cmd.g.type(tip)}"
    )
