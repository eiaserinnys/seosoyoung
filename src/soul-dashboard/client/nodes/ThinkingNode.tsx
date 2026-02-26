/**
 * ThinkingNode - Claude의 중간 텍스트 출력 (사고/추론) 노드
 *
 * streaming 상태일 때 shimmer 애니메이션 오버레이를 표시합니다.
 * keyframes (node-shimmer, pulse)는 App.tsx globalStyles에 정의되어 있습니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type ThinkingNodeType = Node<GraphNodeData, 'thinking'>;

const ACCENT = '#8b5cf6';
const PLAN_ACCENT = '#06b6d4';

const truncateStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
};

export const ThinkingNode = memo(function ThinkingNode({ data, selected }: NodeProps<ThinkingNodeType>) {
  const isStreaming = data.streaming;
  const isPlanMode = data.isPlanMode;
  const accentColor = isPlanMode ? PLAN_ACCENT : ACCENT;

  return (
    <div
        data-testid="thinking-node"
        style={{
          width: 260,
          height: 84,
          boxSizing: 'border-box',
          background: isPlanMode
            ? 'rgba(6, 182, 212, 0.06)'
            : 'rgba(17, 24, 39, 0.95)',
          border: selected
            ? `1px solid ${accentColor}`
            : isPlanMode
              ? '1px solid rgba(6, 182, 212, 0.25)'
              : '1px solid rgba(255,255,255,0.1)',
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
          display: 'flex',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Left accent bar */}
        <div
          style={{
            width: 4,
            flexShrink: 0,
            background: accentColor,
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
            <span style={{ fontSize: 14, flexShrink: 0 }}>{'\u{1F4AD}'}</span>
            <span
              style={{
                fontSize: 10,
                color: isPlanMode ? PLAN_ACCENT : '#6b7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                fontWeight: 600,
              }}
            >
              Thinking
            </span>
            {isPlanMode && (
              <span
                style={{
                  fontSize: 9,
                  color: PLAN_ACCENT,
                  fontWeight: 500,
                  padding: '1px 5px',
                  borderRadius: 3,
                  backgroundColor: 'rgba(6, 182, 212, 0.12)',
                }}
              >
                PLAN
              </span>
            )}
            {isStreaming && (
              <span
                style={{
                  marginLeft: 'auto',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: accentColor,
                  animation: 'pulse 2s infinite',
                  flexShrink: 0,
                }}
              />
            )}
          </div>

          {/* Truncated content */}
          <div
            style={{
              fontSize: 12,
              color: '#9ca3af',
              lineHeight: '1.5',
              fontStyle: 'italic',
              ...truncateStyle,
            }}
          >
            {data.content || data.label || '(thinking...)'}
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
              background: isPlanMode
                ? 'linear-gradient(90deg, transparent 0%, rgba(6, 182, 212, 0.06) 50%, transparent 100%)'
                : 'linear-gradient(90deg, transparent 0%, rgba(139, 92, 246, 0.06) 50%, transparent 100%)',
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
            background: accentColor,
            border: '2px solid rgba(17, 24, 39, 0.95)',
          }}
        />
        <Handle
          type="source"
          position={Position.Bottom}
          style={{
            width: 8,
            height: 8,
            background: accentColor,
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
            background: accentColor,
            border: '2px solid rgba(17, 24, 39, 0.95)',
          }}
        />
      </div>
  );
});
