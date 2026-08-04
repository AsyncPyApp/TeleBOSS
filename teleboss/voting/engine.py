import logging
import os
import threading
import time
import traceback

from teleboss.shared.runtime import bot, data, sqlWorker


class PollEngine:
    vote_abuse = {}
    post_vote_list = {}

    def auto_restart_polls(self):
        time_now = int(time.time())
        records = sqlWorker.get_all_polls()
        for record in records:

            # Code for backward compatibility, needs to be removed in the future
            try:
                os.remove(data.path + record[0])
            except IOError:
                pass
            # End of code section for backward compatibility

            if record[5] > time_now:
                threading.Thread(target=self.vote_timer, daemon=True,
                                 args=(record[5] - time_now, record[0], record[1])).start()
                logging.info("Restarted poll " + record[0])
            else:
                self.vote_result(record[0], record[1])

    def vote_timer(self, current_timer, unique_id, message_vote_id):
        time.sleep(current_timer)
        self.vote_abuse.clear()
        self.vote_result(unique_id, message_vote_id)

    def vote_result(self, unique_id, message_vote_id):

        records = sqlWorker.get_poll(message_vote_id)
        if not records:
            return
        records = records[0]

        if records[1] != message_vote_id:
            return

        sqlWorker.rem_rec(unique_id)

        try:
            self.post_vote_list[records[2]].post_vote(records)
        except KeyError:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка применения результатов голосования. Итоговая функция не найдена!",
                                  records[3], records[1])

    def get_abuse_timer(self, call_msg):
        try:
            abuse_vote_timer = int(self.vote_abuse.get(str(call_msg.message.id) + "." + str(call_msg.from_user.id)))
        except TypeError:
            abuse_vote_timer = None

        if abuse_vote_timer is not None:
            if abuse_vote_timer + data.wait_timer > int(time.time()):
                please_wait = data.wait_timer - int(time.time()) + abuse_vote_timer
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text="Вы слишком часто нажимаете кнопку. Пожалуйста, подождите ещё " +
                                               f"{please_wait}с.", show_alert=True)
                return True
            else:
                self.vote_abuse.pop(str(call_msg.message.id) + "." + str(call_msg.from_user.id), None)
                return False
        return None


poll_engine = PollEngine()
