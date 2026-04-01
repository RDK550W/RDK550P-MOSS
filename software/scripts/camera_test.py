#!/usr/bin/env python3
"""Minimal MIPI camera capture test for RDK X5"""

import numpy as np
import cv2

try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy

WIDTH = 1920
HEIGHT = 1080

print("Opening MIPI camera...")
cam = srcampy.Camera()
# open_cam(pipe_id, video_index, fps, width_list, height_list, sensor_h, sensor_w)
# Use -1 for auto-detect on video_index and fps
cam.open_cam(0, -1, -1, [WIDTH], [HEIGHT], HEIGHT, WIDTH)

print("Capturing frame...")
# get_img(channel, width, height) - channel 2 for NV12 output
img_data = cam.get_img(2, WIDTH, HEIGHT)

if img_data is not None:
    nv12 = np.frombuffer(img_data, dtype=np.uint8).reshape(HEIGHT * 3 // 2, WIDTH)
    bgr = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
    out_path = "/root/.openclaw/workspace/capture.jpg"
    cv2.imwrite(out_path, bgr)
    print(f"Saved to {out_path} ({bgr.shape[1]}x{bgr.shape[0]})")
else:
    print("ERROR: got no image data from camera")

cam.close_cam()
print("Camera closed.")
