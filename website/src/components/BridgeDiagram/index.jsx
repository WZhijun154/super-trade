import React from 'react';
import FlowDiagram, {edge, makeNode} from '@site/src/components/FlowDiagram';

const COLORS = {
  shared: '#f59e0b', // amber — the shared strategy + risk
  sim: '#0ea5e9', // sky — backtest / dry-run
  qmt: '#e11d48', // rose — live
};

const nodes = [
  makeNode(
    'shared',
    0,
    110,
    'Strategy + RiskManager',
    'one code path',
    COLORS.shared,
  ),
  makeNode(
    'sim',
    340,
    20,
    'SimBroker',
    'dry-run · event-driven backtest',
    COLORS.sim,
  ),
  makeNode(
    'qmt',
    340,
    200,
    'QmtBroker',
    'live · QMT simulation account',
    COLORS.qmt,
  ),
];

const edges = [
  edge('b1', 'shared', 'sim', 'backtest / dry-run'),
  edge('b2', 'shared', 'qmt', 'live'),
];

export default function BridgeDiagram() {
  return <FlowDiagram nodes={nodes} edges={edges} height={300} />;
}
