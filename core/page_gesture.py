"""Local motion recognition for turning HUD pages with a horizontal swipe."""

import time


class PageSwipe:
    def __init__(self):
        self.previous = None
        self.origin = 0
        self.motion = 0
        self.steps = 0
        self.started = 0
        self.last_turn = float("-inf")

    def feed(self, frame):
        import cv2
        import numpy as np

        # Use the center of the image, where the reader waves their hand.
        image = cv2.resize(frame, (240, 160))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[30:130, 20:220]
        previous, self.previous = self.previous, gray
        now = time.monotonic()
        if previous is None or now - self.last_turn < 1.0:
            return 0
        changed = cv2.absdiff(previous, gray) > 24
        ys, xs = np.nonzero(changed)
        # Ignore still scenes, tiny motion and large lighting changes.
        if not 280 <= len(xs) <= 5700 or np.ptp(ys) < 9 or np.ptp(xs) > 145:
            self.steps = 0
            return 0
        x = float(np.median(xs))
        delta = x - self.motion
        if not self.steps or now - self.started > .8 or abs(delta) > 62:
            self.origin, self.started, self.steps = x, now, 1
        elif abs(delta) >= 3:
            self.steps += 1
        self.motion = x
        if self.steps >= 3 and abs(x - self.origin) >= 55:
            self.steps = 0
            self.last_turn = now
            return 1 if x < self.origin else -1
        return 0
