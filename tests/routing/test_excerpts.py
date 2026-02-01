"""발췌 부분 테스트"""
import asyncio
import os
from anthropic import AsyncAnthropic
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 프로젝트 루트 추가
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.routing.loader import ToolLoader
from seosoyoung.routing.evaluator import ToolEvaluator


async def main():
    api_key = os.environ.get("RECALL_API_KEY")
    if not api_key:
        print("❌ RECALL_API_KEY 환경변수가 설정되지 않았습니다")
        return

    # slackbot_workspace 경로
    workspace_path = Path(__file__).parent.parent.parent.parent
    print(f"🗂️  워크스페이스: {workspace_path}")
    loader = ToolLoader(workspace_path)
    tools = loader.load_all()

    print(f"✅ 도구 로드 완료: {len(tools)}개")

    # lore 에이전트만 선택
    lore_tool = next((t for t in tools if t.name == "lore"), None)
    if not lore_tool:
        print("❌ lore 에이전트를 찾을 수 없습니다")
        return

    print(f"\n📋 도구: {lore_tool.name}")
    print(f"📄 본문 길이: {len(lore_tool.body)} 자")

    client = AsyncAnthropic(api_key=api_key)
    evaluator = ToolEvaluator(client)

    user_request = "펜릭스가 천사에 대해 언급하는 대사를 찾아줘"
    print(f"\n💬 사용자 요청: {user_request}")
    print("\n⏳ 평가 중...")

    result = await evaluator.evaluate_tool(lore_tool, user_request)

    print(f"\n✨ 결과:")
    print(f"  점수: {result.score}/10")
    print(f"\n  📌 발췌 부분:")
    if result.reason:
        for line in result.reason.split("\n"):
            if line.strip():
                print(f"    {line}")
    else:
        print("    (없음)")
    print(f"\n  🎯 접근 방식:")
    print(f"    {result.approach}")


if __name__ == "__main__":
    asyncio.run(main())
