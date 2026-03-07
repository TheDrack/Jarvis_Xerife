
# -*- coding: utf-8 -*-
"""FineTuneDatasetCollector — coleta e formata pares de treino para fine-tuning LoRA.

Responsabilidade: coletar pares (prompt, código gerado) aprovados pelo sistema de
recompensa e formatá-los no padrão de fine-tuning do Qwen/Llama.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_DATASET_DIR = Path("data/finetune")
_GLOBAL_DIR = _DATASET_DIR / "global"
_USERS_DIR = _DATASET_DIR / "users"

class FineTuneDatasetCollector(NexusComponent):
    """Coleta pares de treino para fine-tuning do modelo local."""
    
    def __init__(self):
        super().__init__()
        self._global_dir = _GLOBAL_DIR
        self._users_dir = _USERS_DIR
        self._global_dir.mkdir(parents=True, exist_ok=True)
        self._users_dir.mkdir(parents=True, exist_ok=True)
    
    def collect(self, min_reward: float = 0.7) -> List[dict]:
        """Coleta pares com reward >= min_reward do ThoughtLog."""
        thought_log = nexus.resolve("thought_log_service")
        if thought_log is None:
            logger.warning("[FineTuneCollector] ThoughtLogService indisponível.")
            return []
        
        samples = []
        logs = thought_log.get_last_n_entries(1000)
        for log in logs:
            reward = log.get("reward", 0.0)
            if reward >= min_reward:
                sample = {
                    "prompt": log.get("prompt", ""),
                    "completion": log.get("completion", ""),
                    "reward": reward,
                    "scope": self._classify_scope(log.get("prompt", ""), log.get("completion", "")),
                    "user_id": log.get("user_id", "system"),
                    "timestamp": log.get("timestamp", datetime.now(timezone.utc).isoformat())
                }
                samples.append(sample)
        
        logger.info("[FineTuneCollector] %d pares coletados com reward >= %.2f", len(samples), min_reward)
        return samples
    
    def collect_from_interaction(self, user_id: str, prompt: str, 
                                  completion: str, outcome: str, 
                                  source: str, feedback: Optional[str] = None):
        """Coleta interações de Telegram/HUD para fine-tuning.
        
        ADIÇÃO: Método novo para integração com interfaces.
        """
        reward_signal = nexus.resolve("reward_signal_provider")
        if reward_signal is None:
            logger.warning("[FineTuneCollector] RewardSignalProvider indisponível.")
            return
        
        reward = reward_signal.calculate_interaction_reward(outcome, feedback)
        if reward >= 0.6:
            sample = {
                "user_id": user_id,
                "prompt": prompt,
                "completion": completion,
                "reward": reward,
                "scope": self._classify_scope(prompt, completion),
                "source": source,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self._append_to_jsonl(sample, user_id=user_id)
            
            # Data augmentation se reward >= 0.7
            if reward >= 0.7:
                self._augment_with_llm(sample, user_id)
    
    def _classify_scope(self, prompt: str, completion: str) -> str:
        """Define se o aprendizado é pessoal ou global."""
        personal_keywords = ["prefiro", "meu", "minha", "eu gosto", "para mim", "meu estilo"]
        global_keywords = ["bug", "performance", "arquitetura", "teste", "api", "capability", "cap-"]
        
        text = f"{prompt} {completion}".lower()
        
        if any(kw in text for kw in personal_keywords):
            return "personal"
        elif any(kw in text for kw in global_keywords):
            return "global"
        else:
            return "global"
    
    def _append_to_jsonl(self, sample: dict, user_id: str):
        """Armazena sample em arquivo JSONL separado por usuário/escopo."""
        scope = sample.get("scope", "global")
        
        if scope == "global":
            file_path = self._global_dir / f"experiences_{datetime.now().strftime('%Y%m')}.jsonl"
        else:
            user_dir = self._users_dir / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            file_path = user_dir / f"preferences_{datetime.now().strftime('%Y%m')}.jsonl"
        
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        
        logger.debug("[FineTuneCollector] Sample salvo em %s", file_path)
    
    async def _augment_with_llm(self, base_sample: dict, user_id: str):
        """Gera 3 variações sintéticas de um exemplo válido via LLM."""
        llm_router = nexus.resolve("llm_router")
        if llm_router is None:
            return
        
        prompt = f"""Base: "{base_sample['prompt']}" → "{base_sample['completion']}"
Gere 3 variações do comando do usuário com mesma intenção, formuladas diferente.
Retorne apenas JSON: {{"variations": ["var1", "var2", "var3"]}}"""
        
        try:
            result = await llm_router.execute({
                "prompt": prompt,
                "task_type": "data_augmentation",
                "require_json": True
            })
            
            variations = json.loads(result.get("response", "{}")).get("variations", [])
            for var in variations[:3]:
                aug_sample = {**base_sample, "prompt": var, "synthetic": True}
                self._append_to_jsonl(aug_sample, user_id=user_id)
            
            logger.info("[FineTuneCollector] %d variações geradas via LLM", len(variations[:3]))
        except Exception as e:
            logger.warning("[FineTuneCollector] Augmentation falhou: %s", e)
    
    def export_dataset(self, output_path: str, user_id: Optional[str] = None) -> str:
        """Exporta dataset consolidado para fine-tuning."""
        samples = []
        
        # Global samples
        for file_path in self._global_dir.glob("*.jsonl"):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    samples.append(json.loads(line))
        
        # User samples se especificado
        if user_id:
            user_dir = self._users_dir / user_id
            for file_path in user_dir.glob("*.jsonl"):
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        samples.append(json.loads(line))
        
        # Formato Qwen/Llama
        formatted = []
        for sample in samples:
            formatted.append({
                "messages": [
                    {"role": "user", "content": sample["prompt"]},
                    {"role": "assistant", "content": sample["completion"]}
                ],
                "reward": sample["reward"]
            })
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(formatted, f, indent=2, ensure_ascii=False)
        
        logger.info("[FineTuneCollector] Dataset exportado: %s (%d samples)", output_path, len(formatted))
        return output_path