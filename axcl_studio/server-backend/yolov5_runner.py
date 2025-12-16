import colorsys
import random
import time
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from axengine import axclrt_provider_name, axengine_provider_name

CONF_THRESH = 0.45
IOU_THRESH = 0.45
STRIDES = [8, 16, 32]
ANCHORS = [
    [10, 13, 16, 30, 33, 23],
    [30, 61, 62, 45, 59, 119],
    [116, 90, 156, 198, 373, 326],
]
INPUT_SHAPE = (640, 640)
CLASS_NAMES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


def draw_bbox(
    image: Optional[np.ndarray],
    bboxes: np.ndarray,
    classes: Optional[Sequence[str]] = None,
    show_label: bool = True,
    threshold: float = 0.1,
    logger: Optional[Callable[[str], None]] = None,
) -> Optional[np.ndarray]:
    if classes is None:
        classes = CLASS_NAMES

    if logger:
        for bbox in bboxes:
            score = bbox[4]
            if score < threshold:
                continue
            class_ind = int(bbox[5])
            name = classes[class_ind] if 0 <= class_ind < len(classes) else str(class_ind)
            coor = np.array(bbox[:4], dtype=np.int32)
            logger(f"  {class_ind:>3}: {name:<12}: {coor.tolist()}, score: {score * 100:3.2f}%")
    return None


def xywh2xyxy(x: np.ndarray) -> np.ndarray:
    y = x.copy()
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def bboxes_iou(boxes1: np.ndarray, boxes2: np.ndarray) -> np.ndarray:
    boxes1_area = (boxes1[..., 2] - boxes1[..., 0]) * (boxes1[..., 3] - boxes1[..., 1])
    boxes2_area = (boxes2[..., 2] - boxes2[..., 0]) * (boxes2[..., 3] - boxes2[..., 1])

    left_up = np.maximum(boxes1[..., :2], boxes2[..., :2])
    right_down = np.minimum(boxes1[..., 2:], boxes2[..., 2:])

    inter_section = np.maximum(right_down - left_up, 0.0)
    inter_area = inter_section[..., 0] * inter_section[..., 1]
    union_area = boxes1_area + boxes2_area - inter_area
    ious = np.maximum(inter_area / np.maximum(union_area, np.finfo(np.float32).eps), np.finfo(np.float32).eps)

    return ious


def nms(proposals: np.ndarray, iou_threshold: float, conf_threshold: float, multi_label: bool = False) -> np.ndarray:
    xc = proposals[..., 4] > conf_threshold
    proposals = proposals[xc]
    if not len(proposals):
        return np.empty((0, 6), dtype=np.float32)

    proposals[:, 5:] *= proposals[:, 4:5]
    bboxes = xywh2xyxy(proposals[:, :4])

    if multi_label:
        mask = proposals[:, 5:] > conf_threshold
        nonzero_indices = np.argwhere(mask)
        if nonzero_indices.size <= 0:
            return np.empty((0, 6), dtype=np.float32)
        i, j = nonzero_indices.T
        bboxes = np.hstack((bboxes[i], proposals[i, j + 5][:, None], j[:, None].astype(float)))
    else:
        confidences = proposals[:, 5:]
        conf = confidences.max(axis=1, keepdims=True)
        j = confidences.argmax(axis=1)[:, None]

        bboxes = np.hstack((bboxes, conf, j.astype(float)))
        mask = conf.reshape(-1) > conf_threshold
        bboxes = bboxes[mask]

    classes_in_img = list(set(bboxes[:, 5]))
    bboxes = bboxes[bboxes[:, 4].argsort()[::-1][:300]]
    best_bboxes = []

    for cls in classes_in_img:
        cls_mask = bboxes[:, 5] == cls
        cls_bboxes = bboxes[cls_mask]

        while len(cls_bboxes) > 0:
            max_ind = np.argmax(cls_bboxes[:, 4])
            best_bbox = cls_bboxes[max_ind]
            best_bboxes.append(best_bbox)
            cls_bboxes = np.concatenate((cls_bboxes[:max_ind], cls_bboxes[max_ind + 1 :]))
            if len(cls_bboxes) == 0:
                break
            iou = bboxes_iou(best_bbox[np.newaxis, :4], cls_bboxes[:, :4])
            weight = np.ones((len(iou),), dtype=np.float32)
            iou_mask = iou > iou_threshold
            weight[iou_mask] = 0.0
            cls_bboxes[:, 4] = cls_bboxes[:, 4] * weight
            score_mask = cls_bboxes[:, 4] > 0.0
            cls_bboxes = cls_bboxes[score_mask]

    if not best_bboxes:
        return np.empty((0, 6), dtype=np.float32)

    best_bboxes = np.vstack(best_bboxes)
    best_bboxes = best_bboxes[best_bboxes[:, 4].argsort()[::-1]]
    return best_bboxes


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (np.exp(-x) + 1.0)


