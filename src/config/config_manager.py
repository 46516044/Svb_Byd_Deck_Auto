"""
配置管理器
负责配置的加载、验证和管理
"""

import copy
import json
import os
import logging
from typing import Dict, Any, Optional

from src.config.config_repository import ConfigRepository
from src.config.paths import get_config_path
from src.config.constants_manager import ConstantsManager
from src.config.io_guard import is_in_battle
from src.core.json_io import write_json_atomic

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器类"""

    def __init__(self, config_file: Optional[str] = None):
        # Default to a canonical config path (independent of CWD).
        self.config_file = os.path.abspath(config_file or get_config_path())
        self.repository = ConfigRepository(self.config_file)
        self.config = self._load_config()
        self.constants_manager = ConstantsManager(self.config)

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if is_in_battle():
            logger.warning("[IO] battle context: loading config from disk: %s", self.config_file)

        file_exists = os.path.exists(self.config_file)
        if not file_exists:
            logger.info(f"创建默认配置文件: {self.config_file}")

        loaded, parse_ok, err = self.repository.load_existing(allow_default_on_error=True)
        config = loaded if isinstance(loaded, dict) else {}

        if not file_exists:
            # Keep historical behavior: create config file on first run.
            save_res = self.repository.save(config, indent=2, ensure_ascii=False)
            if not save_res.ok:
                logger.error(f"保存配置文件失败: {save_res.error}")
            return config

        if not parse_ok:
            logger.error(f"加载配置文件失败: {str(err)}，使用默认配置")
            return config

        # If repository normalization/migrations changed the content, persist once.
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raw = {}
            if raw != config:
                save_res = self.repository.save(config, indent=2, ensure_ascii=False)
                if not save_res.ok:
                    logger.error(f"保存配置文件失败: {save_res.error}")
        except Exception:
            pass

        return config
    
    def _merge_configs(self, default_config: Dict[str, Any], user_config: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并配置"""
        # Treat defaults as immutable; avoid leaking nested references.
        merged: Dict[str, Any] = copy.deepcopy(default_config) if isinstance(default_config, dict) else {}

        if not isinstance(user_config, dict):
            return merged

        for key, value in user_config.items():
            if key in merged and isinstance(merged.get(key), dict) and isinstance(value, dict):
                merged[key] = self._merge_configs(merged[key], value)
            else:
                # Copy nested containers to avoid sharing references with caller data.
                if isinstance(value, (dict, list)):
                    merged[key] = copy.deepcopy(value)
                else:
                    merged[key] = value

        return merged
    
    def _save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置到文件"""
        res = self.repository.replace_with_snapshot(config, indent=2, ensure_ascii=False)
        if not res.ok:
            logger.error(f"保存配置文件失败: {str(res.error)}")
            return False

        if isinstance(config, dict):
            self.config = config
        return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置值"""
        keys = key.split('.')
        config = self.config
        
        # 导航到父级
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置值（字典采用深合并，避免覆盖/丢失隐藏字段）
        last_key = keys[-1]
        if isinstance(config.get(last_key), dict) and isinstance(value, dict):
            config[last_key] = self._merge_configs(config[last_key], value)
        else:
            config[last_key] = value
        return self._save_config(self.config)
    
    def get_devices(self) -> list[Dict[str, Any]]:
        """获取设备配置列表"""
        return self.config.get("devices", [])
    
    def get_device_by_serial(self, serial: str) -> Optional[Dict[str, Any]]:
        """根据序列号获取设备配置"""
        devices = self.get_devices()
        for device in devices:
            if device.get("serial") == serial:
                return device
        return None
    
    def add_device(self, device_config: Dict[str, Any]) -> bool:
        """添加设备配置"""
        devices = self.get_devices()
        devices.append(device_config)
        return self.set("devices", devices)
    
    def remove_device(self, serial: str) -> bool:
        """移除设备配置"""
        devices = self.get_devices()
        devices = [d for d in devices if d.get("serial") != serial]
        return self.set("devices", devices)
    
    def validate_config(self) -> bool:
        """验证配置的有效性"""
        try:
            # 验证设备配置
            devices = self.get_devices()
            if not devices:
                logger.error("配置文件中未找到设备列表")
                return False
            
            for device in devices:
                if not device.get("serial"):
                    logger.error("设备配置缺少serial字段")
                    return False
            
            # 验证游戏配置
            game_config = self.config.get("game", {})
            if not game_config.get("resolution"):
                logger.error("游戏配置缺少resolution字段")
                return False
            
            # 验证其他必要配置
            if not self.config.get("auto_restart"):
                logger.error("配置缺少auto_restart字段")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {str(e)}")
            return False
    
    def reload(self) -> bool:
        """重新加载配置"""
        try:
            self.config = self._load_config()
            return self.validate_config()
        except Exception as e:
            logger.error(f"重新加载配置失败: {str(e)}")
            return False
    
    def export_config(self, export_path: str) -> bool:
        """导出配置到指定路径"""
        try:
            if is_in_battle():
                logger.warning("[IO] battle context: exporting config to disk: %s", export_path)
            write_json_atomic(export_path, self.config, indent=2, ensure_ascii=False)
            logger.info(f"配置已导出到: {export_path}")
            return True
        except Exception as e:
            logger.error(f"导出配置失败: {str(e)}")
            return False
    
    def import_config(self, import_path: str) -> bool:
        """从指定路径导入配置"""
        try:
            if is_in_battle():
                logger.warning("[IO] battle context: importing config from disk: %s", import_path)
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)

            if not isinstance(imported_config, dict):
                imported_config = {}

            save_res = self.repository.replace_with_snapshot(
                imported_config,
                indent=2,
                ensure_ascii=False,
            )
            if not save_res.ok:
                logger.error(f"导入配置失败: {str(save_res.error)}")
                return False

            loaded, _parse_ok, _err = self.repository.load_existing(allow_default_on_error=True)
            self.config = loaded if isinstance(loaded, dict) else {}

            # 重新初始化常量管理器
            self.constants_manager = ConstantsManager(self.config)

            # 保存并验证
            if self.validate_config():
                logger.info(f"配置已从 {import_path} 导入")
                return True

            logger.error("导入的配置验证失败")
            return False

        except Exception as e:
            logger.error(f"导入配置失败: {str(e)}")
            return False
    
    def get_constants_manager(self) -> ConstantsManager:
        """获取常量管理器"""
        return self.constants_manager 

    def get_change_card_cost_threshold(self) -> int:
        """获取换牌费用阈值，默认3"""
        return self.get("change_card_cost_threshold", 3) 
