from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "智能代码审查与漏洞修复系统"
    app_version: str = "0.1.0"
    debug: bool = True


settings = Settings()
