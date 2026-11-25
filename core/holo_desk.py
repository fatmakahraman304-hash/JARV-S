"""Local spatial desk geometry and hand input. Never executes imported code."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from urllib.request import urlopen

import numpy as np

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_SHA = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def model_path():
    from memory.continuity import data_dir
    return data_dir() / "holo-desk" / "hand_landmarker.task"


def valid_model(path):
    try:
        return Path(path).stat().st_size == 7819105 and hashlib.sha256(Path(path).read_bytes()).hexdigest() == MODEL_SHA
    except OSError:
        return False


def install_tracking(log=print):
    """Only called from a worker after the user's explicit setup click."""
    from importlib.util import find_spec
    if find_spec("mediapipe") is None:
        from core.installer import _pip
        if not _pip("mediapipe>=0.10.31,<0.11", log=log,extra_packages=("opencv-contrib-python>=4.8,<5",)):
            raise RuntimeError("MediaPipe kurulamadı. Kamerayı açmadan FRIDAY’ı yeniden başlatıp kurulumu tekrar deneyin; Python paket uyumluluğunu kontrol edin.")
    path = model_path()
    if valid_model(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".download")
    try:
        with urlopen(MODEL_URL, timeout=30) as response:
            data = response.read(9000000)
        if len(data) != 7819105 or hashlib.sha256(data).hexdigest() != MODEL_SHA:
            raise ValueError("El modeli bütünlük doğrulamasından geçmedi.")
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


class HandTracker:
    def __init__(self, path=None):
        import mediapipe as mp
        self.mp = mp
        path = path or model_path()
        if not valid_model(path):
            raise RuntimeError("Önce El takibini kur düğmesiyle modeli hazırla.")
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
            min_hand_detection_confidence=.55, min_hand_presence_confidence=.55,
            min_tracking_confidence=.55)
        self.detector = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.timestamp = -1

    def detect(self, rgb, timestamp_ms):
        self.timestamp = max(self.timestamp + 1, int(timestamp_ms))
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self.detector.detect_for_video(image, self.timestamp)
        return [{"id": side[0].category_name, "score": float(side[0].score),
                 "points": [[p.x, p.y, p.z] for p in points]}
                for points, side in zip(result.hand_landmarks, result.handedness)]

    def close(self):
        self.detector.close()


class Hands:
    """Hysteresis and smoothing; release immediately on tracking loss."""
    def __init__(self):
        self.previous = {}

    def update(self, values, aspect=1.0):
        output = {}
        for value in values[:2]:
            try:
                points = np.asarray(value["points"], dtype=float)
                if points.shape != (21, 3) or not np.isfinite(points).all() or value.get("score", 0) < .55:
                    continue
                if np.max(np.abs(points[:, :2])) > 2:
                    continue
                hand_id = str(value["id"])
                width = np.linalg.norm(points[5, :2] - points[17, :2])
                if width < .025:
                    continue
                old = self.previous.get(hand_id)
                metric=np.array([max(.2,min(5.,float(aspect))),1.])
                ratio = np.linalg.norm((points[4, :2] - points[8, :2])*metric) / np.linalg.norm((points[5,:2]-points[17,:2])*metric)
                pinch = ratio < (.48 if old and old["pinch"] else .32)
                pointer = (points[4, :2] + points[8, :2]) / 2
                palm = points[[0, 5, 9, 13, 17], :2].mean(axis=0)
                # Reacquisition far from the previous hand starts a new grip.
                continuous = old and np.linalg.norm(pointer - old["pointer"]) < .30
                if continuous:
                    pointer = .45 * pointer + .55 * old["pointer"]
                output[hand_id] = {"id": hand_id, "points": points, "palm": palm,
                    "pointer": pointer, "pinch": pinch,
                    "down": pinch and not (continuous and old["pinch"]), "width": width}
            except (KeyError, TypeError, ValueError):
                continue
        self.previous = output
        return list(output.values())


