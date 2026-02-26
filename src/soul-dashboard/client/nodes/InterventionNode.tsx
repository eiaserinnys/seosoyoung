/**
 * InterventionNode - 사용자 개입 노드
 *
 * 세션 중간에 사용자가 보낸 추가 메시지/개입을 표시합니다.
 * UserNode와 비슷하지만 주황색 계열로 구분됩니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type InterventionNodeType = Node<GraphNodeData, 'intervention'>;

const ACCENT = '#f97316';

const truncateStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
};

export const InterventionNode = memo(function InterventionNode({ data, selected }: NodeProps<InterventionNodeType>) {
  return (
    <div
      data-testid="intervention-node"
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
          <span style={{ fontSize: 14, flexShrink: 0 }}>{'\u270B'}</span>
          <span
            style={{
              fontSize: 10,
              color: '#6b7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 600,
            }}
          >
            Intervention
          </span>
        </div>

        {/* User label if subAgentId or label differs */}
        {data.label && data.label !== data.content && (
          <div
            style={{
              fontSize: 11,
              color: ACCENT,
              fontWeight: 600,
              marginBottom: 4,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {data.label}
          </div>
        )}

        {/* Truncated message */}
        <div
          style={{
            fontSize: 12,
            color: '#d1d5db',
            lineHeight: '1.5',
            ...truncateStyle,
          }}
        >
          {data.content || '(empty)'}
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
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
