"""번역 기능 CLI 테스트

사용법:
    python -m seosoyoung.slackbot.translator "번역할 텍스트"
    python -m seosoyoung.slackbot.translator -f en "Translate this to Korean"
    python -m seosoyoung.slackbot.translator --detect "자동 감지 테스트"
"""

import argparse
import json
import sys

from seosoyoung.slackbot.translator.detector import detect_language, Language
from seosoyoung.slackbot.translator.translator import translate
from seosoyoung.slackbot.translator.glossary import find_relevant_terms_v2


def main():
    parser = argparse.ArgumentParser(
        description="번역 기능 CLI 테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python -m seosoyoung.slackbot.translator "펜릭스는 악마사냥꾼이다"
  python -m seosoyoung.slackbot.translator -f en "Fenrix is a demon hunter"
  python -m seosoyoung.slackbot.translator --detect "자동 감지"
  python -m seosoyoung.slackbot.translator --glossary "아리엘라와 펜릭스"
        """
    )
    parser.add_argument("text", nargs="?", help="번역할 텍스트")
    parser.add_argument(
        "-f", "--from", dest="source_lang",
        choices=["ko", "en", "auto"],
        default="auto",
        help="원본 언어 (기본: auto)"
    )
    parser.add_argument(
        "--detect", action="store_true",
        help="언어 감지만 수행"
    )
    parser.add_argument(
        "--glossary", action="store_true",
        help="용어집 매칭만 수행"
    )
    parser.add_argument(
        "--model", default=None,
        help="사용할 모델 (기본: Config.translate.model)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="JSON 형식으로 출력"
    )

    args = parser.parse_args()

    if not args.text:
        parser.print_help()
        sys.exit(1)

    text = args.text

    # 언어 감지만
    if args.detect:
        lang = detect_language(text)
        if args.json:
            print(json.dumps({"language": lang.value}, ensure_ascii=False))
        else:
            print(f"감지된 언어: {lang.value}")
        return

    # 용어집 매칭만
    if args.glossary:
        # 먼저 언어 감지
        lang = detect_language(text)
        lang_code = "ko" if lang == Language.KOREAN else "en"
        result = find_relevant_terms_v2(text, lang_code)

        if args.json:
            print(json.dumps({
                "language": lang.value,
                "matched_terms": result.matched_terms,
                "stats": {
                    "candidates_checked": result.candidates_checked,
                    "fuzzy_matches": result.fuzzy_matches,
                }
            }, ensure_ascii=False, indent=2))
        else:
            print(f"감지된 언어: {lang.value}")
            if result.matched_terms:
                print(f"매칭된 용어 ({len(result.matched_terms)}개):")
                for src, tgt in result.matched_terms:
                    print(f"  {src} → {tgt}")
            else:
                print("매칭된 용어 없음")
        return

    # 번역 수행
    if args.source_lang == "auto":
        source_lang = detect_language(text)
    elif args.source_lang == "ko":
        source_lang = Language.KOREAN
    else:
        source_lang = Language.ENGLISH

    try:
        translated, cost, glossary_terms, match_result = translate(
            text,
            source_lang,
            model=args.model
        )

        if args.json:
            output = {
                "source_language": source_lang.value,
                "source_text": text,
                "translated_text": translated,
                "cost_usd": cost,
                "glossary_terms": glossary_terms,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            target_lang = "영어" if source_lang == Language.KOREAN else "한국어"
            print(f"원본 ({source_lang.value}): {text}")
            print(f"번역 ({target_lang}): {translated}")
            print(f"비용: ${cost:.6f}")
            if glossary_terms:
                print(f"참고 용어: {', '.join(f'{s}→{t}' for s, t in glossary_terms)}")

    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"번역 실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
