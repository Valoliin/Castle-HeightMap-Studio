#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Castle HeightMap Studio v4.2
============================

Éditeur de textures / height-maps pour façades imprimées en 3D.

Fonctions principales :
- plusieurs images / calques ;
- déplacement direct dans le cadre du mur ;
- 8 poignées de redimensionnement façon traitement de texte ;
- étirement libre X/Y ;
- fond noir = relief nul ;
- chevauchement + raccord doux ;
- raccord automatique par recherche locale de motif ;
- réglages HSV / niveaux / gamma ;
- aperçu 3D ;
- export PNG height-map ;
- export STEP OpenCascade/CadQuery.

Le STEP est produit en loft lissé par défaut.
"""

from __future__ import annotations

import math
import re
import threading
import traceback
import time
import logging
import json
import io
import zipfile
import copy
import os
import sys
import platform
import webbrowser
import urllib.request
import urllib.error
import subprocess
import configparser
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageTk


APP_TITLE = "Castle HeightMap Studio v4.3"

APP_NAME = "Castle HeightMap Studio"
APP_VERSION = "4.3"
APP_AUTHOR = "Valentin Bonali"


def resource_path(relative: str) -> Path:
    """
    Chemin d'une ressource aussi bien depuis les sources que depuis PyInstaller.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def parse_version(value: str):
    nums = re.findall(r"\d+", value or "")
    return tuple(int(x) for x in nums[:4]) or (0,)


def detect_github_repo() -> str:
    """
    Ordre :
    1. update_config.json à côté de l'exécutable ;
    2. update_config.json embarqué ;
    3. variable GITHUB_REPOSITORY ;
    4. remote origin de .git/config.
    """
    candidates = [
        executable_dir() / "update_config.json",
        resource_path("update_config.json"),
    ]

    for path in candidates:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                repo = str(data.get("github_repo", "")).strip()
                if repo and "/" in repo and "YOUR_" not in repo:
                    return repo
        except Exception:
            pass

    env_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if env_repo and "/" in env_repo:
        return env_repo

    # Recherche du .git parent depuis le dossier du programme.
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        git_config = parent / ".git" / "config"
        if not git_config.exists():
            continue
        try:
            cfg = configparser.ConfigParser()
            cfg.read(git_config, encoding="utf-8")
            for section in cfg.sections():
                if not section.startswith('remote "origin"'):
                    continue
                url = cfg.get(section, "url", fallback="")
                m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", url.strip())
                if m:
                    return f"{m.group(1)}/{m.group(2)}"
        except Exception:
            pass

    return ""


EDITOR_MIN_W = 700
EDITOR_MIN_H = 440
HEIGHT_PREVIEW_W = 430
HEIGHT_PREVIEW_H = 440

HANDLE_SIZE = 9
MIN_LAYER_SIZE = 0.02  # fraction de la dimension du mur


LOG_FILENAME = "castle_heightmap.log"


class AppLogger:
    """
    Logger double sortie :
    - fichier castle_heightmap.log dans le dossier du programme ;
    - callback optionnel vers l'interface graphique.
    """
    def __init__(self):
        self.ui_callback = None
        self.log_path = Path(__file__).resolve().parent / LOG_FILENAME

        self.logger = logging.getLogger("CastleHeightMapStudio")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        if not self.logger.handlers:
            handler = logging.FileHandler(
                self.log_path,
                encoding="utf-8",
            )
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self.logger.addHandler(handler)

    def set_ui_callback(self, callback):
        self.ui_callback = callback

    def _emit(self, level, message):
        getattr(self.logger, level)(message)
        if self.ui_callback:
            try:
                self.ui_callback(
                    level.upper(),
                    message,
                )
            except Exception:
                pass

    def debug(self, message):
        self._emit("debug", message)

    def info(self, message):
        self._emit("info", message)

    def warning(self, message):
        self._emit("warning", message)

    def error(self, message):
        self._emit("error", message)

    def exception(self, message):
        self.logger.exception(message)
        if self.ui_callback:
            try:
                self.ui_callback(
                    "ERROR",
                    message + " — voir le fichier log pour la traceback.",
                )
            except Exception:
                pass


APP_LOG = AppLogger()


def fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds*1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes} min {rest:.1f} s"



def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def parse_float(text: str, name: str) -> float:
    try:
        return float(text.replace(",", "."))
    except Exception:
        raise ValueError(f"Valeur invalide pour « {name} ».")


def adjust_hsv_rgb(
    img: Image.Image,
    hue_shift_deg: float,
    saturation_pct: float,
    value_pct: float,
) -> Image.Image:
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32).copy()

    hue_delta = (float(hue_shift_deg) / 360.0) * 255.0
    hsv[..., 0] = np.mod(hsv[..., 0] + hue_delta, 256.0)

    hsv[..., 1] = np.clip(
        hsv[..., 1] * (float(saturation_pct) / 100.0), 0, 255
    )
    hsv[..., 2] = np.clip(
        hsv[..., 2] * (float(value_pct) / 100.0), 0, 255
    )

    return Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")


def image_to_heightmap(
    img: Image.Image,
    hue_shift_deg: float = 0.0,
    saturation_pct: float = 100.0,
    value_pct: float = 100.0,
    contrast_pct: float = 120.0,
    black_level_pct: float = 5.0,
    white_level_pct: float = 95.0,
    gamma: float = 1.0,
    blur_radius: float = 0.6,
    invert: bool = False,
) -> Image.Image:
    rgb = adjust_hsv_rgb(
        img.convert("RGB"),
        hue_shift_deg,
        saturation_pct,
        value_pct,
    )

    gray = ImageOps.grayscale(rgb)

    if abs(float(contrast_pct) - 100.0) > 0.001:
        gray = ImageEnhance.Contrast(gray).enhance(float(contrast_pct) / 100.0)

    arr = np.asarray(gray, dtype=np.float32) / 255.0

    lo = clamp(float(black_level_pct) / 100.0, 0.0, 0.98)
    hi = clamp(float(white_level_pct) / 100.0, 0.02, 1.0)

    if hi <= lo + 0.01:
        hi = min(1.0, lo + 0.01)

    arr = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    arr = np.power(arr, max(0.05, float(gamma)))

    out = Image.fromarray(
        np.uint8(np.clip(arr * 255.0, 0, 255)),
        "L",
    )

    if float(blur_radius) > 0:
        out = out.filter(ImageFilter.GaussianBlur(float(blur_radius)))

    if invert:
        out = ImageOps.invert(out)

    return out


@dataclass
class TextureLayer:
    name: str
    path: str
    image: Image.Image

    # Coordonnées normalisées par rapport au rectangle du mur.
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0

    visible: bool = True
    locked: bool = False
    rotation_deg: float = 0.0
    lock_aspect: bool = False

    # Pour les calques additionnels : fondu sur les bords.
    feather_pct: float = 6.0

    uid: int = field(default=0)


@dataclass
class MaskShape:
    # kind = brush / rect / ellipse
    kind: str
    uid: int
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    points: list = field(default_factory=list)
    brush_mm: float = 5.0


def wall_rect(canvas_w: int, canvas_h: int, aspect: float):
    margin = 28.0
    aw = max(10.0, canvas_w - 2 * margin)
    ah = max(10.0, canvas_h - 2 * margin)
    aspect = max(0.01, aspect)

    if aw / ah > aspect:
        h = ah
        w = h * aspect
    else:
        w = aw
        h = w / aspect

    cx = canvas_w / 2
    cy = canvas_h / 2

    return (
        cx - w / 2,
        cy - h / 2,
        cx + w / 2,
        cy + h / 2,
    )


def norm_to_canvas(layer: TextureLayer, rect):
    x0, y0, x1, y1 = rect
    rw = x1 - x0
    rh = y1 - y0

    return (
        x0 + layer.x * rw,
        y0 + layer.y * rh,
        x0 + (layer.x + layer.w) * rw,
        y0 + (layer.y + layer.h) * rh,
    )


def canvas_delta_to_norm(dx, dy, rect):
    x0, y0, x1, y1 = rect
    rw = max(1.0, x1 - x0)
    rh = max(1.0, y1 - y0)
    return dx / rw, dy / rh


def make_edge_feather_mask(width: int, height: int, feather_pct: float) -> Image.Image:
    """
    Masque alpha : opaque au centre, fondu progressif vers les 4 bords.
    Le fondu n'est appliqué que si feather_pct > 0.
    """
    if feather_pct <= 0 or width <= 2 or height <= 2:
        return Image.new("L", (width, height), 255)

    fx = max(1, int(width * feather_pct / 100.0))
    fy = max(1, int(height * feather_pct / 100.0))

    x = np.arange(width, dtype=np.float32)
    y = np.arange(height, dtype=np.float32)

    dx = np.minimum(x, width - 1 - x)
    dy = np.minimum(y, height - 1 - y)

    ax = np.clip(dx / max(1, fx), 0.0, 1.0)
    ay = np.clip(dy / max(1, fy), 0.0, 1.0)

    # Le minimum donne un fondu propre sur chaque bord et dans les coins.
    alpha = np.minimum(ay[:, None], ax[None, :])

    # Courbe douce (smoothstep)
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)

    return Image.fromarray(np.uint8(np.clip(alpha * 255.0, 0, 255)), "L")


