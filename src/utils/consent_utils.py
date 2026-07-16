"""
用户同意工具模块
处理免责声明和用户同意
"""

import json
import os
import logging

from src.config.paths import get_app_root, get_config_path
from src.config.settings import DISCLAIMER, DISCLAIMER_VERSION
from src.core.json_io import write_json_atomic, write_text_atomic

logger = logging.getLogger(__name__)
_session_consent = False


def _read_consent_version(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("免责声明版本="):
                    return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return 0


def check_consent_file() -> bool:
    """
    检查是否存在同意文件
    
    返回：
        bool: 是否已同意
    """
    if _session_consent:
        return True

    # 1）优先读取界面与 CLI 共用的配置标记。
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            if bool(config_data.get("agreed_to_disclaimer", False)) and int(
                config_data.get("disclaimer_version", 0) or 0
            ) == DISCLAIMER_VERSION:
                return True
    except Exception:
        pass

    # 2）其次读取应用根目录下、不依赖当前工作目录的同意文件。
    try:
        consent_path = os.path.join(get_app_root(), "consent.txt")
        if _read_consent_version(consent_path) == DISCLAIMER_VERSION:
            return True
    except Exception:
        pass

    # 3）为兼容旧版本，最后检查当前工作目录中的同意文件。
    return _read_consent_version("consent.txt") == DISCLAIMER_VERSION


def save_consent(*, persist_to_config: bool = True) -> bool:
    """
    保存用户同意状态到文件
    
    返回：
        bool: 是否保存成功
    """
    accept_consent_for_session()
    try:
        consent_path = os.path.join(get_app_root(), "consent.txt")
        write_text_atomic(
            consent_path,
            f"免责声明版本={DISCLAIMER_VERSION}\n用户已阅读并同意免责声明\n",
            encoding="utf-8",
        )

        if persist_to_config:
            try:
                config_path = get_config_path()
                config_data = {}
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as cf:
                            config_data = json.load(cf)
                    except Exception:
                        # 配置可能已经损坏，此时不得覆盖原文件。
                        config_data = None

                if isinstance(config_data, dict):
                    config_data["agreed_to_disclaimer"] = True
                    config_data["disclaimer_version"] = DISCLAIMER_VERSION
                    write_json_atomic(config_path, config_data, indent=4, ensure_ascii=False)
            except Exception:
                # 同意文件已足够生效，配置持久化仅作尽力处理。
                pass

        return True
    except Exception as e:
        logger.error(f"保存同意状态失败: {str(e)}")
        return False


def accept_consent_for_session() -> None:
    """仅在当前进程中记录同意，关闭程序后自动失效。"""

    global _session_consent
    _session_consent = True


def display_disclaimer_and_get_consent() -> bool:
    """
    显示免责声明并获取用户同意
    
    返回：
        bool: 用户是否同意
    """
    # 清屏
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # 显示声明
    print(DISCLAIMER)
    print("\n" + "=" * 80)
    
    # 检查是否已同意
    if check_consent_file():
        print("\n您已同意免责声明，程序继续运行...")
        return True
    
    # 获取用户同意
    while True:
        try:
            response = input(
                "\n请仔细阅读以上声明，输入'同意'表示您已理解并接受所有条款: "
            ).strip()
        except EOFError:
            # pythonw 或打包界面等非交互环境不读取标准输入。
            return False
        
        if response == "同意":
            if save_consent(persist_to_config=True):
                print("\n感谢您的同意，现在可以正常使用本软件。")
                return True
            else:
                print("\n保存同意状态失败，请检查文件权限。")
        else:
            print("\n您必须同意免责声明才能使用本软件。")
            print("输入'退出'将关闭程序，或重新输入'同意'继续使用。")
            
            if response == "退出":
                print("\n您已选择退出程序。")
                return False


def remove_consent() -> bool:
    """
    移除用户同意文件（用于重新获取同意）
    
    返回：
        bool: 是否移除成功
    """
    global _session_consent
    _session_consent = False
    success = True
    try:
        consent_path = os.path.join(get_app_root(), "consent.txt")
        if os.path.exists(consent_path):
            try:
                os.remove(consent_path)
            except Exception:
                success = False

        # 为兼容旧版本，同时删除当前工作目录中的旧同意文件。
        if os.path.exists("consent.txt"):
            try:
                os.remove("consent.txt")
            except Exception:
                success = False

        # 尽力清除配置中的同意标记。
        try:
            config_path = get_config_path()
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                if isinstance(config_data, dict) and (
                    "agreed_to_disclaimer" in config_data
                    or "disclaimer_version" in config_data
                ):
                    config_data.pop("agreed_to_disclaimer", None)
                    config_data.pop("disclaimer_version", None)
                    write_json_atomic(config_path, config_data, indent=4, ensure_ascii=False)
        except Exception:
            success = False

        if success:
            logger.info("已移除用户持久化同意状态")
        else:
            logger.warning("用户持久化同意状态未完全移除")
        return success
    except Exception as e:
        logger.error(f"移除同意文件失败: {str(e)}")
        return False 
