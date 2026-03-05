"""
游戏管理器
实现核心游戏逻辑和操作
"""

import cv2
import numpy as np
import random
import time
import logging
import os
import onnxruntime as ort
from src.game.follower_manager import FollowerManager
from src.game.template_manager import TemplateManager
from src.game.game_actions import GameActions
from src.game.state_machine import GameStateMachine
from src.utils.gpu_utils import get_easyocr_reader
from src.utils.resource_utils import resource_path
from src.utils.card_filename import parse_card_stem
from src.utils.hp_detection import (
    detect_hp_in_window,
    sliding_window_detect,
    merge_detections,
    recognize_hp_with_fallback,
)
from src.utils.mnist_preprocessor import MNISTPreprocessor
from src.config.game_constants import (
    ENEMY_HP_REGION,
    ENEMY_HP_REGION_UP,
    ENEMY_HP_HSV,
    ENEMY_FOLLOWER_Y_ADJUST,
    ENEMY_FOLLOWER_Y_RANDOM,
    OUR_FOLLOWER_REGION,
    OUR_ATK_REGION,
    OUR_FOLLOWER_HSV,
    ENEMY_HP_REGION_OFFSET_X,
    ENEMY_HP_REGION_OFFSET_Y,
    ENEMY_FOLLOWER_OFFSET_X,
    ENEMY_FOLLOWER_OFFSET_Y,
    ENEMY_ATK_REGION,
    OCR_CROP_HALF_SIZE,
    ENEMY_SHIELD_REGION,
    ENEMY_ATK_HSV,
    HP_WINDOW_WIDTH,
    HP_WINDOW_HEIGHT,
    HP_SLIDE_STEP,
    HP_MIN_FOLLOWER_GAP,
    HP_MAX_FOLLOWERS,
    HP_RED_BG_THRESHOLD,
    HP_OTHER_THRESHOLD,
    HP_DIGIT_THRESHOLD,
    HP_BRIGHT_RED_V_THRESHOLD,
)

logger = logging.getLogger(__name__)


