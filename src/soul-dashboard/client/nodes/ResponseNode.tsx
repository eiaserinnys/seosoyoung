/**
 * ResponseNode - Claude의 최종 응답 노드
 *
 * Thinking 노드보다 약간 더 크고 눈에 띄는 디자인입니다.
 * 실행 흐름의 종단점으로 상단 target handle만 갖습니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type ResponseNodeType = Node<GraphNodeData, 'response'>;

const ACCENT = '#10b981';

const truncateStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
};

export const ResponseNode = memo(function ResponseNode({ data, selected }: NodeProps<ResponseNodeType>) {
  const isStreaming = data.streaming;

  return (
    <div
        data-testid="response-node"
        style={{
          width: 260,
          height: 84,
          boxSizing: 'border-box',
          background: 'rgba(17, 24, 39, 0.95)',
          border: selected
            ? `1px solid ${ACCENT}`
            : `1px solid rgba(16, 185, 129, 0.25)`,
          borderRadius: 8,
          boxShadow: `0 2px 12px rgba(0,0,0,0.5), 0 0 0 ${selected ? '1px' : '0px'} ${ACCENT}44`,
          display: 'flex',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Left accent bar (wider for emphasis) */}
        <div
          style={{
            width: 5,
            flexShrink: 0,
            background: ACCENT,
            borderRadius: '8px 0 0 8px',
          }}
        />

        {/* Content area */}
        <div style={{ flex: 1, padding: '12px 14px', minWidth: 0 }}>
          {/* Header row */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 14, flexShrink: 0 }}>{'\u{1F4AC}'}</span>
            <span
              style={{
                fontSize: 10,
                color: ACCENT,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                fontWeight: 700,
              }}
            >
              Response
            </span>
            {isStreaming && (
              <span
                style={{
                  marginLeft: 'auto',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: ACCENT,
                  animation: 'pulse 2s infinite',
                  flexShrink: 0,
                }}
              />
            )}
          </div>

          {/* Truncated content (3 lines for response) */}
          <div
            style={{
              fontSize: 12,
              color: '#d1d5db',
              lineHeight: '1.6',
              ...truncateStyle,
            }}
          >
            {data.content || data.label || '(empty response)'}
          </div>
        </div>

        {/* Shimmer overlay when streaming */}
        {isStreaming && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 8,
              pointerEvents: 'none',
              background:
                'linear-gradient(90deg, transparent 0%, rgba(16, 185, 129, 0.06) 50%, transparent 100%)',
              backgroundSize: '200px 100%',
              animation: 'node-shimmer 1.5s infinite linear',
            }}
          />
        )}

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
