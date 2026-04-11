"""
配置管理模块
支持从环境变量和配置文件加载配置
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def load_dotenv(
    *paths: Union[str, Path],
    override: bool = False,
) -> List[Path]:
    """
    加载 .env 文件到环境变量。

    优先级：环境变量 > 后加载的 .env > 先加载的 .env

    Args:
        *paths: .env 文件路径列表，按优先级从低到高排列
        override: 是否覆盖已存在的环境变量

    Returns:
        成功加载的文件路径列表

    Example:
        >>> # 项目根 .env 优先级低，app .env 优先级高
        >>> load_dotenv(
        ...     get_project_root() / '.env',
        ...     Path(__file__).parent / '.env',
        ... )
    """
    loaded = []

    for path in paths:
        path = Path(path)
        if not path.exists():
            continue

        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 解析 key=value
                if '=' not in line:
                    continue

                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()

                # 移除引号
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                # 设置环境变量
                if key:
                    if override or key not in os.environ:
                        os.environ[key] = value

        loaded.append(path)

    return loaded


def load_config(
    config_file: Optional[Path] = None,
    env_prefix: str = "",
) -> Dict[str, Any]:
    """
    加载配置

    优先级：环境变量 > 配置文件 > 默认值

    Args:
        config_file: 配置文件路径（JSON 格式）
        env_prefix: 环境变量前缀

    Returns:
        配置字典

    Example:
        >>> config = load_config()
        >>> api_key = config.get("API_KEY")
    """
    config = {}

    # 从配置文件加载
    if config_file and config_file.exists():
        with open(config_file) as f:
            config.update(json.load(f))

    # 从环境变量加载（覆盖配置文件）
    for key, value in os.environ.items():
        if env_prefix and not key.startswith(env_prefix):
            continue

        # 移除前缀
        config_key = key[len(env_prefix):] if env_prefix else key
        config[config_key] = value

    return config


def get_env(
    key: str,
    default: Optional[str] = None,
    required: bool = False,
) -> Optional[str]:
    """
    获取环境变量
    
    Args:
        key: 环境变量名
        default: 默认值
        required: 是否必需
        
    Returns:
        环境变量值
        
    Raises:
        ValueError: 如果 required=True 且环境变量不存在
        
    Example:
        >>> api_key = get_env("API_KEY", required=True)
    """
    value = os.getenv(key, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    
    return value


def get_project_root() -> Path:
    """
    获取项目根目录
    
    Returns:
        项目根目录路径
    """
    # 从当前文件向上查找，直到找到包含 .git 的目录
    current = Path(__file__).resolve()
    
    for parent in current.parents:
        if (parent / ".git").exists():
            return parent
    
    # 如果找不到 .git，返回当前文件的上 4 级目录
    # tools/python/libs/common/config.py -> 项目根目录
    return current.parents[3]


# =============================================================================
# BaseAppSettings - 应用配置基类
# =============================================================================

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    
    class BaseAppSettings(BaseSettings):
        """
        应用配置基类，自动加载：
        1. 项目根目录 .env（低优先级）
        2. 环境变量（最高优先级）
        
        使用方法：
            class Settings(BaseAppSettings):
                '''App 专用配置'''
                my_app_port: int = 8080
                my_app_secret: str = ""
                
                model_config = SettingsConfigDict(
                    env_file=[
                        str(get_project_root() / ".env"),  # 继承根目录
                        ".env",                             # app 目录覆盖
                    ],
                    env_file_encoding="utf-8",
                    extra="ignore",
                )
        
        共享配置项（所有 app 可用）
        """
        # 项目配置
        environment: str = "development"
        log_level: str = "INFO"
        
        # 共享 API Keys
        openai_api_key: str = ""
        anthropic_api_key: str = ""

        # GitLab（多服务共享）
        gitlab_token: str = ""
        gitlab_api_base: str = "https://git.ringcentral.com/api/v4"
        
        model_config = SettingsConfigDict(
            env_file=str(get_project_root() / ".env"),
            env_file_encoding="utf-8",
            extra="ignore",
        )

except ImportError:
    # pydantic-settings 未安装时的 fallback
    BaseAppSettings = None  # type: ignore

