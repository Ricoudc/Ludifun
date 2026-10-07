"""Moteur d'images de Ludifun (étape 27) : une interface, plusieurs moteurs interchangeables.

Ludifun ne connaît que `ImageEngine` : stable-diffusion.cpp, ComfyUI, ou plus tard un service en
ligne, se branchent sans que le reste change (`LUDIFUN_IMAGE_ENGINE`).
"""
