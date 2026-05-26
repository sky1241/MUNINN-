"""Tests for fleet_raft.py FleetState Raft consensus."""
import time
import sys
import pytest
sys.path.insert(0, "/home/sky/bin")


@pytest.fixture
def three_nodes():
    """Spin up 3 in-process Raft nodes on localhost."""
    from fleet_raft import FleetState
    from pysyncobj import SyncObjConf

    addrs = [
        "127.0.0.1:17871",
        "127.0.0.1:17872",
        "127.0.0.1:17873",
    ]
    nodes = []
    for i, addr in enumerate(addrs):
        partners = [a for a in addrs if a != addr]
        # Override config for test (no persistence, fast timeouts)
        obj = FleetState.__new__(FleetState)
        cfg = SyncObjConf(
            dynamicMembershipChange=False,
            autoTick=True,
            journalFile=None,
            fullDumpFile=None,
        )
        SyncObj.__init__(obj, addr, partners, conf=cfg)
        obj._heartbeats = {}
        obj._locks = {}
        obj._roles = {}
        nodes.append(obj)

    deadline = time.time() + 15
    while time.time() < deadline:
        if all(n.isReady() for n in nodes):
            break
        time.sleep(0.1)

    yield nodes

    for n in nodes:
        n.destroy()
    time.sleep(0.3)


from pysyncobj import SyncObj


def _wait_replicated(nodes, check_fn, timeout=10):
    """Wait until check_fn(node) is True for all nodes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(check_fn(n) for n in nodes):
            return True
        time.sleep(0.1)
    return False


def test_heartbeat_replicates(three_nodes):
    nodes = three_nodes
    ts = time.time()
    nodes[0].heartbeat("nodeA", ts)

    assert _wait_replicated(
        nodes,
        lambda n: n.get_heartbeats().get("nodeA") == ts,
    ), f"Heartbeat not replicated. States: {[n.get_heartbeats() for n in nodes]}"


def test_acquire_lock_exclusive(three_nodes):
    nodes = three_nodes
    ts = time.time()

    nodes[0].acquire_lock("prune", "pc1", ts)
    _wait_replicated(nodes, lambda n: "prune" in n.get_locks(), timeout=5)

    nodes[1].acquire_lock("prune", "pc2", ts + 1)
    time.sleep(1)

    for n in nodes:
        lock = n.get_locks().get("prune", {})
        assert lock.get("holder") == "pc1", f"Lock should be held by pc1, got {lock}"


def test_release_lock_holder_only(three_nodes):
    nodes = three_nodes
    ts = time.time()

    nodes[0].acquire_lock("sync", "pc1", ts)
    _wait_replicated(nodes, lambda n: "sync" in n.get_locks(), timeout=5)

    nodes[1].release_lock("sync", "pc2")
    time.sleep(1)
    for n in nodes:
        assert "sync" in n.get_locks(), "Non-holder release should be no-op"

    nodes[0].release_lock("sync", "pc1")
    assert _wait_replicated(
        nodes, lambda n: "sync" not in n.get_locks()
    ), "Holder release should remove lock"


def test_assign_role_replicated(three_nodes):
    nodes = three_nodes
    nodes[0].assign_role("orchestrator", "sky-master")

    assert _wait_replicated(
        nodes,
        lambda n: n.get_roles().get("orchestrator") == "sky-master",
    ), f"Role not replicated. States: {[n.get_roles() for n in nodes]}"
