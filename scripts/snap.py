#!/usr/bin/env python3
"""Quick MIPI camera snapshot. Usage: snap.py [output.jpg]"""
import sys, numpy as np, cv2

try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy

out = sys.argv[1] if len(sys.argv) > 1 else "/root/.openclaw/workspace/media/snapshot.jpg"
cam = srcampy.Camera()
cam.open_cam(0, -1, -1, [1920], [1080], 1080, 1920)
nv12 = cam.get_img(2, 1920, 1080)
cam.close_cam()
if nv12 is None:
    print("ERROR: capture failed"); sys.exit(1)
bgr = cv2.cvtColor(np.frombuffer(nv12, dtype=np.uint8).reshape(1620, 1920), cv2.COLOR_YUV2BGR_NV12)
cv2.imwrite(out, bgr)
print(f"OK: {out}")
