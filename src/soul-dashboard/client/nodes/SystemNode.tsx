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
        width: 280,
        height: 40,
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

      {/* Content area (compact) */}
      <div
        style={{
          flex: 1,
          padding: '6px 10px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minWidth: 0,
        }}
      >
        <span style={{ fontSize: 12, flexShrink: 0 }}>{'\u2699\uFE0F'}</span>
        <span
          style={{
            fontSize: 11,
            color: isError ? '#fca5a5' : '#9ca3af',
            fontWeight: 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {data.label || 'system'}
        </span>
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
