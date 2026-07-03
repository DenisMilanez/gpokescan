# -*- coding: utf-8 -*-
"""
IO de imagem seguro para caminhos com acento (Unicode) no Windows.

O cv2.imread/imwrite do OpenCV usa a API ANSI no Windows e FALHA (silenciosamente)
com caminhos que tenham acento — como a nossa pasta 'calibração'. Aqui usamos o IO
do numpy (fromfile/tofile), que respeita Unicode, e o cv2.imdecode/imencode.
"""

import os

import cv2
import numpy as np


def imread(caminho, flags=cv2.IMREAD_COLOR):
    """Le uma imagem de qualquer caminho (inclusive com acento). None se falhar."""
    try:
        dados = np.fromfile(str(caminho), dtype=np.uint8)
        if dados.size == 0:
            return None
        return cv2.imdecode(dados, flags)
    except Exception:
        return None


def imdecode(raw, flags=cv2.IMREAD_COLOR):
    """Decodifica bytes de imagem (ex.: PNG do screencap) em array. None se falhar."""
    try:
        if not raw:
            return None
        return cv2.imdecode(np.frombuffer(raw, np.uint8), flags)
    except Exception:
        return None


def imwrite(caminho, img):
    """Grava uma imagem em qualquer caminho (inclusive com acento). True/False."""
    ext = os.path.splitext(str(caminho))[1] or ".png"
    try:
        ok, buf = cv2.imencode(ext, img)
        if not ok:
            return False
        buf.tofile(str(caminho))
        return True
    except Exception:
        return False
