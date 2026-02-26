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
`;

export function App() {
  return (
    <>
      <style>{globalStyles}</style>
      <DashboardLayout />
    </>
  );
}
