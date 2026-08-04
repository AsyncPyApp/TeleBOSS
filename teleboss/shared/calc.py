import logging
import traceback


def calc_engine(calc_text, to_send):
    try:
        result = eval(calc_text.replace(',', '.').replace('^', '**'))
        if isinstance(result, float):
            result = round(result, 10)
            if result.is_integer():
                result = int(result)
        result = str(result)
    except SyntaxError:
        to_send.put("Неверно введено выражение для вычисления.")
        return
    except ZeroDivisionError:
        to_send.put(f"{calc_text}\n=деление на 0")
        return
    except ValueError as e:
        if 'Exceeds the limit' in str(e):
            to_send.put("Результат слишком большой для отправки.")
        else:
            logging.error(traceback.format_exc())
            to_send.put("Неизвестная ошибка вычисления! Информация сохранена в логи бота.")
        return
    except (OverflowError, MemoryError, RecursionError):
        to_send.put("Результат слишком большой для вычисления.")
        return
    except Exception:
        # Без этой ветки упавший дочерний процесс оставит очередь пустой,
        # и вызывающий поток заблокируется на to_send.get()
        logging.error(traceback.format_exc())
        to_send.put("Неизвестная ошибка вычисления! Информация сохранена в логи бота.")
        return
    result = result.replace('.', ',') if calc_text.count(',') >= calc_text.count('.') else result
    to_send.put(f"{calc_text}\n=<code>{result}</code>")
