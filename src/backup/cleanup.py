import os
import datetime
import logging

from ..config.schemas import FullConfig

logger = logging.getLogger("MySQLBackup.Cleanup")

def clean_old_backups_for_config(config: FullConfig):
    """为单个配置清理旧备份"""
    try:
        # 计算过期时间点
        retention_date = datetime.datetime.now(
        ) - datetime.timedelta(days=config.backup.days_to_keep)

        deleted_files = []
        # 遍历备份目录
        for filename in os.listdir(config.backup.backup_dir):
            if not filename.startswith(f"backup_{config.config_name}") or not filename.endswith(".sql.gz"):
                continue

            filepath = os.path.join(config.backup.backup_dir, filename)
            file_time = datetime.datetime.fromtimestamp(
                os.path.getctime(filepath))

            # 删除过期备份
            if file_time < retention_date:
                try:
                    os.remove(filepath)
                    deleted_files.append(filename)
                    logger.info(f"[{config.config_name}] 已删除过期备份: {filename}")
                except Exception as e:
                    logger.error(
                        f"[{config.config_name}] 删除文件 {filename} 失败: {str(e)}")

        return deleted_files

    except Exception as e:
        logger.error(f"[{config.config_name}] 清理旧备份时出错: {str(e)}")
        return []