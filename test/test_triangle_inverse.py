from pytestqt.qtbot import QtBot
from pyzx.utils import VertexType, EdgeType, get_triangle_partner
from zxlive.commands import AddTriangleInverseNode, ChangeNodeType
from zxlive.common import GraphT, find_unknown_tikz_styles, new_graph
from zxlive.vitem import DEFAULT_COLOR_KEY_BY_TYPE, PRESSED_COLOR_KEY_BY_TYPE
from zxlive.graphscene import GraphScene


def test_inverse_styles_are_known() -> None:
    tikz = r"\node [style=triangle inverse] (0) at (0, 0) {};" + "\n" + \
           r"\node [style=triangle inverse input] (1) at (0, 1) {};"
    assert find_unknown_tikz_styles(tikz) == []


class _FakeGraphScene:
    def __init__(self) -> None:
        self.g: GraphT = new_graph()


class _FakeGraphView:
    """Minimal stub satisfying BaseCommand's interface."""
    def __init__(self) -> None:
        self.graph_scene = _FakeGraphScene()
        self._last_graph: GraphT | None = None

    def update_graph(self, g: GraphT, select_new: bool = False) -> None:  # type: ignore[override]
        self._last_graph = g


def test_add_triangle_inverse_creates_pair() -> None:
    gv = _FakeGraphView()
    cmd = AddTriangleInverseNode(gv, 2.0, 1.0)  # type: ignore[arg-type]
    cmd.redo()
    g = cmd.g
    tys = sorted(int(g.type(v)) for v in g.vertices())
    assert tys == [int(VertexType.TRIANGLE_INVERSE_INPUT),
                   int(VertexType.TRIANGLE_INVERSE_OUTPUT)]
    body = next(v for v in g.vertices()
                if g.type(v) == VertexType.TRIANGLE_INVERSE_OUTPUT)
    assert g.type(get_triangle_partner(g, body)) == VertexType.TRIANGLE_INVERSE_INPUT
    cmd.undo()
    assert len(list(g.vertices())) == 0


def test_inverse_color_keys() -> None:
    assert DEFAULT_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INVERSE_OUTPUT] == "hadamard"
    assert DEFAULT_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INVERSE_INPUT] == "w_input"
    assert PRESSED_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INVERSE_OUTPUT] == "hadamard_pressed"
    assert PRESSED_COLOR_KEY_BY_TYPE[VertexType.TRIANGLE_INVERSE_INPUT] == "w_input_pressed"


def test_inverse_renders(qtbot: QtBot) -> None:
    """Inverse pair added to a graph must appear in scene.vertex_map and must
    not raise during refresh / shape-path / bar-marker paint; body auto-rotates."""
    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INVERSE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_INVERSE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    scene = GraphScene()
    scene.set_graph(g)

    assert tip in scene.vertex_map, "TRIANGLE_INVERSE_INPUT must be in vertex_map"
    assert body in scene.vertex_map, "TRIANGLE_INVERSE_OUTPUT must be in vertex_map"

    body_vitem = scene.vertex_map[body]
    body_vitem.refresh()  # _make_shape_path must not raise
    assert body_vitem.rotation() != 0.0, "Body should auto-rotate toward tip"


def test_inverse_in_palette() -> None:
    from zxlive.editor_base_panel import vertices_data
    data = vertices_data()
    assert VertexType.TRIANGLE_INVERSE_OUTPUT in data
    assert data[VertexType.TRIANGLE_INVERSE_OUTPUT]["text"] == "Triangle inverse"


def test_inverse_graph_json_roundtrip() -> None:
    """Inverse pair must survive JSON round-trip (copy/paste + save/load)."""
    g = new_graph()
    tip = g.add_vertex(VertexType.TRIANGLE_INVERSE_INPUT, 0, 1)
    body = g.add_vertex(VertexType.TRIANGLE_INVERSE_OUTPUT, 0, 2)
    g.add_edge((tip, body), EdgeType.W_IO)
    g2 = GraphT.from_json(g.to_json())
    tys = sorted(int(g2.type(v)) for v in g2.vertices())
    assert tys == [int(VertexType.TRIANGLE_INVERSE_INPUT),
                   int(VertexType.TRIANGLE_INVERSE_OUTPUT)]
    assert any(g2.edge_type(e) == EdgeType.W_IO for e in g2.edges())


def test_change_node_type_noop_for_inverse() -> None:
    """ChangeNodeType on an inverse vertex must be a no-op (inherited guard)."""
    gv = _FakeGraphView()
    g = gv.graph_scene.g
    tip = g.add_vertex(VertexType.TRIANGLE_INVERSE_INPUT, qubit=0, row=0)
    body = g.add_vertex(VertexType.TRIANGLE_INVERSE_OUTPUT, qubit=0, row=1)
    g.add_edge((tip, body), EdgeType.W_IO)

    cmd = ChangeNodeType(gv, [body], VertexType.Z)  # type: ignore[arg-type]
    cmd.redo()

    assert cmd.g.type(body) == VertexType.TRIANGLE_INVERSE_OUTPUT
    assert cmd.g.type(tip) == VertexType.TRIANGLE_INVERSE_INPUT


def test_tikz_export_survives_settings_refresh() -> None:
    """Regression: zxlive replaces pyzx.settings.tikz_classes on settings load
    (settings.refresh_pyzx_tikz_settings, called at startup and on dialog save).
    That rebuilt dict must keep the triangle + triangle-inverse styles, or
    copy / export-to-TikZ raises KeyError on any triangle node."""
    from zxlive.common import to_tikz
    from zxlive.settings import refresh_pyzx_tikz_settings
    refresh_pyzx_tikz_settings()
    for tin, tout in [
        (VertexType.TRIANGLE_INPUT, VertexType.TRIANGLE_OUTPUT),
        (VertexType.TRIANGLE_INVERSE_INPUT, VertexType.TRIANGLE_INVERSE_OUTPUT),
    ]:
        g = new_graph()
        a = g.add_vertex(tin, 0, 1)
        b = g.add_vertex(tout, 0, 2)
        g.add_edge((a, b), EdgeType.W_IO)
        to_tikz(g)  # must not raise KeyError
