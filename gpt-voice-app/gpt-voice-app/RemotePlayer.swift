
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
    var sseManager: SSEManager?

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

    func thinkAndReply(sseManager: SSEManager, userId:String, text: String) {
        self.sseManager = sseManager
        var text1 = text
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            print("thinkAndReply: 空字符串")
            text1 = "hello"
        }
        let base = "\(AppConfig.apiBaseUrl)/think_and_reply"
        let user = userId
        let messageId = UUID().uuidString
        
        guard let encodedText = text1.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
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
        let base = "\(AppConfig.apiBaseUrl)/speech"
        guard let encodedText = text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(base)?text=\(encodedText)") else { return }
        self._remoteVoice(url: url)
    }

    func _remoteVoice(url: URL) {
        configureAudioSession()

        let playerItem = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: playerItem)

        playerItem.addObserver(self, forKeyPath: "loadedTimeRanges", options: [.new, .old], context: nil)
        //playerItem.addObserver(self, forKeyPath: "status", options: [.new, .old], context: nil)
        
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: playerItem, queue: .main) { [weak self] _ in
            print("播放完成")
            DispatchQueue.main.async {
                self?.state = .done
            }
            self?.removeObservers()
        }
        player?.play()
        DispatchQueue.main.async {
            self.state = .thinking
        }
        print("开始连接远程播放")
    }

    override func observeValue(forKeyPath keyPath: String?, of object: Any?, change: [NSKeyValueChangeKey : Any]?, context: UnsafeMutableRawPointer?) {
        if let keyPath = keyPath, let playerItem = object as? AVPlayerItem {
            if keyPath == "loadedTimeRanges" {
                print("接收到音频数据")
                DispatchQueue.main.async {
                    self.state = .playing
                }
                return
            }
            if keyPath == "status" {
                switch playerItem.status {
                case .failed:
                    let s = ("播放时出错了: \(String(describing: playerItem.error))")
                    print(s)
                    DispatchQueue.main.async {
                        self.sseManager?.botText += "\n" + s
                    }
                    self.stop()
//                case .readyToPlay:
//                    print("接收到音频数据, 准备播放")
//                    DispatchQueue.main.async {
//                        self.state = .playing
//                    }
                case .unknown:
                    print("播放未知状态")
                @unknown default:
                    break
                }
                return
            }
            super.observeValue(forKeyPath: keyPath, of: object, change: change, context: context)
        }
    }

    func stop() {
        player?.pause()
        DispatchQueue.main.async {
            self.state = .done
        }
        self.removeObservers()
    }

    private func removeObservers() {
        player?.currentItem?.removeObserver(self, forKeyPath: "loadedTimeRanges")
        NotificationCenter.default.removeObserver(self, name: .AVPlayerItemDidPlayToEndTime, object: player?.currentItem)
    }

    deinit {
        removeObservers()
    }
}

