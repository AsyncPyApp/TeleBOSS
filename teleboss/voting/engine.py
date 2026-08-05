"""Poll completion engine with durable claim/recovery lifecycle."""

import logging
import os
import threading
import time
import traceback
import weakref

from teleboss.shared.runtime import bot, data, sqlWorker


class PollEngine:
    """Coordinates poll timers, completion claims, and restart recovery."""

    vote_abuse = {}
    post_vote_list = {}
    _handler_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
    _handler_locks_guard = threading.Lock()

    @classmethod
    def _lock_for_handler(cls, handler: object) -> threading.Lock:
        """Return a process-wide lock for a shared post-vote handler instance.

        Args:
            handler: Mutable post-vote instance from ``post_vote_list``.

        Returns:
            Lock shared by all engine instances for this handler object.
        """
        with cls._handler_locks_guard:
            lock = cls._handler_locks.get(handler)
            if lock is None:
                lock = threading.Lock()
                cls._handler_locks[handler] = lock
            return lock

    @staticmethod
    def _handler_succeeded(outcome: object) -> bool:
        """Interpret a post-vote return value per the lifecycle outcome protocol.

        Args:
            outcome: Handler return value (``True``, ``False``, or legacy ``None``).

        Returns:
            True when the outcome means durable success; False for controlled failure.
        """
        return outcome is not False

    def auto_restart_polls(self) -> None:
        """Recover incomplete polls after restart (runs after plugin construction).

        Future ``open`` polls are rescheduled for their remaining duration.
        Expired ``open``, ``failed``, and stranded ``completing`` rows are
        retried immediately. Completed rows are never listed by the repository.
        """
        time_now = int(time.time())
        records = sqlWorker.get_recoverable_polls()
        for record in records:
            unique_id = record[0]
            message_vote_id = record[1]
            timer = record[5]
            state = record[10]

            # Code for backward compatibility, needs to be removed in the future
            try:
                os.remove(data.path + unique_id)
            except IOError:
                pass
            # End of code section for backward compatibility

            if state == "open" and timer > time_now:
                threading.Thread(
                    target=self.vote_timer,
                    daemon=True,
                    args=(timer - time_now, unique_id, message_vote_id),
                ).start()
                logging.info(
                    "poll lifecycle unique_id=%s transition=reschedule "
                    "state=%s remaining_s=%s",
                    unique_id,
                    state,
                    timer - time_now,
                )
            else:
                logging.info(
                    "poll lifecycle unique_id=%s transition=recovery_retry "
                    "state=%s",
                    unique_id,
                    state,
                )
                # Stranded completing is requeued only from restart recovery.
                # Live hot-path contenders treat completing as claim-lost.
                if state == "completing":
                    if not sqlWorker.requeue_for_retry(unique_id):
                        logging.info(
                            "poll lifecycle unique_id=%s "
                            "transition=requeue_skipped from_state=completing",
                            unique_id,
                        )
                        continue
                    logging.info(
                        "poll lifecycle unique_id=%s "
                        "transition=completing→open",
                        unique_id,
                    )
                self.vote_result(unique_id, message_vote_id)

    def vote_timer(self, current_timer, unique_id, message_vote_id) -> None:
        """Sleep until expiry, then attempt completion for ``unique_id``.

        Args:
            current_timer: Seconds to wait before completion.
            unique_id: Logical poll primary key.
            message_vote_id: Displayed Telegram message id (identity check).
        """
        time.sleep(current_timer)
        self.vote_abuse.clear()
        self.vote_result(unique_id, message_vote_id)

    def vote_result(self, unique_id, message_vote_id) -> None:
        """Claim completion, run the post-vote handler, then mark terminal state.

        Claim losers perform no handler work. Success path is
        ``claim → handler → mark_completed → delete_completed``. Controlled
        failure, missing handler, or raised exceptions mark ``failed`` and
        retain the row for restart recovery.

        Live ``completing`` is treated as claim-lost (no requeue). Only
        ``failed`` rows are requeued on this hot path; stranded ``completing``
        is requeued solely from :meth:`auto_restart_polls`.

        Args:
            unique_id: Logical poll primary key.
            message_vote_id: Expected Telegram message id for this poll.
        """
        rows = sqlWorker.get_poll_by_unique_id(unique_id)
        if not rows:
            return
        records = rows[0]

        if records[1] != message_vote_id:
            return

        state = records[10]
        if state == "completed":
            return

        # Live completing means another contender already claimed; do not
        # steal the claim. Stranded completing is requeued only in recovery.
        if state == "completing":
            logging.info(
                "poll lifecycle unique_id=%s transition=claim_lost "
                "from_state=completing",
                unique_id,
            )
            return

        if state == "failed":
            if not sqlWorker.requeue_for_retry(unique_id):
                logging.info(
                    "poll lifecycle unique_id=%s transition=requeue_skipped "
                    "from_state=failed",
                    unique_id,
                )
                return
            logging.info(
                "poll lifecycle unique_id=%s transition=failed→open",
                unique_id,
            )
        elif state != "open":
            return

        if not sqlWorker.claim_completion(unique_id):
            logging.info(
                "poll lifecycle unique_id=%s transition=claim_lost",
                unique_id,
            )
            return

        logging.info(
            "poll lifecycle unique_id=%s transition=open→completing",
            unique_id,
        )

        # Re-fetch after claim so the handler sees post-claim row contents
        # (avoids a stale pre-claim snapshot vs late open-state mutations).
        claimed_rows = sqlWorker.get_poll_by_unique_id(unique_id)
        if not claimed_rows:
            logging.error(
                "poll lifecycle unique_id=%s transition=completing→failed "
                "handler_type=missing reason=row_vanished_after_claim",
                unique_id,
            )
            sqlWorker.mark_failed(unique_id)
            return
        records = claimed_rows[0]

        vote_type = records[2]
        handler = self.post_vote_list.get(vote_type)
        if handler is None:
            logging.error(
                "poll lifecycle unique_id=%s transition=completing→failed "
                "handler_type=missing vote_type=%s",
                unique_id,
                vote_type,
            )
            sqlWorker.mark_failed(unique_id)
            try:
                bot.edit_message_text(
                    "Ошибка применения результатов голосования. "
                    "Итоговая функция не найдена!",
                    records[3],
                    records[1],
                )
            except Exception as e:
                logging.error(
                    "poll lifecycle unique_id=%s notify_missing_handler "
                    "error_class=%s",
                    unique_id,
                    type(e).__name__,
                )
            return

        handler_name = type(handler).__name__
        lock = self._lock_for_handler(handler)
        with lock:
            try:
                outcome = handler.post_vote(records)
            except Exception as e:
                logging.error(
                    "poll lifecycle unique_id=%s transition=completing→failed "
                    "handler_type=%s error_class=%s",
                    unique_id,
                    handler_name,
                    type(e).__name__,
                )
                logging.error(traceback.format_exc())
                sqlWorker.mark_failed(unique_id)
                return

            if not self._handler_succeeded(outcome):
                logging.info(
                    "poll lifecycle unique_id=%s transition=completing→failed "
                    "handler_type=%s reason=controlled_false",
                    unique_id,
                    handler_name,
                )
                sqlWorker.mark_failed(unique_id)
                return

            if not sqlWorker.mark_completed(unique_id):
                logging.error(
                    "poll lifecycle unique_id=%s transition=mark_completed_failed "
                    "handler_type=%s",
                    unique_id,
                    handler_name,
                )
                return

            logging.info(
                "poll lifecycle unique_id=%s transition=completing→completed "
                "handler_type=%s",
                unique_id,
                handler_name,
            )
            if sqlWorker.delete_completed(unique_id):
                logging.info(
                    "poll lifecycle unique_id=%s transition=completed→deleted "
                    "handler_type=%s",
                    unique_id,
                    handler_name,
                )
            else:
                logging.info(
                    "poll lifecycle unique_id=%s transition=delete_deferred "
                    "handler_type=%s",
                    unique_id,
                    handler_name,
                )

    def get_abuse_timer(self, call_msg):
        """Return whether the callback sender is still in the vote abuse window.

        Args:
            call_msg: Telegram callback query.

        Returns:
            True when the caller must wait; False when the window expired and
            was cleared; None when no abuse entry exists.
        """
        try:
            abuse_vote_timer = int(
                self.vote_abuse.get(
                    str(call_msg.message.id) + "." + str(call_msg.from_user.id)
                )
            )
        except TypeError:
            abuse_vote_timer = None

        if abuse_vote_timer is not None:
            if abuse_vote_timer + data.wait_timer > int(time.time()):
                please_wait = data.wait_timer - int(time.time()) + abuse_vote_timer
                bot.answer_callback_query(
                    callback_query_id=call_msg.id,
                    text="Вы слишком часто нажимаете кнопку. Пожалуйста, подождите ещё "
                    + f"{please_wait}с.",
                    show_alert=True,
                )
                return True
            else:
                self.vote_abuse.pop(
                    str(call_msg.message.id) + "." + str(call_msg.from_user.id),
                    None,
                )
                return False
        return None


poll_engine = PollEngine()
