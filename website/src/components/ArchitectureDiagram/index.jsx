import React from 'react';
import FlowDiagram, {edge, makeNode} from '@site/src/components/FlowDiagram';

const COLORS = {
  acquire: '#6366f1', // indigo
  store: '#0ea5e9', // sky
  pipeline: '#14b8a6', // teal
  metrics: '#f59e0b', // amber
  backtest: '#ef4444', // red
  execution: '#e11d48', // rose
  viz: '#a855f7', // purple
  dashboard: '#64748b', // slate
};

const nodes = [
  makeNode('sources', 0, 150, 'Acquisition', 'sources · akshare / QMT', COLORS.acquire),
  makeNode('ingest', 210, 150, 'Pipeline', 'ingest · DailyBackfill', COLORS.pipeline),
  makeNode('data', 420, 150, 'Storage', 'data · ClickHouse', COLORS.store),
  makeNode('metrics', 630, 150, 'Metrics', 'indicators + stats', COLORS.metrics),
  makeNode('backtest', 850, 10, 'Backtest', 'engine · strategies', COLORS.backtest),
  makeNode('execution', 850, 150, 'Execution', 'live · SimBroker / QMT', COLORS.execution),
  makeNode('viz', 850, 290, 'Visualization', 'viz · Plotly', COLORS.viz),
  makeNode('dashboard', 1070, 150, 'Dashboard', 'Streamlit', COLORS.dashboard),
];

const edges = [
  edge('e1', 'sources', 'ingest', 'fetch'),
  edge('e2', 'ingest', 'data', 'write (idempotent)'),
  edge('e3', 'data', 'metrics', 'read bars'),
  edge('e4', 'metrics', 'backtest', 'signals + stats'),
  edge('e5', 'metrics', 'execution', 'signals (live)'),
  edge('e6', 'metrics', 'viz', 'indicators'),
  edge('e7', 'backtest', 'viz', 'equity / drawdown'),
  edge('e8', 'viz', 'dashboard'),
];

export default function ArchitectureDiagram() {
  return <FlowDiagram nodes={nodes} edges={edges} />;
}
