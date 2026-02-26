/**
 * ToolCallNode - 도구 호출 노드
 *
 * 도구 이름을 강조 표시하고, 입력 파라미터를 축약하여 보여줍니다.
 * streaming 상태(결과 대기 중)일 때 pulsing border를 표시합니다.
 * 플랜 모드 진입/종료 노드는 시안 계열로 시각적 구분됩니다.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { GraphNodeData } from '../lib/layout-engine';

type ToolCallNodeType = Node<GraphNodeData, 'tool_call'>;

const ACCENT = '#f59e0b';
const PLAN_ACCENT = '#06b6d4';

function truncateInput(input?: Record<string, unknown>): string {
  if (!input) return '';
  const str = JSON.stringify(input);
  if (str.length <= 80) return str;
  return str.slice(0, 77) + '...';
}

export const ToolCallNode = memo(function ToolCallNode({ data, selected }: NodeProps<ToolCallNodeType>) {
  const isStreaming = data.streaming;
  const isPlanEntry = data.isPlanModeEntry;
  const isPlanExit = data.isPlanModeExit;
  const isPlanMode = data.isPlanMode;

  // 플랜 모드 진입/종료 노드는 시안 계열로 시각적 구분
  const accentColor = (isPlanEntry || isPlanExit) ? PLAN_ACCENT : ACCENT;

  return (
    <div
        data-testid="tool-call-node"
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
            <span style={{ fontSize: 14, flexShrink: 0 }}>
              {isPlanEntry ? '\u{1F4CB}' : isPlanExit ? '\u{2705}' : '\u{1F527}'}
            </span>
            <span
              style={{
                fontSize: 10,
                color: (isPlanEntry || isPlanExit) ? PLAN_ACCENT : '#6b7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                fontWeight: 600,
              }}
            >
              {isPlanEntry ? 'Plan Mode' : isPlanExit ? 'Plan Exit' : 'Tool Call'}
            </span>
            {isStreaming && (
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 10,
                  color: accentColor,
                  fontWeight: 500,
                }}
              >
                running...
              </span>
            )}
            {isPlanMode && !isPlanEntry && !isPlanExit && (
              <span
                style={{
                  marginLeft: 'auto',
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

          {/* Truncated input params */}
          {data.toolInput && (
            <div
              style={{
                fontSize: 11,
                color: '#6b7280',
                fontFamily: "'Cascadia Code', 'Fira Code', monospace",
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {truncateInput(data.toolInput)}
            </div>
          )}
        </div>

        {/* Handles */}
        <Handle
          type="target"
          position={Position.Top}
          id="top"
          style={{
            width: 8,
            height: 8,
            background: accentColor,
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
            background: accentColor,
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
