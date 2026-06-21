import React from 'react';
import FlowDiagram, {edge, makeNode} from '@site/src/components/FlowDiagram';

const COLORS = {
  signal: '#f59e0b', // amber
  weight: '#0ea5e9', // sky
  order: '#e11d48', // rose
  fill: '#64748b', // slate
};

const nodes = [
  makeNode('signal', 0, 60, 'Signal / alpha', 'what the strategy thinks', COLORS.signal),
  makeNode('weight', 250, 60, 'Target weight', 'how much to hold (sizing)', COLORS.weight),
  makeNode('order', 500, 60, 'Order', 'reconcile current → target', COLORS.order),
  makeNode('fill', 750, 60, 'Fill', 'executed trade + cost', COLORS.fill),
];

const edges = [
  edge('c1', 'signal', 'weight', 'size / risk'),
  edge('c2', 'weight', 'order', 'reconcile'),
  edge('c3', 'order', 'fill', 'broker'),
];

export default function ConceptDiagram() {
  return <FlowDiagram nodes={nodes} edges={edges} height={240} />;
}
