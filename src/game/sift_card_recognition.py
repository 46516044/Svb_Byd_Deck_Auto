"""
SIFT卡牌识别模块
基于SIFT特征匹配识别手牌区域中的卡牌及其费用
"""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportMissingTypeArgument=false

import cv2
import numpy as np
import os
import logging
import threading
from typing import Any, List, Tuple, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.resource_utils import resource_path
from src.utils.card_filename import normalize_card_base_name, parse_card_stem

logger = logging.getLogger(__name__)

SUPPORTED_CARD_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

# Shared template cache (read-only) across instances/devices.
_TEMPLATE_CACHE: Dict[Tuple[str, float, str], Dict[str, Dict[str, Any]]] = {}
_TEMPLATE_CACHE_LOCK = threading.Lock()


def _template_dir_signature(card_images_dir: str) -> str:
    """Build a lightweight signature for cache invalidation."""

    try:
        if not os.path.isdir(card_images_dir):
            return "missing"

        parts: List[str] = []
        for filename in sorted(os.listdir(card_images_dir)):
            if not str(filename or "").lower().endswith(SUPPORTED_CARD_IMAGE_EXTENSIONS):
                continue
            path = os.path.join(card_images_dir, filename)
            try:
                st = os.stat(path)
                parts.append(f"{filename.lower()}:{int(st.st_size)}:{int(st.st_mtime_ns)}")
            except Exception:
                parts.append(f"{filename.lower()}:na")

        return "|".join(parts)
    except Exception:
        return "unknown"


def _build_card_templates(*, card_images_dir: str, scale_factor: float) -> Dict[str, Dict[str, Any]]:
    """Load card templates from disk and compute SIFT features.

    Returned mapping is intended to be treated as read-only.
    """

    templates: Dict[str, Dict[str, Any]] = {}

    if not os.path.exists(card_images_dir):
        logger.error(f"卡牌图片目录不存在: {card_images_dir}")
        return templates

    sift = cv2.SIFT_create()

    card_files: List[str] = []
    for filename in os.listdir(card_images_dir):
        if filename.lower().endswith(SUPPORTED_CARD_IMAGE_EXTENSIONS):
            card_files.append(os.path.join(card_images_dir, filename))

    logger.info(f"找到 {len(card_files)} 个卡牌模板文件")

    for card_file in card_files:
        try:
            filename = os.path.basename(card_file)
            name_without_ext = os.path.splitext(filename)[0]

            if "_" not in name_without_ext:
                logger.warning(f"文件名格式不正确: {filename}")
                continue

            cost, enhance_costs, card_name = parse_card_stem(name_without_ext)
            if not card_name:
                logger.warning(f"文件名解析失败(缺少卡名): {filename}")
                continue
            card_name = normalize_card_base_name(card_name)
            if not card_name:
                logger.warning(f"文件名解析失败(卡名归一化为空): {filename}")
                continue

            from PIL import Image

            with Image.open(card_file) as pil_image:
                if pil_image.mode not in ("RGB", "RGBA"):
                    pil_image = pil_image.convert("RGBA")
                template = np.array(pil_image)

            if template is None:
                logger.warning(f"无法读取图片: {card_file}")
                continue
            if template.dtype != np.uint8:
                template = template.astype(np.uint8, copy=False)

            if template.ndim == 2:
                template = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            elif template.ndim == 3:
                ch = template.shape[2]
                if ch == 4:
                    template = cv2.cvtColor(template, cv2.COLOR_RGBA2BGR)
                elif ch == 3:
                    template = cv2.cvtColor(template, cv2.COLOR_RGB2BGR)
                elif ch == 1:
                    template = cv2.cvtColor(template[:, :, 0], cv2.COLOR_GRAY2BGR)
                else:
                    logger.warning(f"图片通道数异常({ch})，跳过: {card_file}")
                    continue
            else:
                logger.warning(f"图片维度异常({template.ndim})，跳过: {card_file}")
                continue

            height, width = template.shape[:2]
            new_height = int(height * float(scale_factor))
            new_width = int(width * float(scale_factor))
            if new_height <= 0 or new_width <= 0:
                logger.warning(f"图片尺寸过小，缩放后为0，跳过: {card_file}")
                continue

            scaled_template = cv2.resize(template, (new_width, new_height))
            scaled_template_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)

            keypoints, descriptors = sift.detectAndCompute(scaled_template_gray, None)
            if descriptors is None:
                continue

            templates[name_without_ext] = {
                "cost": cost,
                "name": card_name,
                "enhance_costs": list(enhance_costs or []),
                "template": scaled_template,
                "keypoints": keypoints,
                "descriptors": descriptors,
            }
            logger.debug(f"加载卡牌模板: {name_without_ext} (费用: {cost})")

        except Exception as e:
            logger.error(f"处理文件 {card_file} 时出错: {str(e)}")
            continue

    logger.info(f"成功加载 {len(templates)} 张卡牌模板")
    return templates


