#!/usr/bin/env python3
"""haniel.yaml -> cogito-manifest.yaml 자동 생성.

soulstream-server pre_start 훅으로 실행됨.
실행 cwd: D:/haniel-root/soulstream/
"""
import os
import sys
import yaml
from pathlib import Path


def parse_port(ready) -> int | None:
    s = str(ready) if ready is not None else ""
    if s.startswith("port:"):
        try:
            return int(s.split(":")[1])
        except (IndexError, ValueError):
            return None
    return None


def main() -> None:
    haniel_yaml = Path(os.environ.get("HANIEL_YAML_PATH", "../haniel.yaml"))
    output = Path(os.environ.get("COGITO_MANIFEST_OUTPUT", "./cogito-manifest.yaml"))

    if not haniel_yaml.exists():
        print(f"ERROR: haniel.yaml not found: {haniel_yaml.resolve()}", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(haniel_yaml.read_text(encoding="utf-8"))
    services = config.get("services", {})

    entries = []
    for name, svc in services.items():
        if not svc.get("reflect"):
            continue
        port = parse_port(svc.get("ready"))
        if port is None:
            print(f"WARNING: '{name}' has reflect:true but no port ready check, skipping", file=sys.stderr)
            continue
        entries.append({
            "name": name,
            "type": "internal",
            "endpoint": f"http://localhost:{port}/reflect",
        })

    manifest = {"services": entries}
    output.write_text(
        yaml.dump(manifest, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"cogito manifest: {output.resolve()} ({len(entries)} services)")


if __name__ == "__main__":
    main()
