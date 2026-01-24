#!/usr/bin/env python3
"""코드베이스 자동 문서 생성기

Python AST를 사용하여 소스 코드에서 함수, 클래스, docstring을 추출하고
계층적 문서 인덱스를 생성합니다.

사용법:
    python .docs/generate.py
"""

import ast
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FunctionInfo:
    """함수 정보"""
    name: str
    lineno: int
    docstring: Optional[str]
    args: list[str]
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """클래스 정보"""
    name: str
    lineno: int
    docstring: Optional[str]
    methods: list[FunctionInfo] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """모듈 정보"""
    path: Path
    relative_path: str
    docstring: Optional[str]
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


class CodebaseAnalyzer:
    """코드베이스 분석기"""

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.modules: list[ModuleInfo] = []

    def analyze(self) -> list[ModuleInfo]:
        """소스 디렉토리의 모든 Python 파일 분석"""
        for py_file in sorted(self.src_dir.rglob("*.py")):
            # __pycache__ 무시
            if "__pycache__" in str(py_file):
                continue

            try:
                module_info = self._analyze_file(py_file)
                if module_info:
                    self.modules.append(module_info)
            except SyntaxError as e:
                print(f"구문 오류: {py_file}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"분석 오류: {py_file}: {e}", file=sys.stderr)

        return self.modules

    def _analyze_file(self, filepath: Path) -> Optional[ModuleInfo]:
        """단일 파일 분석"""
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(filepath))

        # 모듈 docstring
        docstring = ast.get_docstring(tree)

        # 상대 경로 계산
        try:
            relative_path = filepath.relative_to(self.src_dir.parent)
        except ValueError:
            relative_path = filepath

        module_info = ModuleInfo(
            path=filepath,
            relative_path=str(relative_path).replace("\\", "/"),
            docstring=docstring,
        )

        # 최상위 요소 분석
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._analyze_function(node)
                module_info.functions.append(func_info)

            elif isinstance(node, ast.ClassDef):
                class_info = self._analyze_class(node)
                module_info.classes.append(class_info)

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                module_info.imports.extend(self._analyze_import(node))

        return module_info

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        """함수 분석"""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)

        decorators = []
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name):
                decorators.append(deco.id)
            elif isinstance(deco, ast.Attribute):
                decorators.append(f"{self._get_attr_name(deco)}")
            elif isinstance(deco, ast.Call):
                if isinstance(deco.func, ast.Name):
                    decorators.append(deco.func.id)
                elif isinstance(deco.func, ast.Attribute):
                    decorators.append(self._get_attr_name(deco.func))

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            docstring=ast.get_docstring(node),
            args=args,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
        )

    def _analyze_class(self, node: ast.ClassDef) -> ClassInfo:
        """클래스 분석"""
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attr_name(base))

        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._analyze_function(item))

        return ClassInfo(
            name=node.name,
            lineno=node.lineno,
            docstring=ast.get_docstring(node),
            methods=methods,
            bases=bases,
        )

    def _analyze_import(self, node: ast.Import | ast.ImportFrom) -> list[str]:
        """import 분석"""
        imports = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)
        return imports

    def _get_attr_name(self, node: ast.Attribute) -> str:
        """속성 이름 추출"""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))


