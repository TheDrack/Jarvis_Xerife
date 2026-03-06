# -*- coding: utf-8 -*-
"""
_NexusRegistryMixin – local JRVS registry I/O and GitHub Gist sync.

Mixed into JarvisNexus so the registry logic lives in its own file while
still having access to the instance attributes ``_cache``, ``_mutated``,
``base_dir`` and ``gist_id`` that JarvisNexus defines in ``__init__``.
"""
import logging
import os
import time
from typing import Dict

from app.utils.jrvs_codec import JrvsDecodeError, read_file as _jrvs_read, write_file as _jrvs_write

logger = logging.getLogger(__name__)


class _NexusRegistryMixin:
    """Provides local-registry and remote Gist persistence for JarvisNexus."""

    # ------------------------------------------------------------------
    # Local registry helpers
    # ------------------------------------------------------------------

    def _load_local_registry(self) -> Dict[str, str]:
        """Read nexus_registry.jrvs; if missing locally, try Supabase Storage as fallback."""
        registry_path = os.path.join(self.base_dir, "data", "nexus_registry.jrvs")
        try:
            data = _jrvs_read(registry_path)
            result: Dict[str, str] = {}
            for component_id, path in data.get("components", {}).items():
                parts = path.rsplit(".", 1)
                if len(parts) == 2 and parts[1] and parts[1][0].isupper():
                    result[component_id] = parts[0]
                else:
                    result[component_id] = path
            return result
        except (FileNotFoundError, JrvsDecodeError, OSError):
            pass

        # --- Supabase fallback: download registry from cloud if local file missing ---
        # NOTE: Direct instantiation here is intentional — this code runs during Nexus
        # bootstrap (__init__), before nexus.resolve() is available. Using nexus.resolve()
        # here would create a circular dependency.
        try:
            from app.adapters.infrastructure.jrvs_cloud_storage import JrvsCloudStorage

            cloud = JrvsCloudStorage()
            raw = cloud.download("jrvs-snapshots", "data/nexus_registry.jrvs")
            if raw:
                os.makedirs(os.path.dirname(registry_path), exist_ok=True)
                with open(registry_path, "wb") as fh:
                    fh.write(raw)
                logger.info("[NEXUS] nexus_registry.jrvs restaurado do Supabase Storage.")
                data = _jrvs_read(registry_path)
                result = {}
                for component_id, path in data.get("components", {}).items():
                    parts = path.rsplit(".", 1)
                    if len(parts) == 2 and parts[1] and parts[1][0].isupper():
                        result[component_id] = parts[0]
                    else:
                        result[component_id] = path
                return result
        except Exception as exc:
            logger.debug("[NEXUS] Supabase fallback indisponível: %s", exc)

        return {}

    def _update_local_registry(self) -> None:
        """Write _cache back to nexus_registry.jrvs with a ``.ClassName`` suffix.

        After a successful local write, uploads the file to Supabase Storage
        in the background as an automatic backup (non-blocking).
        """
        components: Dict[str, str] = {}
        for component_id, module_path in self._cache.items():
            last_segment = module_path.rsplit(".", 1)[-1]
            class_name = "".join(part.capitalize() for part in last_segment.split("_"))
            components[component_id] = f"{module_path}.{class_name}"
        registry_path = os.path.join(self.base_dir, "data", "nexus_registry.jrvs")
        _jrvs_write(registry_path, {"components": components})

        # --- Parallel cloud backup via Nexus-resolved JrvsCloudStorage (best-effort, never blocks) ---
        try:
            import threading

            with open(registry_path, "rb") as fh:
                raw = fh.read()

            def _upload() -> None:
                try:
                    # Resolve via Nexus — safe here because _update_local_registry is
                    # called AFTER the Nexus has finished bootstrapping.
                    from app.core.nexus import nexus as _nexus

                    cloud = _nexus.resolve("jrvs_cloud_storage")
                    cloud.upload("jrvs-snapshots", "data/nexus_registry.jrvs", raw)
                except Exception as exc:
                    logger.debug("[NEXUS] Supabase backup falhou silenciosamente: %s", exc)

            threading.Thread(target=_upload, daemon=True).start()
        except Exception as exc:
            logger.debug("[NEXUS] Falha ao iniciar backup Supabase: %s", exc)

    def _load_remote_memory(self) -> Dict[str, str]:
        """Fetch the component registry from the configured GitHub Gist."""
        try:
            import requests  # noqa: PLC0415

            gist_id = getattr(self, "gist_id", "")
            if not gist_id:
                return {}
            response = requests.get(f"https://api.github.com/gists/{gist_id}")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Gist sync
    # ------------------------------------------------------------------

    def commit_memory(self) -> None:
        """Push _cache to the configured GitHub Gist.

        Retries up to 3 times with exponential back-off (0.1 s → 0.2 s).
        ``_update_local_registry()`` is called *only* after a confirmed 200.
        """
        import requests  # noqa: PLC0415

        if not getattr(self, "_mutated", False):
            return

        gist_pat = os.getenv("GIST_PAT", "")
        if not gist_pat:
            logger.warning("[NEXUS] No GIST_PAT set; skipping gist sync.")
            return

        cache = getattr(self, "_cache", {})
        if not isinstance(cache, dict) or not all(isinstance(v, str) for v in cache.values()):
            logger.error("[NEXUS] Invalid cache structure; aborting gist sync.")
            return

        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {
            "Authorization": f"token {gist_pat}",
            "Accept": "application/vnd.github.v3+json",
        }

        for attempt in range(3):
            try:
                response = requests.patch(url, headers=headers, json=cache)
                if response.status_code == 200:
                    self._update_local_registry()
                    self._mutated = False
                    return
                logger.warning(
                    "[NEXUS] Gist patch attempt %d returned %d.",
                    attempt + 1,
                    response.status_code,
                )
            except Exception as err:
                logger.error("[NEXUS] Gist patch attempt %d exception: %s.", attempt + 1, err)
            if attempt < 2:
                time.sleep(0.1 * (2**attempt))

        logger.error("[NEXUS] All gist patch attempts failed; _mutated remains True.")
