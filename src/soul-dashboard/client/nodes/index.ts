/**
 * Node Types - React Flow 노드 타입 레지스트리
 *
 * GraphNodeType별 커스텀 노드 컴포넌트를 매핑합니다.
 * ReactFlow의 nodeTypes prop에 직접 전달할 수 있습니다.
 */

import type { NodeTypes } from '@xyflow/react';

import { UserNode } from './UserNode';
import { ThinkingNode } from './ThinkingNode';
import { ToolCallNode } from './ToolCallNode';
import { ToolResultNode } from './ToolResultNode';
import { ToolGroupNode } from './ToolGroupNode';
import { ResponseNode } from './ResponseNode';
import { SystemNode } from './SystemNode';
import { InterventionNode } from './InterventionNode';

export const nodeTypes: NodeTypes = {
  user: UserNode,
  thinking: ThinkingNode,
  tool_call: ToolCallNode,
  tool_result: ToolResultNode,
  tool_group: ToolGroupNode,
  response: ResponseNode,
  system: SystemNode,
  intervention: InterventionNode,
};

export {
  UserNode,
  ThinkingNode,
  ToolCallNode,
  ToolResultNode,
  ToolGroupNode,
  ResponseNode,
  SystemNode,
  InterventionNode,
};
