"""Exact-model retrieval of sourced specifications for grounded Gemma recommendations.

Unrecognized models remain unknown. A name resembling another board is not evidence.
"""
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

PATH = Path(__file__).with_name("knowledge") / "compatibility.json"


@lru_cache(maxsize=1)
def load_knowledge():
    raw = PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def knowledge_version():
    return load_knowledge()[1]


def identity(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def lookup(kind, name):
    query = identity(name)
    matches = []
    for row in load_knowledge()[0][kind]:
        # Freshness and explicit source are required; names preserve D4/WiFi/etc.
        try:
            age = (date.today() - date.fromisoformat(row["last_verified"])).days
        except (KeyError, ValueError):
            continue
        names = {identity(row["model"]), identity(row["vendor"] + " " + row["model"])}
        if query in names and 0 <= age <= 365:
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def board_for(snapshot):
    board = snapshot.data("hardware").get("motherboard") or {}
    row = lookup("boards", board.get("product"))
    vendor = identity(board.get("manufacturer"))
    if row and vendor:
        aliases = {"asus": {"asus", "asustekcomputerinc"}, "msi": {"msi", "microstarinternationalcoltd"},
                   "asrock": {"asrock", "asrockinc"}}
        expected = identity(row["vendor"])
        if vendor not in aliases.get(expected, {expected}):
            return None
    return row


def memory_facts(snapshot):
    from app.logic.compatibility import infer_memory_generation
    hardware = snapshot.data("hardware")
    memory = hardware.get("memory") or {}
    modules = memory.get("modules") or []
    board = board_for(snapshot)
    generations = {m.get("memory_generation") for m in modules if m.get("memory_generation")}
    generations.update({{26: "DDR4", 34: "DDR5"}[m["smbios_memory_type"]]
                        for m in modules if m.get("smbios_memory_type") in (26, 34)})
    if board:
        generations.add(board["ram_type"])
    else:
        hinted = infer_memory_generation((hardware.get("motherboard") or {}).get("product"))
        if hinted:
            generations.add(hinted)
    factors = {"DIMM" if m.get("form_factor") == "UDIMM" else m.get("form_factor") for m in modules if m.get("form_factor")}
    if board and board.get("memory_form_factor"):
        factors.add("DIMM" if board["memory_form_factor"] == "UDIMM" else board["memory_form_factor"])
    slots = [v for v in (memory.get("slot_count"), board.get("ram_slots") if board else None) if isinstance(v, int) and v > 0]
    capacities = [v for v in (memory.get("max_capacity_gb"), board.get("ram_max_gb") if board else None) if isinstance(v, (int, float)) and v > 0]
    return {"generation": next(iter(generations)) if len(generations) == 1 else None,
            "form_factor": next(iter(factors)) if len(factors) == 1 else None,
            "conflict": len(generations) > 1 or len(factors) > 1,
            "slot_count": min(slots) if slots else None,
            "max_capacity_gb": min(capacities) if capacities else None,
            "board": board}


def memory_candidate_allowed(snapshot, product):
    facts = memory_facts(snapshot)
    if facts["conflict"]:
        return False
    for field, product_field in (("generation", "memory_generation"), ("form_factor", "form_factor")):
        expected = "DIMM" if field == "form_factor" and product.get(product_field) == "UDIMM" else product.get(product_field)
        if facts[field] and facts[field] != expected:
            return False
    if facts["slot_count"] and product["module_count"] > facts["slot_count"]:
        return False
    if facts["max_capacity_gb"] and product["capacity_gb"] > facts["max_capacity_gb"]:
        return False
    return True
