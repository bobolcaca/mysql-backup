import configparser
import glob
import json
import logging
import os
import os.path
from typing import List, Optional, Tuple, Union

from .schemas import DBConfig, BackupConfig, EmailConfig, SSHConfig, FullConfig, ProjectConfig

logger = logging.getLogger("MySQLBackup.Config")


class ConfigError(Exception):
    """配置加载异常"""
    pass


def resolve_project_root() -> str:
    """解析项目根目录路径"""
    current_file = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(current_file)))


def load_project_config() -> ProjectConfig:
    """加载项目配置文件（严格要求）"""
    config = configparser.ConfigParser()
    project_root = resolve_project_root()
    project_config_path = os.path.join(project_root, "config.ini")

    # 检查配置文件是否存在
    if not os.path.exists(project_config_path):
        raise ConfigError(f"项目配置文件不存在: {project_config_path}")

    try:
        config.read(project_config_path, encoding='utf-8')
    except Exception as e:
        raise ConfigError(f"读取项目配置文件失败: {str(e)}")

    try:
        # 备份配置
        if not config.has_section('backup'):
            raise ConfigError("项目配置文件缺少[backup]节")

        backup_section = config['backup']

        # 检查必须字段
        required_keys = ['mysql_bin_dir',
                         'days_to_keep', 'backup_time', 'report_time']
        for key in required_keys:
            if not backup_section.get(key):
                raise ConfigError(f"项目配置[backup]节缺少必须项: {key}")

        project_backup = BackupConfig(
            enabled=True,  # 项目备份总是启用
            backup_dir="",  # 业务自行指定
            days_to_keep=backup_section.getint('days_to_keep'),
            mysql_bin_dir=backup_section.get('mysql_bin_dir'),
            backup_time=backup_section.get('backup_time'),
            report_time=backup_section.get('report_time'),
            backup_root_path=backup_section.get('backup_root_path', '')
        )

        # 邮件配置
        project_email = None
        if config.has_section('email'):
            email_section = config['email']

            # 检查邮件配置完整性
            if email_section.getboolean('enabled', False):
                required_keys = ['smtp_server', 'smtp_user',
                                 'smtp_password', 'from_addr', 'to_addrs']
                for key in required_keys:
                    if not email_section.get(key):
                        raise ConfigError(f"项目邮件配置缺少必须项: {key}")

                def parse_list(val):
                    try:
                        return json.loads(val)
                    except Exception:
                        return [v.strip() for v in val.split(',') if v.strip()]

                project_email = EmailConfig(
                    enabled=True,
                    smtp_server=email_section.get('smtp_server'),
                    smtp_port=email_section.getint('smtp_port', 587),
                    smtp_user=email_section.get('smtp_user'),
                    smtp_password=email_section.get('smtp_password'),
                    sender_name=email_section.get('sender_name', 'MySQL备份系统'),
                    from_addr=email_section.get('from_addr'),
                    to_addrs=parse_list(email_section.get('to_addrs', '[]')),
                    copy_to=parse_list(email_section.get('copy_to', '[]')),
                    additional_to=parse_list(
                        email_section.get('additional_to', '[]'))
                )

        return ProjectConfig(
            backup=project_backup,
            email=project_email
        )

    except Exception as e:
        logger.critical(f"解析项目配置文件失败: {str(e)}")
        raise


