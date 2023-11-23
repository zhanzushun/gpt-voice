import SwiftUI
import AVFoundation
import Speech

enum ViewState {
    case microphone
    case playable
}

struct ContentView: View {

    @State private var humanText = ""
    @State private var viewState: ViewState = .microphone

    @StateObject private var audioRecorder = AudioRecorder()
    @StateObject private var sseManager = SSEManager()
    @StateObject private var remotePlayer = RemotePlayer()

    func getUserId() -> String {
        if let userIdentifier = UserDefaults.standard.string(forKey: "UserIdentifier") {
            print("已存在的用户标识符：\(userIdentifier)")
            return userIdentifier
        } else {
            let newIdentifier = UUID().uuidString
            UserDefaults.standard.set(newIdentifier, forKey: "UserIdentifier")
            UserDefaults.standard.synchronize()
            print("新生成的用户标识符：\(newIdentifier)")
            return newIdentifier
        }
    }
    
    var body: some View {
        
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all) // 黑色背景

            VStack {
                Spacer()
                switch viewState {
                case .microphone:
                    if audioRecorder.isRecording {
                        RecordingView()
                    }
                case .playable:
                    Text(humanText).foregroundColor(.white).padding()
                    Text(sseManager.botText).foregroundColor(.white).padding()
                    Spacer()
                    if remotePlayer.state == .thinking {
                        ThinkingView()
                    }
                    else {
                        if remotePlayer.state == .playing {
                            PlayingView()
                        }
                    }
                }
                Spacer()
                HStack {
                    Button(action: { // 录音按钮
                        if audioRecorder.isRecording {
                            print("停止录音")
                            audioRecorder.stopRecording()
                            viewState = .playable
                            remotePlayer.thinkAndReply(sseManager: sseManager, userId: getUserId(), text: humanText)
                        } else {
                            print("开始录音")
                            audioRecorder.startRecording()
                            audioRecorder.transcription = ""
                            sseManager.botText = ""
                        }
                    }) {
                        Image(systemName: audioRecorder.isRecording ? "mic.slash.fill" : "mic.fill")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 50, height: 50)
                            .foregroundColor(.white)
                            .padding()
                    }
                }
            }
        }
        .onAppear {
            audioRecorder.requestAuthorization()
        }
        .onChange(of: audioRecorder.transcription) { newhumanText in
            print("人类说:" + newhumanText)
            self.humanText = newhumanText
        }
    }
}

// 录音界面的视图
struct RecordingView: View {
    @State private var isAnimating = false

    var body: some View {
        Circle()
            //.stroke(Color.white, lineWidth: 8)
            .fill(Color.white)
            .frame(width: 150, height: 150)
            .scaleEffect(isAnimating ? 1 : 0.9)
            .onAppear {
                withAnimation(Animation.easeInOut(duration: 1).repeatForever(autoreverses: true)) {
                    isAnimating = true
                }
            }
    }
}

// 播放界面的视图
struct PlayingView: View {
    @State private var isAnimating = false

    var body: some View {
        HStack(spacing: 30) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(Color.white)
                    .frame(width: 50, height: 50)
                    .scaleEffect(isAnimating ? 1 : 0.8)
            }
        }
        .onAppear {
            withAnimation(Animation.easeInOut(duration: 1).repeatForever(autoreverses: true)) {
                isAnimating = true
            }
        }
    }
}


struct ThinkingView: View {
    @State private var isAnimating = false

    var body: some View {
        ZStack {
            Circle()
                .frame(width: 120, height: 120) // 尺寸增加两倍
                .offset(x: -40, y: -40)        // 偏移量增加两倍
            Circle()
                .frame(width: 160, height: 160) // 尺寸增加两倍
            Circle()
                .frame(width: 120, height: 120) // 尺寸增加两倍
                .offset(x: 40, y: -20)         // 偏移量增加两倍
            Circle()
                .frame(width: 80, height: 80)  // 尺寸增加两倍
                .offset(x: 60, y: 40)          // 偏移量增加两倍
            Circle()
                .frame(width: 140, height: 140) // 尺寸增加两倍
                .offset(x: -60, y: 40)         // 偏移量增加两倍
        }
        .foregroundColor(.white)
        .scaleEffect(isAnimating ? 1.0 : 0.9)
        .animation(Animation.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: isAnimating)
        .onAppear {
            isAnimating = true
        }
    }
}
