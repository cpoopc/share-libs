"""
日志工具模块
提供统一的日志配置
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    设置并返回一个配置好的 logger
    
    Args:
        name: Logger 名称（通常使用 __name__）
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径（可选）
        format_string: 自定义日志格式（可选）
        
    Returns:
        配置好的 Logger 实例
        
    Example:
        >>> logger = setup_logger(__name__)
        >>> logger.info("Application started")
    """
    # 获取或创建 logger
    logger = logging.getLogger(name)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 设置日志级别
    log_level = level or "INFO"
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 设置日志格式
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    formatter = logging.Formatter(format_string)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定）
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的 logger
    
    Args:
        name: Logger 名称
        
    Returns:
        Logger 实例
    """
    return logging.getLogger(name)

