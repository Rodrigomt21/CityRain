import cv2
import os
import time
from datetime import datetime

os.makedirs("/home/maua/frames", existok = True)

cap = cv2.VideoCapture(0)

if not cap.isOpened():
        exit(1)


while True:
        ret, frame = cap.read()
        if not ret:
                time.sleep(5)
                continue

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        caminho = os.path.join("frames", "frame_%s.jpg" % timestamp)
        cv2.imwrite(caminho, frame)

        time.sleep(1)


cap.release()
