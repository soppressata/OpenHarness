"""
Global Intelligence Fabric ("The Commons").

Consent-based anonymized telemetry, versioned test-genome recipes,
cross-project recommendations, and 24h opt-out purge.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from openharness.mesh.identity import PeerIdentity, _canonical_json
from openharness.mesh.events import EventType, make_event


# Patterns scrubbed from telemetry (PII linter).
_PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "[UUID]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
]


def scrub_pii(text: str) -> str:
    """Redact PII and secrets from free text (AC-17)."""
    out = text
    for pattern, repl in _PII_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_pii(value)
    if isinstance(value, dict):
        return {str(k): _scrub_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def anonymize_telemetry(
    record: Dict[str, Any],
    project_id: str,
    salt: str = "openharness-commons",
) -> Dict[str, Any]:
    """Produce anonymized telemetry for the public corpus (AC-17)."""
    scrubbed = _scrub_value(record)
    anon_project = hashlib.sha256(f"{salt}:{project_id}".encode()).hexdigest()[:16]
    return {
        "project_hash": anon_project,
        "ingested_at": time.time(),
        "payload": scrubbed,
        "pii_scrubbed": True,
    }


class TestGenomeRecipe(BaseModel):
    """Versioned, diffable, installable test fixture/matrix recipe (AC-18)."""

    __test__ = False

    recipe_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    version: str = "1.0.0"
    description: str = ""
    pattern: Dict[str, Any] = Field(default_factory=dict)
    fixtures: Dict[str, Any] = Field(default_factory=dict)
    matrix: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    def content_digest(self) -> str:
        body = self.model_dump()
        body.pop("created_at", None)
        return hashlib.sha256(_canonical_json(body)).hexdigest()[:16]

    def diff(self, other: "TestGenomeRecipe") -> Dict[str, Any]:
        """Structural diff against another recipe version."""
        a, b = self.model_dump(), other.model_dump()
        changed = {}
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                changed[key] = {"from": a.get(key), "to": b.get(key)}
        return changed


class CommonsClient:
    """Local-first Commons store (file-backed public corpus simulation)."""

    def __init__(
        self,
        root: str | Path,
        project_id: str = "default",
        identity: Optional[PeerIdentity] = None,
        consent: bool = False,
    ):
        self.root = Path(root)
        self.project_id = project_id
        self.identity = identity
        self.consent = consent
        self.telemetry_dir = self.root / "telemetry"
        self.recipes_dir = self.root / "recipes"
        self.contributions_index = self.root / "contributions.json"
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        if not self.contributions_index.exists():
            self.contributions_index.write_text("{}", encoding="utf-8")

    def _load_index(self) -> Dict[str, Any]:
        try:
            return json.loads(self.contributions_index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_index(self, index: Dict[str, Any]) -> None:
        self.contributions_index.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    def contribute_telemetry(self, record: Dict[str, Any]) -> Optional[str]:
        """Contribute anonymized telemetry if consent is granted."""
        if not self.consent:
            return None
        anon = anonymize_telemetry(record, self.project_id)
        entry_id = uuid.uuid4().hex
        path = self.telemetry_dir / f"{entry_id}.json"
        path.write_text(json.dumps(anon, indent=2, sort_keys=True), encoding="utf-8")
        index = self._load_index()
        proj = index.setdefault(self.project_id, {"telemetry": [], "recipes": [], "opted_out": False})
        if proj.get("opted_out"):
            path.unlink(missing_ok=True)
            return None
        proj["telemetry"].append({"id": entry_id, "path": str(path), "at": time.time()})
        self._save_index(index)
        if self.identity:
            make_event(EventType.TELEMETRY, self.identity, payload={"entry_id": entry_id})
        return entry_id

    def publish_recipe(self, recipe: TestGenomeRecipe) -> str:
        """Publish a versioned genome recipe."""
        fname = f"{recipe.name.replace(' ', '_').lower()}-{recipe.version}.json"
        path = self.recipes_dir / fname
        path.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")
        if self.consent:
            index = self._load_index()
            proj = index.setdefault(self.project_id, {"telemetry": [], "recipes": [], "opted_out": False})
            if not proj.get("opted_out"):
                proj["recipes"].append({"id": recipe.recipe_id, "path": str(path), "at": time.time()})
                self._save_index(index)
        return str(path.resolve())

    def install_recipe(self, name: str, version: str, dest_dir: str | Path) -> str:
        """Install a recipe via a single call (AC-18)."""
        fname = f"{name.replace(' ', '_').lower()}-{version}.json"
        src = self.recipes_dir / fname
        if not src.exists():
            # try search
            matches = list(self.recipes_dir.glob(f"*{name}*{version}*.json"))
            if not matches:
                raise FileNotFoundError(f"recipe not found: {name}@{version}")
            src = matches[0]
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / src.name
        target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return str(target.resolve())

    def list_recipes(self) -> List[TestGenomeRecipe]:
        recipes: List[TestGenomeRecipe] = []
        for path in sorted(self.recipes_dir.glob("*.json")):
            try:
                recipes.append(TestGenomeRecipe(**json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return recipes

    def recommend(self, project_pattern: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
        """Surface actionable recipe suggestions by structural similarity (AC-19)."""
        suggestions: List[Dict[str, Any]] = []
        project_tags = set(project_pattern.get("tags", []))
        project_keys = set(project_pattern.get("pattern", {}).keys()) if isinstance(project_pattern.get("pattern"), dict) else set()
        suite_name = str(project_pattern.get("suite", project_pattern.get("name", "")))

        for recipe in self.list_recipes():
            score = 0.0
            reasons: List[str] = []
            recipe_tags = set(recipe.tags)
            overlap = project_tags & recipe_tags
            if overlap:
                score += 0.4 * (len(overlap) / max(1, len(project_tags | recipe_tags)))
                reasons.append(f"shared tags: {sorted(overlap)}")
            rkeys = set(recipe.pattern.keys())
            key_overlap = project_keys & rkeys
            if key_overlap:
                score += 0.4 * (len(key_overlap) / max(1, len(project_keys | rkeys)))
                reasons.append(f"pattern keys overlap: {sorted(key_overlap)}")
            if suite_name and suite_name.lower() in recipe.name.lower():
                score += 0.3
                reasons.append(f"name match with suite '{suite_name}'")
            # structural identity bonus
            if project_pattern.get("pattern") == recipe.pattern and recipe.pattern:
                score += 0.5
                reasons.append("structurally identical pattern")
            runtime_cut = recipe.metrics.get("runtime_reduction_pct")
            if runtime_cut:
                reasons.append(f"measured runtime reduction {runtime_cut}%")
                score += 0.1
            if score > 0:
                suggestions.append({
                    "recipe_id": recipe.recipe_id,
                    "name": recipe.name,
                    "version": recipe.version,
                    "score": round(score, 4),
                    "reasons": reasons,
                    "metrics": recipe.metrics,
                    "action": f"install recipe {recipe.name}@{recipe.version}",
                })
        suggestions.sort(key=lambda s: s["score"], reverse=True)
        return suggestions[:limit]

    def opt_out(self, purge: bool = True) -> Dict[str, Any]:
        """Opt out and remove prior contributions from the public corpus (AC-20).

        Removal is immediate in this local implementation (within 24h SLA).
        """
        self.consent = False
        index = self._load_index()
        proj = index.setdefault(self.project_id, {"telemetry": [], "recipes": [], "opted_out": False})
        removed = {"telemetry": 0, "recipes": 0}
        if purge:
            for entry in proj.get("telemetry", []):
                p = Path(entry.get("path", ""))
                if p.exists():
                    p.unlink()
                    removed["telemetry"] += 1
            # recipes stay globally if shared by name; only drop contribution refs
            removed["recipes"] = len(proj.get("recipes", []))
            proj["telemetry"] = []
            proj["recipes"] = []
        proj["opted_out"] = True
        proj["opted_out_at"] = time.time()
        self._save_index(index)
        return {"project_id": self.project_id, "opted_out": True, "removed": removed, "within_24h": True}
