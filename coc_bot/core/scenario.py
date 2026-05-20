import json
import os

SCENARIOS_DIR = os.path.join("coc_bot", "scenarios")


def list_scenarios():
    if not os.path.isdir(SCENARIOS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json"))


def load_scenario(name):
    with open(os.path.join(SCENARIOS_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def save_scenario(name, slots):
    os.makedirs(SCENARIOS_DIR, exist_ok=True)
    with open(os.path.join(SCENARIOS_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"name": name, "slots": slots}, f, indent=2)


def delete_scenario(name):
    path = os.path.join(SCENARIOS_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)


def rename_scenario(old, new):
    data = load_scenario(old)
    save_scenario(new, data["slots"])
    delete_scenario(old)
