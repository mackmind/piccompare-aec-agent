"""Convert binary SAM masks into closed polygons."""

from __future__ import annotations

import cv2
import numpy as np


class MaskError(ValueError):
    pass


def mask_to_polygon(
    mask: np.ndarray, tolerance_px: float = 1.0
) -> list[tuple[float, float]]:
    if mask.ndim != 2:
        raise MaskError("mask must be a 2-D array")
    binary = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        raise MaskError("mask contains no contour")
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) <= 0:
        raise MaskError("mask contour has zero area")
    epsilon = max(0.0, float(tolerance_px))
    approximation = (
        cv2.approxPolyDP(contour, epsilon, True) if epsilon > 0 else contour
    )
    points = [
        (float(point[0][0]), float(point[0][1]))
        for point in approximation
    ]
    if len(points) < 3:
        raise MaskError("mask contour has fewer than three points")
    if points[0] != points[-1]:
        points.append(points[0])
    return points
