import subprocess
import os
import sys
import logging

logger = logging.getLogger("MySQLBackup.Scheduler")

def create_windows_task(configs):
    """根据传入的业务配置对象列表创建/更新/删除Windows计划任务"""
    try:
        # 获取主脚本路径（main.py）
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script_path = os.path.join(project_root, 'main.py')
        python_exe = sys.executable
        if not configs:
            logger.error("未找到任何有效业务配置")
            return

        for cfg in configs:
            config_name = cfg.config_name
            config_path = cfg.config_path

            backup_time = getattr(cfg.backup, 'backup_time', None)
            check_time = getattr(cfg.backup, 'report_time', None)

            # 任务名唯一化
            task_name_backup = f"MySQLBackup_{config_name}"
            task_name_check = f"MySQLBackupCheck_{config_name}"

            # 删除旧任务（如果存在）
            for tn in [task_name_backup, task_name_check]:
                try:
                    subprocess.run([
                        'schtasks', '/Delete', '/TN', tn, '/F'
                    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

            # 创建备份任务
            if backup_time:
                backup_cmd = f'"{python_exe}" "{script_path}" --backup --config "{config_path}"'
                try:
                    subprocess.run([
                        'schtasks', '/Create', '/TN', task_name_backup, '/SC', 'DAILY', '/ST', backup_time,
                        '/TR', backup_cmd, '/RL', 'HIGHEST', '/F'
                    ], check=True)
                    logger.info(f"备份任务已创建: {task_name_backup} (每天 {backup_time})")
                except subprocess.CalledProcessError as e:
                    logger.error(f"创建备份任务失败: {task_name_backup}, 错误: {str(e)}")

            # 仅在有 check_time 时创建检查任务
            if check_time:
                check_cmd = f'"{python_exe}" "{script_path}" --check --config "{config_path}"'
                try:
                    subprocess.run([
                        'schtasks', '/Create', '/TN', task_name_check, '/SC', 'DAILY', '/ST', check_time,
                        '/TR', check_cmd, '/RL', 'HIGHEST', '/F'
                    ], check=True)
                    logger.info(f"检查任务已创建: {task_name_check} (每天 {check_time})")
                except subprocess.CalledProcessError as e:
                    logger.error(f"创建检查任务失败: {task_name_check}, 错误: {str(e)}")

        logger.info("所有业务配置的计划任务已处理完成！")

    except Exception as e:
        logger.error(f"创建计划任务时出错: {str(e)}")