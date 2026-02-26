/**
 * Soul Dashboard - Root App Component
 *
 * 글로벌 스타일(CSS 리셋, 애니메이션)을 주입하고 DashboardLayout을 렌더링합니다.
 */

import { DashboardLayout } from "./DashboardLayout";

/** 글로벌 CSS (리셋 + 애니메이션) */
const globalStyles = `
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    overflow: hidden;
    background: #111827;
  }

  /* Scrollbar */
  ::-webkit-scrollbar {
    width: 6px;
  }
  ::-webkit-scrollbar-track {
    background: transparent;
  }
  ::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.1);
    border-radius: 3px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: rgba(255,255,255,0.2);
  }

  /* Status indicator pulse animation */
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* Node graph shimmer animation (thinking/response nodes) */
  @keyframes node-shimmer {
    0% { background-position: -200px 0; }
    100% { background-position: 200px 0; }
  }

  /* Tool call pulsing border animation */
  @keyframes tool-call-pulse {
    0%, 100% { border-color: rgba(245, 158, 11, 0.3); }
    50% { border-color: rgba(245, 158, 11, 0.7); }
  }

  /* React Flow dark theme overrides */
  .react-flow__background {
    background-color: #111827 !important;
  }
  .react-flow__controls button {
    background: rgba(17, 24, 39, 0.95) !important;
    border-color: rgba(255,255,255,0.1) !important;
    color: #9ca3af !important;
    fill: #9ca3af !important;
  }
  .react-flow__controls button:hover {
    background: rgba(31, 41, 55, 0.95) !important;
  }
  .react-flow__edge-path {
    stroke: #4b5563 !important;
  }
  .react-flow__edge.animated .react-flow__edge-path {
    stroke: #3b82f6 !important;
  }
`;

export function App() {
  return (
    <>
      <style>{globalStyles}</style>
      <DashboardLayout />
    </>
  );
}
