import socket
import logging
from sshtunnel import SSHTunnelForwarder

from ..config.schemas import SSHConfig

logger = logging.getLogger("MySQLBackup.SSH")

def check_ssh_connectivity(host: str, port: int) -> bool:
    """检查SSH服务器可达性"""
    try:
        with socket.create_connection((host, port), timeout=10):
            return True
    except Exception as e:
        logger.error(f"无法连接到SSH服务器 {host}:{port} - {str(e)}")
        return False

def setup_ssh_tunnel(ssh_config: SSHConfig):
    """使用sshtunnel建立SSH隧道"""
    try:
        # 创建SSH隧道
        tunnel = SSHTunnelForwarder(
            ssh_address_or_host=(ssh_config.host, ssh_config.port),
            ssh_username=ssh_config.user,
            ssh_pkey=ssh_config.private_key if ssh_config.private_key else None,
            ssh_password=ssh_config.password or None,
            remote_bind_address=(
                ssh_config.remote_bind_host, ssh_config.remote_bind_port),
            local_bind_address=('127.0.0.1', ssh_config.local_bind_port)
        )

        # 启动隧道
        tunnel.start()
        logger.info(f"SSH隧道已建立: 127.0.0.1:{ssh_config.local_bind_port} -> "
                   f"{ssh_config.host}:{ssh_config.port} -> "
                   f"{ssh_config.remote_bind_host}:{ssh_config.remote_bind_port}")
        return tunnel
    except Exception as e:
        logger.error(f"隧道建立失败: {str(e)}", exc_info=True)
        return None