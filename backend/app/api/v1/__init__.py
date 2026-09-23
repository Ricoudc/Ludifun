from fastapi import APIRouter

# Les routes métier (appareils, leçons, séances) sont ajoutées à l'étape 6.
router = APIRouter(prefix="/v1")
