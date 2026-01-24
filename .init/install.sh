#!/bin/sh
# Git hooks 설치 스크립트
# 사용법: .init/install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_SRC="$SCRIPT_DIR/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

echo "Git hooks 설치 중..."

# hooks 폴더의 모든 파일 복사
for hook in "$HOOKS_SRC"/*; do
    if [ -f "$hook" ]; then
        hook_name=$(basename "$hook")
        cp "$hook" "$HOOKS_DST/$hook_name"
        chmod +x "$HOOKS_DST/$hook_name"
        echo "  설치됨: $hook_name"
    fi
done

echo "완료."