class GameManager:
    """游戏管理器类"""

    def __init__(self, device_state):
        self.device_state = device_state
        self.follower_manager = FollowerManager()
        # 传递设备配置给模板管理器
        self.template_manager = TemplateManager(device_state.device_config)
        self.game_actions = GameActions(device_state)
        self.state_machine = GameStateMachine()
        self.reader = get_easyocr_reader()

        # 加载MNIST模型用于HP识别的后备方案
        self.mnist_session = None
        self.logger = logger
        mnist_path = "models/mnist_adv.onnx"
        if not os.path.exists(mnist_path):
            mnist_path = resource_path(mnist_path)
        if os.path.exists(mnist_path):
            try:
                self.mnist_session = ort.InferenceSession(mnist_path, providers=["CPUExecutionProvider"])
                logger.info(f"MNIST模型已加载: {mnist_path}")
            except Exception as e:
                logger.warning(f"加载MNIST模型失败: {e}，将仅使用EasyOCR")
        else:
            logger.warning(f"未找到MNIST模型: {mnist_path}，将仅使用EasyOCR")

        # 加载HP检测遮罩（内部资源，不作为用户可编辑模板的一部分）
        self.hp_mask = None
        mask_candidates = [
            resource_path(os.path.join("src", "masks", "hp_mask.png")),
            # Backward compatibility (older layouts might ship it under templates).
            self.template_manager.get_template_path("hp_mask.png"),
        ]

        mask_path = ""
        for p in mask_candidates:
            if p and os.path.exists(p):
                mask_path = p
                break

        if mask_path:
            self.hp_mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            if self.hp_mask is not None:
                logger.info(f"HP遮罩已加载: {mask_path}, 尺寸: {self.hp_mask.shape}")
            else:
                logger.warning(f"HP遮罩文件读取失败: {mask_path}，将不使用遮罩")
        else:
            logger.warning("未找到HP遮罩文件，将不使用遮罩")

        # 创建MNIST预处理器用于HP识别
        self.hp_preprocessor = MNISTPreprocessor(
            target_size=(28, 28),
            intermediate_size=(128, 128),
            margin=0,
            remove_brown_edges=True,
            denoise_strength=2,
            dilation_iterations=2,
            detect_double_digit=True,
            split_threshold=10,
            bright_red_v_threshold=HP_BRIGHT_RED_V_THRESHOLD,
            red_erosion_iterations=0,
            red_edge_margin=0,
            green_erosion_iterations=1,
            green_edge_margin=0
        )
        logger.info("HP识别预处理器已初始化")

        # 设置设备状态中的随从管理器
        device_state.follower_manager = self.follower_manager

    def scan_enemy_ATK(self, screenshot, debug_flag=False):
        """扫描敌方攻击力数值位置，返回敌方随从位置列表"""
        enemy_atk_positions = []

        # 确保debug目录存在
        if debug_flag:
            os.makedirs("debug", exist_ok=True)

        region_blue = screenshot.crop(ENEMY_ATK_REGION)
        region_blue_np = np.array(region_blue)
        region_blue_cv = cv2.cvtColor(region_blue_np, cv2.COLOR_RGB2BGR)
        hsv_blue = cv2.cvtColor(region_blue_cv, cv2.COLOR_BGR2HSV)
        settings = ENEMY_ATK_HSV
        lower_blue = np.array(settings["blue"][:3])
        upper_blue = np.array(settings["blue"][3:])
        blue_mask = cv2.inRange(hsv_blue, lower_blue, upper_blue)

        kernel = np.ones((1, 1), np.uint8)
        blue_eroded = cv2.erode(
            cv2.dilate(blue_mask, kernel, iterations=1), kernel, iterations=1
        )
        blue_contours, _ = cv2.findContours(
            blue_eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # 创建用于调试的图像
        if debug_flag:
            debug_img = region_blue_cv.copy()

        for cnt in blue_contours:
            rect = cv2.minAreaRect(cnt)
            (x, y), (w, h), angle = rect
            area = cv2.contourArea(cnt)
            max_dim = max(w, h)
            min_dim = min(w, h)
            center_x, center_y = rect[0]

            if 15 < max_dim < 40 and 3 < min_dim < 15 and area < 200:
                # 区域截图中敌方随从的中心位置
                in_card_center_x_full = center_x + 50
                in_card_center_y_full = center_y - 46
                # 全局中敌方随从中心位置
                center_x_full = in_card_center_x_full + 263
                center_y_full = in_card_center_y_full + 297

                # 添加到结果列表
                enemy_atk_positions.append((center_x_full, 227 + random.randint(-5, 5)))

                # Debug 标注
                if debug_flag:
                    # 画中心点
                    cv2.circle(
                        debug_img, (int(center_x), int(center_y)), 5, (0, 0, 255), -1
                    )
                    # 画外接矩形
                    box = cv2.boxPoints(rect).astype(int)
                    cv2.drawContours(debug_img, [box], 0, (0, 255, 0), 2)
                    # 添加标注文字
                    label = f"W:{w:.1f} H:{h:.1f} Area:{area:.0f}"
                    cv2.putText(
                        debug_img,
                        label,
                        (int(center_x), int(center_y)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 0, 0),
                        1,
                    )

        # 保存debug图像
        if debug_flag:
            timestamp = int(time.time() * 1000)
            cv2.imwrite(f"debug/enemy_ATK_debug_{timestamp}.png", debug_img)
            cv2.imwrite(f"debug/enemy_ATK_mask_{timestamp}.png", blue_eroded)

        return enemy_atk_positions

    def scan_enemy_followers(self, screenshot, debug_flag=False, is_select=False):
        """
        检测场上的敌方随从位置与血量 (Improved with sliding window + fallback recognition)

        Returns:
            List[Tuple[int, int, str, str]]: [(x, y, "normal", hp_value), ...]
            - x, y: Screen coordinates (calibrated)
            - "normal": Follower type (always "normal" for compatibility)
            - hp_value: HP as string (e.g., "5", "99")
        """
        timestamp = int(time.time() * 1000)
        HP_REGION = ENEMY_HP_REGION
        if is_select:
            HP_REGION = ENEMY_HP_REGION_UP
        try:
            # 确保debug目录存在
            if debug_flag:
                os.makedirs("debug", exist_ok=True)
                screenshot_np = np.array(screenshot)
                screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
                cv2.imwrite(f"debug/screenshot_{timestamp}.png", screenshot_cv)

            # Step 1: Crop enemy HP region
            x1, y1, x2, y2 = HP_REGION
            region = screenshot.crop(HP_REGION)
            region_np = np.array(region)
            region_cv = cv2.cvtColor(region_np, cv2.COLOR_RGB2BGR)

            # Step 2: Sliding window detection with color analysis
            detections_raw = sliding_window_detect(
                region_cv,
                self.hp_mask,
                window_width=HP_WINDOW_WIDTH,
                window_height=HP_WINDOW_HEIGHT,
                slide_step=HP_SLIDE_STEP,
                red_bg_threshold=HP_RED_BG_THRESHOLD,
                other_threshold=HP_OTHER_THRESHOLD,
                digit_threshold=HP_DIGIT_THRESHOLD,
                bright_red_v_threshold=HP_BRIGHT_RED_V_THRESHOLD
            )

            # Step 3: Merge overlapping detections
            detections = merge_detections(
                detections_raw,
                min_gap=HP_MIN_FOLLOWER_GAP,
                max_followers=HP_MAX_FOLLOWERS
            )

            logger.info(f"检测到 {len(detections)} 个敌方随从HP位置")

            # Step 4: Recognize HP for each detection
            enemy_followers = []
            for idx, (center_x, width) in enumerate(detections):
                # Crop HP window
                crop_x1 = max(0, center_x - width // 2)
                crop_x2 = min(region_cv.shape[1], center_x + width // 2)
                hp_crop = region_cv[0:HP_WINDOW_HEIGHT, crop_x1:crop_x2].copy()

                # Convert to RGBA and apply mask
                hp_crop_rgba = cv2.cvtColor(hp_crop, cv2.COLOR_BGR2BGRA)
                if self.hp_mask is not None:
                    mask_resized = cv2.resize(self.hp_mask, (hp_crop_rgba.shape[1], hp_crop_rgba.shape[0]), interpolation=cv2.INTER_NEAREST)
                    hp_crop_rgba[:, :, 3] = mask_resized
                else:
                    # If no mask, use full alpha
                    hp_crop_rgba[:, :, 3] = 255

                # Save debug crop if requested
                if debug_flag:
                    debug_path = f"debug/hp_crop_{idx}_{timestamp}.png"
                    cv2.imwrite(debug_path, hp_crop_rgba)

                # Preprocess to 28x28
                digit_list = self.hp_preprocessor.preprocess(hp_crop_rgba, None)

                # Recognize with fallback (EasyOCR → MNIST)
                hp_value = recognize_hp_with_fallback(
                    digit_list,
                    self.reader,
                    self.mnist_session
                )

                # Fallback to "99" if recognition completely failed
                if not hp_value or hp_value in ["?", "error", "unknown", "none"]:
                    hp_value = "99"
                    logger.warning(f"HP识别失败，使用默认值99 (位置: x={center_x})")

                # Calculate global screen coordinates
                enemy_x = x1 + center_x + ENEMY_FOLLOWER_OFFSET_X
                enemy_y = ENEMY_FOLLOWER_Y_ADJUST + random.randint(
                    -ENEMY_FOLLOWER_Y_RANDOM,
                    ENEMY_FOLLOWER_Y_RANDOM
                )

                enemy_followers.append((enemy_x, enemy_y, "normal", hp_value))

                logger.info(f"随从 {idx+1}: HP={hp_value}, X={enemy_x}, Y={enemy_y}")

            # Debug visualization if requested
            if debug_flag and enemy_followers:
                timestamp = int(time.time() * 1000)
                debug_img = region_cv.copy()
                for idx, (center_x, width) in enumerate(detections):
                    # Draw detection window
                    x_left = center_x - width // 2
                    x_right = center_x + width // 2
                    cv2.rectangle(debug_img, (x_left, 0), (x_right, HP_WINDOW_HEIGHT), (0, 255, 0), 2)
                    cv2.circle(debug_img, (center_x, HP_WINDOW_HEIGHT // 2), 5, (0, 255, 255), -1)
                    # Add HP label
                    hp_text = enemy_followers[idx][3] if idx < len(enemy_followers) else "?"
                    cv2.putText(debug_img, f"HP:{hp_text}", (center_x - 20, 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                cv2.imwrite(f"debug/enemy_hp_detection_{timestamp}.png", debug_img)

            return enemy_followers

        except Exception as e:
            logger.error(f"Enemy follower detection failed: {e}", exc_info=True)
            return []

    def scan_our_followers(
        self,
        screenshot,
        debug_flag: bool = False,
        extra_shots: int = 2,
        sort_desc: bool = False,
        shot_delay_range=(0.12, 0.22),
        with_names: bool = True,
    ):
        """检测场上的我方随从位置和状态。

        设计目标：把“补扫/重扫”的零碎逻辑收敛到一次扫描里。
        默认会在较短的随机间隔内采样3帧（1 + extra_shots=2），再做去重与命名汇总，
        用于降低动画/特效导致的单帧漏检。

        Args:
            screenshot: 当前截图（PIL Image）
            debug_flag: 是否输出debug图片
            extra_shots: 额外补充截图次数（默认2，即总共3帧）
            sort_desc: True=按x坐标从右到左排序；False=从左到右排序
            shot_delay_range: 多帧采样的随机间隔范围（秒）
        """
        import time
        import random
        from math import hypot
        import numpy as np
        import cv2
        from PIL import Image
        import os
        from concurrent.futures import ThreadPoolExecutor, as_completed

        screenshots = [screenshot]
        # 多帧采样：随机短间隔补两帧，减少过渡帧/特效干扰
        if hasattr(self.device_state, "take_screenshot"):
            try:
                extra = int(extra_shots)
            except Exception:
                extra = 2
            extra = max(0, extra)
            try:
                dmin, dmax = float(shot_delay_range[0]), float(shot_delay_range[1])
            except Exception:
                dmin, dmax = 0.12, 0.22
            if dmax < dmin:
                dmin, dmax = dmax, dmin
            dmin = max(0.0, dmin)
            dmax = max(dmin, dmax)
            for _ in range(extra):
                time.sleep(random.uniform(dmin, dmax))
                screenshots.append(self.device_state.take_screenshot())

        def _type_priority(t: str) -> int:
            return {"green": 3, "yellow": 2, "normal": 1}.get(t, 0)

        def _dedup_by_x(followers, x_thresh: int = 54):
            """按x轴聚类去重：同一随从保留更高优先级类型，并尽量保留名字"""
            if not followers:
                return []
            followers_sorted = sorted(followers, key=lambda p: p[0])
            clusters = []  # [{'x':float, 'items':[...]}]
            for item in followers_sorted:
                x = int(item[0])
                matched = False
                for c in clusters:
                    if abs(x - c["x"]) < x_thresh:
                        c["items"].append(item)
                        # 更新中心（简单平均即可）
                        c["x"] = (c["x"] * (len(c["items"]) - 1) + x) / len(c["items"])
                        matched = True
                        break
                if not matched:
                    clusters.append({"x": float(x), "items": [item]})

            merged = []
            for c in clusters:
                items = c["items"]
                # 选类型优先级最高的条目
                best = max(items, key=lambda it: _type_priority(it[2]))
                bx, by, bt = int(best[0]), best[1], best[2]

                # 名字：优先取任意非空名字（若冲突取出现次数最多）
                names = [it[3] for it in items if len(it) > 3 and it[3]]
                name = None
                if names:
                    from collections import Counter

                    name = Counter(names).most_common(1)[0][0]

                merged.append((bx, by, bt, name))

            return merged

        # 单帧识别：返回(positions, rectangles)
        def recognize_followers(shot, debug_flag, *, collect_rectangles: bool):
            # 原有的单次随从识别逻辑
            if shot is None:
                return [], []
            # 创建debug文件夹
            if debug_flag:
                os.makedirs("debug", exist_ok=True)
            region_color = shot.crop(OUR_FOLLOWER_REGION)
            region_color_np = np.array(region_color)
            region_color_cv = cv2.cvtColor(region_color_np, cv2.COLOR_RGB2BGR)
            region_blue = shot.crop(OUR_ATK_REGION)
            region_blue_np = np.array(region_blue)
            region_blue_cv = cv2.cvtColor(region_blue_np, cv2.COLOR_RGB2BGR)
            if debug_flag:
                # 为debug创建更大的区域，包含文字空间
                debug_region_color = (
                    OUR_FOLLOWER_REGION[0],
                    OUR_FOLLOWER_REGION[1] - 30,
                    OUR_FOLLOWER_REGION[2],
                    OUR_FOLLOWER_REGION[3] + 30,
                )
                debug_color = shot.crop(debug_region_color)
                debug_color_np = np.array(debug_color)
                debug_img_color = cv2.cvtColor(debug_color_np, cv2.COLOR_RGB2BGR)

                debug_region_blue = (
                    OUR_ATK_REGION[0],
                    OUR_ATK_REGION[1] - 30,
                    OUR_ATK_REGION[2],
                    OUR_ATK_REGION[3] + 30,
                )
                debug_blue = shot.crop(debug_region_blue)
                debug_blue_np = np.array(debug_blue)
                debug_img_blue = cv2.cvtColor(debug_blue_np, cv2.COLOR_RGB2BGR)
            else:
                debug_img_color = None
                debug_img_blue = None
            hsv_color = cv2.cvtColor(region_color_cv, cv2.COLOR_BGR2HSV)
            hsv_blue = cv2.cvtColor(region_blue_cv, cv2.COLOR_BGR2HSV)
            settings = OUR_FOLLOWER_HSV

            # 说明：游戏里“可攻击”的光圈/边框在不同动画/超进化等状态下颜色范围会漂移。
            # 这里把 green/green2、yellow1/yellow2 合并成一个mask，提高检出率。
            lower_green = np.array(settings["green"][:3])
            upper_green = np.array(settings["green"][3:])
            lower_green2 = np.array(settings.get("green2", settings["green"])[:3])
            upper_green2 = np.array(settings.get("green2", settings["green"])[3:])

            lower_yellow1 = np.array(settings["yellow1"][:3])
            upper_yellow1 = np.array(settings["yellow1"][3:])
            lower_yellow2 = np.array(settings.get("yellow2", settings["yellow1"])[:3])
            upper_yellow2 = np.array(settings.get("yellow2", settings["yellow1"])[3:])
            lower_blue = np.array(settings["blue"][:3])
            upper_blue = np.array(settings["blue"][3:])
            green_mask1 = cv2.inRange(hsv_color, lower_green, upper_green)
            green_mask2 = cv2.inRange(hsv_color, lower_green2, upper_green2)
            green_mask = cv2.bitwise_or(green_mask1, green_mask2)

            yellow_mask1 = cv2.inRange(hsv_color, lower_yellow1, upper_yellow1)
            yellow_mask2 = cv2.inRange(hsv_color, lower_yellow2, upper_yellow2)
            yellow1_mask = cv2.bitwise_or(yellow_mask1, yellow_mask2)
            blue_mask = cv2.inRange(hsv_blue, lower_blue, upper_blue)
            kernel = np.ones((1, 1), np.uint8)
            green_eroded = cv2.erode(
                cv2.dilate(green_mask, kernel, iterations=1), kernel, iterations=1
            )
            yellow1_eroded = cv2.erode(
                cv2.dilate(yellow1_mask, kernel, iterations=1), kernel, iterations=1
            )
            blue_eroded = cv2.erode(
                cv2.dilate(blue_mask, kernel, iterations=1), kernel, iterations=1
            )

            # NOTE: These are cheap and deterministic; threadpool overhead is larger
            # than the benefit for such small workloads.
            green_contours = cv2.findContours(
                green_eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )[0]
            yellow1_contours = cv2.findContours(
                yellow1_eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )[0]
            blue_contours = cv2.findContours(
                blue_eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )[0]
            follower_positions = []
            shot_all_follower_positions = []
            green_rects = []
            green_centers = []
            yellow_centers = []
            # 处理绿色框
            for cnt in green_contours:
                rect = cv2.minAreaRect(cnt)
                (x, y), (w, h), angle = rect
                area = cv2.contourArea(cnt)
                min_dim = min(w, h)
                max_dim = max(w, h)
                # 新增：如果max_dim大于230，尝试用分水岭算法分割
                if max_dim > 230:
                    # 1. 提取该轮廓的mask
                    mask = np.zeros(region_color_cv.shape[:2], np.uint8)
                    cv2.drawContours(mask, [cnt], -1, 255, -1)
                    # 2. 对mask做距离变换
                    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
                    ret, sure_fg = cv2.threshold(dist, 0.5 * dist.max(), 255, 0)
                    sure_fg = np.uint8(sure_fg)
                    # 3. 标记不同目标
                    ret, markers = cv2.connectedComponents(sure_fg)
                    markers = markers + 1
                    markers[mask == 0] = 0
                    # 4. 分水岭
                    color_img = region_color_cv.copy()
                    cv2.watershed(color_img, markers)
                    # 5. 提取分割后每个目标的中心点
                    for label in range(2, np.max(markers) + 1):
                        pts = np.column_stack(np.where(markers == label))
                        if len(pts) == 0:
                            continue
                        cy, cx = np.mean(pts, axis=0)
                        center_x_full = cx + 0  # region_color区域内坐标，加偏移
                        center_y_full = cy + 0
                        center_x_full += 176
                        center_y_full += 295
                        # 绿色随从去重检查（分水岭分割后）
                        is_duplicate = False
                        for gx, gy in green_centers:
                            if abs(center_x_full - gx) < 50:
                                is_duplicate = True
                                break
                        if is_duplicate:
                            continue
                        green_centers.append((center_x_full, center_y_full))
                        follower_positions.append(
                            (center_x_full, center_y_full, "green")
                        )
                        if debug_flag:
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_cx = int(cx)
                            debug_cy = int(cy) + 30  # 向下偏移30像素
                            cv2.circle(
                                debug_img_color,
                                (debug_cx, debug_cy),
                                7,
                                (0, 255, 255),
                                2,
                            )
                    continue  # 分水岭分割后不再走后续大随从分左右中心逻辑
                if 230 > max_dim > 80:
                    if max_dim > 230:
                        box = cv2.boxPoints(rect)
                        box = box.astype(np.int32)
                        if w > h:
                            cx, cy = rect[0]
                            left_center = (cx - w / 4, cy)
                            right_center = (cx + w / 4, cy)
                        else:
                            cx, cy = rect[0]
                            left_center = (cx, cy - h / 4)
                            right_center = (cx, cy + h / 4)
                        left_center_full = (left_center[0] + 176, left_center[1] + 295)
                        right_center_full = (
                            right_center[0] + 176,
                            right_center[1] + 295,
                        )
                        green_centers.append(left_center_full)
                        green_centers.append(right_center_full)
                        follower_positions.append(
                            (left_center_full[0], left_center_full[1], "green")
                        )
                        follower_positions.append(
                            (right_center_full[0], right_center_full[1], "green")
                        )
                        if debug_flag:
                            # 绘制外接矩形、中心点、长宽、面积
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_box = box.copy()
                            debug_box[:, 1] += 30  # Y坐标向下偏移30像素
                            cv2.drawContours(
                                debug_img_color, [debug_box], 0, (0, 255, 0), 2
                            )
                            lcx, lcy = int(left_center[0]), int(left_center[1])
                            rcx, rcy = int(right_center[0]), int(right_center[1])
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_lcx = lcx
                            debug_lcy = lcy + 30
                            debug_rcx = rcx
                            debug_rcy = rcy + 30
                            cv2.circle(
                                debug_img_color,
                                (debug_lcx, debug_lcy),
                                5,
                                (0, 0, 255),
                                -1,
                            )
                            cv2.circle(
                                debug_img_color,
                                (debug_rcx, debug_rcy),
                                5,
                                (0, 0, 255),
                                -1,
                            )
                            label = f"W:{w:.1f} H:{h:.1f} Area:{area:.0f}"
                            cv2.putText(
                                debug_img_color,
                                label,
                                (debug_lcx, debug_lcy - 10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 0, 0),
                                1,
                            )
                            cv2.putText(
                                debug_img_color,
                                label,
                                (debug_rcx, debug_rcy - 10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 0, 0),
                                1,
                            )
                    else:
                        center_x, center_y = rect[0]
                        center_x_full = center_x + 176
                        center_y_full = center_y + 295
                        green_centers.append((center_x_full, center_y_full))
                        follower_positions.append(
                            (center_x_full, center_y_full, "green")
                        )
                        if debug_flag:
                            box = cv2.boxPoints(rect)
                            box = box.astype(np.int32)
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_box = box.copy()
                            debug_box[:, 1] += 30  # Y坐标向下偏移30像素
                            cv2.drawContours(
                                debug_img_color, [debug_box], 0, (0, 255, 0), 2
                            )
                            cx, cy = int(center_x), int(center_y)
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_cx = cx
                            debug_cy = cy + 30  # 向下偏移30像素
                            cv2.circle(
                                debug_img_color,
                                (debug_cx, debug_cy),
                                5,
                                (0, 0, 255),
                                -1,
                            )
                            label = f"W:{w:.1f} H:{h:.1f} Area:{area:.0f}"
                            cv2.putText(
                                debug_img_color,
                                label,
                                (debug_cx, debug_cy - 10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (255, 0, 0),
                                1,
                            )
            # 处理黄色框
            for cnt in yellow1_contours:
                rect = cv2.minAreaRect(cnt)
                (x, y), (w, h), angle = rect
                area = cv2.contourArea(cnt)
                min_dim = min(w, h)
                max_dim = max(w, h)
                if max_dim > 230:
                    # 1. 提取该轮廓的mask
                    mask = np.zeros(region_color_cv.shape[:2], np.uint8)
                    cv2.drawContours(mask, [cnt], -1, 255, -1)
                    # 2. 距离变换
                    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
                    ret, sure_fg = cv2.threshold(dist, 0.5 * dist.max(), 255, 0)
                    sure_fg = np.uint8(sure_fg)
                    # 3. 连通域
                    ret, markers = cv2.connectedComponents(sure_fg)
                    markers = markers + 1
                    markers[mask == 0] = 0
                    # 4. 分水岭
                    color_img = region_color_cv.copy()
                    cv2.watershed(color_img, markers)
                    # 5. 提取分割后每个目标的中心点
                    for label in range(2, np.max(markers) + 1):
                        pts = np.column_stack(np.where(markers == label))
                        if len(pts) == 0:
                            continue
                        cy, cx = np.mean(pts, axis=0)
                        center_x_full = cx + 176
                        center_y_full = cy + 295
                        # 判断是否在绿色框内
                        is_inside_green = False
                        for g_box in green_rects:
                            g_box_full = g_box.copy()
                            g_box_full[:, 0] += 176
                            g_box_full[:, 1] += 295
                            if (
                                cv2.pointPolygonTest(
                                    g_box_full, (center_x_full, center_y_full), False
                                )
                                >= 0
                            ):
                                is_inside_green = True
                                break
                        if is_inside_green:
                            continue  # 跳过该黄色点
                        # 黄色随从去重检查（分水岭分割后）
                        is_duplicate = False
                        for yx, yy in yellow_centers:
                            if abs(center_x_full - yx) < 50:
                                is_duplicate = True
                                break
                        if is_duplicate:
                            continue
                        follower_positions.append(
                            (center_x_full, center_y_full, "yellow")
                        )
                        yellow_centers.append((center_x_full, center_y_full))
                        if debug_flag:
                            # 调整debug坐标，因为debug图像包含了更大的区域
                            debug_cx = int(cx)
                            debug_cy = int(cy) + 30  # 向下偏移30像素
                            cv2.circle(
                                debug_img_color,
                                (debug_cx, debug_cy),
                                7,
                                (0, 255, 255),
                                2,
                            )
                    continue  # 分水岭后不再走后续逻辑
                if 120 > max_dim > 90 or 230 > max_dim > 200:
                    center_x, center_y = rect[0]
                    center_x_full = center_x + 176
                    center_y_full = center_y + 295
                    box = cv2.boxPoints(rect)
                    yellow_box_poly = cv2.convexHull(box.astype(np.int32))
                    yellow_area = cv2.contourArea(yellow_box_poly)
                    is_inside_green = False
                    for g_box in green_rects:
                        g_poly = cv2.convexHull(g_box.astype(np.int32))
                        inter_area = cv2.intersectConvexConvex(yellow_box_poly, g_poly)[
                            0
                        ]
                        if yellow_area > 0 and inter_area / yellow_area > 0.7:
                            is_inside_green = True
                            break
                    follower_type = "green" if is_inside_green else "yellow"
                    follower_positions.append(
                        (center_x_full, center_y_full, follower_type)
                    )
                    if debug_flag:
                        box = cv2.boxPoints(rect)
                        box = box.astype(np.int32)
                        # 调整debug坐标，因为debug图像包含了更大的区域
                        debug_box = box.copy()
                        debug_box[:, 1] += 30  # Y坐标向下偏移30像素
                        cv2.drawContours(
                            debug_img_color, [debug_box], 0, (0, 255, 255), 2
                        )
                        cx, cy = int(center_x), int(center_y)
                        # 调整debug坐标，因为debug图像包含了更大的区域
                        debug_cx = cx
                        debug_cy = cy + 30  # 向下偏移30像素
                        cv2.circle(
                            debug_img_color, (debug_cx, debug_cy), 5, (0, 0, 255), -1
                        )
                        label = f"W:{w:.1f} H:{h:.1f} Area:{area:.0f}"
                        cv2.putText(
                            debug_img_color,
                            label,
                            (debug_cx, debug_cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 0, 0),
                            1,
                        )

            # 所有随从的蓝色攻击力位置
            for cnt in blue_contours:
                rect = cv2.minAreaRect(cnt)
                (x, y), (w, h), angle = rect
                area = cv2.contourArea(cnt)
                center_x, center_y = rect[0]
                min_dim = min(w, h)
                max_dim = max(w, h)
                if 15 < max_dim < 40 and 3 < min_dim < 15 and area < 200:
                    if collect_rectangles:
                        shot_all_follower_positions.append(
                            ((int(center_x + 263), 330), (int(center_x + 263 + 103), 463))
                        )
                    # 区域截图中卡我方随从的中心位置
                    in_card_center_x_full = center_x + 50
                    in_card_center_y_full = center_y - 46
                    # 全局中我方随从中心位置
                    center_x_full = in_card_center_x_full + 263
                    center_y_full = in_card_center_y_full + 466  # 420
                    # 检查是否在绿色中心点或黄色中心点x轴50像素以内
                    is_near_green_or_yellow = False

                    # 检查绿色中心点
                    for gx, gy in green_centers:
                        if abs(center_x_full - gx) <= 50:
                            is_near_green_or_yellow = True
                            break

                    # 检查黄色中心点
                    if not is_near_green_or_yellow:
                        for yx, yy in yellow_centers:
                            if abs(center_x_full - yx) <= 50:
                                is_near_green_or_yellow = True
                                break

                    # 如果距离所有绿色和黄色中心点都在50像素以外，则认为是普通随从
                    if not is_near_green_or_yellow:
                        follower_type = "normal"
                        follower_positions.append(
                            (center_x_full, center_y_full, follower_type)
                        )
                    if debug_flag:
                        box = cv2.boxPoints(rect)
                        box = box.astype(np.int32)
                        # 调整debug坐标，因为debug图像包含了更大的区域
                        debug_box = box.copy()
                        debug_box[:, 1] += 30  # Y坐标向下偏移30像素
                        cv2.drawContours(debug_img_blue, [debug_box], 0, (255, 0, 0), 2)
                        cx, cy = int(center_x), int(center_y)
                        # 调整debug坐标，因为debug图像包含了更大的区域
                        debug_cx = cx
                        debug_cy = cy + 30  # 向下偏移30像素
                        cv2.circle(
                            debug_img_blue, (debug_cx, debug_cy), 5, (0, 0, 255), -1
                        )
                        label = f"W:{w:.1f} H:{h:.1f} Area:{area:.0f}"
                        cv2.putText(
                            debug_img_blue,
                            label,
                            (debug_cx, debug_cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 0, 0),
                            1,
                        )

            if debug_flag:
                import time

                timestamp = int(time.time() * 1000)
                cv2.imwrite(
                    f"debug/our_follower_region_{timestamp}.png", debug_img_color
                )
                cv2.imwrite(f"debug/our_hp_region_{timestamp}.png", debug_img_blue)

            follower_positions.sort(key=lambda pos: pos[0], reverse=sort_desc)
            return follower_positions, shot_all_follower_positions

        # 多帧HSV识别（先得到每帧结果，再做汇总）
        per_shot_followers = []
        all_rectangles = []

        collect_rectangles = bool(with_names)

        valid_shots = [s for s in screenshots if s is not None]
        if not valid_shots:
            return []

        if len(valid_shots) == 1:
            followers, rects = recognize_followers(
                valid_shots[0], debug_flag, collect_rectangles=collect_rectangles
            )
            followers = _dedup_by_x([(x, y, t, None) for (x, y, t) in followers])
            per_shot_followers.append(followers)
            if collect_rectangles:
                all_rectangles.extend(rects)
        else:
            with ThreadPoolExecutor(max_workers=max(1, len(valid_shots))) as executor:
                futures = [
                    executor.submit(
                        recognize_followers,
                        shot,
                        debug_flag,
                        collect_rectangles=collect_rectangles,
                    )
                    for shot in valid_shots
                ]
                import logging

                for future in as_completed(futures):
                    try:
                        followers, rects = future.result()
                        followers = _dedup_by_x(
                            [(x, y, t, None) for (x, y, t) in followers]
                        )
                        per_shot_followers.append(followers)
                        if collect_rectangles:
                            all_rectangles.extend(rects)
                    except Exception as e:
                        logging.error(f"recognize_followers线程异常: {e}")

        # 矩形区域去重（仅用于SIFT命名；左上角x轴在54像素内视为同一个随从区域）
        deduplicated_follower_positions = []
        if with_names and all_rectangles:
            for rect_coords in all_rectangles:
                (x1, y1), (x2, y2) = rect_coords
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                found = False
                for existing_rect in deduplicated_follower_positions:
                    (ex1, ey1), (ex2, ey2) = existing_rect
                    if abs(x1 - ex1) < 54:
                        found = True
                        break
                if not found:
                    deduplicated_follower_positions.append(((x1, y1), (x2, y2)))

        # 新的SIFT识别逻辑：基于去重后的all_follower_positions矩形区域
        def perform_sift_recognition_on_rectangles(base_screenshot):
            """对去重后的all_follower_positions中的每个矩形区域进行SIFT识别"""
            import os
            from PIL import Image

            # 准备截图数据
            if hasattr(base_screenshot, "shape"):
                cv_img = base_screenshot
            else:
                cv_img = np.array(base_screenshot)
                cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)

            # 加载模板图片
            def load_template_features(filename):
                """加载单个模板的特征"""
                if not filename.endswith(".png"):
                    return None
                template_path = os.path.join("shadowverse_cards_cost", filename)
                if not os.path.exists(template_path):
                    template_path = resource_path(template_path)
                tname = os.path.splitext(filename)[0]
                try:
                    # 使用PIL读取图片（处理P/LA/L等模式，避免OpenCV通道数异常）
                    with Image.open(template_path) as pil_img:
                        if pil_img.mode not in ("RGB", "RGBA"):
                            pil_img = pil_img.convert("RGBA")
                        template_img = np.array(pil_img)

                    if template_img is None:
                        return None
                    if template_img.dtype != np.uint8:
                        template_img = template_img.astype(np.uint8, copy=False)

                    # 转为OpenCV常用BGR三通道
                    if template_img.ndim == 2:  # Gray
                        template_img = cv2.cvtColor(template_img, cv2.COLOR_GRAY2BGR)
                    elif template_img.ndim == 3:
                        ch = template_img.shape[2]
                        if ch == 4:
                            template_img = cv2.cvtColor(template_img, cv2.COLOR_RGBA2BGR)
                        elif ch == 3:
                            template_img = cv2.cvtColor(template_img, cv2.COLOR_RGB2BGR)
                        elif ch == 1:
                            template_img = cv2.cvtColor(template_img[:, :, 0], cv2.COLOR_GRAY2BGR)
                        else:
                            return None
                    else:
                        return None
                except Exception as e:
                    return None

                TEMPLATE_SCALE_FACTOR = 0.4

                # 截取模板图片中的指定区域
                TEMPLATE_RECT = (101, 151, 442, 568)
                tx1, ty1, tx2, ty2 = TEMPLATE_RECT
                template = template_img[ty1:ty2, tx1:tx2]
                if template.size == 0:
                    return None

                # 仅对模板应用缩放（关键修改）
                if TEMPLATE_SCALE_FACTOR != 1.0:
                    new_width = int(template.shape[1] * TEMPLATE_SCALE_FACTOR)
                    new_height = int(template.shape[0] * TEMPLATE_SCALE_FACTOR)
                    if new_width <= 0 or new_height <= 0:
                        return None
                    template = cv2.resize(
                        template, (new_width, new_height), interpolation=cv2.INTER_AREA
                    )

                # 图像预处理
                template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                template_gray = cv2.equalizeHist(template_gray)
                template_gray = cv2.GaussianBlur(template_gray, (3, 3), 0.5)

                # SIFT特征提取
                sift = cv2.SIFT_create(
                    nfeatures=0, contrastThreshold=0.02, edgeThreshold=15, sigma=1.6
                )
                tkp, tdes = sift.detectAndCompute(template_gray, None)
                if tdes is not None:
                    return tname, {
                        "template": template,
                        "keypoints": tkp,
                        "descriptors": tdes,
                    }
                return None

            # 加载所有模板（缓存，避免每次扫描重复读取磁盘）
            if getattr(self, "_board_sift_templates", None) is None:
                template_dir = "shadowverse_cards_cost"
                if not os.path.exists(template_dir):
                    template_dir = resource_path(template_dir)
                template_files = [f for f in os.listdir(template_dir) if f.endswith(".png")]
                card_templates = {}

                with ThreadPoolExecutor(max_workers=min(8, len(template_files) or 1)) as executor:
                    futures = [
                        executor.submit(load_template_features, filename)
                        for filename in template_files
                    ]
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result is not None:
                                tname, template_info = result
                                card_templates[tname] = template_info
                        except Exception as e:
                            import logging

                            logging.error(f"模板加载异常: {e}")
                            continue

                self._board_sift_templates = card_templates
            else:
                card_templates = self._board_sift_templates

            # 对每个矩形区域进行SIFT识别
            results = []
            for rect_coords in deduplicated_follower_positions:
                (x1, y1), (x2, y2) = rect_coords

                # 确保坐标为整数
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                # 截取矩形区域
                rect_img = cv_img[y1:y2, x1:x2]
                if rect_img.size == 0:
                    continue

                # 图像预处理
                rect_gray = cv2.cvtColor(rect_img, cv2.COLOR_BGR2GRAY)
                rect_gray = cv2.equalizeHist(rect_gray)
                rect_gray = cv2.GaussianBlur(rect_gray, (3, 3), 0.5)

                # SIFT特征提取
                sift = cv2.SIFT_create(
                    nfeatures=0, contrastThreshold=0.02, edgeThreshold=15, sigma=1.2
                )
                rkp, rdes = sift.detectAndCompute(rect_gray, None)

                if rdes is None:
                    continue

                # 与所有模板进行匹配
                best_match = None
                best_confidence = 0

                for tname, tinfo in card_templates.items():
                    tdes = tinfo["descriptors"]
                    tkp = tinfo["keypoints"]

                    # FLANN匹配
                    FLANN_INDEX_KDTREE = 1
                    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=8)
                    search_params = dict(checks=100)
                    flann = cv2.FlannBasedMatcher(index_params, search_params)
                    matches = flann.knnMatch(tdes, rdes, k=2)

                    good_matches = []
                    for m, n in matches:
                        if m.distance < 0.7 * n.distance:
                            good_matches.append(m)

                    if len(good_matches) < 3:
                        continue

                    # 计算置信度
                    avg_distance = np.mean([m.distance for m in good_matches])
                    if avg_distance <= 120:
                        distance_score = 1.0
                    elif avg_distance <= 250:
                        distance_score = 1.0 - (avg_distance - 120) / 130
                    else:
                        distance_score = max(0, 1.0 - (avg_distance - 250) / 150)

                    match_ratio = len(good_matches) / len(tdes)
                    confidence = distance_score * match_ratio

                    if confidence >= 0.01 and confidence > best_confidence:
                        best_confidence = confidence
                        best_match = tname

                if best_match is not None:
                    # 计算矩形中心点
                    center_x = int((x1 + x2) // 2)
                    center_y = int((y1 + y2) // 2)

                    # 去除前缀的费用数字和下划线，只保留随从名
                    if "_" in best_match:
                        try:
                            _, _, name = parse_card_stem(best_match)
                        except Exception:
                            name = best_match.split("_", 1)[1]
                    else:
                        name = best_match

                    results.append((center_x, center_y, name))

            return results

        sift_results = []
        if with_names and deduplicated_follower_positions:
            # 执行SIFT识别：用最新一帧作为裁剪基准（避免跨帧矩形导致命名失败）
            base_for_naming = None
            for s in reversed(screenshots):
                if s is not None:
                    base_for_naming = s
                    break
            if base_for_naming is None:
                base_for_naming = screenshot

            sift_results = perform_sift_recognition_on_rectangles(base_for_naming)

        def attach_names(followers):
            named = []
            for x, y, t, _ in followers:
                x = int(x)
                name = None
                best_match_distance = float("inf")
                for cx, cy, sift_name in sift_results:
                    x_distance = abs(cx - x)
                    if x_distance < 30 and x_distance < best_match_distance:
                        name = sift_name
                        best_match_distance = x_distance
                named.append((x, y, t, name))
            return named

        if with_names and sift_results:
            per_shot_followers = [attach_names(f) for f in per_shot_followers]

        x_match_thresh = 54
        scan_support_required = None

        if not with_names:
            # 攻击阶段(无命名)使用保守汇总：
            # - 多帧按槽位聚类
            # - 要求跨帧支持(>=2/3帧)
            # - 限制最多5个随从，避免把动画残影并进结果
            support_required = 2 if len(valid_shots) >= 3 else 1
            scan_support_required = support_required
            clusters = []

            for shot_idx, shot_followers in enumerate(per_shot_followers):
                for x, y, t, _ in shot_followers:
                    x_i = int(x)
                    y_i = int(y)
                    t_s = str(t or "normal")

                    matched = None
                    for c in clusters:
                        if abs(x_i - int(c["x"])) < x_match_thresh:
                            matched = c
                            break

                    if matched is None:
                        clusters.append(
                            {
                                "x": float(x_i),
                                "items": [(x_i, y_i, t_s)],
                                "shots": {int(shot_idx)},
                            }
                        )
                        continue

                    items = matched["items"]
                    n = len(items)
                    matched["x"] = (float(matched["x"]) * n + float(x_i)) / (n + 1)
                    items.append((x_i, y_i, t_s))
                    matched["shots"].add(int(shot_idx))

            merged_meta = []
            for c in clusters:
                support = len(c.get("shots") or ())
                if support < support_required:
                    continue

                items = list(c.get("items") or [])
                if not items:
                    continue

                avg_x = int(round(sum(it[0] for it in items) / len(items)))
                avg_y = int(round(sum(it[1] for it in items) / len(items)))
                best_type = max((it[2] for it in items), key=_type_priority)
                merged_meta.append((avg_x, avg_y, best_type, None, support))

            # Shadowverse场上随从上限为5，超出时保留“跨帧支持更强”的候选。
            if len(merged_meta) > 5:
                merged_meta = sorted(
                    merged_meta,
                    key=lambda it: (int(it[4]), _type_priority(it[2]), int(it[0])),
                    reverse=True,
                )[:5]

            merged = [
                (int(x), 399 + random.randint(-7, 7), t, name)
                for (x, y, t, name, support) in merged_meta
            ]
            merged = sorted(merged, key=lambda pos: pos[0], reverse=sort_desc)
        else:
            # 选一帧作为基准（结果最多；若相同则名字更多；再相同则可攻击随从更多）
            def score(followers):
                total = len(followers)
                named_cnt = sum(1 for it in followers if it[3])
                atk_cnt = sum(1 for it in followers if it[2] in ("green", "yellow"))
                return (total, named_cnt, atk_cnt)

            anchor = max(per_shot_followers, key=score) if per_shot_followers else []

            # 汇总：以anchor为骨架，补全名字/升级类型/补齐漏检随从
            merged = list(anchor)

            def merge_one(candidate):
                nonlocal merged
                for x, y, t, name in candidate:
                    matched_idx = None
                    for i, (mx, my, mt, mname) in enumerate(merged):
                        if abs(x - mx) < x_match_thresh:
                            matched_idx = i
                            break

                    if matched_idx is None:
                        merged.append((x, y, t, name))
                        continue

                    mx, my, mt, mname = merged[matched_idx]
                    # 类型升级：green > yellow > normal
                    if _type_priority(t) > _type_priority(mt):
                        mt = t
                    # 名字补全
                    if (not mname) and name:
                        mname = name
                    merged[matched_idx] = (mx, my, mt, mname)

            for shot_followers in per_shot_followers:
                if shot_followers is anchor:
                    continue
                merge_one(shot_followers)

            # 最终按x聚类去重一次，并强制校准y坐标
            merged = _dedup_by_x(merged, x_thresh=x_match_thresh)
            merged = [
                (int(x), 399 + random.randint(-7, 7), t, name)
                for (x, y, t, name) in merged
            ]
            merged = sorted(merged, key=lambda pos: pos[0], reverse=sort_desc)
        try:
            debug_mode = bool(
                isinstance(getattr(self.device_state, "config", None), dict)
                and self.device_state.config.get("ui", {}).get("debug_mode")
            )
        except Exception:
            debug_mode = False

        if (debug_flag or debug_mode) and (not with_names):
            try:
                shot_counts = [len(s) for s in (per_shot_followers or [])]
                self.device_state.logger.info(
                    "我方随从多帧汇总(攻击阶段): "
                    f"shots={shot_counts}, support_required={scan_support_required}, merged={len(merged)}"
                )
            except Exception:
                pass

        if debug_flag or debug_mode:
            self.device_state.logger.info(f"我方当前场上随从: {merged}")
        else:
            self.device_state.logger.debug(f"我方当前场上随从: {merged}")
        return merged

    def scan_shield_targets(self, debug_flag=False):
        """扫描护盾（多线程并发处理）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        shield_targets = []
        images = []
        last_screenshot = None

        # 获取多张截图用于护盾检测
        for _ in range(4):
            time.sleep(0.2)
            screenshot = self.device_state.take_screenshot()
            if screenshot is None:
                continue
            region = screenshot.crop(ENEMY_SHIELD_REGION)
            bgr_image = cv2.cvtColor(np.array(region), cv2.COLOR_RGB2BGR)
            images.append(bgr_image)

        # 获取最后一张截图用于敌方随从有无检测
        if images:
            last_screenshot = self.device_state.take_screenshot()

        if not images or last_screenshot is None:
            return []  # 如果没有图像，直接返回空列表

        # 使用线程池并行处理攻击力检测和护盾检测
        with ThreadPoolExecutor(max_workers=6) as executor:
            # 提交攻击力检测任务
            atk_future = executor.submit(
                self.scan_enemy_ATK, last_screenshot, debug_flag
            )

            # 提交护盾检测任务
            shield_futures = [
                executor.submit(self._process_shield_image, img, debug_flag)
                for img in images
            ]

            # 收集攻击力检测结果
            try:
                enemy_atk_positions = atk_future.result()
                if not enemy_atk_positions:
                    return (
                        []
                    )  # 如果无敌方随从，直接返回空列表（就算护盾处理检测到护盾，没有随从的话也是误识别，比如护符之类）
            except Exception as e:
                import logging

                logging.error(f"敌方随从位置检测异常: {str(e)}")
                return []

            # 收集护盾检测结果
            all_positions = []
            for future in as_completed(shield_futures):
                try:
                    all_positions.extend(future.result())
                except Exception as e:
                    import logging

                    logging.error(f"护盾检测并发任务异常: {str(e)}")

            # 合并去重 + 多帧一致性过滤
            # 过去是“任意一帧命中就算护盾”，容易被特效/闪光误触发。
            # 这里要求同一位置在多帧中重复出现，提高准确率。
            clusters = []  # [{'x':float,'y':float,'count':int}]
            for x, y in all_positions:
                matched = False
                for c in clusters:
                    if abs(x - c['x']) < 40 and abs(y - c['y']) < 40:
                        # 在线更新均值
                        c['count'] += 1
                        c['x'] = (c['x'] * (c['count'] - 1) + x) / c['count']
                        c['y'] = (c['y'] * (c['count'] - 1) + y) / c['count']
                        matched = True
                        break
                if not matched:
                    clusters.append({'x': float(x), 'y': float(y), 'count': 1})

            # 根据采样帧数动态决定一致性要求
            # - >=3帧：至少2帧命中
            # - <3帧：放宽到1帧（避免截图失败导致永远检测不到）
            support_required = 2 if len(images) >= 3 else 1
            final_shields = [
                (int(c['x']), int(c['y']))
                for c in clusters
                if c['count'] >= support_required
            ]

        shield_targets = []

        # 过滤enemy_atk_positions，只保留与final_shields中任意点x轴距离小于50像素的坐标
        for shield_pos in enemy_atk_positions:
            shield_x = shield_pos[0]
            # 检查是否与任意敌方随从位置的x轴距离小于50像素
            for atk_pos in final_shields:
                atk_x = atk_pos[0]
                if abs(shield_x - atk_x) < 50:
                    shield_targets.append(shield_pos)
                    break  # 找到一个匹配到的就足够了

        # 按x轴排序，校准y轴坐标
        if shield_targets:
            shield_targets.sort(key=lambda pos: pos[0])  # 按x坐标排序
            # 校准所有护盾的y轴坐标
            shield_targets = [
                (pos[0], 227 + random.randint(-3, 3)) for pos in shield_targets
            ]

        # self.device_state.logger.info(f"护盾检测完成，检测到 {len(shield_targets)} 个护盾")

        return shield_targets

    def _process_shield_image(self, image, debug_flag):
        """处理护盾图像"""
        shield_targets = []
        offset_x, offset_y = ENEMY_SHIELD_REGION[0], ENEMY_SHIELD_REGION[1]

        if debug_flag:
            os.makedirs("debug", exist_ok=True)
            timestamp = int(time.time() * 1000)
            filename = f"debug/shield_debug_{timestamp}_raw.png"
            result = cv2.imwrite(filename, image)

        # 转换为HSV颜色空间
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([23, 46, 30]), np.array([89, 255, 255]))

        # # 形态学操作 - 使用椭圆核，分别进行腐蚀和膨胀（新方法）
        # kernel_size = 2  # 椭圆核大小
        # kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

        # # 分别进行腐蚀和膨胀操作
        # erode_iterations = 1
        # dilate_iterations = 1

        # # 先进行腐蚀操作
        # if erode_iterations > 0:
        #     mask = cv2.erode(mask, kernel, iterations=erode_iterations)

        # # 再进行膨胀操作
        # if dilate_iterations > 0:
        #     mask = cv2.dilate(mask, kernel, iterations=dilate_iterations)

        # 形态学操作
        kernel = np.ones((1, 1), np.uint8)
        mask = cv2.erode(cv2.dilate(mask, kernel, iterations=1), kernel, iterations=1)
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            min_dim = min(w, h)
            max_dim = max(w, h)

            if 140 > max_dim > 80 and 72 > min_dim > 55 and area > 700:
                cx, cy = x + w // 2, y + h // 2
                # 自动转换为全屏坐标
                global_cx = cx + offset_x
                global_cy = cy + offset_y
                shield_targets.append((global_cx, global_cy))
                if debug_flag:
                    # 创建调试图像
                    debug_img = image.copy()
                    logging.info(
                        f"debug_img shape: {debug_img.shape}, dtype: {debug_img.dtype}"
                    )
                    # 画中心点
                    cv2.circle(debug_img, (cx, cy), 10, (0, 0, 255), -1)

                    # 最小外接矩形
                    rect = cv2.minAreaRect(cnt)
                    box = cv2.boxPoints(rect).astype(int)
                    cv2.drawContours(debug_img, [box], 0, (0, 255, 0), 2)

                    # 宽高面积标注
                    label = f"W:{w} H:{h} Area:{area:.0f}"
                    cv2.putText(
                        debug_img,
                        label,
                        (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2,
                    )

                    # 保存调试图像
                    os.makedirs("debug", exist_ok=True)
                    timestamp = int(time.time() * 1000)
                    filename = (
                        f"debug/shield_debug_{timestamp}_{global_cx}_{global_cy}.png"
                    )
                    logging.info(f"准备保存护盾debug图片: {filename}")
                    result = cv2.imwrite(filename, debug_img)
                    if result:
                        logging.info(f"护盾debug图片已保存: {filename}")
                    else:
                        logging.error(f"护盾debug图片保存失败: {filename}")

        return shield_targets

    def card_can_choose_target_like_amulet(self, debug_flag=False):
        """扫描敌方可攻击目标，比如护符"""
        can_choosetargets = []
        screenshot = self.device_state.take_screenshot()
        if screenshot is None:
            return []
        can_choose_region = (160, 302, 1068, 315)
        region = screenshot.crop(can_choose_region)
        bgr_image = cv2.cvtColor(np.array(region), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        lower_bound = np.array([4, 151, 28])
        upper_bound = np.array([89, 255, 255])
        mask = cv2.inRange(hsv, lower_bound, upper_bound)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            if 500 < area < 1200:
                # 转换为全局坐标
                cx, cy = x + w // 2, y + h // 2
                global_x = can_choose_region[0] + cx
                can_choosetargets.append((global_x, 216 + random.randint(-5, 5)))
            if debug_flag:
                os.makedirs("debug", exist_ok=True)
                timestamp = int(time.time() * 1000)
                # 画出轮廓和中心点
                debug_img = bgr_image.copy()
                cv2.drawContours(debug_img, [cnt], 0, (0, 0, 255), 2)
                cv2.circle(debug_img, (x, y), 10, (0, 0, 255), -1)
                filename = f"debug/can_choose_target_{timestamp}_{x}_{y}.png"
                result = cv2.imwrite(filename, debug_img)
                if result:
                    logging.info(f"can_choose_target图片已保存: {filename}")

        if can_choosetargets:
            can_choosetargets.sort(key=lambda pos: pos[0])

        return can_choosetargets

    def detect_existing_match(self, gray_screenshot, templates):
        """检测是否已经在游戏中"""
        # 检查是否检测到"决斗"按钮
        war_template = templates.get("war")
        if war_template:
            max_loc, max_val = self.template_manager.match_template(
                gray_screenshot, war_template
            )
            if max_val >= war_template["threshold"] and max_loc is not None:
                return True

        # 检查是否检测到"结束回合"按钮
        end_round_template = templates.get("end_round")
        if end_round_template:
            max_loc, max_val = self.template_manager.match_template(
                gray_screenshot, end_round_template
            )
            if max_val >= end_round_template["threshold"] and max_loc is not None:
                return True

        # 检查是否检测到"敌方回合"按钮
        enemy_round_template = templates.get("enemy_round")
        if enemy_round_template:
            max_loc, max_val = self.template_manager.match_template(
                gray_screenshot, enemy_round_template
            )
            if max_val >= enemy_round_template["threshold"] and max_loc is not None:
                return True

        return False
