import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useColorMode} from '@docusaurus/theme-common';
import {
  ReactFlow,
  Background,
  Controls,
  Panel,
  MarkerType,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/** Build a labelled, coloured node. */
export function makeNode(id, x, y, title, subtitle, color) {
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
      width: 180,
      fontSize: 13,
      textAlign: 'center',
      boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
    },
  };
}

/** Build a directed, animated edge with an arrow head. */
export function edge(id, source, target, label) {
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

const buttonStyle = {
  background: 'var(--ifm-background-surface-color)',
  color: 'var(--ifm-font-color-base)',
  border: '1px solid var(--ifm-color-emphasis-300)',
  borderRadius: 6,
  padding: '4px 8px',
  fontSize: 12,
  cursor: 'pointer',
};

/**
 * A reusable React Flow canvas: theme-aware, draggable nodes, fullscreen toggle.
 * Pass `nodes` and `edges` (see makeNode / edge helpers).
 */
export default function FlowDiagram({nodes: initialNodes, edges: initialEdges, height = 380}) {
  const {colorMode} = useColorMode(); // follows the Docusaurus theme
  const wrapperRef = useRef(null);
  const rfRef = useRef(null);
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => rfRef.current?.fitView({padding: 0.15}), 80);
    return () => clearTimeout(t);
  }, [isFullscreen]);

  const toggleFullscreen = useCallback(() => {
    const el = wrapperRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      el.requestFullscreen?.();
    }
  }, []);

  return (
    <div
      ref={wrapperRef}
      style={{
        height: isFullscreen ? '100%' : height,
        width: '100%',
        background: 'var(--ifm-background-color)',
        border: '1px solid var(--ifm-color-emphasis-300)',
        borderRadius: isFullscreen ? 0 : 8,
        margin: isFullscreen ? 0 : '1rem 0',
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={(inst) => {
          rfRef.current = inst;
        }}
        colorMode={colorMode}
        fitView
        fitViewOptions={{padding: 0.15}}
        nodesConnectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
        preventScrolling={false}
        proOptions={{hideAttribution: true}}
      >
        <Background gap={16} />
        <Controls showInteractive={false} />
        <Panel position="top-right">
          <button
            type="button"
            onClick={toggleFullscreen}
            style={buttonStyle}
            title="Toggle fullscreen"
          >
            {isFullscreen ? '✕ Exit fullscreen' : '⛶ Fullscreen'}
          </button>
        </Panel>
      </ReactFlow>
    </div>
  );
}
