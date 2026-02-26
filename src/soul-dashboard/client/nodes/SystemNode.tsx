/**
 * SystemNode - 시스템 이벤트 노드
 *
 * 세션 시작, 완료, 오류 등 시스템 레벨 이벤트를 표시합니다.
 * 다른 노드보다 작고 컴팩트한 디자인입니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type SystemNodeType = Node<GraphNodeData, 'system'>;

const COLOR_NORMAL = '#6b7280';
const COLOR_ERROR = '#ef4444';

export const SystemNode = memo(function SystemNode({ data, selected }: NodeProps<SystemNodeType>) {
  const isError = data.isError ?? false;
  const accent = isError ? COLOR_ERROR : COLOR_NORMAL;

  return (
    <div
      data-testid="system-node"
      style={{
        width: 260,
        height: 84,
        boxSizing: 'border-box',
        background: 'rgba(17, 24, 39, 0.95)',
        border: selected
          ? `1px solid ${accent}`
          : '1px solid rgba(255,255,255,0.07)',
        borderRadius: 8,
        boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
        display: 'flex',
        overflow: 'hidden',
      }}
    >
      {/* Left accent bar */}
      <div
        style={{
          width: 3,
          flexShrink: 0,
          background: accent,
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
          <span style={{ fontSize: 14, flexShrink: 0 }}>{'\u2699\uFE0F'}</span>
          <span
            style={{
              fontSize: 10,
              color: isError ? COLOR_ERROR : '#6b7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 600,
            }}
          >
            {data.label || 'System'}
          </span>
        </div>

        {/* Content text */}
        <div
          style={{
            fontSize: 12,
            color: isError ? '#fca5a5' : '#9ca3af',
            lineHeight: '1.5',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
          }}
        >
          {data.content || ''}
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        style={{
          width: 6,
          height: 6,
          background: accent,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          width: 6,
          height: 6,
          background: accent,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
    </div>
  );
});
