import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger():
    """配置全局日志"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "mysql_backup.log")

    logger = logging.getLogger("MySQLBackup")
    logger.setLevel(logging.INFO)

    # 文件日志 - 最大10MB，保留3个备份
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))

    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger