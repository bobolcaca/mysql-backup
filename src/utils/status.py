# utils/status.py
import os
import json
import datetime
import threading
from typing import Optional, Dict, Any, List

status_lock = threading.Lock()

def get_status_file_path(config_name: str) -> str:
    """获取特定配置的状态文件路径"""
    return os.path.join(os.environ.get('APPDATA', ''), "MySQLBackup", f"backup_status_{config_name}.json")

def save_backup_status(
    config_name: str,
    success: bool,
    message: str,
    backup_file: Optional[str] = None,
    skipped_tables: Optional[List[str]] = None,
    retry_errors: Optional[List[str]] = None,
    running: Optional[bool] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    mail_sent_time: Optional[str] = None
):
    """保存特定配置的备份状态，支持扩展字段"""
    with status_lock:
        status_file = get_status_file_path(config_name)
        status_data = {
            'config_name': config_name,
            'last_run': datetime.datetime.now().isoformat(),
            'success': success,
            'message': message,
            'backup_file': backup_file,
            'skipped_tables': skipped_tables or [],
            'retry_errors': retry_errors or []
        }
        # 扩展字段
        if running is not None:
            status_data['running'] = running
        if start_time is not None:
            status_data['start_time'] = start_time
        if end_time is not None:
            status_data['end_time'] = end_time
        if mail_sent_time is not None:
            status_data['mail_sent_time'] = mail_sent_time

        os.makedirs(os.path.dirname(status_file), exist_ok=True)
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

def load_backup_status(config_name: str) -> Optional[Dict[str, Any]]:
    """加载特定配置的备份状态，兼容扩展字段"""
    status_file = get_status_file_path(config_name)
    if not os.path.exists(status_file):
        return None

    try:
        with open(status_file, 'r') as f:
            data = json.load(f)
            # 兼容旧格式
            if 'skipped_tables' not in data:
                data['skipped_tables'] = []
            if 'retry_errors' not in data:
                data['retry_errors'] = []
            # 新增字段
            if 'running' not in data:
                data['running'] = False
            if 'start_time' not in data:
                data['start_time'] = None
            if 'end_time' not in data:
                data['end_time'] = None
            if 'mail_sent_time' not in data:
                data['mail_sent_time'] = None
            return data
    except:
        return None