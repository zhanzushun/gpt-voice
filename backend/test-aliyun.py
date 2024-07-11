TOKEN = ''
APPKEY = ''

import time
import threading
import nls
import random

# 用户信息
URL = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"

# 音频文件路径
audio_file = 'wav/recorded_audio.wav'

class MyCallback:
    def __init__(self, name='default'):
        self.name = name
    
    def on_sentence_begin(self, message, *args):
        print('识别开始: {}'.format(message))

    def on_sentence_end(self, message, *args):
        print('识别结束: {}'.format(message))

    def on_start(self, message, *args):
        print('识别启动: {}'.format(message))

    def on_error(self, message, *args):
        print('识别错误: {}'.format(message))

    def on_close(self, *args):
        print('识别通道关闭')

    def on_result_changed(self, message, *args):
        print('中间识别结果: {}'.format(message))

    def on_completed(self, message, *args):
        print('识别完成: {}'.format(message))

class SpeechRecognitionThread:
    def __init__(self, tid, test_file):
        self.__th = threading.Thread(target=self.__run)
        self.__id = tid
        self.__test_file = test_file
        self.__callback = MyCallback()

    def loadfile(self, filename):
        with open(filename, "rb") as f:
            self.__data = f.read()
            self.__data = self.__data[44:] # skip head

    def start(self):
        self.loadfile(self.__test_file)
        self.__th.start()

    def __run(self):
        print("thread:{} start..".format(self.__id))
        sr = nls.NlsSpeechTranscriber(
            url=URL,
            token=TOKEN,
            appkey=APPKEY,
            on_sentence_begin=self.__callback.on_sentence_begin,
            on_sentence_end=self.__callback.on_sentence_end,
            on_start=self.__callback.on_start,
            on_result_changed=self.__callback.on_result_changed,
            on_completed=self.__callback.on_completed,
            on_error=self.__callback.on_error,
            on_close=self.__callback.on_close,
            callback_args=[self.__id]
        )

        print("{}: session start".format(self.__id))
        r = sr.start(
            aformat="pcm",
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True
        )

        chunk_size = 3200  # 200ms的音频数据
        for i in range(0, len(self.__data), chunk_size):
            chunk = self.__data[i:i + chunk_size]
            sr.send_audio(chunk)
            pause_time = random.uniform(0.1, 0.5)
            print(f"停顿 {pause_time:.2f} 秒")
            time.sleep(pause_time)

        sr.ctrl(ex={"test": "tttt"})
        time.sleep(1)

        r = sr.stop()
        print("{}: sr stopped:{}".format(self.__id, r))
        time.sleep(1)


nls.enableTrace(False)
name = "thread1"
t = SpeechRecognitionThread(name, audio_file)
t.start()
