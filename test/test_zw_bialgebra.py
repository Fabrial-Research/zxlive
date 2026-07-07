import pytest
from pyzx.utils import VertexType, EdgeType

from zxlive.common import GraphT
from zxlive.rewrite_data import rules_basic, MATCH_DOUBLE, MATCH_COMPOUND

S = EdgeType.SIMPLE


def test_zw_rules_registered() -> None:
    assert 'zw_bialgebra' in rules_basic
    assert 'zw_bialgebra_op' in rules_basic
    assert rules_basic['zw_bialgebra']['type'] == MATCH_DOUBLE
    assert rules_basic['zw_bialgebra']['repeat_rule_application'] is False
    assert rules_basic['zw_bialgebra_op']['type'] == MATCH_COMPOUND


def test_zw_expand_applies_on_grapht() -> None:
    g = GraphT()
    ins = [g.add_vertex(VertexType.BOUNDARY, i, 0) for i in range(2)]
    z = g.add_vertex(VertexType.Z, 2, 1)
    w_in = g.add_vertex(VertexType.W_INPUT, 2, 2)
    w_out = g.add_vertex(VertexType.W_OUTPUT, 2, 2.3)
    g.add_edge((w_in, w_out), EdgeType.W_IO)
    outs = [g.add_vertex(VertexType.BOUNDARY, i, 4) for i in range(2)]
    for b in ins:
        g.add_edge((b, z), S)
    g.add_edge((z, w_in), S)
    for b in outs:
        g.add_edge((w_out, b), S)
    g.set_inputs(tuple(ins))
    g.set_outputs(tuple(outs))

    rule = rules_basic['zw_bialgebra']['rule']
    assert rule.is_match(g, z, w_in)  # type: ignore
    assert rule.apply(g, z, w_in)  # type: ignore
    # Two inputs -> two new W nodes; two outputs -> two new Z spiders.
    n_w_in = sum(1 for v in g.vertices() if g.type(v) == VertexType.W_INPUT)
    n_z = sum(1 for v in g.vertices() if g.type(v) == VertexType.Z)
    assert n_w_in == 2
    assert n_z == 2
