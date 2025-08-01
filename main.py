#!/usr/bin/env python3
import argparse
import concurrent.futures
import logging
import sys

from src.config.loader import load_configs
from src.utils.logger import setup_logger
from src.utils.scheduler import create_windows_task
from src.backup.core import process_config
from src.backup.recovery import (
    perform_recovery, 
    select_config_interactive, 
    select_backup_interactive, 
    list_available_backups
)

logger = logging.getLogger("MySQLBackup")


def main():
    parser = argparse.ArgumentParser(description='MySQL自动备份脚本 (Windows版)')
    parser.add_argument('--backup', action='store_true', help='执行备份操作')
    parser.add_argument('--check', action='store_true', help='检查备份状态并发送警报')
    parser.add_argument('--schedule', action='store_true',
                        help='创建Windows计划任务（需要管理员权限）')
    parser.add_argument('--recovery', action='store_true', help='交互式恢复数据库备份')
    parser.add_argument('--debug', action='store_true',
                        help='调试模式，显示完整命令（不脱敏）')
    parser.add_argument('--config', type=str, default=None,
                        help='指定配置文件模式(如 "backup_configs/*.ini" 或逗号分隔列表)')
    args = parser.parse_args()

    # 初始化日志
    setup_logger()

    # 加载所有配置
    configs = load_configs(args.config)
    if not configs:
        logger.error("没有有效的配置，退出")
        sys.exit(1)

    # debug 模式下关闭邮件发送
    if args.debug:
        for cfg in configs:
            if cfg.email:
                cfg.email.enabled = False

    # 计划任务创建功能
    if args.schedule:
        create_windows_task(configs)
        return

    # 数据库恢复功能
    if args.recovery:
        try:
            # 交互式选择配置
            selected_config = select_config_interactive(configs)
            if not selected_config:
                logger.info("已取消恢复操作")
                return

            # 列出该配置的所有可用备份
            available_backups = list_available_backups(selected_config)
            if not available_backups:
                logger.error(f"[{selected_config.config_name}] 未找到可用的备份文件")
                sys.exit(1)

            # 交互式选择备份文件
            selected_backup = select_backup_interactive(available_backups)
            if not selected_backup:
                logger.info("已取消恢复操作")
                return

            # 执行恢复操作
            success = perform_recovery(selected_config, selected_backup, args)
            if not success:
                sys.exit(1)
            return
            
        except KeyboardInterrupt:
            print("\n操作已取消")
            return

    # 使用线程池并行处理配置
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(configs))) as executor:
        futures = {executor.submit(
            process_config, cfg, args): cfg for cfg in configs}

        # 等待所有任务完成
        for future in concurrent.futures.as_completed(futures):
            cfg = futures[future]
            try:
                result = future.result()
                if result:
                    logger.info(f"[{cfg.config_name}] 任务完成: {result}")
                else:
                    logger.info(f"[{cfg.config_name}] 任务完成")
            except Exception as e:
                logger.error(
                    f"[{cfg.config_name}] 任务执行出错: {str(e)}", exc_info=True)

    logger.info("所有配置处理完成")


if __name__ == "__main__":
    main()
