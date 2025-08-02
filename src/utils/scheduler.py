import os
import sys
import logging
from .platform_utils import PlatformUtils

logger = logging.getLogger("MySQLBackup.Scheduler")

def create_scheduled_task(configs):
    """根据传入的业务配置对象列表创建计划任务（支持Windows/Linux）"""
    try:
        # 获取主脚本路径（main.py）
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, 'main.py')
        python_exe = sys.executable

        if not configs:
            logger.error("未找到任何有效业务配置")
            return

        is_windows = PlatformUtils.is_windows()
        platform_name = "Windows" if is_windows else "Linux"
        
        # 清理所有旧的计划任务
        logger.info(f"正在清理旧的{platform_name}计划任务...")
        PlatformUtils.clean_old_tasks()
        
        for cfg in configs:
            config_name = cfg.config_name
            config_path = cfg.config_path
            
            backup_time = getattr(cfg.backup, 'backup_time', None)
            check_time = getattr(cfg.backup, 'report_time', None)

            # 任务名唯一化
            task_name_backup = f"MySQLBackup_{config_name}"
            task_name_check = f"MySQLBackupCheck_{config_name}"

            # 创建备份任务
            if backup_time:
                backup_cmd = f'"{python_exe}" "{script_path}" --backup --config "{config_path}"'
                success, error = PlatformUtils.schedule_task(
                    task_name_backup, 
                    backup_time, 
                    backup_cmd
                )
                
                if success:
                    logger.info(f"[{platform_name}] 备份任务已创建: {task_name_backup} (每天 {backup_time})")
                else:
                    logger.error(f"[{platform_name}] 创建备份任务失败: {task_name_backup}, 错误: {error}")

            # 创建检查任务
            if check_time:
                check_cmd = f'"{python_exe}" "{script_path}" --check --config "{config_path}"'
                success, error = PlatformUtils.schedule_task(
                    task_name_check,
                    check_time,
                    check_cmd
                )
                
                if success:
                    logger.info(f"[{platform_name}] 检查任务已创建: {task_name_check} (每天 {check_time})")
                else:
                    logger.error(f"[{platform_name}] 创建检查任务失败: {task_name_check}, 错误: {error}")

        logger.info(f"所有业务配置的{platform_name}计划任务已处理完成！")

    except Exception as e:
        logger.error(f"创建计划任务时出错: {str(e)}")