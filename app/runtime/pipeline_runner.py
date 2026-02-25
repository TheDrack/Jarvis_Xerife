# -*- coding: utf-8 -*-

import yaml
from app.core.nexus import nexus


def run_pipeline(config_path: str):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    components = {}

    for name, meta in config["components"].items():
        instance = nexus.resolve(
            target_id=meta["id"],
            hint_path=meta.get("hint_path"),
            singleton=meta.get("singleton", True),
        )

        if "config" in meta:
            instance.configure(meta["config"])

        components[name] = instance

    consolidator = components["consolidator"]
    uploader = components["drive_uploader"]

    artifact = consolidator.consolidate()
    uploader.upload(artifact)


if __name__ == "__main__":
    run_pipeline("config/pipeline.yml")