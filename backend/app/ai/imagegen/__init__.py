"""Moteur d'images de Ludifun (étape 27) : une interface, plusieurs moteurs interchangeables.

Ludifun ne connaît que `ImageEngine` : stable-diffusion.cpp, ComfyUI, ou le service en ligne
Pollinations, se branchent sans que le reste change (`LUDIFUN_IMAGE_ENGINE`).
"""
