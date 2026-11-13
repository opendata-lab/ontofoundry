"""Best-effort asynchronous audit recording. Public methods never propagate failures."""

import logging
import queue
import threading
from contextlib import suppress
from copy import deepcopy

from sqlalchemy import or_, update
from sqlalchemy.exc import OperationalError

from ontofoundry_api.db_models import (
    OntologyGatewayCallRecord,
    OntologyGatewayCallWorkspaceRecord,
    PersonalAccessTokenRecord,
)

logger = logging.getLogger(__name__)
QUEUE_CAPACITY = 10_000


class GatewayCallRecorder:
    def __init__(self, session_factory, *, capacity=QUEUE_CAPACITY):
        self.session_factory = session_factory
        self.queue = queue.Queue(maxsize=capacity)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="gateway-call-recorder", daemon=True)

    def start(self):
        try:
            self.thread.start()
        except Exception:
            logger.exception("Gateway recorder startup failed")

    def enqueue(self, event):
        try:
            if self.stopping.is_set():
                logger.warning("Gateway recorder is stopping; event dropped")
                return
            self.queue.put_nowait(deepcopy(event))
        except queue.Full:
            logger.warning("Gateway recorder queue is full; event dropped")
        except Exception:
            logger.exception("Gateway recorder enqueue failed")

    def touch(self, token_id, used_at):
        self.enqueue({"type": "touch", "token_id": token_id, "used_at": used_at})

    def started(self, call, workspaces):
        self.enqueue({"type": "call", "call": call, "workspaces": workspaces})

    def finished(self, call, workspaces):
        self.enqueue({"type": "call", "call": call, "workspaces": workspaces})

    def stop(self):
        try:
            self.stopping.set()
            with suppress(queue.Full):
                self.queue.put_nowait({"type": "stop"})
            self.thread.join(timeout=5)
            if self.thread.is_alive() or not self.queue.empty():
                logger.warning("Gateway recorder shutdown drain exceeded 5 seconds; remaining events dropped")
                while True:
                    try:
                        self.queue.get_nowait()
                        self.queue.task_done()
                    except queue.Empty:
                        break
        except Exception:
            logger.exception("Gateway recorder shutdown failed")

    def _run(self):
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                first = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            batch = [first]
            for _ in range(99):
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._write_batch(batch)
            except OperationalError:
                logger.exception("Gateway recorder database unavailable")
                # Retry through the same bounded queue. Never wait on a producer.
                self.stopping.wait(0.2)
                for event in batch:
                    self.enqueue(event)
            except Exception:
                logger.exception("Gateway recorder batch failed; batch dropped")
            finally:
                for _ in batch:
                    self.queue.task_done()

    def _write_batch(self, events):
        events = [event for event in events if event["type"] != "stop"]
        if not events:
            return
        with self.session_factory() as db:
            for event in events:
                if event["type"] == "touch":
                    db.execute(update(PersonalAccessTokenRecord).where(
                        PersonalAccessTokenRecord.id == event["token_id"],
                        or_(PersonalAccessTokenRecord.last_used_at.is_(None),
                            PersonalAccessTokenRecord.last_used_at < event["used_at"]),
                    ).values(last_used_at=event["used_at"]))
                    continue
                values = event["call"]
                item = db.get(OntologyGatewayCallRecord, values["id"])
                if item is None:
                    item = OntologyGatewayCallRecord(**values)
                    db.add(item)
                    db.flush()
                elif values["outcome"] != "started":
                    for key, value in values.items():
                        setattr(item, key, value)
                else:
                    # A delayed start must never regress an already finished row.
                    continue
                for workspace in event["workspaces"]:
                    key = (item.id, workspace["workspace_id"])
                    row = db.get(OntologyGatewayCallWorkspaceRecord, key)
                    if row is None:
                        row = OntologyGatewayCallWorkspaceRecord(call_id=item.id, **workspace, created_at=item.created_at)
                        db.add(row)
                        db.flush()
                    else:
                        row.version_id = workspace.get("version_id")
                        row.version_number = workspace.get("version_number")
                db.flush()
            db.commit()