def _get_shared_card_templates(*, card_images_dir: str, scale_factor: float) -> Dict[str, Dict[str, Any]]:
    key = (
        os.path.abspath(card_images_dir),
        float(scale_factor),
        _template_dir_signature(card_images_dir),
    )
    with _TEMPLATE_CACHE_LOCK:
        cached = _TEMPLATE_CACHE.get(key)
        if cached is not None:
            return cached

        templates = _build_card_templates(card_images_dir=card_images_dir, scale_factor=scale_factor)
        _TEMPLATE_CACHE[key] = templates
        return templates


class SiftCardRecognition:
    """SIFT卡牌识别类"""
    
    def __init__(self, card_images_dir: str = "card_cost"):
        """
        初始化SIFT卡牌识别器
        
        Args:
            card_images_dir: 卡牌图片目录路径
        """
        self.card_images_dir = card_images_dir
        # Backward compatible: prefer CWD-relative path if it exists, otherwise
        # resolve relative to app root (source/PyInstaller).
        if (
            self.card_images_dir
            and not os.path.isabs(self.card_images_dir)
            and not os.path.exists(self.card_images_dir)
        ):
            self.card_images_dir = resource_path(self.card_images_dir)
        try:
            if self.card_images_dir:
                os.makedirs(self.card_images_dir, exist_ok=True)
        except Exception:
            pass
        self.card_templates = {}  # 缓存卡牌模板
        self.sift = cv2.SIFT_create()
        # 恢复到 d5d10c5 的识别参数（更稳，减少误识别/漏识别）
        self.scale_factor = 0.3  # 缩放因子（匹配游戏中卡牌的实际大小）
        self.hand_area = (229, 539, 1130, 710)  # 手牌区域 (x1, y1, x2, y2) - 更新为新坐标
        self.min_matches = 4  # 最小匹配点数
        self.match_threshold = 0.01  # 匹配阈值

        # Use a shared, read-only template cache.
        self.card_templates = _get_shared_card_templates(
            card_images_dir=self.card_images_dir,
            scale_factor=self.scale_factor,
        )
    
    def recognize_hand_cards(
        self,
        screenshot,
        *,
        hand_area: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[Dict]:
        """
        识别手牌区域中的卡牌（支持同名卡牌多张识别，支持多模板并发SIFT加速）
        """
        try:
            # 转换为OpenCV格式
            if hasattr(screenshot, 'shape'):
                image = screenshot
            else:
                image = np.array(screenshot)
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            # Accept explicit hand_area; never mutate instance state.
            area = self.hand_area
            if isinstance(hand_area, (list, tuple)) and len(hand_area) == 4:
                try:
                    area = (
                        int(hand_area[0]),
                        int(hand_area[1]),
                        int(hand_area[2]),
                        int(hand_area[3]),
                    )
                except Exception:
                    area = self.hand_area

            x1, y1, x2, y2 = area
            hand_region = image[y1:y2, x1:x2]
            
            # 转换为灰度图像进行SIFT特征提取
            hand_region_gray = cv2.cvtColor(hand_region, cv2.COLOR_BGR2GRAY)
            hand_keypoints, hand_descriptors = self.sift.detectAndCompute(hand_region_gray, None)
            if hand_descriptors is None:
                logger.warning("手牌区域未检测到SIFT特征")
                return []
            logger.debug(f"手牌区域SIFT特征点数: {len(hand_keypoints)}")

            def match_and_cluster(template_name, template_info):
                recognized_cards = []
                template_descriptors = template_info['descriptors']
                FLANN_INDEX_KDTREE = 1
                index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
                search_params = dict(checks=50)
                flann = cv2.FlannBasedMatcher(index_params, search_params)
                try:
                    matches = flann.knnMatch(template_descriptors, hand_descriptors, k=2)
                except Exception as e:
                    logger.debug(f"模板 {template_name} 匹配失败: {str(e)}")
                    return []
                good_matches = []
                for match_pair in matches:
                    if len(match_pair) == 2:
                        m, n = match_pair
                        if m.distance < 0.7 * n.distance:
                            good_matches.append(m)
                if len(good_matches) >= self.min_matches:
                    dst_pts = np.float32([hand_keypoints[m.trainIdx].pt for m in good_matches])
                    clusters = []
                    cluster_indices = []
                    # 根据区域动态调整聚类阈值
                    region_width = x2 - x1
                    if region_width > 700:  # 换牌区域（789px）
                        distance_thresh = 100  # d5d10c5: 更紧的聚类阈值
                    else:  # 战斗手牌区域（901px）
                        distance_thresh = 80
                    for i, pt in enumerate(dst_pts):
                        found = False
                        for cidx, c in enumerate(clusters):
                            if np.linalg.norm(pt - c) < distance_thresh:
                                cluster_indices[cidx].append(i)
                                clusters[cidx] = (clusters[cidx] * (len(cluster_indices[cidx])-1) + pt) / len(cluster_indices[cidx])
                                found = True
                                break
                        if not found:
                            clusters.append(pt.copy())
                            cluster_indices.append([i])
                    for idx_list in cluster_indices:
                        if len(idx_list) < 4:  # findHomography至少需要4个点
                            continue
                        cluster_good_matches = [good_matches[i] for i in idx_list]
                        src_pts = np.float32([template_info['keypoints'][m.queryIdx].pt for m in cluster_good_matches]).reshape(-1, 1, 2)
                        dst_pts_c = np.float32([hand_keypoints[m.trainIdx].pt for m in cluster_good_matches]).reshape(-1, 1, 2)
                        M, mask = cv2.findHomography(src_pts, dst_pts_c, cv2.RANSAC, 5.0)
                        # 优化Homography检查：确保有足够的内点
                        if M is not None:
                            inliers = mask.ravel().tolist()
                            inlier_count = sum(inliers)
                            if inlier_count < self.min_matches:
                                continue
                            h, w = template_info['template'].shape[:2]
                            template_center = np.array([w / 2.0, h / 2.0, 1.0], dtype=np.float64)
                            proj = np.dot(M, template_center)

                            # 检查除零和无效值（兼容 NumPy 2.x，避免数组直接转 int）
                            if proj.shape[0] < 3 or not np.isfinite(proj).all():
                                continue

                            z = float(proj[2])
                            if abs(z) < 1e-8:
                                continue

                            tx = float(proj[0]) / z
                            ty = float(proj[1]) / z
                            if (not np.isfinite(tx)) or (not np.isfinite(ty)):
                                continue

                            global_x = int(round(tx)) + x1
                            global_y = int(round(ty)) + y1
                            avg_distance = np.mean([m.distance for m in cluster_good_matches])
                            if avg_distance <= 100:
                                distance_score = 1.0
                            elif avg_distance <= 200:
                                distance_score = 1.0 - (avg_distance - 100) / 100
                            else:
                                distance_score = max(0, 1.0 - (avg_distance - 200) / 100)
                            match_ratio = len(cluster_good_matches) / len(template_descriptors)
                            confidence = distance_score * match_ratio
                            if confidence >= self.match_threshold:
                                recognized_cards.append({
                                    'center': (global_x, global_y),
                                    'cost': template_info['cost'],
                                    'name': template_info['name'],
                                    'enhance_costs': list(template_info.get('enhance_costs') or []),
                                    'confidence': confidence,
                                    'template_name': template_name
                                })
                                logger.debug(f"识别到卡牌: {template_name} (费用: {template_info['cost']}, 置信度: {confidence:.3f})")
                return recognized_cards

            # 动态获取可用核心数，优先8核
            try:
                max_workers = min(8, os.cpu_count() or 4)
            except Exception:
                max_workers = 4
            recognized_cards = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for template_name, template_info in self.card_templates.items():
                    futures.append(executor.submit(match_and_cluster, template_name, template_info))
                for future in as_completed(futures):
                    try:
                        recognized_cards.extend(future.result())
                    except Exception as e:
                        logger.error(f"SIFT并发识别任务异常: {str(e)}")
            # --- 位置去重（NMS）：同一张实体卡可能匹配到多个模板，按置信度保留最优 ---
            # 以中心点距离阈值进行抑制，优先保留置信度高的候选。
            recognized_cards.sort(key=lambda c: c.get('confidence', 0), reverse=True)
            final_cards: List[Dict] = []
            for card in recognized_cards:
                cx, cy = card.get('center', (None, None))
                if cx is None or cy is None:
                    continue

                too_close = False
                for kept in final_cards:
                    kx, ky = kept.get('center', (0, 0))
                    dx = cx - kx
                    dy = cy - ky
                    if dx * dx + dy * dy < 1600:  # 40px 内认为是同一张
                        too_close = True
                        break

                if not too_close:
                    final_cards.append(card)

            # 再做一次同名去重（极少数情况下同名双卡会靠得很近）
            dedup_by_name: List[Dict] = []
            for card in final_cards:
                too_close_same_name = False
                for kept in dedup_by_name:
                    if card.get('name') != kept.get('name'):
                        continue
                    dx = card['center'][0] - kept['center'][0]
                    dy = card['center'][1] - kept['center'][1]
                    if dx * dx + dy * dy < 1600:
                        too_close_same_name = True
                        break
                if not too_close_same_name:
                    dedup_by_name.append(card)

            dedup_by_name.sort(key=lambda card: card['center'][0])
            return dedup_by_name
        except Exception as e:
            logger.error(f"SIFT卡牌识别出错: {str(e)}")
            return []
    
    def get_card_cost_by_name(self, card_name: str) -> Optional[int]:
        """
        根据卡牌名称获取费用
        
        Args:
            card_name: 卡牌名称
            
        Returns:
            Optional[int]: 卡牌费用，如果未找到返回None
        """
        for template_name, template_info in self.card_templates.items():
            if template_info['name'] == card_name:
                return template_info['cost']
        return None
    
    def get_all_card_names(self) -> List[str]:
        """
        获取所有卡牌名称
        
        Returns:
            List[str]: 所有卡牌名称列表
        """
        return [template_info['name'] for template_info in self.card_templates.values()]
    
    def get_all_card_costs(self) -> Dict[str, int]:
        """
        获取所有卡牌的费用映射
        
        Returns:
            Dict[str, int]: 卡牌名称到费用的映射
        """
        return {template_info['name']: template_info['cost'] 
                for template_info in self.card_templates.values()} 
