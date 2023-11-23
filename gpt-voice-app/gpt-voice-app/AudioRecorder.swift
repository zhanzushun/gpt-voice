//
//  AudioRecorder.swift
//  gpt-voice-app
//
//  Created by Zushun Zhan on 11/21/23.
//

import Foundation
import AVFoundation
import Speech

class AudioRecorder: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var transcription = ""

    private let audioEngine = AVAudioEngine()
    private let speechRecognizer = SFSpeechRecognizer()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?

    override init() {
        super.init()
        speechRecognizer?.delegate = self
    }

    func startRecording() {
        isRecording = true
        // 确保没有正在进行的识别任务
        if recognitionTask != nil {
            recognitionTask?.cancel()
            recognitionTask = nil
        }

        // 配置音频会话
        let audioSession = AVAudioSession.sharedInstance()
        try! audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
        try! audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()

        let inputNode = audioEngine.inputNode
        guard let recognitionRequest = recognitionRequest else { return }

        recognitionRequest.shouldReportPartialResults = true

        // 启动语音识别任务
        recognitionTask = speechRecognizer?.recognitionTask(with: recognitionRequest) { result, error in
           var isFinal = false

            if let result = result {
                self.transcription = result.bestTranscription.formattedString
                isFinal = result.isFinal
            }

            if error != nil || isFinal {
                self.audioEngine.stop()
                inputNode.removeTap(onBus: 0)
                self.recognitionRequest = nil
                self.recognitionTask = nil
                self.isRecording = false
            }
        }

        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { (buffer, _) in
            self.recognitionRequest?.append(buffer)
        }

        audioEngine.prepare()
        try! audioEngine.start()
    }

    func stopRecording() {
        audioEngine.stop()
        recognitionRequest?.endAudio()
        isRecording = false
    }

    func requestAuthorization() {
        SFSpeechRecognizer.requestAuthorization { authStatus in
            // 处理授权结果...
        }
    }
}

extension AudioRecorder: SFSpeechRecognizerDelegate {
    // 处理语音识别器的可用性更改
    func speechRecognizer(_ speechRecognizer: SFSpeechRecognizer, availabilityDidChange available: Bool) {
        if !available {
            // 处理不可用的情况
        }
    }
}

