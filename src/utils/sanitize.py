import re

def sanitize_command(cmd_list: list, debug_mode: bool = False) -> list:
    """脱敏命令中的敏感信息"""
    if debug_mode:
        return cmd_list  # 调试模式下不脱敏

    def mask_middle(s):  # 保留前2后3
        return f"{s[:2]}***{s[-3:]}" if len(s) > 5 else "***"

    SENSITIVE_RULES = {
        "--password=": lambda _: "***",
        "--defaults-file=": lambda _: "***",
        "--user=": mask_middle,
        "--host=": mask_middle,
    }

    sanitized = []
    for item in cmd_list:
        for prefix, rule in SENSITIVE_RULES.items():
            if item.startswith(prefix):
                item = prefix + rule(item[len(prefix):])
                break
        sanitized.append(item)
    return sanitized