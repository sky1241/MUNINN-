"""Tests for fleet_raft 5-voter mode + client wrapper."""
import time
import sys
import pytest

sys.path.insert(0, "/home/sky/bin")
from pysyncobj import SyncObj, SyncObjConf


def _make_cluster(n_voters):
    """Spin up n in-process voters on localhost."""
    from fleet_raft import FleetState

    base_port = 19871
    addrs = [f"127.0.0.1:{base_port + i}" for i in range(n_voters)]
    nodes = []
    for i, addr in enumerate(addrs):
        partners = [a for a in addrs if a != addr]
        obj = FleetState.__new__(FleetState)
        cfg = SyncObjConf(dynamicMembershipChange=True, autoTick=True)
        SyncObj.__init__(obj, addr, partners, conf=cfg)
        obj._heartbeats = {}
        obj._locks = {}
        obj._roles = {}
        nodes.append(obj)
    return nodes


def _wait(nodes, check_fn, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(check_fn(n) for n in nodes):
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def five_voters():
    nodes = _make_cluster(5)
    deadline = time.time() + 15
    while time.time() < deadline:
        if all(n.isReady() for n in nodes):
            break
        time.sleep(0.1)
    yield nodes
    for n in nodes:
        n.destroy()
    time.sleep(0.3)


def test_five_voter_cluster_forms(five_voters):
    assert all(n.isReady() for n in five_voters)
    leaders = [n._getLeader() for n in five_voters]
    assert leaders[0] is not None
    assert all(l == leaders[0] for l in leaders), f"Split brain: {leaders}"


def test_quorum_survives_2_down(five_voters):
    nodes = five_voters
    nodes[3].destroy()
    nodes[4].destroy()
    time.sleep(2)
    remaining = nodes[:3]
    ts = time.time()
    remaining[0].heartbeat("survivor", ts)
    assert _wait(
        remaining,
        lambda n: n.get_heartbeats().get("survivor") == ts,
    ), "Quorum 3/5 should hold with 2 nodes down"


def test_lock_replicates_5_voters(five_voters):
    nodes = five_voters
    ts = time.time()
    nodes[2].acquire_lock("5v-lock", "pc3", ts)
    assert _wait(
        nodes,
        lambda n: n.get_locks().get("5v-lock", {}).get("holder") == "pc3",
    ), f"Lock not replicated across 5 voters: {[n.get_locks() for n in nodes]}"


def test_hostname_mapping():
    from fleet_raft_client import HOSTNAME_TO_NODE
    from fleet_raft import VOTERS
    for hostname, node_id in HOSTNAME_TO_NODE.items():
        assert node_id in VOTERS, f"{node_id} not in VOTERS"
