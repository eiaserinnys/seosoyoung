"""
Seosoyoung Soul - 공통 상수 정의

중복 방지를 위해 여러 모듈에서 사용하는 상수를 한 곳에 정의합니다.
"""

# 첨부 파일 최대 크기 (8MB)
MAX_ATTACHMENT_SIZE = 8 * 1024 * 1024

# 위험한 파일 확장자 목록 (민감한 정보가 포함될 수 있는 파일)
DANGEROUS_EXTENSIONS = [
    '.env',
    '.pem',
    '.key',
    '.crt',
    '.p12',
    '.pfx',
    '.jks',
]