def paste_layer_to_wall(
    base: Image.Image,
    layer: TextureLayer,
    feather: bool = True,
):
    """
    Compose un calque dans une image de la taille du mur.
    Les coordonnées du calque peuvent sortir du mur.
    """
    if not layer.visible:
        return

    W, H = base.size

    left = int(round(layer.x * W))
    top = int(round(layer.y * H))
    right = int(round((layer.x + layer.w) * W))
    bottom = int(round((layer.y + layer.h) * H))

    dw = max(1, right - left)
    dh = max(1, bottom - top)

    # La déformation X/Y libre est volontaire.
    resized = layer.image.resize((dw, dh), Image.Resampling.LANCZOS).convert("RGBA")

    feather_pct = layer.feather_pct if feather else 0.0
    mask = make_edge_feather_mask(dw, dh, feather_pct)
    resized.putalpha(mask)

    # Rotation autour du centre du calque. Les dimensions w/h restent celles
    # du rectangle de travail ; la rotation peut dépasser et sera simplement
    # coupée par les limites du mur lors du composite.
    angle = float(getattr(layer, "rotation_deg", 0.0))
    if abs(angle) > 1e-6:
        resized = resized.rotate(
            -angle,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        left = int(round((left + right) / 2 - resized.width / 2))
        top = int(round((top + bottom) / 2 - resized.height / 2))

    base.alpha_composite(resized, dest=(left, top))


def compose_layers(
    layers: list[TextureLayer],
    size: tuple[int, int],
    include_feather: bool = True,
    exclude_uid: Optional[int] = None,
) -> Image.Image:
    """
    Composite toutes les textures sur fond noir.
    Les zones sans texture restent donc noires = relief nul.
    """
    W, H = size
    base = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    visible = [
        layer for layer in layers
        if layer.visible and layer.uid != exclude_uid
    ]

    for idx, layer in enumerate(visible):
        # Le premier calque visible sert généralement de base : on évite de
        # le faire fondre vers du noir sur ses bords.
        old = layer.feather_pct
        if idx == 0:
            layer.feather_pct = 0.0
        try:
            paste_layer_to_wall(base, layer, feather=include_feather)
        finally:
            layer.feather_pct = old

    return base.convert("RGB")


def overlap_bbox_px(layer: TextureLayer, W: int, H: int):
    left = int(round(layer.x * W))
    top = int(round(layer.y * H))
    right = int(round((layer.x + layer.w) * W))
    bottom = int(round((layer.y + layer.h) * H))

    return (
        max(0, left),
        max(0, top),
        min(W, right),
        min(H, bottom),
    )


def _gradient_map(arr: np.ndarray) -> np.ndarray:
    """
    Carte de contours simple et légère.
    Pour un mur en pierre, les joints sont plus fiables pour l'alignement
    que la luminosité brute des pierres.
    """
    arr = arr.astype(np.float32)
    gy, gx = np.gradient(arr)
    mag = np.hypot(gx, gy)

    # Normalisation robuste.
    p = float(np.percentile(mag, 95))
    if p > 1e-6:
        mag = np.clip(mag / p, 0.0, 1.0)

    return mag


def _processed_layer_array(
    layer: TextureLayer,
    size: tuple[int, int],
    *,
    hue_shift_deg: float,
    saturation_pct: float,
    value_pct: float,
    contrast_pct: float,
    black_level_pct: float,
    white_level_pct: float,
    gamma: float,
    blur_radius: float,
    invert: bool,
) -> np.ndarray:
    W, H = size
    dw = max(2, int(round(layer.w * W)))
    dh = max(2, int(round(layer.h * H)))

    resized = layer.image.resize(
        (dw, dh),
        Image.Resampling.BILINEAR,
    )

    hm = image_to_heightmap(
        resized,
        hue_shift_deg=hue_shift_deg,
        saturation_pct=saturation_pct,
        value_pct=value_pct,
        contrast_pct=contrast_pct,
        black_level_pct=black_level_pct,
        white_level_pct=white_level_pct,
        gamma=gamma,
        blur_radius=blur_radius,
        invert=invert,
    )

    return np.asarray(hm, dtype=np.float32) / 255.0


def auto_match_layer(
    layers: list[TextureLayer],
    selected: TextureLayer,
    search_px: int = 60,
    preview_size: tuple[int, int] = (700, 260),
    *,
    hue_shift_deg: float = 0.0,
    saturation_pct: float = 100.0,
    value_pct: float = 100.0,
    contrast_pct: float = 120.0,
    black_level_pct: float = 5.0,
    white_level_pct: float = 95.0,
    gamma: float = 1.0,
    blur_radius: float = 0.6,
    invert: bool = False,
):
    """
    Aligne le calque sélectionné sur les autres en comparant LA HEIGHT-MAP
    réellement affichée, donc après HSV / niveaux / gamma / lissage.

    Le score combine :
    - la corrélation des contours (très importante pour les joints de pierre) ;
    - la corrélation de hauteur ;
    - une petite pénalité de déplacement pour éviter de sauter d'une rangée
      de briques vers une autre quand le motif est répétitif.

    Cela améliore nettement les raccords, mais une photo non répétable ne peut
    toujours pas devenir mathématiquement raccordable par simple translation.
    Pour ce cas, utiliser les duplications miroir.
    """
    W, H = preview_size

    # Les autres calques composés sans feather, puis transformés exactement
    # avec les mêmes réglages que la height-map finale.
    under_rgb = compose_layers(
        layers,
        preview_size,
        include_feather=False,
        exclude_uid=selected.uid,
    )

    under_hm = image_to_heightmap(
        under_rgb,
        hue_shift_deg=hue_shift_deg,
        saturation_pct=saturation_pct,
        value_pct=value_pct,
        contrast_pct=contrast_pct,
        black_level_pct=black_level_pct,
        white_level_pct=white_level_pct,
        gamma=gamma,
        blur_radius=blur_radius,
        invert=invert,
    )

    under = np.asarray(under_hm, dtype=np.float32) / 255.0

    if float(under.max()) < 0.02:
        raise ValueError(
            "Il n'y a pas d'autre texture exploitable sous ce calque."
        )

    sel = _processed_layer_array(
        selected,
        preview_size,
        hue_shift_deg=hue_shift_deg,
        saturation_pct=saturation_pct,
        value_pct=value_pct,
        contrast_pct=contrast_pct,
        black_level_pct=black_level_pct,
        white_level_pct=white_level_pct,
        gamma=gamma,
        blur_radius=blur_radius,
        invert=invert,
    )

    under_edges = _gradient_map(under)
    sel_edges = _gradient_map(sel)

    base_left = int(round(selected.x * W))
    base_top = int(round(selected.y * H))

    # Recherche proportionnelle à la taille du calque, mais sans partir
    # à l'autre bout du mur.
    adaptive = max(
        18,
        min(
            int(search_px),
            int(max(sel.shape[1], sel.shape[0]) * 0.18),
        ),
    )

    coarse_step = max(2, adaptive // 14)
    candidates = []

    for dy in range(-adaptive, adaptive + 1, coarse_step):
        for dx in range(-adaptive, adaptive + 1, coarse_step):
            score = _processed_match_score(
                under,
                under_edges,
                sel,
                sel_edges,
                base_left + dx,
                base_top + dy,
                dx,
                dy,
                adaptive,
            )
            if score is not None:
                candidates.append((score, dx, dy))

    if not candidates:
        raise ValueError(
            "Aucune zone de chevauchement suffisante. Fais se recouvrir "
            "les deux textures d'environ 10 à 30 %, puis relance « Raccord auto »."
        )

    candidates.sort(key=lambda x: x[0])
    _, best_dx, best_dy = candidates[0]

    # Recherche fine autour du meilleur candidat.
    fine_radius = max(3, coarse_step + 1)
    fine = []

    for dy in range(best_dy - fine_radius, best_dy + fine_radius + 1):
        for dx in range(best_dx - fine_radius, best_dx + fine_radius + 1):
            score = _processed_match_score(
                under,
                under_edges,
                sel,
                sel_edges,
                base_left + dx,
                base_top + dy,
                dx,
                dy,
                adaptive,
            )
            if score is not None:
                fine.append((score, dx, dy))

    if fine:
        fine.sort(key=lambda x: x[0])
        _, best_dx, best_dy = fine[0]

    selected.x += best_dx / W
    selected.y += best_dy / H

    return best_dx, best_dy


def _normalized_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 10 or b.size < 10:
        return 0.0

    a = a.astype(np.float32)
    b = b.astype(np.float32)

    a = a - float(a.mean())
    b = b - float(b.mean())

    sa = float(a.std())
    sb = float(b.std())

    if sa < 1e-5 or sb < 1e-5:
        return 0.0

    return float(np.mean(a * b) / (sa * sb + 1e-7))


def _processed_match_score(
    background: np.ndarray,
    background_edges: np.ndarray,
    selected: np.ndarray,
    selected_edges: np.ndarray,
    left: int,
    top: int,
    dx: int,
    dy: int,
    search_radius: int,
):
    H, W = background.shape
    sh, sw = selected.shape

    x0 = max(0, left)
    y0 = max(0, top)
    x1 = min(W, left + sw)
    y1 = min(H, top + sh)

    ow = x1 - x0
    oh = y1 - y0

    if ow < 16 or oh < 16:
        return None

    sx0 = x0 - left
    sy0 = y0 - top
    sx1 = sx0 + ow
    sy1 = sy0 + oh

    bg = background[y0:y1, x0:x1]
    fg = selected[sy0:sy1, sx0:sx1]

    bge = background_edges[y0:y1, x0:x1]
    fge = selected_edges[sy0:sy1, sx0:sx1]

    # On ignore le vrai fond noir du mur, mais on conserve les joints noirs
    # internes grâce à un masque dilaté implicitement par les contours.
    support = (bg > 0.02) | (bge > 0.08)

    min_support = max(180, int(ow * oh * 0.10))
    if int(support.sum()) < min_support:
        return None

    corr_height = _normalized_corr(bg[support], fg[support])
    corr_edges = _normalized_corr(bge[support], fge[support])

    # Les contours sont prioritaires : pour des pierres, aligner les joints
    # est plus important qu'aligner les variations de gris dans une pierre.
    similarity = 0.72 * corr_edges + 0.28 * corr_height

    # Motifs répétitifs = plusieurs maxima plausibles.
    # Petite préférence pour le candidat le plus proche de la position manuelle.
    radius = max(1.0, float(search_radius))
    displacement = math.sqrt(dx * dx + dy * dy) / radius
    penalty = 0.10 * displacement * displacement

    # On minimise le score.
    return -similarity + penalty



def make_seamless_mirror_tile(img: Image.Image) -> Image.Image:
    """
    Fabrique une texture répétable par miroir interne.

    On construit un motif 2x2 miroir puis on recadre au centre. Les bords
    opposés du résultat sont donc continus pixel pour pixel. C'est volontairement
    plus prévisible qu'un remplissage génératif pour une height-map technique.
    """
    src = img.convert("RGB")
    w, h = src.size
    if w < 2 or h < 2:
        return src.copy()

    big = Image.new("RGB", (w * 2, h * 2))
    big.paste(src, (0, 0))
    big.paste(ImageOps.mirror(src), (w, 0))
    flipped = ImageOps.flip(src)
    big.paste(flipped, (0, h))
    big.paste(ImageOps.mirror(flipped), (w, h))

    left = w // 2
    top = h // 2
    return big.crop((left, top, left + w, top + h))


def apply_masks_to_heightmap(
    heightmap: Image.Image,
    masks: list[MaskShape],
    wall_w_mm: float,
    wall_h_mm: float,
) -> Image.Image:
    """Applique les masques globaux : zone masquée => noir => relief nul."""
    if not masks:
        return heightmap

    from PIL import ImageDraw

    out = heightmap.copy().convert("L")
    draw = ImageDraw.Draw(out)
    W, H = out.size

    for mask in masks:
        if mask.kind == "rect":
            x0 = int(round(mask.x * W))
            y0 = int(round(mask.y * H))
            x1 = int(round((mask.x + mask.w) * W))
            y1 = int(round((mask.y + mask.h) * H))
            draw.rectangle((x0, y0, x1, y1), fill=0)
        elif mask.kind == "ellipse":
            x0 = int(round(mask.x * W))
            y0 = int(round(mask.y * H))
            x1 = int(round((mask.x + mask.w) * W))
            y1 = int(round((mask.y + mask.h) * H))
            draw.ellipse((x0, y0, x1, y1), fill=0)
        elif mask.kind == "brush" and mask.points:
            # brush_mm est converti en pixels à partir de la largeur du mur ;
            # on moyenne X/Y pour rester cohérent si le ratio écran diffère.
            px_per_mm_x = W / max(1e-9, float(wall_w_mm))
            px_per_mm_y = H / max(1e-9, float(wall_h_mm))
            width_px = max(1, int(round(mask.brush_mm * (px_per_mm_x + px_per_mm_y) / 2)))
            pts = [(int(round(x * W)), int(round(y * H))) for x, y in mask.points]
            if len(pts) == 1:
                x, y = pts[0]
                r = width_px // 2
                draw.ellipse((x-r, y-r, x+r, y+r), fill=0)
            else:
                draw.line(pts, fill=0, width=width_px, joint="curve")
                r = width_px // 2
                for x, y in (pts[0], pts[-1]):
                    draw.ellipse((x-r, y-r, x+r, y+r), fill=0)

    return out


def _rdp_profile(points, epsilon):
    """Ramer-Douglas-Peucker sur un profil (x,z)."""
    if len(points) <= 2:
        return points

    p0 = np.asarray(points[0], dtype=float)
    p1 = np.asarray(points[-1], dtype=float)
    v = p1 - p0
    vv = float(np.dot(v, v))

    max_dist = -1.0
    max_idx = 0
    for i in range(1, len(points)-1):
        p = np.asarray(points[i], dtype=float)
        if vv < 1e-12:
            dist = float(np.linalg.norm(p-p0))
        else:
            t = clamp(float(np.dot(p-p0, v) / vv), 0.0, 1.0)
            proj = p0 + t*v
            dist = float(np.linalg.norm(p-proj))
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > epsilon:
        left = _rdp_profile(points[:max_idx+1], epsilon)
        right = _rdp_profile(points[max_idx:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]


def _nearest_source_index(xs: np.ndarray, x: float) -> int:
    idx = int(np.searchsorted(xs, x))
    if idx <= 0:
        return 0
    if idx >= len(xs):
        return len(xs) - 1
    return idx if abs(float(xs[idx]) - x) < abs(float(xs[idx - 1]) - x) else idx - 1


def adaptive_profile_indices(
    xs: np.ndarray,
    zs: np.ndarray,
    tolerance_mm: float,
    sample_mm: float,
    base_mm: float,
    density_factor: float = 1.0,
):
    """
    Simplification adaptée aux B-Splines OpenCascade.

    RDP seul est insuffisant : une polyligne peut respecter la tolérance alors
    qu'une spline interpolante oscille fortement entre les points conservés.
    """
    n = len(xs)
    if n <= 4:
        return list(range(n))

    density = max(0.12, min(1.0, float(density_factor)))
    tol = max(0.001, float(tolerance_mm)) * density
    sample = max(1e-6, float(sample_mm))

    keep = {0, n - 1}

    # Points importants détectés par RDP.
    raw_pts = [(float(x), float(z)) for x, z in zip(xs, zs)]
    for x, _z in _rdp_profile(raw_pts, tol):
        keep.add(_nearest_source_index(xs, x))

    # Limite stricte de l'espacement. À 0,5 mm : 2 mm au premier essai.
    nominal_max_spacing = max(sample, min(2.0, sample * 4.0))
    max_spacing = max(sample, nominal_max_spacing * density)
    max_stride = max(1, int(math.floor(max_spacing / sample)))

    for i in range(0, n, max_stride):
        keep.add(i)
    keep.add(n - 1)

    # Garde les voisins des changements de pente/hauteur importants.
    dz = np.abs(np.diff(zs))
    sharp_threshold = max(0.012, float(tolerance_mm) * 0.45)
    for i in np.where(dz >= sharp_threshold)[0]:
        for k in range(i - 3, i + 5):
            if 0 <= k < n:
                keep.add(k)

    # Garde encore davantage de points aux transitions fond <-> relief.
    base_eps = max(0.008, float(tolerance_mm) * 0.30)
    is_base = np.abs(zs - float(base_mm)) <= base_eps
    for i in np.where(is_base[:-1] != is_base[1:])[0]:
        for k in range(i - 7, i + 9):
            if 0 <= k < n:
                keep.add(k)

    ids = sorted(keep)

    # Aucun intervalle résiduel ne peut dépasser max_stride.
    out = [ids[0]]
    for target in ids[1:]:
        prev = out[-1]
        while target - prev > max_stride:
            prev = min(target, prev + max_stride)
            out.append(prev)
        if out[-1] != target:
            out.append(target)

    return sorted(set(out))


def simplify_profile(
    xs: np.ndarray,
    zs: np.ndarray,
    tolerance_mm: float,
    sample_mm: float = 1.0,
    base_mm: float = 0.0,
    density_factor: float = 1.0,
):
    ids = adaptive_profile_indices(
        xs,
        zs,
        tolerance_mm,
        sample_mm,
        base_mm,
        density_factor,
    )
    return [(float(xs[i]), float(zs[i])) for i in ids]


def _spline_safety_check(
    edge,
    width_mm: float,
    zmin: float,
    zmax: float,
    tolerance_mm: float,
):
    """
    Refuse une B-Spline qui dépasse l'enveloppe du profil source ou revient
    en arrière suivant X.
    """
    allowed_z = max(0.025, float(tolerance_mm) * 1.5)
    allowed_x = max(0.015, float(width_mm) * 1e-5)

    bb = edge.BoundingBox()

    if bb.xmin < -allowed_x:
        return False, f"xmin={bb.xmin:.3f}"
    if bb.xmax > float(width_mm) + allowed_x:
        return False, f"xmax={bb.xmax:.3f}"
    if bb.zmin < float(zmin) - allowed_z:
        return False, f"zmin={bb.zmin:.3f} < {zmin:.3f}"
    if bb.zmax > float(zmax) + allowed_z:
        return False, f"zmax={bb.zmax:.3f} > {zmax:.3f}"

    try:
        pts = [edge.positionAt(float(t)) for t in np.linspace(0.0, 1.0, 49)]
        curve_x = np.asarray([p.x for p in pts], dtype=float)

        # La spline est construite de X=max vers X=0.
        if np.any(np.diff(curve_x) > max(0.03, float(width_mm) * 2e-5)):
            return False, "retour arrière suivant X"
    except Exception:
        pass

    return True, "OK"


def make_safe_adaptive_spline(
    cq,
    xs: np.ndarray,
    zrow: np.ndarray,
    y: float,
    tolerance_mm: float,
    sample_mm: float,
    base_mm: float,
    width_mm: float,
    logger,
    section_label: str,
):
    """
    Crée une spline adaptative, la contrôle, puis la redensifie si nécessaire.
    """
    zmin = float(np.min(zrow))
    zmax = float(np.max(zrow))

    attempts = [
        (1.00, "adaptatif"),
        (0.60, "densifié x1.7"),
        (0.35, "densifié x2.9"),
        (0.20, "densifié x5"),
    ]

    for attempt_no, (density, label) in enumerate(attempts):
        profile = simplify_profile(
            xs,
            zrow,
            tolerance_mm,
            sample_mm=sample_mm,
            base_mm=base_mm,
            density_factor=density,
        )

        points = [cq.Vector(x, y, z) for x, z in reversed(profile)]
        edge = cq.Edge.makeSpline(points)

        safe, reason = _spline_safety_check(
            edge,
            width_mm,
            zmin,
            zmax,
            tolerance_mm,
        )

        logger.debug(
            f"{section_label} {label}: {len(profile)}/{len(xs)} pts ; "
            f"safe={safe} ({reason})"
        )

        if safe:
            return edge, profile, attempt_no, reason

        logger.warning(
            f"{section_label} spline refusée ({reason}) ; redensification."
        )

    # Dernier recours : résolution brute.
    profile = [(float(x), float(z)) for x, z in zip(xs, zrow)]
    points = [cq.Vector(x, y, z) for x, z in reversed(profile)]
    edge = cq.Edge.makeSpline(points)

    safe, reason = _spline_safety_check(
        edge,
        width_mm,
        zmin,
        zmax,
        tolerance_mm,
    )

    logger.warning(
        f"{section_label} profil brut utilisé : {len(profile)} pts ; "
        f"safe={safe} ({reason})"
    )

    return edge, profile, len(attempts), reason


def adaptive_row_indices(
    hmap: np.ndarray,
    relief_mm: float,
    tolerance_mm: float,
    max_skip: int = 1,
):
    """
    Mode v4.1 : aucune rangée Y n'est supprimée.

    Cela retire une source entière d'oscillations du loft. L'optimisation
    porte uniquement sur les points X, où chaque spline peut être contrôlée
    avant d'être envoyée au loft.
    """
    return list(range(hmap.shape[0]))



def export_reference_assembly(cq, full_solid, width_mm, height_mm, base_mm, output_path, logger):
    """
    Exporte UN SEUL STEP contenant deux corps dans le même repère :
      - Mur_complet : le relief complet ;
      - Base_reference : un parallélépipède exactement de l'épaisseur de fond.

    Dans FreeCAD, Cut(Mur_complet, Base_reference) produit le relief seul sans
    aucun recalage.
    """
    base = cq.Solid.makeBox(
        float(width_mm),
        float(height_mm),
        float(base_mm),
        cq.Vector(0, 0, 0),
    )
    assy = cq.Assembly(name="CastleHeightMap")
    assy.add(full_solid, name="Mur_complet")
    assy.add(base, name="Base_reference")
    logger.info("Export STEP multi-corps : Mur_complet + Base_reference")
    cq.exporters.assembly.exportAssembly(assy, str(output_path))


def heightmap_to_array(
    heightmap: Image.Image,
    nx: int,
    ny: int,
    flip_y: bool = False,
) -> np.ndarray:
    img = heightmap.resize((nx, ny), Image.Resampling.LANCZOS)
    arr = np.asarray(img, dtype=np.float64) / 255.0

    if not flip_y:
        arr = np.flipud(arr)

    return arr


def generate_step_from_heightmap(
    heightmap: Image.Image,
    output_path: str,
    width_mm: float,
    height_mm: float,
    base_mm: float,
    relief_mm: float,
    sample_mm: float,
    flip_y: bool = False,
    bands_mode: bool = False,
    adaptive: bool = True,
    adaptive_tolerance_mm: float = 0.04,
    reference_body: bool = False,
    progress: Optional[Callable[[float, str], None]] = None,
    logger: Optional[AppLogger] = None,
):
    logger = logger or APP_LOG
    total_t0 = time.perf_counter()

    logger.info("=" * 72)
    logger.info("Début génération STEP v4")
    logger.info(
        f"mur={width_mm}x{height_mm} mm | fond={base_mm} | relief={relief_mm} | "
        f"pas={sample_mm} | adaptive={adaptive} tol={adaptive_tolerance_mm} | "
        f"base_reference={reference_body}"
    )

    try:
        import cadquery as cq
    except Exception as exc:
        logger.exception("Échec import CadQuery")
        raise RuntimeError(
            "CadQuery n'est pas installé. Relance l'installateur du logiciel."
        ) from exc

    width_mm = float(width_mm)
    height_mm = float(height_mm)
    base_mm = float(base_mm)
    relief_mm = float(relief_mm)
    sample_mm = float(sample_mm)
    adaptive_tolerance_mm = float(adaptive_tolerance_mm)

    if width_mm <= 0 or height_mm <= 0 or base_mm <= 0 or sample_mm <= 0:
        raise ValueError("Dimensions, fond et pas STEP doivent être > 0.")
    if relief_mm < 0:
        raise ValueError("Le relief doit être >= 0.")

    nx = max(4, int(math.ceil(width_mm / sample_mm)) + 1)
    ny = max(4, int(math.ceil(height_mm / sample_mm)) + 1)

    if nx > 801 or ny > 501 or nx * ny > 180000:
        raise ValueError(
            f"Résolution trop lourde : {nx} × {ny} = {nx*ny:,} points. "
            "Augmente le pas STEP."
        )

    if progress:
        progress(0.03, f"Préparation height-map {nx} × {ny}…")

    hmap = heightmap_to_array(heightmap, nx, ny, flip_y=flip_y)
    xs = np.linspace(0.0, width_mm, nx)
    ys_all = np.linspace(0.0, height_mm, ny)

    if adaptive:
        row_ids = adaptive_row_indices(
            hmap, relief_mm, adaptive_tolerance_mm, max_skip=4
        )
    else:
        row_ids = list(range(ny))

    logger.info(
        f"Grille brute {nx}x{ny} ({nx*ny:,} points) ; "
        f"sections Y utilisées : {len(row_ids)}/{ny} (aucun saut Y)."
    )

    wires = []
    raw_profile_points = 0
    kept_profile_points = 0
    sections_t0 = time.perf_counter()

    for pos, j in enumerate(row_ids):
        y = float(ys_all[j])
        section_no = pos + 1
        total_sections = len(row_ids)
        t_section = time.perf_counter()
        zrow = base_mm + relief_mm * hmap[j, :]

        raw_profile_points += nx

        bl = cq.Vector(0.0, y, 0.0)
        br = cq.Vector(width_mm, y, 0.0)
        tr = cq.Vector(width_mm, y, float(zrow[-1]))
        tl = cq.Vector(0.0, y, float(zrow[0]))

        if progress:
            progress(
                0.08 + 0.58 * (pos / max(1, total_sections)),
                f"Section {section_no}/{total_sections} — spline sécurisée…",
            )

        t0 = time.perf_counter()
        logger.debug(
            f"[Section {section_no:03d}/{total_sections:03d}] makeSpline START "
            f"y={y:.3f}"
        )

        if adaptive:
            top_edge, profile, fallback_level, safety_reason = make_safe_adaptive_spline(
                cq,
                xs,
                zrow,
                y,
                adaptive_tolerance_mm,
                sample_mm,
                base_mm,
                width_mm,
                logger,
                f"[Section {section_no:03d}/{total_sections:03d}]",
            )
        else:
            profile = [(float(x), float(z)) for x, z in zip(xs, zrow)]
            top_points = [cq.Vector(x, y, z) for x, z in reversed(profile)]
            top_edge = cq.Edge.makeSpline(top_points)
            fallback_level = 0
            safety_reason = "adaptatif désactivé"

        kept_profile_points += len(profile)

        spline_dt = time.perf_counter() - t0
        logger.debug(
            f"[Section {section_no:03d}/{total_sections:03d}] makeSpline END "
            f"{fmt_duration(spline_dt)} | {len(profile)}/{nx} pts | "
            f"{safety_reason}"
        )

        edges = [
            cq.Edge.makeLine(bl, br),
            cq.Edge.makeLine(br, tr),
            top_edge,
            cq.Edge.makeLine(tl, bl),
        ]
        wires.append(cq.Wire.assembleEdges(edges))

        section_dt = time.perf_counter() - t_section
        if spline_dt > 5:
            logger.warning(
                f"Section {section_no}/{total_sections} spline lente : "
                f"{fmt_duration(spline_dt)}"
            )
        logger.info(
            f"Section {section_no}/{total_sections} OK en {fmt_duration(section_dt)} "
            f"({len(profile)}/{nx} pts)"
        )

    logger.info(
        f"Sections terminées en {fmt_duration(time.perf_counter()-sections_t0)} ; "
        f"points profils conservés {kept_profile_points:,}/{raw_profile_points:,}."
    )

    if progress:
        progress(0.70, "Loft OpenCascade…")

    fallback_used = False
    loft_t0 = time.perf_counter()
    try:
        solid = cq.Solid.makeLoft(wires, ruled=bands_mode)
    except Exception as first_exc:
        logger.exception("Loft lissé échoué")
        if not bands_mode:
            try:
                solid = cq.Solid.makeLoft(wires, ruled=True)
                fallback_used = True
            except Exception:
                raise first_exc
        else:
            raise
    logger.info(f"Loft terminé en {fmt_duration(time.perf_counter()-loft_t0)}")

    if solid is None:
        raise RuntimeError("OpenCascade n'a pas réussi à créer le solide.")

    valid = True
    try:
        valid = bool(solid.isValid())
    except Exception:
        logger.exception("Validation du solide impossible")

    if progress:
        progress(0.88, "Export STEP…")

    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    export_t0 = time.perf_counter()

    if reference_body:
        export_reference_assembly(
            cq, solid, width_mm, height_mm, base_mm, out, logger
        )
    else:
        cq.exporters.export(solid, str(out))

    logger.info(f"Export terminé en {fmt_duration(time.perf_counter()-export_t0)}")

    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("Le fichier STEP n'a pas été créé.")

    if progress:
        progress(1.0, "STEP terminé.")

    logger.info(
        f"Génération totale {fmt_duration(time.perf_counter()-total_t0)} | "
        f"{out.stat().st_size/(1024*1024):.2f} Mo"
    )

    return {
        "path": str(out),
        "nx": nx,
        "ny": ny,
        "sections": len(row_ids),
        "points_raw": raw_profile_points,
        "points_kept": kept_profile_points,
        "valid": valid,
        "size_bytes": out.stat().st_size,
        "min_z": base_mm,
        "max_z": base_mm + relief_mm,
        "surface_mode": "bandes" if bands_mode or fallback_used else "continue",
        "reference_body": bool(reference_body),
    }



class MarkdownTextRenderer:
    """
    Petit rendu Markdown natif pour tkinter.Text.
    L'objectif n'est pas CommonMark complet mais un rendu propre de la
    documentation intégrée sans navigateur HTML embarqué supplémentaire.
    """

    URL_RE = re.compile(r"https?://[^\s)>]+")

    def __init__(self, text_widget: tk.Text):
        self.text = text_widget
        self._link_counter = 0
        self._configure_tags()

    def _configure_tags(self):
        t = self.text
        base_font = ("TkDefaultFont", 10)
        t.configure(font=base_font, padx=12, pady=10, spacing1=1, spacing3=2)

        t.tag_configure("h1", font=("TkDefaultFont", 19, "bold"), spacing1=12, spacing3=9)
        t.tag_configure("h2", font=("TkDefaultFont", 15, "bold"), spacing1=10, spacing3=6)
        t.tag_configure("h3", font=("TkDefaultFont", 12, "bold"), spacing1=8, spacing3=4)
        t.tag_configure("bold", font=("TkDefaultFont", 10, "bold"))
        t.tag_configure("italic", font=("TkDefaultFont", 10, "italic"))
        t.tag_configure("code", font=("monospace", 10), background="#e9ecef")
        t.tag_configure(
            "codeblock",
            font=("monospace", 10),
            background="#eef1f4",
            lmargin1=18,
            lmargin2=18,
            rmargin=18,
            spacing1=6,
            spacing3=6,
        )
        t.tag_configure(
            "quote",
            font=("TkDefaultFont", 10, "italic"),
            lmargin1=18,
            lmargin2=18,
            foreground="#555555",
        )
        t.tag_configure(
            "bullet",
            lmargin1=12,
            lmargin2=30,
        )
        t.tag_configure(
            "number",
            lmargin1=12,
            lmargin2=34,
        )
        t.tag_configure(
            "link",
            foreground="#0066cc",
            underline=True,
        )
        t.tag_configure(
            "rule",
            foreground="#999999",
        )

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

    def render(self, markdown: str):
        self.clear()

        lines = markdown.splitlines()
        in_code = False
        code_lines = []

        for line in lines:
            stripped = line.rstrip()

            if stripped.startswith("```"):
                if in_code:
                    self._insert_code_block("\n".join(code_lines))
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                continue

            if in_code:
                code_lines.append(line)
                continue

            if not stripped:
                self.text.insert("end", "\n")
                continue

            if stripped.startswith("# "):
                self._insert_inline(stripped[2:], ("h1",))
                self.text.insert("end", "\n")
                continue

            if stripped.startswith("## "):
                self._insert_inline(stripped[3:], ("h2",))
                self.text.insert("end", "\n")
                continue

            if stripped.startswith("### "):
                self._insert_inline(stripped[4:], ("h3",))
                self.text.insert("end", "\n")
                continue

            if stripped.strip() in {"---", "***", "___"}:
                self.text.insert("end", "────────────────────────────────────────\n", ("rule",))
                continue

            if stripped.startswith("> "):
                self.text.insert("end", "▌ ")
                self._insert_inline(stripped[2:], ("quote",))
                self.text.insert("end", "\n")
                continue

            m = re.match(r"^\s*[-*+]\s+(.*)$", stripped)
            if m:
                self.text.insert("end", "• ", ("bullet",))
                self._insert_inline(m.group(1), ("bullet",))
                self.text.insert("end", "\n")
                continue

            m = re.match(r"^\s*(\d+)\.\s+(.*)$", stripped)
            if m:
                self.text.insert("end", f"{m.group(1)}. ", ("number",))
                self._insert_inline(m.group(2), ("number",))
                self.text.insert("end", "\n")
                continue

            # Tableaux simples : affichage monospace lisible.
            if stripped.startswith("|") and stripped.endswith("|"):
                if re.match(r"^\|[\s\-:|]+\|$", stripped):
                    continue
                cols = [x.strip() for x in stripped.strip("|").split("|")]
                self.text.insert("end", "   ".join(cols) + "\n", ("codeblock",))
                continue

            self._insert_inline(stripped)
            self.text.insert("end", "\n")

        if in_code and code_lines:
            self._insert_code_block("\n".join(code_lines))

        self.text.configure(state="disabled")
        self.text.see("1.0")

    def _insert_code_block(self, value: str):
        self.text.insert("end", value.rstrip() + "\n", ("codeblock",))

    def _insert_inline(self, value: str, base_tags=()):
        """
        Supporte :
        **gras**
        *italique*
        `code`
        [texte](https://...)
        URLs nues
        """
        token_re = re.compile(
            r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\(https?://[^)]+\)|(?<!\*)\*[^*\n]+\*(?!\*)|https?://[^\s)>]+)"
        )

        pos = 0
        for match in token_re.finditer(value):
            if match.start() > pos:
                self.text.insert("end", value[pos:match.start()], base_tags)

            token = match.group(0)

            if token.startswith("**") and token.endswith("**"):
                self.text.insert("end", token[2:-2], tuple(base_tags) + ("bold",))
            elif token.startswith("`") and token.endswith("`"):
                self.text.insert("end", token[1:-1], tuple(base_tags) + ("code",))
            elif token.startswith("["):
                m = re.match(r"\[([^\]]+)\]\((https?://[^)]+)\)", token)
                if m:
                    self._insert_link(m.group(1), m.group(2), base_tags)
                else:
                    self.text.insert("end", token, base_tags)
            elif token.startswith("*") and token.endswith("*"):
                self.text.insert("end", token[1:-1], tuple(base_tags) + ("italic",))
            elif token.startswith("http://") or token.startswith("https://"):
                self._insert_link(token, token, base_tags)
            else:
                self.text.insert("end", token, base_tags)

            pos = match.end()

        if pos < len(value):
            self.text.insert("end", value[pos:], base_tags)

    def _insert_link(self, label: str, url: str, base_tags=()):
        tag = f"mdlink_{self._link_counter}"
        self._link_counter += 1
        self.text.insert("end", label, tuple(base_tags) + ("link", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
        self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.configure(cursor=""))


class WikiHelpView(ttk.Frame):
    """
    Mini wiki embarqué : navigation, recherche et rendu Markdown.
    """

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.pages = []
        self.filtered_pages = []
        self.current_index = -1
        self.search_var = tk.StringVar()

        self._load_index()
        self._build()
        self._populate_tree()

        if self.filtered_pages:
            self.show_page(0)

    def _load_index(self):
        index_path = resource_path("docs/wiki_index.json")
        try:
            self.pages = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            APP_LOG.error(f"Wiki index non chargé : {exc}")
            self.pages = [
                {"title": "Aide", "file": "../HELP.md"},
            ]
        self.filtered_pages = list(self.pages)

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=4, pady=4)

        ttk.Button(toolbar, text="←", width=3, command=self.previous_page).pack(side="left")
        ttk.Button(toolbar, text="→", width=3, command=self.next_page).pack(side="left", padx=(2, 8))

        ttk.Label(toolbar, text="Rechercher :").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(5, 0))
        search.bind("<KeyRelease>", lambda _e: self.filter_pages())

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        nav_frame = ttk.Frame(body)
        content_frame = ttk.Frame(body)
        body.add(nav_frame, weight=1)
        body.add(content_frame, weight=4)

        self.tree = ttk.Treeview(nav_frame, show="tree", selectmode="browse")
        nav_scroll = ttk.Scrollbar(nav_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=nav_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        nav_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.text = tk.Text(content_frame, wrap="word", state="disabled")
        content_scroll = ttk.Scrollbar(content_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=content_scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        content_scroll.pack(side="right", fill="y")

        self.renderer = MarkdownTextRenderer(self.text)

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, page in enumerate(self.filtered_pages):
            self.tree.insert("", "end", iid=str(idx), text=page["title"])

    def filter_pages(self):
        query = self.search_var.get().strip().lower()

        if not query:
            self.filtered_pages = list(self.pages)
        else:
            matches = []
            for page in self.pages:
                title = page["title"].lower()
                content = self._read_page(page).lower()
                if query in title or query in content:
                    matches.append(page)
            self.filtered_pages = matches

        self._populate_tree()

        if self.filtered_pages:
            self.show_page(0)
        else:
            self.renderer.render("# Aucun résultat\n\nAucune page ne correspond à la recherche.")

    def _read_page(self, page):
        file_value = page["file"]
        path = resource_path("docs/wiki") / file_value
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            # Fallback pour chemins relatifs exceptionnels.
            try:
                return (resource_path("docs/wiki") / file_value).resolve().read_text(encoding="utf-8")
            except Exception as exc:
                return f"# Erreur\n\nImpossible d'ouvrir la page `{file_value}`.\n\n{exc}"

    def show_page(self, idx):
        if not self.filtered_pages:
            return
        idx = max(0, min(idx, len(self.filtered_pages) - 1))
        self.current_index = idx
        page = self.filtered_pages[idx]
        self.renderer.render(self._read_page(page))

        try:
            self.tree.selection_set(str(idx))
            self.tree.see(str(idx))
        except Exception:
            pass

    def on_tree_select(self, _event):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            idx = int(selected[0])
        except Exception:
            return
        if idx != self.current_index:
            self.show_page(idx)

    def previous_page(self):
        self.show_page(self.current_index - 1)

    def next_page(self):
        self.show_page(self.current_index + 1)



class App(tk.Tk):
    HISTORY_LIMIT = 30

    PRESETS = {
        "Neutre": dict(hue=0, sat=100, val=100, contrast=100, black=0, white=100, gamma=1.0, blur=0.0),
        "Pierre douce": dict(hue=0, sat=70, val=100, contrast=135, black=7, white=92, gamma=0.95, blur=0.8),
        "Pierre marquée": dict(hue=0, sat=40, val=100, contrast=175, black=12, white=86, gamma=0.85, blur=0.45),
        "Gravure": dict(hue=0, sat=0, val=100, contrast=220, black=18, white=76, gamma=0.75, blur=0.2),
    }

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1680x980")
        self.minsize(1280, 800)

        self.layers: list[TextureLayer] = []
        self.masks: list[MaskShape] = []
        self.selected_uid: Optional[int] = None
        self.next_uid = 1
        self.next_mask_uid = 1
        self.project_path: Optional[Path] = None
        self.dirty = False

        self.history = []
        self.redo_stack = []
        self._restoring = False

        self.editor_photo = None
        self.height_photo = None
        self.render_after = None
        self.preview3d_after = None

        self.drag_mode = None
        self.drag_start = None
        self.drag_layer_start = None
        self.mask_start_norm = None
        self.current_mask_uid = None

        # Mur / STEP
        self.wall_w = tk.StringVar(value="200")
        self.wall_h = tk.StringVar(value="60")
        self.base_mm = tk.StringVar(value="1.6")
        self.relief_mm = tk.StringVar(value="2.0")
        self.sample_mm = tk.StringVar(value="1.0")
        self.flip_y = tk.BooleanVar(value=False)
        self.bands_mode = tk.BooleanVar(value=False)
        self.adaptive = tk.BooleanVar(value=True)
        self.adaptive_tol = tk.StringVar(value="0.04")
        self.reference_body = tk.BooleanVar(value=False)

        # Traitement global
        self.hue = tk.DoubleVar(value=0)
        self.sat = tk.DoubleVar(value=100)
        self.val = tk.DoubleVar(value=100)
        self.contrast = tk.DoubleVar(value=120)
        self.black = tk.DoubleVar(value=5)
        self.white = tk.DoubleVar(value=95)
        self.gamma = tk.DoubleVar(value=1.0)
        self.blur = tk.DoubleVar(value=0.6)
        self.invert = tk.BooleanVar(value=False)
        self.preset = tk.StringVar(value="Personnalisé")

        # Calque sélectionné
        self.feather = tk.DoubleVar(value=6.0)
        self.layer_x_mm = tk.StringVar(value="0")
        self.layer_y_mm = tk.StringVar(value="0")
        self.layer_w_mm = tk.StringVar(value="0")
        self.layer_h_mm = tk.StringVar(value="0")
        self.layer_rotation = tk.StringVar(value="0")
        self.layer_lock_aspect = tk.BooleanVar(value=False)

        # Outils
        self.tool_mode = tk.StringVar(value="select")
        self.brush_mm = tk.StringVar(value="5")
        self.snap_grid = tk.BooleanVar(value=False)
        self.grid_mm = tk.StringVar(value="5")

        self.status = tk.StringVar(value="Ajoute une texture pour commencer.")
        self.layer_info = tk.StringVar(value="Aucun calque sélectionné.")
        self.estimate_text = tk.StringVar(value="Estimation STEP : —")

        self.log_queue = []
        self.log_lock = threading.Lock()
        APP_LOG.set_ui_callback(self.queue_log_message)
        APP_LOG.info(f"Application démarrée — {APP_NAME} v{APP_VERSION}")

        self._install_window_icon()
        self._build_menubar()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._bind_shortcuts()
        self._install_traces()
        self.update_estimate()
        self.refresh_layer_tree()
        self.after(200, self.update_3d_preview)
        self.update_window_title()

    # ------------------------------------------------------------------
    # Application / menus / aide
    # ------------------------------------------------------------------

    def _install_window_icon(self):
        try:
            icon_path = resource_path("assets/castle_heightmap_studio.png")
            if icon_path.exists():
                self._app_icon_photo = ImageTk.PhotoImage(Image.open(icon_path).convert("RGBA"))
                self.iconphoto(True, self._app_icon_photo)
        except Exception as exc:
            APP_LOG.warning(f"Icône application non chargée : {exc}")

    def _build_menubar(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Nouveau", accelerator="Ctrl+N", command=self.new_project)
        file_menu.add_command(label="Ouvrir…", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Enregistrer", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Enregistrer sous…", accelerator="Ctrl+Shift+S", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exporter la height-map PNG…", command=self.export_heightmap)
        file_menu.add_command(label="Créer le STEP…", command=self.export_step)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", accelerator="Alt+F4", command=self.on_close)
        menubar.add_cascade(label="Fichier", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Annuler", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Rétablir", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Ajouter une image…", command=self.add_image)
        edit_menu.add_command(label="Dupliquer le calque", accelerator="Ctrl+D", command=self.duplicate_selected)
        edit_menu.add_command(label="Supprimer le calque", accelerator="Suppr", command=self.delete_selected)
        menubar.add_cascade(label="Édition", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Aide", accelerator="F1", command=lambda: self.show_info_dialog("help"))
        help_menu.add_command(label="Changelog", command=lambda: self.show_info_dialog("changelog"))
        help_menu.add_separator()
        help_menu.add_command(label="Rechercher les mises à jour…", command=self.check_for_updates)
        help_menu.add_separator()
        help_menu.add_command(label="À propos de Castle HeightMap Studio", command=lambda: self.show_info_dialog("about"))
        menubar.add_cascade(label="Aide", menu=help_menu)

        self.config(menu=menubar)

    def _load_text_resource(self, relative_path: str, fallback: str) -> str:
        path = resource_path(relative_path)
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return fallback

    def _about_system_info(self) -> str:
        cq_version = "non disponible"
        np_version = getattr(np, "__version__", "?")
        pil_version = getattr(Image, "__version__", "?")
        mpl_version = "non disponible"

        try:
            import cadquery as cq
            cq_version = getattr(cq, "__version__", "installé")
        except Exception:
            pass

        try:
            import matplotlib
            mpl_version = getattr(matplotlib, "__version__", "?")
        except Exception:
            pass

        return (
            f"{APP_NAME}\n"
            f"Version : {APP_VERSION}\n"
            f"Auteur : {APP_AUTHOR}\n\n"
            f"Système : {platform.system()} {platform.release()}\n"
            f"Architecture : {platform.machine()}\n"
            f"Python : {platform.python_version()}\n"
            f"Tk : {self.tk.call('info', 'patchlevel')}\n"
            f"NumPy : {np_version}\n"
            f"Pillow : {pil_version}\n"
            f"Matplotlib : {mpl_version}\n"
            f"CadQuery : {cq_version}\n"
            f"Dépôt GitHub : {detect_github_repo() or 'non configuré'}"
        )

    def show_info_dialog(self, initial_tab="about"):
        win = tk.Toplevel(self)
        win.title("À propos / Aide")
        win.geometry("900x680")
        win.minsize(720, 520)
        win.transient(self)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        about_tab = ttk.Frame(notebook, padding=18)
        help_tab = ttk.Frame(notebook, padding=4)
        changelog_tab = ttk.Frame(notebook, padding=4)
        libs_tab = ttk.Frame(notebook, padding=18)

        notebook.add(about_tab, text="À propos")
        notebook.add(help_tab, text="Aide / Wiki")
        notebook.add(changelog_tab, text="Changelog")
        notebook.add(libs_tab, text="Bibliothèques")

        # ---- À propos -------------------------------------------------
        header = ttk.Frame(about_tab)
        header.pack(fill="x")

        try:
            icon_path = resource_path("assets/castle_heightmap_studio.png")
            about_img = Image.open(icon_path).convert("RGBA")
            about_img.thumbnail((128, 128), Image.Resampling.LANCZOS)
            win._about_icon = ImageTk.PhotoImage(about_img)
            ttk.Label(header, image=win._about_icon).pack(side="left", padx=(0, 18))
        except Exception:
            pass

        title_frame = ttk.Frame(header)
        title_frame.pack(side="left", fill="x", expand=True)

        ttk.Label(
            title_frame,
            text=APP_NAME,
            font=("TkDefaultFont", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            title_frame,
            text=f"version {APP_VERSION}",
            font=("TkDefaultFont", 12),
        ).pack(anchor="w", pady=(2, 10))

        ttk.Label(
            title_frame,
            text=f"Auteur : {APP_AUTHOR}",
        ).pack(anchor="w")

        ttk.Separator(
            about_tab,
            orient="horizontal",
        ).pack(fill="x", pady=18)

        ttk.Label(
            about_tab,
            text=self._about_system_info(),
            justify="left",
        ).pack(anchor="w", fill="x")

        about_buttons = ttk.Frame(about_tab)
        about_buttons.pack(fill="x", side="bottom", pady=(15, 0))

        def copy_about():
            self.clipboard_clear()
            self.clipboard_append(self._about_system_info())

        ttk.Button(
            about_buttons,
            text="Copier les informations",
            command=copy_about,
        ).pack(side="left")

        ttk.Button(
            about_buttons,
            text="Rechercher les mises à jour",
            command=self.check_for_updates,
        ).pack(side="left", padx=6)

        repo = detect_github_repo()
        if repo:
            ttk.Button(
                about_buttons,
                text="GitHub",
                command=lambda r=repo: webbrowser.open(f"https://github.com/{r}"),
            ).pack(side="left")

        ttk.Button(
            about_buttons,
            text="Fermer",
            command=win.destroy,
        ).pack(side="right")

        # ---- Wiki -----------------------------------------------------
        wiki = WikiHelpView(help_tab, self)
        wiki.pack(fill="both", expand=True)

        # ---- Changelog Markdown --------------------------------------
        changelog_frame = ttk.Frame(changelog_tab)
        changelog_frame.pack(fill="both", expand=True)

        changelog_text = tk.Text(
            changelog_frame,
            wrap="word",
            state="disabled",
        )
        changelog_scroll = ttk.Scrollbar(
            changelog_frame,
            orient="vertical",
            command=changelog_text.yview,
        )
        changelog_text.configure(yscrollcommand=changelog_scroll.set)

        changelog_text.pack(side="left", fill="both", expand=True)
        changelog_scroll.pack(side="right", fill="y")

        changelog_renderer = MarkdownTextRenderer(changelog_text)
        changelog_renderer.render(
            self._load_text_resource(
                "docs/CHANGELOG.md",
                "# Changelog\n\nLe changelog n'est pas disponible.",
            )
        )
        win._changelog_renderer = changelog_renderer

        # ---- Bibliothèques -------------------------------------------
        libs_md = """# Bibliothèques

Castle HeightMap Studio utilise principalement :

- **Python** — langage principal.
- **Tk / tkinter** — interface graphique.
- **Pillow** — traitement des images.
- **NumPy** — calcul numérique et height-maps.
- **Matplotlib** — aperçu 3D.
- **CadQuery / OpenCascade** — géométrie CAO et export STEP.

Les licences de ces composants restent celles de leurs projets respectifs.
"""
        libs_frame = ttk.Frame(libs_tab)
        libs_frame.pack(fill="both", expand=True)
        libs_text = tk.Text(libs_frame, wrap="word", state="disabled")
        libs_text.pack(fill="both", expand=True)
        libs_renderer = MarkdownTextRenderer(libs_text)
        libs_renderer.render(libs_md)
        win._libs_renderer = libs_renderer

        tab_map = {
            "about": 0,
            "help": 1,
            "changelog": 2,
            "libraries": 3,
        }
        notebook.select(tab_map.get(initial_tab, 0))


    def _github_api_latest_release(self, repo: str):
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    def _select_release_asset(self, release: dict):
        assets = release.get("assets", []) or []
        system = platform.system().lower()

        preferred = []
        if system == "windows":
            preferred = [".exe", "windows.zip", ".zip"]
        elif system == "linux":
            preferred = [".appimage", "linux.zip", ".zip"]
        else:
            preferred = [".zip"]

        for suffix in preferred:
            for asset in assets:
                name = str(asset.get("name", ""))
                if name.lower().endswith(suffix.lower()):
                    return asset
        return None

    def check_for_updates(self):
        repo = detect_github_repo()
        if not repo:
            messagebox.showinfo(
                "Mises à jour",
                "Le dépôt GitHub n'est pas encore configuré.\n\n"
                "Quand le projet sera sur GitHub, le build automatique renseignera "
                "le dépôt dans update_config.json.\n\n"
                "Depuis un clone Git, le logiciel sait aussi détecter automatiquement "
                "le remote origin."
            )
            return

        self.status.set("Recherche d'une mise à jour sur GitHub…")
        APP_LOG.info(f"Recherche GitHub Release : {repo}")

        def worker():
            try:
                release = self._github_api_latest_release(repo)
                self.after(0, lambda: self._handle_update_release(repo, release))
            except urllib.error.HTTPError as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Mises à jour",
                    f"GitHub a renvoyé l'erreur HTTP {exc.code}."
                ))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Mises à jour",
                    f"Impossible de vérifier les mises à jour.\n\n{exc}"
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_release(self, repo: str, release: dict):
        latest_tag = str(release.get("tag_name") or release.get("name") or "").strip()
        latest_version = parse_version(latest_tag)
        current_version = parse_version(APP_VERSION)

        if latest_version <= current_version:
            self.status.set("Le logiciel est à jour.")
            messagebox.showinfo(
                "Mises à jour",
                f"{APP_NAME} {APP_VERSION} est à jour.\n\n"
                f"Dernière release GitHub : {latest_tag or 'inconnue'}."
            )
            return

        asset = self._select_release_asset(release)
        body = (
            f"Une nouvelle version est disponible.\n\n"
            f"Version installée : {APP_VERSION}\n"
            f"Dernière version : {latest_tag}\n\n"
        )

        if asset:
            body += f"Fichier proposé : {asset.get('name', '')}\n\nTélécharger maintenant ?"
            if messagebox.askyesno("Mise à jour disponible", body):
                self._download_release_asset(asset, release)
        else:
            body += "Aucun binaire adapté n'a été trouvé dans cette release.\n\nOuvrir la page GitHub ?"
            if messagebox.askyesno("Mise à jour disponible", body):
                webbrowser.open(release.get("html_url") or f"https://github.com/{repo}/releases/latest")

    def _download_release_asset(self, asset: dict, release: dict):
        url = asset.get("browser_download_url")
        name = asset.get("name") or "CastleHeightMapStudio-update"
        if not url:
            webbrowser.open(release.get("html_url", ""))
            return

        target = filedialog.asksaveasfilename(
            title="Enregistrer la mise à jour",
            initialfile=name,
        )
        if not target:
            return

        self.status.set(f"Téléchargement de {name}…")
        APP_LOG.info(f"Téléchargement update : {url} -> {target}")

        def worker():
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=30) as src, open(target, "wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
                self.after(0, lambda: self._download_update_done(Path(target)))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Mise à jour",
                    f"Le téléchargement a échoué.\n\n{exc}"
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _download_update_done(self, target: Path):
        self.status.set(f"Mise à jour téléchargée : {target}")
        messagebox.showinfo(
            "Mise à jour téléchargée",
            f"La nouvelle version a été téléchargée ici :\n\n{target}\n\n"
            "Par sécurité, Castle HeightMap Studio ne remplace pas automatiquement "
            "l'exécutable en cours d'utilisation. Ferme le logiciel puis lance "
            "le nouveau fichier."
        )
        try:
            if platform.system().lower() == "windows":
                os.startfile(str(target.parent))
            else:
                subprocess.Popen(["xdg-open", str(target.parent)])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Construction interface
    # ------------------------------------------------------------------

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")

        for text, cmd in [
            ("Nouveau", self.new_project),
            ("Ouvrir projet", self.open_project),
            ("Enregistrer", self.save_project),
            ("Enregistrer sous", self.save_project_as),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Button(toolbar, text="↶ Annuler", command=self.undo).pack(side="left", padx=2)
        ttk.Button(toolbar, text="↷ Rétablir", command=self.redo).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Button(toolbar, text="+ Image", command=self.add_image).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Dupliquer", command=self.duplicate_selected).pack(side="left", padx=2)

        connected_btn = ttk.Menubutton(toolbar, text="+ Raccordé")
        connected_btn.pack(side="left", padx=2)
        connected_menu = tk.Menu(connected_btn, tearoff=0)
        connected_menu.add_command(label="À droite (miroir X)", command=lambda: self.duplicate_connected("right"))
        connected_menu.add_command(label="À gauche (miroir X)", command=lambda: self.duplicate_connected("left"))
        connected_menu.add_separator()
        connected_menu.add_command(label="En bas (miroir Y)", command=lambda: self.duplicate_connected("bottom"))
        connected_menu.add_command(label="En haut (miroir Y)", command=lambda: self.duplicate_connected("top"))
        connected_btn["menu"] = connected_menu

        ttk.Button(toolbar, text="Rendre répétable", command=self.make_selected_seamless).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Raccord auto", command=self.auto_match_selected).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=7)
        ttk.Label(toolbar, text="Outil :").pack(side="left", padx=(0, 3))
        for value, label in [("select", "Sélection"), ("brush", "Pinceau"), ("rect", "Rectangle"), ("ellipse", "Cercle")]:
            ttk.Radiobutton(toolbar, text=label, variable=self.tool_mode, value=value).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Suppr dernier masque", command=self.delete_last_mask).pack(side="left", padx=(8, 2))
        ttk.Button(toolbar, text="Effacer masques", command=self.clear_masks).pack(side="left", padx=2)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=4)
        main.add(right, weight=2)

        views = ttk.Panedwindow(left, orient="horizontal")
        views.pack(fill="both", expand=True)

        # Panneau calques
        layer_frame = ttk.LabelFrame(views, text="Calques", padding=5)
        views.add(layer_frame, weight=1)
        self.layer_tree = ttk.Treeview(layer_frame, columns=("visible", "lock"), show="tree headings", selectmode="browse", height=15)
        self.layer_tree.heading("#0", text="Texture")
        self.layer_tree.heading("visible", text="Œil")
        self.layer_tree.heading("lock", text="Verrou")
        self.layer_tree.column("#0", width=170, stretch=True)
        self.layer_tree.column("visible", width=45, anchor="center", stretch=False)
        self.layer_tree.column("lock", width=55, anchor="center", stretch=False)
        self.layer_tree.pack(fill="both", expand=True)
        self.layer_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        lbuttons = ttk.Frame(layer_frame)
        lbuttons.pack(fill="x", pady=(5, 0))
        ttk.Button(lbuttons, text="Œil", width=4, command=self.toggle_selected_visible).pack(side="left")
        ttk.Button(lbuttons, text="🔒", width=4, command=self.toggle_selected_lock).pack(side="left", padx=2)
        ttk.Button(lbuttons, text="↑", width=3, command=lambda: self.move_layer_order(1)).pack(side="left", padx=(8, 2))
        ttk.Button(lbuttons, text="↓", width=3, command=lambda: self.move_layer_order(-1)).pack(side="left")
        ttk.Button(lbuttons, text="Renommer", command=self.rename_selected).pack(side="right")

        # Éditeur
        edit_frame = ttk.LabelFrame(views, text="Composition du mur", padding=5)
        views.add(edit_frame, weight=4)
        self.canvas = tk.Canvas(edit_frame, width=EDITOR_MIN_W, height=EDITOR_MIN_H, bg="#171717", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.schedule_render())
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Prévisualisation height-map + 3D intégrée
        preview_frame = ttk.LabelFrame(views, text="Prévisualisation", padding=4)
        views.add(preview_frame, weight=2)
        self.preview_notebook = ttk.Notebook(preview_frame)
        self.preview_notebook.pack(fill="both", expand=True)
        hm_tab = ttk.Frame(self.preview_notebook)
        d3_tab = ttk.Frame(self.preview_notebook)
        self.preview_notebook.add(hm_tab, text="Height-map")
        self.preview_notebook.add(d3_tab, text="3D")
        self.height_label = ttk.Label(hm_tab, anchor="center")
        self.height_label.pack(fill="both", expand=True)
        self._build_embedded_3d(d3_tab)

        # Panneau de droite avec onglets
        tabs = ttk.Notebook(right)
        tabs.pack(fill="both", expand=True)
        edit_tab = ttk.Frame(tabs, padding=6)
        relief_tab = ttk.Frame(tabs, padding=6)
        log_tab = ttk.Frame(tabs, padding=6)
        tabs.add(edit_tab, text="Mur / Calque")
        tabs.add(relief_tab, text="Relief / Export")
        tabs.add(log_tab, text="Logs")

        wall_box = ttk.LabelFrame(edit_tab, text="Mur", padding=7)
        wall_box.pack(fill="x")
        self._entry_grid(wall_box, [
            ("Largeur", self.wall_w, "mm"), ("Hauteur", self.wall_h, "mm"),
            ("Fond", self.base_mm, "mm"), ("Relief max.", self.relief_mm, "mm"),
            ("Pas STEP", self.sample_mm, "mm"),
        ])

        gridline = ttk.Frame(wall_box)
        gridline.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        ttk.Checkbutton(gridline, text="Aimantation grille", variable=self.snap_grid).pack(side="left")
        ttk.Label(gridline, text="Pas").pack(side="left", padx=(10, 3))
        ttk.Entry(gridline, textvariable=self.grid_mm, width=7).pack(side="left")
        ttk.Label(gridline, text="mm").pack(side="left", padx=(3, 0))
        ttk.Label(gridline, text="Taille pinceau").pack(side="left", padx=(15, 3))
        ttk.Entry(gridline, textvariable=self.brush_mm, width=7).pack(side="left")
        ttk.Label(gridline, text="mm").pack(side="left")

        layer_box = ttk.LabelFrame(edit_tab, text="Texture sélectionnée", padding=7)
        layer_box.pack(fill="x", pady=(7, 0))
        ttk.Label(layer_box, textvariable=self.layer_info, wraplength=430).pack(fill="x")
        self._slider(layer_box, "Raccord doux", self.feather, 0, 25, "%", callback=self.on_feather_change)

        numeric = ttk.Frame(layer_box)
        numeric.pack(fill="x", pady=(5, 0))
        specs = [("X", self.layer_x_mm), ("Y", self.layer_y_mm), ("L", self.layer_w_mm), ("H", self.layer_h_mm), ("Rotation", self.layer_rotation)]
        for i, (lab, var) in enumerate(specs):
            f = ttk.Frame(numeric)
            f.grid(row=i//3, column=i%3, sticky="ew", padx=3, pady=2)
            numeric.columnconfigure(i%3, weight=1)
            ttk.Label(f, text=lab).pack(anchor="w")
            ttk.Entry(f, textvariable=var, width=9).pack(side="left", fill="x", expand=True)
            ttk.Label(f, text="°" if lab=="Rotation" else "mm").pack(side="left", padx=(2,0))
        ttk.Checkbutton(layer_box, text="Verrouiller le ratio", variable=self.layer_lock_aspect, command=self.on_aspect_lock_change).pack(anchor="w", pady=(4,0))
        quick = ttk.Frame(layer_box); quick.pack(fill="x", pady=(5,0))
        ttk.Button(quick, text="20 %", command=lambda: self.set_selected_scale(0.20)).pack(side="left")
        ttk.Button(quick, text="50 %", command=lambda: self.set_selected_scale(0.50)).pack(side="left", padx=3)
        ttk.Button(quick, text="100 %", command=lambda: self.set_selected_scale(1.00)).pack(side="left")
        ttk.Button(quick, text="Remplir mur", command=self.fill_wall_selected).pack(side="right")
        row = ttk.Frame(layer_box); row.pack(fill="x", pady=(5,0))
        ttk.Button(row, text="Appliquer dimensions", command=self.apply_layer_numeric).pack(side="left")
        ttk.Button(row, text="Supprimer", command=self.delete_selected).pack(side="right")

        preset_box = ttk.LabelFrame(edit_tab, text="Presets", padding=7)
        preset_box.pack(fill="x", pady=(7,0))
        cb = ttk.Combobox(preset_box, textvariable=self.preset, state="readonly", values=list(self.PRESETS.keys()), width=20)
        cb.pack(side="left", fill="x", expand=True)
        ttk.Button(preset_box, text="Appliquer", command=self.apply_preset).pack(side="left", padx=(5,0))

        img_box = ttk.LabelFrame(relief_tab, text="Transformation couleur → relief", padding=7)
        img_box.pack(fill="x")
        self._slider(img_box, "Teinte H", self.hue, -180, 180, "°")
        self._slider(img_box, "Saturation S", self.sat, 0, 200, "%")
        self._slider(img_box, "Luminosité V", self.val, 0, 200, "%")
        self._slider(img_box, "Contraste", self.contrast, 50, 250, "%")
        self._slider(img_box, "Niveau noir", self.black, 0, 70, "%")
        self._slider(img_box, "Niveau blanc", self.white, 30, 100, "%")
        self._slider(img_box, "Gamma", self.gamma, 0.25, 3.0, "")
        self._slider(img_box, "Lissage", self.blur, 0.0, 5.0, "px")
        ttk.Checkbutton(img_box, text="Inverser noir / blanc", variable=self.invert, command=self.on_simple_change).pack(anchor="w", pady=(4,0))

        adaptive_box = ttk.LabelFrame(relief_tab, text="Optimisation STEP", padding=7)
        adaptive_box.pack(fill="x", pady=(7,0))
        ttk.Checkbutton(adaptive_box, text="Résolution adaptative sécurisée", variable=self.adaptive, command=self.on_simple_change).pack(anchor="w")
        tolrow = ttk.Frame(adaptive_box); tolrow.pack(fill="x", pady=3)
        ttk.Label(tolrow, text="Tolérance géométrique").pack(side="left")
        ttk.Entry(tolrow, textvariable=self.adaptive_tol, width=8).pack(side="left", padx=(5,2))
        ttk.Label(tolrow, text="mm").pack(side="left")
        ttk.Button(tolrow, text="Analyser précisément", command=self.analyze_resolution).pack(side="right")
        ttk.Label(adaptive_box, textvariable=self.estimate_text, wraplength=440).pack(fill="x", pady=(4,0))
        ttk.Label(
            adaptive_box,
            text="Sécurisé : aucune ligne Y supprimée ; ancres X + contrôle anti-overshoot et redensification automatique.",
            wraplength=440,
        ).pack(fill="x", pady=(3,0))


        export_box = ttk.LabelFrame(relief_tab, text="Export", padding=7)
        export_box.pack(fill="x", pady=(7,0))
        ttk.Checkbutton(export_box, text="Retourner Y dans le STEP", variable=self.flip_y).pack(anchor="w")
        ttk.Checkbutton(export_box, text="Mode bandes (secours)", variable=self.bands_mode).pack(anchor="w")
        ttk.Checkbutton(
            export_box,
            text="Ajouter Base_reference dans le même STEP (FreeCAD)",
            variable=self.reference_body,
        ).pack(anchor="w")
        ttk.Label(
            export_box,
            text="Avec Base_reference : FreeCAD importe Mur_complet + Base_reference dans le même repère. Cut(Mur_complet, Base_reference) donne le relief seul.",
            wraplength=440,
        ).pack(fill="x", pady=(3,5))
        erow = ttk.Frame(export_box); erow.pack(fill="x")
        ttk.Button(erow, text="Exporter PNG", command=self.export_heightmap).pack(side="left")
        self.step_button = ttk.Button(erow, text="Créer le STEP…", command=self.export_step)
        self.step_button.pack(side="right")

        self.progress = ttk.Progressbar(relief_tab, maximum=100)
        self.progress.pack(fill="x", pady=(10,3))
        ttk.Label(relief_tab, textvariable=self.status, wraplength=450).pack(fill="x")

        # Logs
        log_buttons = ttk.Frame(log_tab); log_buttons.pack(fill="x")
        ttk.Button(log_buttons, text="Effacer affichage", command=self.clear_log_view).pack(side="left")
        ttk.Button(log_buttons, text="Ouvrir dossier du log", command=self.open_log_folder).pack(side="left", padx=5)
        ttk.Label(log_tab, text=f"Fichier : {APP_LOG.log_path}", wraplength=450).pack(fill="x", pady=4)
        log_frame = ttk.Frame(log_tab); log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, wrap="none", state="disabled", font=("monospace", 9))
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.after(100, self.flush_log_queue)

    def _build_embedded_3d(self, parent):
        self.fig3d = None
        self.ax3d = None
        self.canvas3d = None
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            self.fig3d = Figure(figsize=(4.2, 3.4), dpi=100)
            self.ax3d = self.fig3d.add_subplot(111, projection="3d")
            self.canvas3d = FigureCanvasTkAgg(self.fig3d, master=parent)
            self.canvas3d.get_tk_widget().pack(fill="both", expand=True)
        except Exception as exc:
            ttk.Label(parent, text=f"Aperçu 3D indisponible : {exc}", wraplength=300).pack(expand=True)

    def _entry_grid(self, parent, specs):
        for i, (label, var, unit) in enumerate(specs):
            r, c = divmod(i, 2)
            f = ttk.Frame(parent); f.grid(row=r, column=c, sticky="ew", padx=4, pady=2)
            parent.columnconfigure(c, weight=1)
            ttk.Label(f, text=label).pack(anchor="w")
            line = ttk.Frame(f); line.pack(fill="x")
            entry = ttk.Entry(line, textvariable=var, width=10)
            entry.pack(side="left", fill="x", expand=True)
            entry.bind("<FocusIn>", lambda _e: self.push_history())
            ttk.Label(line, text=unit).pack(side="left", padx=(3,0))

    def _slider(self, parent, text, var, lo, hi, unit, callback=None):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=text, width=15).pack(side="left")
        def changed(_=None):
            self.dirty = True
            if callback: callback()
            else: self.schedule_render()
        scale = ttk.Scale(row, from_=lo, to=hi, variable=var, command=changed)
        scale.pack(side="left", fill="x", expand=True, padx=5)
        scale.bind("<ButtonPress-1>", lambda _e: self.push_history())
        vl = ttk.Label(row, width=8, anchor="e"); vl.pack(side="right")
        def refresh(*_):
            v = var.get(); vl.config(text=f"{v:.2f}{unit}" if hi-lo <= 5 else f"{v:.0f}{unit}")
        var.trace_add("write", refresh); refresh()

    def _install_traces(self):
        for var in (self.wall_w, self.wall_h, self.base_mm, self.relief_mm, self.sample_mm, self.adaptive_tol):
            var.trace_add("write", lambda *_: (self.schedule_render(), self.update_estimate()))

    def _bind_shortcuts(self):
        self.bind_all("<Control-n>", lambda _e: self.new_project())
        self.bind_all("<F1>", lambda _e: self.show_info_dialog("help"))
        self.bind_all("<Control-s>", lambda _e: self.save_project())
        self.bind_all("<Control-Shift-S>", lambda _e: self.save_project_as())
        self.bind_all("<Control-o>", lambda _e: self.open_project())
        self.bind_all("<Control-z>", lambda _e: self.undo())
        self.bind_all("<Control-y>", lambda _e: self.redo())
        self.bind_all("<Control-d>", lambda _e: self.duplicate_selected())
        self.bind_all("<Delete>", lambda _e: self.delete_selected())

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def queue_log_message(self, level, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        with self.log_lock:
            self.log_queue.append(f"{stamp} | {level:<7} | {message}")

    def flush_log_queue(self):
        try:
            with self.log_lock:
                lines = self.log_queue[:]; self.log_queue.clear()
            if lines and hasattr(self, "log_text"):
                self.log_text.configure(state="normal")
                for line in lines: self.log_text.insert("end", line+"\n")
                count = int(self.log_text.index("end-1c").split(".")[0])
                if count > 1600: self.log_text.delete("1.0", f"{count-1300}.0")
                self.log_text.see("end"); self.log_text.configure(state="disabled")
        finally:
            self.after(120, self.flush_log_queue)

    def clear_log_view(self):
        self.log_text.configure(state="normal"); self.log_text.delete("1.0", "end"); self.log_text.configure(state="disabled")

    def open_log_folder(self):
        import subprocess, sys
        try:
            folder = str(APP_LOG.log_path.parent)
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Impossible d'ouvrir le dossier.\n{exc}\n\n{APP_LOG.log_path}")

    # ------------------------------------------------------------------
    # Historique / projets
    # ------------------------------------------------------------------

    def capture_state(self):
        layers = []
        for l in self.layers:
            layers.append(dict(
                name=l.name, path=l.path, image=l.image.copy(), x=l.x, y=l.y, w=l.w, h=l.h,
                visible=l.visible, locked=l.locked, rotation_deg=l.rotation_deg,
                lock_aspect=l.lock_aspect, feather_pct=l.feather_pct, uid=l.uid,
            ))
        masks = copy.deepcopy(self.masks)
        settings = {
            "wall_w": self.wall_w.get(), "wall_h": self.wall_h.get(), "base_mm": self.base_mm.get(),
            "relief_mm": self.relief_mm.get(), "sample_mm": self.sample_mm.get(), "flip_y": self.flip_y.get(),
            "bands_mode": self.bands_mode.get(), "adaptive": self.adaptive.get(), "adaptive_tol": self.adaptive_tol.get(),
            "reference_body": self.reference_body.get(), "hue": self.hue.get(), "sat": self.sat.get(), "val": self.val.get(),
            "contrast": self.contrast.get(), "black": self.black.get(), "white": self.white.get(), "gamma": self.gamma.get(),
            "blur": self.blur.get(), "invert": self.invert.get(), "grid_mm": self.grid_mm.get(), "snap_grid": self.snap_grid.get(),
            "brush_mm": self.brush_mm.get(),
        }
        return dict(layers=layers, masks=masks, settings=settings, selected_uid=self.selected_uid,
                    next_uid=self.next_uid, next_mask_uid=self.next_mask_uid)

    def restore_state(self, state):
        self._restoring = True
        try:
            self.layers = [TextureLayer(**d) for d in state["layers"]]
            self.masks = copy.deepcopy(state["masks"])
            s = state["settings"]
            vars_map = {
                "wall_w": self.wall_w, "wall_h": self.wall_h, "base_mm": self.base_mm, "relief_mm": self.relief_mm,
                "sample_mm": self.sample_mm, "flip_y": self.flip_y, "bands_mode": self.bands_mode, "adaptive": self.adaptive,
                "adaptive_tol": self.adaptive_tol, "reference_body": self.reference_body, "hue": self.hue, "sat": self.sat,
                "val": self.val, "contrast": self.contrast, "black": self.black, "white": self.white, "gamma": self.gamma,
                "blur": self.blur, "invert": self.invert, "grid_mm": self.grid_mm, "snap_grid": self.snap_grid,
                "brush_mm": self.brush_mm,
            }
            for k, var in vars_map.items():
                if k in s: var.set(s[k])
            self.selected_uid = state.get("selected_uid")
            self.next_uid = state.get("next_uid", 1)
            self.next_mask_uid = state.get("next_mask_uid", 1)
        finally:
            self._restoring = False
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render(); self.update_estimate(); self.dirty = True

    def push_history(self):
        if self._restoring: return
        self.history.append(self.capture_state())
        if len(self.history) > self.HISTORY_LIMIT: self.history.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.history: return
        self.redo_stack.append(self.capture_state())
        self.restore_state(self.history.pop())
        self.status.set("Annulation effectuée.")

    def redo(self):
        if not self.redo_stack: return
        self.history.append(self.capture_state())
        self.restore_state(self.redo_stack.pop())
        self.status.set("Rétablissement effectué.")

    def update_window_title(self):
        suffix = ""
        if self.project_path:
            suffix = f" — {self.project_path.name}"
        dirty = " *" if self.dirty else ""
        self.title(f"{APP_NAME} v{APP_VERSION}{suffix}{dirty}")

    def on_close(self):
        if self.dirty:
            ans=messagebox.askyesnocancel(APP_TITLE,"Enregistrer le projet avant de quitter ?")
            if ans is None:return
            if ans:
                self.save_project()
                if self.dirty:return
        self.destroy()

    def new_project(self):
        if self.dirty and not messagebox.askyesno(APP_TITLE, "Créer un nouveau projet et abandonner les modifications actuelles ?"):
            return
        self.layers=[]; self.masks=[]; self.selected_uid=None; self.next_uid=1; self.next_mask_uid=1
        self.project_path=None; self.history=[]; self.redo_stack=[]; self.dirty=False
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render(); self.status.set("Nouveau projet."); self.update_window_title()

    def project_settings_json(self):
        return {
            "wall_w": self.wall_w.get(), "wall_h": self.wall_h.get(), "base_mm": self.base_mm.get(), "relief_mm": self.relief_mm.get(),
            "sample_mm": self.sample_mm.get(), "flip_y": self.flip_y.get(), "bands_mode": self.bands_mode.get(), "adaptive": self.adaptive.get(),
            "adaptive_tol": self.adaptive_tol.get(), "reference_body": self.reference_body.get(), "hue": self.hue.get(), "sat": self.sat.get(),
            "val": self.val.get(), "contrast": self.contrast.get(), "black": self.black.get(), "white": self.white.get(), "gamma": self.gamma.get(),
            "blur": self.blur.get(), "invert": self.invert.get(), "grid_mm": self.grid_mm.get(), "snap_grid": self.snap_grid.get(),
            "brush_mm": self.brush_mm.get(),
        }

    def save_project(self):
        if not self.project_path: return self.save_project_as()
        return self._save_project_to(self.project_path)

    def save_project_as(self):
        path = filedialog.asksaveasfilename(title="Enregistrer le projet", defaultextension=".castlehm",
                                            filetypes=[("Castle HeightMap Project", "*.castlehm")])
        if not path: return
        self.project_path = Path(path)
        return self._save_project_to(self.project_path)

    def _save_project_to(self, path: Path):
        try:
            data = {"version": 4, "settings": self.project_settings_json(), "selected_uid": self.selected_uid,
                    "next_uid": self.next_uid, "next_mask_uid": self.next_mask_uid, "layers": [], "masks": []}
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for i, l in enumerate(self.layers):
                    img_name=f"images/layer_{i:03d}_{l.uid}.png"
                    buf=io.BytesIO(); l.image.save(buf, format="PNG"); z.writestr(img_name, buf.getvalue())
                    data["layers"].append({"name":l.name,"path":l.path,"image":img_name,"x":l.x,"y":l.y,"w":l.w,"h":l.h,
                        "visible":l.visible,"locked":l.locked,"rotation_deg":l.rotation_deg,"lock_aspect":l.lock_aspect,
                        "feather_pct":l.feather_pct,"uid":l.uid})
                for m in self.masks:
                    data["masks"].append({"kind":m.kind,"uid":m.uid,"x":m.x,"y":m.y,"w":m.w,"h":m.h,
                                          "points":m.points,"brush_mm":m.brush_mm})
                z.writestr("project.json", json.dumps(data, ensure_ascii=False, indent=2))
            self.dirty=False; self.status.set(f"Projet enregistré : {path}"); APP_LOG.info(f"Projet enregistré : {path}"); self.update_window_title()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Échec enregistrement projet :\n{exc}")

    def open_project(self):
        path=filedialog.askopenfilename(title="Ouvrir un projet", filetypes=[("Castle HeightMap Project", "*.castlehm")])
        if not path: return
        try:
            with zipfile.ZipFile(path, "r") as z:
                data=json.loads(z.read("project.json").decode("utf-8"))
                layers=[]
                for d in data.get("layers",[]):
                    img=Image.open(io.BytesIO(z.read(d["image"]))).convert("RGB")
                    layers.append(TextureLayer(name=d["name"],path=d.get("path",""),image=img,x=d["x"],y=d["y"],w=d["w"],h=d["h"],
                        visible=d.get("visible",True),locked=d.get("locked",False),rotation_deg=d.get("rotation_deg",0),
                        lock_aspect=d.get("lock_aspect",False),feather_pct=d.get("feather_pct",0),uid=d["uid"]))
                masks=[MaskShape(**m) for m in data.get("masks",[])]
            self.layers=layers; self.masks=masks; self.selected_uid=data.get("selected_uid")
            self.next_uid=data.get("next_uid", max([l.uid for l in layers], default=0)+1)
            self.next_mask_uid=data.get("next_mask_uid", max([m.uid for m in masks], default=0)+1)
            s=data.get("settings",{})
            for key,var in [("wall_w",self.wall_w),("wall_h",self.wall_h),("base_mm",self.base_mm),("relief_mm",self.relief_mm),
                ("sample_mm",self.sample_mm),("flip_y",self.flip_y),("bands_mode",self.bands_mode),("adaptive",self.adaptive),
                ("adaptive_tol",self.adaptive_tol),("reference_body",self.reference_body),("hue",self.hue),("sat",self.sat),
                ("val",self.val),("contrast",self.contrast),("black",self.black),("white",self.white),("gamma",self.gamma),
                ("blur",self.blur),("invert",self.invert),("grid_mm",self.grid_mm),("snap_grid",self.snap_grid),("brush_mm",self.brush_mm)]:
                if key in s: var.set(s[key])
            self.project_path=Path(path); self.history=[]; self.redo_stack=[]; self.dirty=False
            self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render(); self.status.set(f"Projet ouvert : {path}"); self.update_window_title()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Impossible d'ouvrir le projet :\n{exc}")

    # ------------------------------------------------------------------
    # Calques
    # ------------------------------------------------------------------

    def selected_layer(self):
        return next((l for l in self.layers if l.uid==self.selected_uid), None)

    def add_image(self):
        path=filedialog.askopenfilename(title="Ajouter une texture", filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),("Tous","*.*")])
        if not path: return
        try:
            img=Image.open(path); img.load(); img=img.convert("RGB")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return
        self.push_history()
        if not self.layers:
            ia=img.width/max(1,img.height); wa=self.aspect_ratio()
            if ia>=wa: h=1.0; w=ia/wa
            else: w=1.0; h=wa/ia
            x=(1-w)/2; y=(1-h)/2; feather=0
        else:
            w=.60; ia=img.width/max(1,img.height); wa=self.aspect_ratio(); h=w*wa/ia; x=.20; y=(1-h)/2; feather=float(self.feather.get())
        layer=TextureLayer(Path(path).name,path,img,x,y,w,h,True,False,0.0,False,feather,self.next_uid)
        self.next_uid+=1; self.layers.append(layer); self.selected_uid=layer.uid; self.dirty=True
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render()

    def duplicate_selected(self):
        src=self.selected_layer()
        if not src: return
        self.push_history()
        l=TextureLayer(src.name+" copie",src.path,src.image.copy(),src.x+.04,src.y+.04,src.w,src.h,src.visible,False,src.rotation_deg,
                       src.lock_aspect,max(4.0,src.feather_pct),self.next_uid)
        self.next_uid+=1; self.layers.append(l); self.selected_uid=l.uid; self.dirty=True
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render()

    def duplicate_connected(self, direction):
        src=self.selected_layer()
        if not src: return
        self.push_history(); img=src.image.copy(); x,y=src.x,src.y
        if direction=="right": img=ImageOps.mirror(img); x=src.x+src.w
        elif direction=="left": img=ImageOps.mirror(img); x=src.x-src.w
        elif direction=="bottom": img=ImageOps.flip(img); y=src.y+src.h
        elif direction=="top": img=ImageOps.flip(img); y=src.y-src.h
        l=TextureLayer(src.name+" raccordé",src.path,img,x,y,src.w,src.h,src.visible,False,src.rotation_deg,src.lock_aspect,0,self.next_uid)
        self.next_uid+=1; self.layers.append(l); self.selected_uid=l.uid; self.dirty=True
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render()

    def make_selected_seamless(self):
        l=self.selected_layer()
        if not l: return
        self.push_history(); l.image=make_seamless_mirror_tile(l.image); self.dirty=True
        self.schedule_render(); self.status.set("Texture rendue répétable par miroir interne ; bords opposés continus.")

    def delete_selected(self):
        if self.selected_uid is None: return
        self.push_history(); self.layers=[l for l in self.layers if l.uid!=self.selected_uid]
        self.selected_uid=self.layers[-1].uid if self.layers else None; self.dirty=True
        self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render()

    def rename_selected(self):
        l=self.selected_layer()
        if not l: return
        name=simpledialog.askstring(APP_TITLE,"Nouveau nom du calque :",initialvalue=l.name)
        if not name: return
        self.push_history(); l.name=name; self.dirty=True; self.refresh_layer_tree(); self.update_layer_fields()

    def move_layer_order(self, direction):
        l=self.selected_layer()
        if not l: return
        i=self.layers.index(l); ni=int(clamp(i+direction,0,len(self.layers)-1))
        if ni==i:return
        self.push_history(); self.layers.pop(i); self.layers.insert(ni,l); self.dirty=True; self.refresh_layer_tree(); self.schedule_render()

    def toggle_selected_visible(self):
        l=self.selected_layer()
        if not l:return
        self.push_history(); l.visible=not l.visible; self.dirty=True; self.refresh_layer_tree(); self.schedule_render()

    def toggle_selected_lock(self):
        l=self.selected_layer()
        if not l:return
        self.push_history(); l.locked=not l.locked; self.dirty=True; self.refresh_layer_tree(); self.update_layer_fields(); self.schedule_render()

    def refresh_layer_tree(self):
        if not hasattr(self,"layer_tree"):return
        self.layer_tree.delete(*self.layer_tree.get_children())
        # Haut de liste = calque au-dessus
        for l in reversed(self.layers):
            iid=str(l.uid)
            self.layer_tree.insert("","end",iid=iid,text=l.name,values=("✓" if l.visible else "—","🔒" if l.locked else ""))
        if self.selected_uid is not None and self.layer_tree.exists(str(self.selected_uid)):
            self.layer_tree.selection_set(str(self.selected_uid)); self.layer_tree.see(str(self.selected_uid))

    def on_tree_select(self,_e=None):
        sel=self.layer_tree.selection()
        if not sel:return
        self.selected_uid=int(sel[0]); l=self.selected_layer()
        if l:self.feather.set(l.feather_pct)
        self.update_layer_fields(); self.schedule_render()

    def update_layer_fields(self):
        l=self.selected_layer()
        if not l:
            self.layer_info.set("Aucun calque sélectionné."); return
        try:w=float(self.wall_w.get().replace(",",".")); h=float(self.wall_h.get().replace(",","."))
        except:w,h=200,60
        self.layer_x_mm.set(f"{l.x*w:.2f}"); self.layer_y_mm.set(f"{l.y*h:.2f}")
        self.layer_w_mm.set(f"{l.w*w:.2f}"); self.layer_h_mm.set(f"{l.h*h:.2f}"); self.layer_rotation.set(f"{l.rotation_deg:.2f}")
        self.layer_lock_aspect.set(l.lock_aspect); self.feather.set(l.feather_pct)
        self.layer_info.set(f"{l.name} — {'VERROUILLÉ — ' if l.locked else ''}taille {l.w*w:.1f} × {l.h*h:.1f} mm")

    def apply_layer_numeric(self):
        l=self.selected_layer()
        if not l or l.locked:return
        try:
            ww=float(self.wall_w.get().replace(",",".")); wh=float(self.wall_h.get().replace(",","."))
            x=float(self.layer_x_mm.get().replace(",",".")); y=float(self.layer_y_mm.get().replace(",","."))
            w=float(self.layer_w_mm.get().replace(",",".")); h=float(self.layer_h_mm.get().replace(",",".")); rot=float(self.layer_rotation.get().replace(",","."))
        except Exception: messagebox.showerror(APP_TITLE,"Dimensions du calque invalides."); return
        self.push_history(); l.x=x/ww; l.y=y/wh; l.w=max(MIN_LAYER_SIZE,w/ww); l.h=max(MIN_LAYER_SIZE,h/wh); l.rotation_deg=rot; l.lock_aspect=self.layer_lock_aspect.get(); self.dirty=True
        self.update_layer_fields(); self.schedule_render()

    def set_selected_scale(self, scale):
        l=self.selected_layer()
        if not l or l.locked:return
        self.push_history()
        cx=l.x+l.w/2;cy=l.y+l.h/2
        ia=l.image.width/max(1,l.image.height);wa=self.aspect_ratio()
        l.w=float(scale);l.h=l.w*wa/ia;l.x=cx-l.w/2;l.y=cy-l.h/2
        self.dirty=True;self.update_layer_fields();self.schedule_render()

    def fill_wall_selected(self):
        l=self.selected_layer()
        if not l or l.locked:return
        self.push_history(); l.x=0;l.y=0;l.w=1;l.h=1; self.dirty=True; self.update_layer_fields(); self.schedule_render()

    def on_feather_change(self):
        l=self.selected_layer()
        if l and not self._restoring: l.feather_pct=float(self.feather.get()); self.dirty=True
        self.schedule_render()

    def on_aspect_lock_change(self):
        l=self.selected_layer()
        if l: self.push_history(); l.lock_aspect=self.layer_lock_aspect.get(); self.dirty=True

    def apply_preset(self):
        name=self.preset.get()
        if name not in self.PRESETS:return
        self.push_history(); p=self.PRESETS[name]
        for k,var in [("hue",self.hue),("sat",self.sat),("val",self.val),("contrast",self.contrast),("black",self.black),("white",self.white),("gamma",self.gamma),("blur",self.blur)]: var.set(p[k])
        self.dirty=True; self.schedule_render()

    def on_simple_change(self):
        self.dirty=True; self.schedule_render(); self.update_estimate()

    # ------------------------------------------------------------------
    # Masques
    # ------------------------------------------------------------------

    def delete_last_mask(self):
        if not self.masks:return
        self.push_history(); self.masks.pop(); self.dirty=True; self.schedule_render()

    def clear_masks(self):
        if not self.masks:return
        self.push_history(); self.masks.clear(); self.dirty=True; self.schedule_render()

    def canvas_to_norm(self,x,y):
        x0,y0,x1,y1=self.current_wall_rect(); rw=x1-x0; rh=y1-y0
        return clamp((x-x0)/rw,0,1),clamp((y-y0)/rh,0,1)

    # ------------------------------------------------------------------
    # Manipulation canvas
    # ------------------------------------------------------------------

    def aspect_ratio(self):
        try:
            w=float(self.wall_w.get().replace(",",".")); h=float(self.wall_h.get().replace(",",".")); return w/h if w>0 and h>0 else 200/60
        except:return 200/60

    def current_wall_rect(self):
        return wall_rect(max(20,self.canvas.winfo_width()),max(20,self.canvas.winfo_height()),self.aspect_ratio())

    def handle_positions(self,b):
        x0,y0,x1,y1=b;cx=(x0+x1)/2;cy=(y0+y1)/2
        return {"nw":(x0,y0),"n":(cx,y0),"ne":(x1,y0),"e":(x1,cy),"se":(x1,y1),"s":(cx,y1),"sw":(x0,y1),"w":(x0,cy)}

    def hit_test_handle(self,x,y,l):
        b=norm_to_canvas(l,self.current_wall_rect()); hs=HANDLE_SIZE+4
        for n,(hx,hy) in self.handle_positions(b).items():
            if abs(x-hx)<=hs and abs(y-hy)<=hs:return n
        return None

    def hit_test_layer(self,x,y):
        rect=self.current_wall_rect()
        for l in reversed(self.layers):
            x0,y0,x1,y1=norm_to_canvas(l,rect)
            if x0<=x<=x1 and y0<=y<=y1:return l
        return None

    def snap_x(self,norm):
        if not self.snap_grid.get():return norm
        try:g=float(self.grid_mm.get().replace(",","."));w=float(self.wall_w.get().replace(",","."));return round(norm*w/g)*g/w
        except:return norm
    def snap_y(self,norm):
        if not self.snap_grid.get():return norm
        try:g=float(self.grid_mm.get().replace(",","."));h=float(self.wall_h.get().replace(",","."));return round(norm*h/g)*g/h
        except:return norm

    def on_mouse_down(self,event):
        tool=self.tool_mode.get()
        x0,y0,x1,y1=self.current_wall_rect()
        inside=x0<=event.x<=x1 and y0<=event.y<=y1
        if tool in ("brush","rect","ellipse"):
            if not inside:return
            self.push_history(); nx,ny=self.canvas_to_norm(event.x,event.y); self.mask_start_norm=(nx,ny)
            if tool=="brush":
                try:b=float(self.brush_mm.get().replace(",","."))
                except:b=5
                m=MaskShape("brush",self.next_mask_uid,points=[(nx,ny)],brush_mm=b)
            else:m=MaskShape(tool if tool=="rect" else "ellipse",self.next_mask_uid,x=nx,y=ny,w=0,h=0)
            self.next_mask_uid+=1;self.masks.append(m);self.current_mask_uid=m.uid;self.drag_mode="mask";self.dirty=True;self.schedule_render();return

        l=self.selected_layer()
        if l and not l.locked:
            handle=self.hit_test_handle(event.x,event.y,l)
            if handle:
                self.push_history();self.drag_mode="resize:"+handle;self.drag_start=(event.x,event.y);self.drag_layer_start=(l.x,l.y,l.w,l.h);return
        l=self.hit_test_layer(event.x,event.y)
        if not l:
            self.selected_uid=None;self.refresh_layer_tree();self.update_layer_fields();self.schedule_render();return
        self.selected_uid=l.uid;self.refresh_layer_tree();self.update_layer_fields()
        if not l.locked:
            self.push_history();self.drag_mode="move";self.drag_start=(event.x,event.y);self.drag_layer_start=(l.x,l.y,l.w,l.h)

    def on_mouse_drag(self,event):
        if self.drag_mode=="mask":
            m=next((x for x in self.masks if x.uid==self.current_mask_uid),None)
            if not m:return
            nx,ny=self.canvas_to_norm(event.x,event.y)
            if m.kind=="brush":m.points.append((nx,ny))
            else:
                sx,sy=self.mask_start_norm;m.x=min(sx,nx);m.y=min(sy,ny);m.w=abs(nx-sx);m.h=abs(ny-sy)
            self.schedule_render();return
        l=self.selected_layer()
        if not l or l.locked or not self.drag_mode or not self.drag_start:return
        sx,sy=self.drag_start;dx,dy=event.x-sx,event.y-sy;rect=self.current_wall_rect();ndx,ndy=canvas_delta_to_norm(dx,dy,rect)
        x,y,w,h=self.drag_layer_start
        if self.drag_mode=="move":
            l.x=self.snap_x(x+ndx);l.y=self.snap_y(y+ndy)
        elif self.drag_mode.startswith("resize:"):
            handle=self.drag_mode.split(":",1)[1];left=x;top=y;right=x+w;bottom=y+h
            if "w" in handle:left=min(right-MIN_LAYER_SIZE,left+ndx)
            if "e" in handle:right=max(left+MIN_LAYER_SIZE,right+ndx)
            if "n" in handle:top=min(bottom-MIN_LAYER_SIZE,top+ndy)
            if "s" in handle:bottom=max(top+MIN_LAYER_SIZE,bottom+ndy)
            nw=right-left;nh=bottom-top
            if l.lock_aspect and handle in ("nw","ne","se","sw"):
                ratio=w/max(h,1e-9)
                if abs(ndx)>=abs(ndy):nh=nw/ratio
                else:nw=nh*ratio
                if "w" in handle:left=right-nw
                else:right=left+nw
                if "n" in handle:top=bottom-nh
                else:bottom=top+nh
            l.x=self.snap_x(left);l.y=self.snap_y(top);l.w=max(MIN_LAYER_SIZE,self.snap_x(right)-l.x);l.h=max(MIN_LAYER_SIZE,self.snap_y(bottom)-l.y)
        self.dirty=True;self.update_layer_fields();self.schedule_render()

    def on_mouse_up(self,_event):
        self.drag_mode=None;self.drag_start=None;self.drag_layer_start=None;self.mask_start_norm=None;self.current_mask_uid=None

    # ------------------------------------------------------------------
    # Rendu / preview
    # ------------------------------------------------------------------

    def processed_heightmap(self,size):
        source=compose_layers(self.layers,size,include_feather=True)
        hm=image_to_heightmap(source,hue_shift_deg=self.hue.get(),saturation_pct=self.sat.get(),value_pct=self.val.get(),
            contrast_pct=self.contrast.get(),black_level_pct=self.black.get(),white_level_pct=self.white.get(),gamma=self.gamma.get(),
            blur_radius=self.blur.get(),invert=self.invert.get())
        try:ww=float(self.wall_w.get().replace(",","."));wh=float(self.wall_h.get().replace(",","."))
        except:ww,wh=200,60
        return apply_masks_to_heightmap(hm,self.masks,ww,wh)

    def schedule_render(self):
        if self.render_after is not None:
            try:self.after_cancel(self.render_after)
            except:pass
        self.render_after=self.after(45,self.render)
        if self.preview3d_after is not None:
            try:self.after_cancel(self.preview3d_after)
            except:pass
        self.preview3d_after=self.after(650,self.update_3d_preview)

    def render(self):
        self.render_after=None;self.canvas.delete("all")
        cw=max(30,self.canvas.winfo_width());ch=max(30,self.canvas.winfo_height());rect=wall_rect(cw,ch,self.aspect_ratio());x0,y0,x1,y1=rect
        rw=max(2,int(round(x1-x0)));rh=max(2,int(round(y1-y0)))
        if self.layers:
            preview=compose_layers(self.layers,(rw,rh),include_feather=True);self.editor_photo=ImageTk.PhotoImage(preview)
            self.canvas.create_image(x0,y0,image=self.editor_photo,anchor="nw")
        else:self.canvas.create_rectangle(x0,y0,x1,y1,fill="#000000",outline="")
        self.canvas.create_rectangle(x0,y0,x1,y1,outline="#ff3030",width=3)
        try:w=float(self.wall_w.get().replace(",","."));h=float(self.wall_h.get().replace(",","."));label=f"{w:g} × {h:g} mm"
        except:label="mur"
        self.canvas.create_text(x0+8,y0+8,anchor="nw",text=label,fill="#ff3030",font=("TkDefaultFont",11,"bold"))

        # Grille aimantée
        if self.snap_grid.get():
            try:
                gw=float(self.grid_mm.get().replace(",","."));ww=float(self.wall_w.get().replace(",","."));wh=float(self.wall_h.get().replace(",","."))
                if gw>0:
                    xx=gw
                    while xx<ww:self.canvas.create_line(x0+(xx/ww)*(x1-x0),y0,x0+(xx/ww)*(x1-x0),y1,fill="#333333");xx+=gw
                    yy=gw
                    while yy<wh:self.canvas.create_line(x0,y0+(yy/wh)*(y1-y0),x1,y0+(yy/wh)*(y1-y0),fill="#333333");yy+=gw
            except:pass

        for l in self.layers:
            b=norm_to_canvas(l,rect);col="#666666" if not l.locked else "#a66a00"
            if l.uid!=self.selected_uid:self.canvas.create_rectangle(*b,outline=col,width=1,dash=(3,3))
        l=self.selected_layer()
        if l:
            b=norm_to_canvas(l,rect);self.canvas.create_rectangle(*b,outline="#ffd23f",width=2)
            if not l.locked:
                for hx,hy in self.handle_positions(b).values():
                    hs=HANDLE_SIZE/2;self.canvas.create_rectangle(hx-hs,hy-hs,hx+hs,hy+hs,fill="#ffffff",outline="#222222")

        # Overlay des masques
        for m in self.masks:
            if m.kind in ("rect","ellipse"):
                bx0=x0+m.x*(x1-x0);by0=y0+m.y*(y1-y0);bx1=x0+(m.x+m.w)*(x1-x0);by1=y0+(m.y+m.h)*(y1-y0)
                if m.kind=="rect":self.canvas.create_rectangle(bx0,by0,bx1,by1,outline="#00d9ff",width=2,fill="#003c48",stipple="gray25")
                else:self.canvas.create_oval(bx0,by0,bx1,by1,outline="#00d9ff",width=2,fill="#003c48",stipple="gray25")
            elif m.kind=="brush" and m.points:
                pts=[]
                for nx,ny in m.points:pts.extend([x0+nx*(x1-x0),y0+ny*(y1-y0)])
                try:ww=float(self.wall_w.get().replace(",","."));px=max(2,int(m.brush_mm/ww*(x1-x0)))
                except:px=8
                if len(pts)>=4:self.canvas.create_line(*pts,fill="#00d9ff",width=px,smooth=True)

        if self.layers:
            try:
                hm=self.processed_heightmap((max(600,rw),max(180,rh)));hm.thumbnail((HEIGHT_PREVIEW_W,HEIGHT_PREVIEW_H),Image.Resampling.LANCZOS)
                self.height_photo=ImageTk.PhotoImage(hm.convert("RGB"));self.height_label.config(image=self.height_photo,text="")
            except Exception as exc:self.height_label.config(image="",text=str(exc))
        else:self.height_label.config(image="",text="La height-map apparaîtra ici.")

    def update_3d_preview(self):
        self.preview3d_after=None
        if not self.ax3d or not self.canvas3d:return
        self.ax3d.clear()
        if not self.layers:
            self.ax3d.set_title("Ajoute une texture");self.canvas3d.draw_idle();return
        try:
            w,h,base,relief,_=self.read_wall_values();nx=130;ny=max(35,int(nx*h/max(w,1e-9)));ny=min(ny,100)
            hm=self.processed_heightmap((nx,ny));z=base+relief*np.asarray(hm,dtype=float)/255.0
            X,Y=np.meshgrid(np.linspace(0,w,nx),np.linspace(0,h,ny));self.ax3d.plot_surface(X,Y,z,cmap="gray",linewidth=0,antialiased=True)
            self.ax3d.set_xlabel("X mm");self.ax3d.set_ylabel("Y mm");self.ax3d.set_zlabel("Z mm");self.ax3d.set_title("Aperçu 3D")
            try:self.ax3d.set_box_aspect((w,h,max(relief*8,min(w,h)*.12)))
            except:pass
        except Exception as exc:self.ax3d.set_title(str(exc))
        self.canvas3d.draw_idle()

    # ------------------------------------------------------------------
    # Raccord / analyse
    # ------------------------------------------------------------------

    def auto_match_selected(self):
        l=self.selected_layer()
        if not l or len(self.layers)<2:return
        self.push_history()
        try:
            dx,dy=auto_match_layer(self.layers,l,search_px=80,preview_size=(800,300),hue_shift_deg=self.hue.get(),saturation_pct=self.sat.get(),
                value_pct=self.val.get(),contrast_pct=self.contrast.get(),black_level_pct=self.black.get(),white_level_pct=self.white.get(),
                gamma=self.gamma.get(),blur_radius=self.blur.get(),invert=self.invert.get())
            self.dirty=True;self.update_layer_fields();self.schedule_render();self.status.set(f"Raccord auto : {dx:+d}px, {dy:+d}px.")
        except Exception as exc:
            if self.history:self.history.pop()  # aucune modification
            messagebox.showwarning(APP_TITLE,str(exc))

    def update_estimate(self):
        try:
            w=float(self.wall_w.get().replace(",","."));h=float(self.wall_h.get().replace(",","."));s=float(self.sample_mm.get().replace(",","."))
            nx=max(4,int(math.ceil(w/s))+1);ny=max(4,int(math.ceil(h/s))+1);pts=nx*ny
            level="léger" if pts<18000 else "moyen" if pts<50000 else "lourd" if pts<100000 else "très lourd"
            extra=" ; adaptatif sécurisé X" if self.adaptive.get() else ""
            self.estimate_text.set(f"Grille brute : {nx} × {ny} = {pts:,} points — {level}{extra}.")
        except:self.estimate_text.set("Estimation STEP : paramètres invalides.")

    def analyze_resolution(self):
        if not self.layers:return
        try:
            w,h,_b,r,s=self.read_wall_values();tol=float(self.adaptive_tol.get().replace(",","."));nx=max(4,int(math.ceil(w/s))+1);ny=max(4,int(math.ceil(h/s))+1)
            if nx*ny>180000:raise ValueError("Grille trop lourde pour l'analyse.")
            hmarr=heightmap_to_array(self.processed_heightmap((nx,ny)),nx,ny,flip_y=self.flip_y.get());xs=np.linspace(0,w,nx)
            rows=list(range(ny));raw=len(rows)*nx;kept=0
            for j in rows:
                kept += len(
                    simplify_profile(
                        xs,
                        self.base_value()+r*hmarr[j],
                        tol,
                        sample_mm=s,
                        base_mm=self.base_value(),
                    )
                ) if self.adaptive.get() else nx
            reduction=100*(1-kept/max(1,raw))
            self.estimate_text.set(
                f"Analyse sûre : {len(rows)}/{ny} sections Y ; "
                f"~{kept:,}/{raw:,} points X ({reduction:.0f}% retirés avant validation spline)."
            )
        except Exception as exc:messagebox.showerror(APP_TITLE,str(exc))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def base_value(self):return float(self.base_mm.get().replace(",","."))
    def read_wall_values(self):
        return (float(self.wall_w.get().replace(",",".")),float(self.wall_h.get().replace(",",".")),self.base_value(),
                float(self.relief_mm.get().replace(",",".")),float(self.sample_mm.get().replace(",",".")))

    def export_heightmap(self):
        if not self.layers:return
        out=filedialog.asksaveasfilename(title="Exporter height-map",defaultextension=".png",filetypes=[("PNG","*.png")])
        if not out:return
        try:
            w,h,_b,_r,s=self.read_wall_values();pxw=max(800,int(math.ceil(w/max(.2,s)))*4);pxh=max(240,int(round(pxw*h/w)))
            self.processed_heightmap((pxw,pxh)).save(out);self.status.set(f"Height-map enregistrée : {out}")
        except Exception as exc:messagebox.showerror(APP_TITLE,str(exc))

    def export_step(self):
        if not self.layers:return
        try:w,h,base,relief,sample=self.read_wall_values();tol=float(self.adaptive_tol.get().replace(",","."))
        except Exception as exc:messagebox.showerror(APP_TITLE,str(exc));return
        out=filedialog.asksaveasfilename(title="Créer le STEP",defaultextension=".step",initialfile=f"mur_{w:g}x{h:g}.step",filetypes=[("STEP","*.step *.stp")])
        if not out:return
        target_w=max(600,int(math.ceil(w/sample))*3);target_h=max(200,int(math.ceil(h/sample))*3)
        hm=self.processed_heightmap((target_w,target_h));self.step_button.config(state="disabled");self.progress["value"]=0;self.status.set("Génération STEP…")
        def progress(v,msg):self.after(0,lambda:self._set_progress(v,msg))
        def worker():
            try:
                info=generate_step_from_heightmap(hm,out,w,h,base,relief,sample,flip_y=self.flip_y.get(),bands_mode=self.bands_mode.get(),
                    adaptive=self.adaptive.get(),adaptive_tolerance_mm=tol,reference_body=self.reference_body.get(),progress=progress,logger=APP_LOG)
                self.after(0,lambda:self._step_ok(info))
            except Exception as exc:
                tb=traceback.format_exc();self.after(0,lambda:self._step_error(exc,tb))
        threading.Thread(target=worker,daemon=True).start()

    def _set_progress(self,v,msg):self.progress["value"]=clamp(v,0,1)*100;self.status.set(msg)
    def _step_ok(self,info):
        self.step_button.config(state="normal");self.progress["value"]=100;mb=info["size_bytes"]/(1024*1024);valid="oui" if info["valid"] else "non vérifié"
        ref="\nSTEP multi-corps : Mur_complet + Base_reference" if info.get("reference_body") else ""
        self.status.set(f"STEP créé : {info['path']}")
        messagebox.showinfo(APP_TITLE,f"STEP créé.\n\nGrille brute : {info['nx']} × {info['ny']}\nSections utilisées : {info['sections']}\nPoints profils : {info['points_kept']:,}/{info['points_raw']:,}\nÉpaisseur : {info['min_z']:.2f} à {info['max_z']:.2f} mm\nTaille : {mb:.1f} Mo\nSolide valide : {valid}\nSurface : {info['surface_mode']}{ref}")
    def _step_error(self,exc,tb):
        self.step_button.config(state="normal");self.progress["value"]=0;self.status.set("Échec génération.");APP_LOG.error(str(exc));APP_LOG.logger.error(tb);messagebox.showerror(APP_TITLE,f"{exc}\n\nVoir l'onglet Logs.")

def main():
    App().mainloop()


if __name__ == "__main__":
    main()
