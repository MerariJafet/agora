"""Bounded queues and inbox behavior (S2-T08/T17, efficiency invariants)."""

from agora_api.realtime import CLIENT_QUEUE_LIMIT, RtClient
from agora_bridge.inbox import A2AInbox


def test_client_queue_is_bounded_and_lossy():
    client = RtClient(kind="browser")
    for i in range(CLIENT_QUEUE_LIMIT * 2):
        client.offer({"type": "message", "seq": i})
    assert client.queue.qsize() <= CLIENT_QUEUE_LIMIT
    # oldest frames were dropped, newest survive
    first = client.queue.get_nowait()
    assert first["seq"] >= CLIENT_QUEUE_LIMIT - 1


def test_inbox_bounded_and_overflow_counted():
    inbox = A2AInbox(limit=5)
    for i in range(9):
        inbox.offer({"task_id": f"tsk-{i}"})
    assert inbox.pending_count() == 5
    assert inbox.overflow_dropped == 4


def test_inbox_duplicate_task_dropped():
    inbox = A2AInbox()
    assert inbox.offer({"task_id": "tsk-dup"}) is True
    assert inbox.offer({"task_id": "tsk-dup"}) is False
    assert inbox.duplicates_dropped == 1
    assert inbox.pending_count() == 1
    # even after the task is taken/processed, redelivery stays deduplicated
    inbox.take()
    assert inbox.offer({"task_id": "tsk-dup"}) is False


def test_inbox_rejects_malformed_frames():
    inbox = A2AInbox()
    assert inbox.offer({}) is False
    assert inbox.offer({"task_id": 42}) is False