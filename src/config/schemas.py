from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DBConfig:
    host: str
    user: str
    port: int
    password: str
    defaults_file: Optional[str]
    database_names: str

@dataclass
class BackupConfig:
    enabled: bool
    backup_dir: str
    days_to_keep: int
    mysql_bin_dir: str
    backup_time: str
    report_time: str
    backup_root_path: str = ''

@dataclass
class EmailConfig:
    enabled: bool
    smtp_server: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    sender_name: str
    from_addr: str
    to_addrs: List[str]
    copy_to: List[str]
    additional_to: List[str]

@dataclass
class SSHConfig:
    enabled: bool
    host: str
    port: int
    user: str
    private_key: Optional[str]
    password: Optional[str]
    local_bind_port: int
    remote_bind_host: str
    remote_bind_port: int

@dataclass
class FullConfig:
    config_path: str
    config_name: str
    database: DBConfig
    backup: BackupConfig
    email: EmailConfig
    ssh: Optional[SSHConfig]

# 简化项目配置类
@dataclass
class ProjectConfig:
    backup: BackupConfig
    email: EmailConfig