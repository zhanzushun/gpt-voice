
from deepgram import Deepgram
import asyncio
import json

import config


async def transcribe_audio(audio_file_path):
    # 初始化Deepgram客户端
    dg_client = Deepgram(config.DEEPGRAM_API_KEY)

    # 打开音频文件
    with open(audio_file_path, 'rb') as audio:
        # 发送转录请求
        source = {'buffer': audio, 'mimetype': 'audio/mp3'}
        response = await dg_client.transcription.prerecorded(
            source,
            {
                'smart_format': True,
                'model': 'general',
                 'language': 'zh-CN',  # 设置主要语言为中文
                'detect_language': True,  # 启用语言检测，以处理英文部分
                'punctuate': True,
                'diarize': True
            }
        )
    
    return response

async def main():
    audio_file = 'static/18616699733_20240720_094740_272.mp3'
    
    try:
        result = await transcribe_audio(audio_file)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"转录过程中出现错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())


# pip install deepgram-sdk==2.12.0