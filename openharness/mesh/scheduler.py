"""
Cross-cluster mesh scheduler with geo-optimal peer selection.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from openharness.mesh.discovery import PeerInfo
from openharness.mesh.manifest import RunManifest, SuiteResult, create_run_manifest, dual_sign_manifest
from openharness.mesh.identity import PeerIdentity


# Approximate region centroids (lat, lon) for geo distance scoring.
_REGION_COORDS: Dict[str, tuple[float, float]] = {
    "local": (0.0, 0.0),
    "us-east": (39.0, -77.0),
    "us-west": (37.0, -122.0),
    "eu-west": (53.0, -6.0),
    "eu-central": (50.0, 8.0),
    "ap-south": (19.0, 73.0),
    "ap-northeast": (35.0, 139.0),
    "sa-east": (-23.0, -46.0),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers between two WGS84 points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def region_distance_km(region_a: str, region_b: str) -> float:
    """Distance between named regions; unknown regions treated as far away."""
    a = _REGION_COORDS.get(region_a.lower(), (0.0, 180.0))
    b = _REGION_COORDS.get(region_b.lower(), (0.0, -180.0))
    return haversine_km(a[0], a[1], b[0], b[1])


def select_geo_optimal_peer(
    origin_region: str,
    peers: Sequence[PeerInfo],
    required_capabilities: Optional[Dict[str, Any]] = None,
) -> Optional[PeerInfo]:
    """Pick the fastest peer geo-optimally among peers with identical capabilities (AC-8).

    Scoring: lower is better.
      score = geo_distance_km + latency_ms_estimate
    When multiple peers advertise identical capabilities, the nearest/lowest-latency wins.
    """
    required = required_capabilities or {}
    candidates: List[PeerInfo] = []
    for peer in peers:
        if required:
            if any(peer.capabilities.get(k) != v for k, v in required.items()):
                continue
        candidates.append(peer)
    if not candidates:
        return None

    def score(p: PeerInfo) -> float:
        return region_distance_km(origin_region, p.region) + float(p.latency_ms_estimate)

    return min(candidates, key=score)


class MeshScheduler:
    """Schedules suite runs onto local or remote mesh peers."""

    def __init__(self, identity: PeerIdentity):
        self.identity = identity

    def select_peer(
        self,
        peers: Sequence[PeerInfo],
        required_capabilities: Optional[Dict[str, Any]] = None,
    ) -> Optional[PeerInfo]:
        """Select geo-optimal peer for this origin's region."""
        return select_geo_optimal_peer(
            self.identity.region,
            peers,
            required_capabilities=required_capabilities,
        )

    def schedule_remote(
        self,
        suite_id: str,
        executor: PeerIdentity,
        results: List[SuiteResult],
        suite_name: str = "",
        environment: Optional[Dict[str, Any]] = None,
    ) -> RunManifest:
        """Produce a dual-signed run manifest for a remote execution."""
        manifest = create_run_manifest(
            suite_id=suite_id,
            origin=self.identity,
            suite_name=suite_name,
            environment=environment or {"scheduler": "mesh", "origin_region": self.identity.region},
        )
        return dual_sign_manifest(manifest, executor, results)

    def rank_peers(
        self,
        peers: Sequence[PeerInfo],
        required_capabilities: Optional[Dict[str, Any]] = None,
    ) -> List[PeerInfo]:
        """Return peers sorted by geo+latency score (best first)."""
        required = required_capabilities or {}
        filtered = [
            p
            for p in peers
            if not required or all(p.capabilities.get(k) == v for k, v in required.items())
        ]
        return sorted(
            filtered,
            key=lambda p: region_distance_km(self.identity.region, p.region) + float(p.latency_ms_estimate),
        )
