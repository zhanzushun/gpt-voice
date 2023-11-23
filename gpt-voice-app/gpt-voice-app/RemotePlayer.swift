
import Foundation
import AVFoundation


enum PlayerState {
    case thinking
    case playing
    case done
}

class RemotePlayer: NSObject, ObservableObject {
    var player: AVPlayer?
    @Published var state: PlayerState = .done

    private func configureAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playback, mode: .default)
            try audioSession.setActive(true)
            print("完成语音功能初始化")
        } catch {
            print("Failed to set audio session category: \(error)")
        }
    }

    func thinkAndReply(sseManager: SSEManager, text: String) {
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            print("thinkAndReply: 空字符串")
            return
        }
        let base = "http://38.102.232.213:5012/api_12/think_and_reply"
        let user = "user_1"
        let messageId = "message_id_1"
        
        guard let encodedText = text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
            let encodedUser = user.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
            let encodedMsgId = messageId.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
            let url = URL(string: "\(base)?user=\(encodedUser)&message_id=\(encodedMsgId)&message=\(encodedText)") else { return }

        sseManager.connectToSSE(messageId: messageId)
        self._remoteVoice(url: url)
    }

    func remoteSpeech(text: String){
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            print("speech: 空字符串")
            return
        }
        let base = "http://38.102.232.213:5012/api_12/speech"
        guard let encodedText = text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(base)?text=\(encodedText)") else { return }
        self._remoteVoice(url: url)
    }

    func _remoteVoice(url: URL) {
        configureAudioSession()

        let playerItem = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: playerItem)

        playerItem.addObserver(self, forKeyPath: "loadedTimeRanges", options: [.new, .old], context: nil)
        
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: playerItem, queue: .main) { [weak self] _ in
            print("播放完成")
            self?.state = .done
            self?.removeObservers()
        }
        player?.play()
        self.state = .thinking
        print("开始连接远程播放")
    }

    override func observeValue(forKeyPath keyPath: String?, of object: Any?, change: [NSKeyValueChangeKey : Any]?, context: UnsafeMutableRawPointer?) {
        if keyPath == "loadedTimeRanges" {
            print("接收到音频数据")
            self.state = .playing
        }
    }

    private func removeObservers() {
        player?.currentItem?.removeObserver(self, forKeyPath: "loadedTimeRanges")
        NotificationCenter.default.removeObserver(self, name: .AVPlayerItemDidPlayToEndTime, object: player?.currentItem)
    }

    deinit {
        removeObservers()
    }
}