class DocumentGenerator:
    """문서 생성기"""

    def __init__(self, modules: list[ModuleInfo], output_dir: Path):
        self.modules = modules
        self.output_dir = output_dir
        self.modules_dir = output_dir / "modules"

    def generate(self):
        """모든 문서 생성"""
        self.modules_dir.mkdir(parents=True, exist_ok=True)

        # INDEX.md 생성
        self._generate_index()

        # 모듈별 상세 문서 생성
        for module in self.modules:
            self._generate_module_doc(module)

        print(f"문서 생성 완료: {len(self.modules)}개 모듈")

    def _generate_index(self):
        """INDEX.md 생성"""
        lines = [
            "# seosoyoung 코드 인덱스",
            "",
            "> 이 문서는 자동 생성되었습니다. 직접 수정하지 마세요.",
            "> 생성 명령: `python .docs/generate.py`",
            "",
            "## 모듈 목록",
            "",
        ]

        # 모듈별 한줄 요약
        for module in self.modules:
            # __init__.py는 패키지 표시
            if module.path.name == "__init__.py":
                continue

            # 상대 경로에서 모듈 이름 추출
            module_name = module.path.stem
            parent_pkg = module.path.parent.name

            # docstring 첫 줄 추출
            summary = ""
            if module.docstring:
                summary = module.docstring.split("\n")[0].strip()

            # 상세 문서 링크
            detail_link = f"modules/{parent_pkg}_{module_name}.md"

            lines.append(f"- [`{parent_pkg}/{module_name}.py`]({detail_link}): {summary}")

        lines.append("")
        lines.append("## 빠른 참조")
        lines.append("")

        # 주요 클래스 목록
        lines.append("### 주요 클래스")
        lines.append("")
        for module in self.modules:
            for cls in module.classes:
                if cls.name.startswith("_"):
                    continue
                desc = cls.docstring.split("\n")[0].strip() if cls.docstring else ""
                lines.append(f"- `{cls.name}` ({module.relative_path}:{cls.lineno}): {desc}")

        lines.append("")
        lines.append("### 주요 함수")
        lines.append("")
        for module in self.modules:
            for func in module.functions:
                if func.name.startswith("_"):
                    continue
                desc = func.docstring.split("\n")[0].strip() if func.docstring else ""
                async_mark = "async " if func.is_async else ""
                lines.append(f"- `{async_mark}{func.name}()` ({module.relative_path}:{func.lineno}): {desc}")

        # 파일 작성
        index_path = self.output_dir / "INDEX.md"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"생성: {index_path}")

    def _generate_module_doc(self, module: ModuleInfo) -> None:
        """모듈 상세 문서 생성"""
        if module.path.name == "__init__.py":
            return

        module_name = module.path.stem
        parent_pkg = module.path.parent.name

        lines = [
            f"# {parent_pkg}/{module_name}.py",
            "",
            f"> 경로: `{module.relative_path}`",
            "",
        ]

        # 모듈 docstring
        if module.docstring:
            lines.append("## 개요")
            lines.append("")
            lines.append(module.docstring)
            lines.append("")

        # 클래스
        if module.classes:
            lines.append("## 클래스")
            lines.append("")
            for cls in module.classes:
                bases_str = f" ({', '.join(cls.bases)})" if cls.bases else ""
                lines.append(f"### `{cls.name}`{bases_str}")
                lines.append(f"- 위치: 줄 {cls.lineno}")
                if cls.docstring:
                    lines.append(f"- 설명: {cls.docstring}")
                lines.append("")

                if cls.methods:
                    lines.append("#### 메서드")
                    lines.append("")
                    for method in cls.methods:
                        async_mark = "async " if method.is_async else ""
                        args_str = ", ".join(method.args)
                        desc = method.docstring.split("\n")[0].strip() if method.docstring else ""
                        lines.append(f"- `{async_mark}{method.name}({args_str})` (줄 {method.lineno}): {desc}")
                    lines.append("")

        # 함수
        if module.functions:
            lines.append("## 함수")
            lines.append("")
            for func in module.functions:
                async_mark = "async " if func.is_async else ""
                args_str = ", ".join(func.args)
                lines.append(f"### `{async_mark}{func.name}({args_str})`")
                lines.append(f"- 위치: 줄 {func.lineno}")
                if func.decorators:
                    lines.append(f"- 데코레이터: {', '.join(func.decorators)}")
                if func.docstring:
                    lines.append(f"- 설명: {func.docstring}")
                lines.append("")

        # 의존성 (내부 모듈만)
        internal_imports = [imp for imp in module.imports if imp.startswith("seosoyoung")]
        if internal_imports:
            lines.append("## 내부 의존성")
            lines.append("")
            for imp in sorted(set(internal_imports)):
                lines.append(f"- `{imp}`")
            lines.append("")

        # 파일 작성
        doc_path = self.modules_dir / f"{parent_pkg}_{module_name}.md"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def main():
    """메인 함수"""
    # 스크립트 위치 기준으로 경로 설정
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    src_dir = project_root / "src" / "seosoyoung"
    output_dir = script_dir  # .docs 폴더

    if not src_dir.exists():
        print(f"소스 디렉토리를 찾을 수 없습니다: {src_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"분석 대상: {src_dir}")
    print(f"출력 위치: {output_dir}")
    print()

    # 분석
    analyzer = CodebaseAnalyzer(src_dir)
    modules = analyzer.analyze()

    print(f"분석 완료: {len(modules)}개 모듈")
    print()

    # 문서 생성
    generator = DocumentGenerator(modules, output_dir)
    generator.generate()


if __name__ == "__main__":
    main()
