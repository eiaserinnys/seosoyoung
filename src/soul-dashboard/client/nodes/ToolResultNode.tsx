/**
 * ToolResultNode - 도구 실행 결과 노드
 *
 * 성공(green) / 에러(red)에 따라 색상이 바뀝니다.
 * tool_call 노드의 right handle에서 이 노드의 left handle로 연결됩니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type ToolResultNodeType = Node<GraphNodeData, 'tool_result'>;

const COLOR_SUCCESS = '#22c55e';
const COLOR_ERROR = '#ef4444';

const truncateStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
};

export const ToolResultNode = memo(function ToolResultNode({ data, selected }: NodeProps<ToolResultNodeType>) {
  const isError = data.isError ?? false;
  const accent = isError ? COLOR_ERROR : COLOR_SUCCESS;
  const icon = isError ? '\u274C' : '\u2705';

  return (
    <div
      data-testid="tool-result-node"
      style={{
        width: 260,
        height: 84,
        boxSizing: 'border-box',
        background: 'rgba(17, 24, 39, 0.95)',
        border: selected
          ? `1px solid ${accent}`
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
          <span style={{ fontSize: 14, flexShrink: 0 }}>{icon}</span>
          <span
            style={{
              fontSize: 10,
              color: '#6b7280',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              fontWeight: 600,
            }}
          >
            {isError ? 'Error' : 'Result'}
          </span>
          {data.toolName && (
            <span
              style={{
                marginLeft: 'auto',
                fontSize: 10,
                color: '#4b5563',
                fontFamily: "'Cascadia Code', 'Fira Code', monospace",
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: 100,
              }}
            >
              {data.toolName}
            </span>
          )}
        </div>

        {/* Truncated result text */}
        <div
          style={{
            fontSize: 12,
            color: isError ? '#fca5a5' : '#9ca3af',
            lineHeight: '1.5',
            fontFamily: "'Cascadia Code', 'Fira Code', monospace",
            ...truncateStyle,
          }}
        >
          {data.toolResult || data.content || '(no result)'}
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        style={{
          width: 8,
          height: 8,
          background: accent,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          width: 8,
          height: 8,
          background: accent,
          border: '2px solid rgba(17, 24, 39, 0.95)',
        }}
      />
    </div>
  );
});
