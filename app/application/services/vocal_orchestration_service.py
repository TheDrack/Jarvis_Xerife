from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Vocal Orchestration Service — speaker identification and voice profile management.

Connects audio capture adapters to speaker recognition capabilities and
persists voice biometrics per user in the Supabase ``voice_profiles`` table
(migration 004).

Match threshold: embeddings with cosine similarity ≥ 0.85 are considered a
confirmed identity match; below that a new profile is created.
"""

import logging
import math
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.85  # minimum cosine similarity to confirm identity
_EMBEDDING_DIM = 512      # must match voice_profiles.voice_embedding size


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a)) or 1.0
    mag_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (mag_a * mag_b)


class VocalOrchestrationService(NexusComponent):
    """Connects audio capture to speaker recognition and Supabase voice profiles.

    Workflow per audio segment:
    1. Diarize the audio → extract per-speaker segments.
    2. Encode each segment → voice embedding (512-dim float vector).
    3. Query ``voice_profiles`` for an existing profile with similarity ≥ 0.85.
    4. If match found → assign ``user_id`` to the session segment.
    5. If no match → insert new ``voice_profiles`` row and notify the user.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("JARVIS_ORCHESTRATOR")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """NexusComponent entry-point.

        Expected context keys:
            ``audio_path`` (str): Path to the audio file to process.
            ``session_user`` (str, optional): Hint for the current user.

        Returns:
            Dict with ``status``, ``segments``, and ``detected_count``.
        """
        ctx = context or {}
        audio_path = ctx.get("audio_path", "")
        session_user = ctx.get("session_user")
        if not audio_path:
            return {"status": "error", "message": "audio_path obrigatório no contexto"}
        return self._run(audio_path, session_user)

    def _run(self, audio_path: str, session_user: Optional[str] = None) -> Dict[str, Any]:
        """Execute the full vocal orchestration pipeline.

        Args:
            audio_path:   Path to the audio file.
            session_user: Optional current-session user hint.

        Returns:
            Orchestration result dict.
        """
        try:
            import torchaudio

            from app.application.containers.hub import hub

            diarizer = hub.resolve("diarizer", "adapters")
            encoder = hub.resolve("audio_processor", "adapters")
            identifier = hub.resolve("identify_speaker", "capabilities")
            learner = hub.resolve("learn_voice", "capabilities")

            if not all([diarizer, encoder, identifier, learner]):
                self._logger.error("Falha ao resolver dependências no Hub.")
                return {"status": "error", "message": "Componentes incompletos"}

            diarization_segments = diarizer(audio_path)
            waveform, sr = torchaudio.load(audio_path)
            final_report: List[Dict[str, Any]] = []

            for turn, _, _ in diarization_segments.itertracks(yield_label=True):
                start_sample = int(turn.start * sr)
                end_sample = int(turn.end * sr)
                segment_audio = waveform[:, start_sample:end_sample]
                embedding = encoder(segment_audio)

                # Convert to plain Python list for DB storage
                embedding_list: List[float] = (
                    embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                )

                name, confidence = identifier(embedding)

                # Try to resolve to a persisted user profile
                user_id = self._resolve_user_id(embedding_list, session_user)

                if not name and not user_id:
                    status_aprendizado = learner(embedding, session_user)
                    name = "Desconhecido"
                    self._logger.info(
                        "Nova voz detectada [%.2fs]: %s", turn.start, status_aprendizado
                    )
                    # Create a new voice profile so future segments match
                    self._create_voice_profile(embedding_list, user_id=None)
                else:
                    self._logger.info("Voz reconhecida: %s (%.2f%%)", name, confidence * 100)
                    if user_id:
                        self._update_voice_profile(embedding_list, user_id)

                final_report.append(
                    {
                        "speaker": name,
                        "confidence": confidence,
                        "user_id": user_id,
                        "start": turn.start,
                        "end": turn.end,
                    }
                )

            return {
                "status": "success",
                "segments": final_report,
                "detected_count": len({seg["speaker"] for seg in final_report}),
            }

        except Exception as exc:
            self._logger.error("Erro na orquestração vocal: %s", exc)
            return {"status": "error", "error_details": str(exc)}

    # ------------------------------------------------------------------
    # Voice profile DB helpers (Supabase)
    # ------------------------------------------------------------------

    def _resolve_user_id(
        self, embedding: List[float], session_user: Optional[str]
    ) -> Optional[str]:
        """Find a matching user_id from voice_profiles via cosine similarity.

        Args:
            embedding:    512-dim voice embedding of the current segment.
            session_user: Optional e-mail / username hint for fast-path lookup.

        Returns:
            ``user_id`` string if a profile matches (≥ threshold), else ``None``.
        """
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                return None

            # Narrow search by session_user hint when available
            query = client.table("voice_profiles").select("id, user_id, voice_embedding")
            if session_user:
                # Try to find user by email first and filter by user_id
                user_resp = (
                    client.table("users").select("id").eq("email", session_user).limit(1).execute()
                )
                rows = user_resp.data
                if rows:
                    query = query.eq("user_id", rows[0]["id"])

            response = query.execute()
            profiles = response.data or []

            best_score = 0.0
            best_user_id: Optional[str] = None

            for profile in profiles:
                stored_emb = profile.get("voice_embedding")
                if not stored_emb or len(stored_emb) != len(embedding):
                    continue
                score = _cosine_similarity(embedding, stored_emb)
                if score > best_score:
                    best_score = score
                    best_user_id = profile.get("user_id")

            if best_score >= _MATCH_THRESHOLD:
                logger.debug(
                    "[VocalOrchestration] Match user_id=%s score=%.3f", best_user_id, best_score
                )
                return best_user_id

        except Exception as exc:
            logger.debug("[VocalOrchestration] _resolve_user_id falhou: %s", exc)

        return None

    def _create_voice_profile(
        self, embedding: List[float], user_id: Optional[str]
    ) -> Optional[str]:
        """Insert a new ``voice_profiles`` row and return its ``id``."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                return None

            row: Dict[str, Any] = {
                "voice_embedding": embedding,
                "samples_count": 1,
                "confidence_score": 0.0,
            }
            if user_id:
                row["user_id"] = user_id

            resp = client.table("voice_profiles").insert(row).execute()
            rows = resp.data
            if rows:
                logger.info("[VocalOrchestration] Novo voice_profile criado: %s", rows[0]["id"])
                return rows[0]["id"]
        except Exception as exc:
            logger.debug("[VocalOrchestration] _create_voice_profile falhou: %s", exc)
        return None

    def _update_voice_profile(self, embedding: List[float], user_id: str) -> None:
        """Update samples_count and confidence_score for *user_id*'s voice profile."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                return

            # Increment samples_count — Supabase RPC or manual fetch+update
            resp = (
                client.table("voice_profiles")
                .select("id, samples_count")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = resp.data
            if rows:
                profile_id = rows[0]["id"]
                new_count = rows[0].get("samples_count", 1) + 1
                client.table("voice_profiles").update(
                    {"samples_count": new_count, "voice_embedding": embedding}
                ).eq("id", profile_id).execute()
        except Exception as exc:
            logger.debug("[VocalOrchestration] _update_voice_profile falhou: %s", exc)


# Nexus compatibility alias
orchestrator = VocalOrchestrationService()

