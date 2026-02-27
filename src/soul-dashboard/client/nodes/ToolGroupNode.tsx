/**
 * ToolGroupNode - 동일 도구 그룹 노드
 *
 * 같은 thinking 노드에 연결된 동일 도구 호출을 하나로 묶어 표시합니다.
 * 예: "Read ×12" — 클릭 시 DetailPanel에서 개별 도구 결과를 확인할 수 있습니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type ToolGroupNodeType = Node<GraphNodeData, 'tool_group'>;

const ACCENT = '#d97706'; // amber-600

export const ToolGroupNode = memo(function ToolGroupNode({ data, selected }: NodeProps<ToolGroupNodeType>) {
  const isStreaming = data.streaming;
  const count = data.groupCount ?? 0;

  return (
    <div
      data-testid="tool-group-node"
      style={{
        width: 260,
        height: 84,
        boxSizing: 'border-box',
        background: 'rgba(17, 24, 39, 0.95)',
        border: selected
          ? `1px solid ${ACCENT}`
          : '1px solid rgba(255,255,255,0.1)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
        display: 'flex',
        overflow: 'hidden',
        ...(isStreaming && !selected
          ? { animation: 'tool-call-pulse 2s infinite' }
          : {}),
      }}
    >
      {/* Left accent bar */}
      <div
        style={{
          width: 4,
          flexShrink: 0,
          background: ACCENT,
          borderRadius: '8px 0 0 8px',
        }}
      />

      {/* Content area */}
      <div style={{ flex: 1, padding: '10px 12px', minWidth: 0 }}>
        {/* Header row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 6,
          }}
        >
          <span style={{ fontSize: 14, flexShrink: 0 }}>📦</span>
          <span
            style={{
              fontSize: 10,
              color: '#6b7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 600,
            }}
          >
            Tool Group
          </span>
          {/* Count badge */}
          <span
            style={{
              marginLeft: 'auto',
              fontSize: 11,
              color: ACCENT,
              fontWeight: 700,
              padding: '1px 6px',
              borderRadius: 4,
              backgroundColor: 'rgba(217, 119, 6, 0.12)',
            }}
          >
            ×{count}
          </span>
        </div>

        {/* Tool name */}
        <div
          style={{
            fontSize: 13,
            color: '#e5e7eb',
            fontWeight: 600,
            fontFamily: "'Cascadia Code', 'Fira Code', monospace",
            marginBottom: 4,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {data.toolName || 'unknown'}
        </div>

        {/* Summary */}
        <div
          style={{
            fontSize: 11,
            color: '#6b7280',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {isStreaming ? 'running...' : `${count} calls grouped`}
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        style={{
          width: 8,
          height: 8,
          background: ACCENT,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        style={{
          width: 8,
          height: 8,
          background: ACCENT,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        style={{
          width: 8,
          height: 8,
          background: ACCENT,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        style={{
          width: 8,
          height: 8,
          background: ACCENT,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
    </div>
  );
});