def gen_proposals(outputs: Sequence[np.ndarray]) -> np.ndarray:
    new_pred = []
    anchor_grid = np.array(ANCHORS).reshape(-1, 1, 1, 3, 2)
    for i, pred in enumerate(outputs):
        pred = sigmoid(pred)
        n, h, w, _ = pred.shape
        pred = pred.reshape(n, h, w, 3, 85)
        conv_shape = pred.shape
        output_size = conv_shape[1]
        conv_raw_dxdy = pred[..., 0:2]
        conv_raw_dwdh = pred[..., 2:4]
        xy_grid = np.meshgrid(np.arange(output_size), np.arange(output_size))
        xy_grid = np.expand_dims(np.stack(xy_grid, axis=-1), axis=2)
        xy_grid = np.tile(np.expand_dims(xy_grid, axis=0), [1, 1, 1, 3, 1])
        xy_grid = xy_grid.astype(np.float32)
        pred_xy = (conv_raw_dxdy * 2.0 - 0.5 + xy_grid) * STRIDES[i]
        pred_wh = (conv_raw_dwdh * 2) ** 2 * anchor_grid[i]
        pred[:, :, :, :, 0:4] = np.concatenate([pred_xy, pred_wh], axis=-1)
        new_pred.append(np.reshape(pred, (-1, np.shape(pred)[-1])))
    return np.concatenate(new_pred, axis=0)


def clip_coords(boxes: np.ndarray, shape: Tuple[int, int]) -> None:
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, shape[1])
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, shape[0])


def scale_coords(img1_shape: Tuple[int, int], coords: np.ndarray, img0_shape: Tuple[int, int], ratio_pad=None) -> np.ndarray:
    if ratio_pad is None:
        gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
        pad = (img1_shape[1] - img0_shape[1] * gain) / 2, (img1_shape[0] - img0_shape[0] * gain) / 2
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]

    coords[:, [0, 2]] -= pad[0]
    coords[:, [1, 3]] -= pad[1]
    coords[:, :4] /= gain
    clip_coords(coords, img0_shape)
    return coords


def post_processing(outputs: Sequence[np.ndarray], origin_shape: Tuple[int, int], input_shape: Tuple[int, int]) -> np.ndarray:
    proposals = gen_proposals(outputs)
    pred = nms(proposals, IOU_THRESH, CONF_THRESH, multi_label=True)
    if pred.size == 0:
        return np.empty((0, 6), dtype=np.float32)
    pred[:, :4] = scale_coords(input_shape, pred[:, :4], origin_shape)
    return pred


def run_detection(
    session,
    inputs: np.ndarray,
    origin_shape: Tuple[int, int],
    repeat: int,
) -> Tuple[np.ndarray, dict, Optional[np.ndarray], List[str]]:
    logs: List[str] = []

    def log(message: str) -> None:
        logs.append(message)

    inputs = np.ascontiguousarray(inputs)

    time_costs: List[float] = []
    results = None
    for _ in range(max(1, repeat)):
        t_start = time.perf_counter()
        results = session.run(None, {"images": inputs})
        t_end = time.perf_counter()
        time_costs.append((t_end - t_start) * 1000)

    if results is None:
        raise RuntimeError("Inference returned no outputs")

    detections = post_processing(results, origin_shape, INPUT_SHAPE)

    log("  ------------------------------------------------------")
    if time_costs:
        log(
            "  min =   %.3f ms   max =   %.3f ms   avg =   %.3f ms"
            % (min(time_costs), max(time_costs), sum(time_costs) / len(time_costs))
        )
    log("  ------------------------------------------------------")
    if detections.size == 0:
        log("  No targets detected")

    annotated = draw_bbox(None, detections, logger=log)

    metrics = {
        "min_ms": min(time_costs) if time_costs else 0.0,
        "max_ms": max(time_costs) if time_costs else 0.0,
        "avg_ms": sum(time_costs) / len(time_costs) if time_costs else 0.0,
    }

    return detections, metrics, annotated, logs


__all__ = [
    "axclrt_provider_name",
    "axengine_provider_name",
    "CLASS_NAMES",
    "run_detection",
]
