/**
 * UserNode - 사용자 입력/프롬프트 노드
 *
 * 사용자가 보낸 메시지를 표시합니다.
 * 실행 흐름의 시작점으로 하단 source handle만 갖습니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type UserNodeType = Node<GraphNodeData, 'user'>;

const ACCENT = '#3b82f6';

const truncateStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
};

export const UserNode = memo(function UserNode({ data, selected }: NodeProps<UserNodeType>) {
  return (
    <div
      data-testid="user-node"
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
          {/* Avatar circle */}
          <div
            style={{
              width: 20,
              height: 20,
              borderRadius: '50%',
              background: `${ACCENT}33`,
              border: `1px solid ${ACCENT}66`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              flexShrink: 0,
            }}
          >
            {'\u{1F464}'}
          </div>
          <span
            style={{
              fontSize: 10,
              color: '#6b7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 600,
            }}
          >
            User
          </span>
        </div>

        {/* Truncated content */}
        <div
          style={{
            fontSize: 12,
            color: '#d1d5db',
            lineHeight: '1.5',
            ...truncateStyle,
          }}
        >
          {data.content || data.label || '(empty)'}
        </div>
      </div>

      {/* Bottom source handle */}
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
