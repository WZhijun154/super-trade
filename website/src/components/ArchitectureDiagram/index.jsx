import React from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const COLORS = {
  acquire: '#6366f1', // indigo
  store: '#0ea5e9', // sky
  pipeline: '#14b8a6', // teal
  metrics: '#f59e0b', // amber
  backtest: '#ef4444', // red
  viz: '#a855f7', // purple
  dashboard: '#64748b', // slate
};

function makeNode(id, x, y, title, subtitle, color) {
  return {
    id,
    position: {x, y},
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: {
      label: (
        <div style={{lineHeight: 1.3}}>
          <strong>{title}</strong>
          <div style={{fontSize: 10, opacity: 0.85}}>{subtitle}</div>
        </div>
      ),
    },
    style: {
      background: color,
      color: '#fff',
      border: 'none',
      borderRadius: 10,
      padding: 10,
      width: 170,
      fontSize: 13,
      textAlign: 'center',
      boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
    },
  };
}

const nodes = [
  makeNode('sources', 0, 130, 'Acquisition', 'sources · akshare / QMT', COLORS.acquire),
  makeNode('ingest', 210, 130, 'Pipeline', 'ingest · DailyBackfill', COLORS.pipeline),
  makeNode('data', 420, 130, 'Storage', 'data · ClickHouse', COLORS.store),
  makeNode('metrics', 630, 130, 'Metrics', 'indicators + stats', COLORS.metrics),
  makeNode('backtest', 850, 40, 'Backtest', 'engine · strategies', COLORS.backtest),
  makeNode('viz', 850, 220, 'Visualization', 'viz · Plotly', COLORS.viz),
  makeNode('dashboard', 1070, 130, 'Dashboard', 'Streamlit', COLORS.dashboard),
];

function edge(id, source, target, label) {
  return {
    id,
    source,
    target,
    label,
    animated: true,
    markerEnd: {type: MarkerType.ArrowClosed},
    style: {strokeWidth: 1.5},
    labelStyle: {fontSize: 10},
  };
}

const edges = [
  edge('e1', 'sources', 'ingest', 'fetch'),
  edge('e2', 'ingest', 'data', 'write (idempotent)'),
  edge('e3', 'data', 'metrics', 'read bars'),
  edge('e4', 'metrics', 'backtest', 'signals + stats'),
  edge('e5', 'metrics', 'viz', 'indicators'),
  edge('e6', 'backtest', 'viz', 'equity / drawdown'),
  edge('e7', 'viz', 'dashboard'),
];

export default function ArchitectureDiagram() {
  return (
    <div
      style={{
        height: 380,
        width: '100%',
        border: '1px solid var(--ifm-color-emphasis-300)',
        borderRadius: 8,
        margin: '1rem 0',
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{padding: 0.15}}
        nodesDraggable={false}
        nodesConnectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
        preventScrolling={false}
        proOptions={{hideAttribution: true}}
      >
        <Background gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