def load_config(config_path: str, project_config: ProjectConfig) -> Optional[FullConfig]:
    """加载单个业务配置文件"""
    config = configparser.ConfigParser()

    try:
        config.read(config_path, encoding='utf-8')
    except Exception as e:
        logger.error(f"读取配置文件 {config_path} 失败: {str(e)}")
        return None

    try:
        # 关键修正：config_name 基于业务配置文件名（不含扩展名）
        config_name = os.path.splitext(os.path.basename(config_path))[0]

        # 数据库配置
        if not config.has_section('database'):
            raise ConfigError("缺少[database]配置节")

        database_section = config['database']
        database_config = DBConfig(
            host=database_section.get('host'),
            user=database_section.get('user'),
            port=database_section.getint('port', 3306),
            password=database_section.get('password'),
            defaults_file=database_section.get('defaults_file', None),
            database_names=database_section.get('database_names', '')
        )

        # 验证必须字段
        if not database_config.host or not database_config.user or not database_config.password:
            raise ConfigError("数据库配置缺少必须字段 (host/user/password)")

        # 备份配置
        if not config.has_section('backup'):
            raise ConfigError("缺少[backup]配置节")

        backup_section = config['backup']

        # 检查备份目录
        backup_dir = backup_section.get('backup_dir')
        if not backup_dir:
            raise ConfigError("必须指定备份目录 (backup_dir)")

        # 融合外层 backup_root_path，健壮处理路径
        project_root = resolve_project_root()
        backup_root_path = getattr(
            project_config.backup, 'backup_root_path', '')
        # 处理 ./ 和 / 前缀

        def clean_path(p):
            return p.lstrip('./\\/') if p else ''

        backup_root_path_clean = clean_path(backup_root_path)
        backup_dir_clean = clean_path(backup_dir)

        if backup_root_path:
            if os.path.isabs(backup_root_path):
                # 绝对路径，始终 backup_root_path + backup_dir_clean
                backup_dir = os.path.join(backup_root_path, backup_dir_clean)
            else:
                # 相对路径，以项目根为基准，始终 project_root + backup_root_path_clean + backup_dir_clean
                backup_dir = os.path.join(project_root, backup_root_path_clean, backup_dir_clean)
        else:
            # 没有 backup_root_path，直接以项目根为基准
            backup_dir = os.path.join(project_root, backup_dir_clean)
        backup_dir = os.path.abspath(backup_dir)
        logger.info(f"[{config_name}] 备份保存路径: {backup_dir}")

        backup_config = BackupConfig(
            enabled=backup_section.getboolean('enabled', True),
            backup_dir=backup_dir,
            days_to_keep=backup_section.getint(
                'days_to_keep', project_config.backup.days_to_keep),
            mysql_bin_dir=project_config.backup.mysql_bin_dir,
            backup_time=backup_section.get(
                'backup_time', project_config.backup.backup_time),
            report_time=backup_section.get(
                'report_time', project_config.backup.report_time)
        )

        # 邮件配置
        email_config = None
        if project_config.email:
            # 默认使用项目邮件配置
            email_config = project_config.email

            # 如果业务配置有email节，使用业务配置
            if config.has_section('email'):
                email_section = config['email']

                def parse_list(val):
                    try:
                        return json.loads(val)
                    except Exception:
                        return [v.strip() for v in val.split(',') if v.strip()]

                email_config = EmailConfig(
                    enabled=email_section.getboolean(
                        'enabled', project_config.email.enabled),
                    smtp_server=email_section.get(
                        'smtp_server', project_config.email.smtp_server),
                    smtp_port=email_section.getint(
                        'smtp_port', project_config.email.smtp_port),
                    smtp_user=email_section.get(
                        'smtp_user', project_config.email.smtp_user),
                    smtp_password=email_section.get(
                        'smtp_password', project_config.email.smtp_password),
                    sender_name=email_section.get(
                        'sender_name', project_config.email.sender_name),
                    from_addr=email_section.get(
                        'from_addr', project_config.email.from_addr),
                    to_addrs=parse_list(email_section.get(
                        'to_addrs', json.dumps(project_config.email.to_addrs))),
                    copy_to=parse_list(email_section.get(
                        'copy_to', json.dumps(project_config.email.copy_to))),
                    additional_to=parse_list(email_section.get(
                        'additional_to', json.dumps(project_config.email.additional_to)))
                )

        # SSH配置
        ssh_config = None
        if config.has_section('ssh') and config.getboolean('ssh', 'enabled', fallback=False):
            ssh_section = config['ssh']

            # 验证SSH配置
            required_keys = ['host', 'user']
            for key in required_keys:
                if not ssh_section.get(key):
                    raise ConfigError(f"SSH配置缺少必须项: {key}")

            if not (ssh_section.get('private_key') or ssh_section.get('password')):
                raise ConfigError("SSH配置需要密码或私钥")

            ssh_config = SSHConfig(
                enabled=True,
                host=ssh_section.get('host'),
                port=ssh_section.getint('port', 22),
                user=ssh_section.get('user'),
                private_key=ssh_section.get('private_key', None),
                password=ssh_section.get('password', None),
                local_bind_port=ssh_section.getint('local_bind_port', 3307),
                remote_bind_host=ssh_section.get(
                    'remote_bind_host', '127.0.0.1'),
                remote_bind_port=ssh_section.getint('remote_bind_port', 3306)
            )

        return FullConfig(
            config_path=config_path,
            config_name=config_name,  # 使用业务配置文件名
            database=database_config,
            backup=backup_config,
            email=email_config,
            ssh=ssh_config
        )

    except ConfigError as e:
        logger.error(f"业务配置错误 [{config_name}]: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"解析配置文件 {config_path} 失败: {str(e)}", exc_info=True)
        return None


def find_config_files(config_pattern: Optional[str] = None) -> List[str]:
    """查找业务配置文件"""
    project_root = resolve_project_root()
    config_dir = os.path.join(project_root, "backup_configs")

    if not os.path.exists(config_dir):
        logger.warning(f"业务配置文件目录不存在: {config_dir}")
        return []

    if config_pattern and ',' in config_pattern:
        config_files = [os.path.join(config_dir, f.strip())
                        for f in config_pattern.split(',')]
    else:
        pattern = config_pattern or "*.ini"
        config_files = glob.glob(os.path.join(config_dir, pattern))

    return [f for f in config_files if os.path.exists(f)]


def load_configs(config_pattern: Optional[str] = None) -> List[FullConfig]:
    """加载所有业务配置（整合项目配置）"""
    try:
        # 加载项目配置
        project_config = load_project_config()
        logger.info("成功加载项目配置")
    except ConfigError as e:
        logger.critical(f"无法加载项目配置: {str(e)}")
        return []

    # 加载业务配置
    config_files = find_config_files(config_pattern)
    if not config_files:
        logger.warning("未找到业务配置文件")
        return []

    configs = []
    for config_file in config_files:
        cfg = load_config(config_file, project_config)
        if cfg:
            configs.append(cfg)
            logger.info(f"成功加载业务配置: {cfg.config_name}")

    return configs