def mesh(shape="Çekirdek"):
    if shape == "Küp":
        v = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], float)
        f = np.array([[0,3,2],[0,2,1],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                      [3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]], int)
    elif shape == "Piramit":
        v = np.array([[-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1],[0,1.3,0]],float)
        f = np.array([[0,2,1],[0,3,2],[0,1,4],[1,2,4],[2,3,4],[3,0,4]],int)
    else:
        v, f = [], []
        rows, cols = (18, 28) if shape == "Küre" else (16, 40)
        for i in range(rows + 1):
            for j in range(cols):
                a, b = i/rows*math.pi, j/cols*math.tau
                if shape == "Küre":
                    point = [math.sin(a)*math.cos(b), math.cos(a), math.sin(a)*math.sin(b)]
                else:
                    a = i/rows*math.tau
                    point = [(1+.30*math.cos(a))*math.cos(b), .30*math.sin(a), (1+.30*math.cos(a))*math.sin(b)]
                v.append(point)
        for i in range(rows):
            for j in range(cols):
                a,b=i*cols+j,i*cols+(j+1)%cols
                c,d=a+cols,b+cols
                f.extend([[a,c,b],[b,c,d]])
        v,f=np.asarray(v,float),np.asarray(f,int)
    return v, f


def parse_obj(text):
    """Bounded vertex/face reader. No materials, paths, commands or Python."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2000000:
        raise ValueError("OBJ en fazla 2 MB olabilir.")
    vertices, faces = [], []
    for line in text.splitlines():
        parts = line.partition("#")[0].split()
        if not parts:
            continue
        if parts[0] == "v":
            if len(parts) < 4 or len(vertices) >= 10000:
                raise ValueError("Geçersiz veya fazla OBJ köşesi.")
            vertex = [float(x) for x in parts[1:4]]
            if not all(math.isfinite(x) and abs(x) < 1e8 for x in vertex):
                raise ValueError("Geçersiz OBJ koordinatı.")
            vertices.append(vertex)
        elif parts[0] == "f":
            if not 4 <= len(parts) <= 65:
                raise ValueError("Geçersiz OBJ yüzü.")
            indices = [int(p.split("/")[0]) for p in parts[1:]]
            indices = [n-1 if n>0 else len(vertices)+n if n<0 else -1 for n in indices]
            if not all(0 <= n < len(vertices) for n in indices):
                raise ValueError("OBJ yüzü olmayan bir köşeyi kullanıyor.")
            faces.extend([[indices[0],indices[j],indices[j+1]] for j in range(1,len(indices)-1)])
            if len(faces) > 10000:
                raise ValueError("OBJ en fazla 10000 üçgen olabilir.")
    if not vertices or not faces:
        raise ValueError("OBJ köşe ve yüz bilgisi içermeli.")
    v = np.array(vertices,float)
    v -= (v.max(axis=0)+v.min(axis=0))/2
    span = np.max(np.linalg.norm(v,axis=1))
    if span < 1e-8:
        raise ValueError("OBJ boyutu sıfır.")
    return v/span*1.25,np.array(faces,int)


def obj_text(vertices, faces):
    return "# FRIDAY Holo Masa — yerel 3D nesne\n" + "".join(
        "v %.7f %.7f %.7f\n" % tuple(v) for v in vertices) + "".join(
        "f %d %d %d\n" % tuple(f+1) for f in faces)


def project(vertices, yaw, pitch, scale=1.0):
    """Perspective geometry; scale limits keep the camera outside the mesh."""
    yaw, pitch = float(yaw), float(pitch)
    if not math.isfinite(yaw+pitch+float(scale)):
        raise ValueError("Geçersiz görünüm")
    scale = max(.25,min(2.5,float(scale)))
    cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rx=np.array([[1,0,0],[0,cp,-sp],[0,sp,cp]])
    posed=np.asarray(vertices)@ry.T@rx.T
    perspective=5/(5-posed[:,2]*.4)
    return posed, posed[:,:2]*perspective[:,None]*scale
