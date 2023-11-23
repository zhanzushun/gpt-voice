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
                            humanText = "hello" // TODO
                            remotePlayer.thinkAndReply(sseManager: sseManager, text: humanText)
                        } else {
                            print("开始录音")
                            audioRecorder.startRecording()
                        }
                    }) {
                        Image(systemName: audioRecorder.isRecording ? "mic.slash.fill" : "mic.fill")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 50, height: 50)
                            .foregroundColor(.white)
                            .padding()
                    }

                    Button(action: { // 播放按钮
                        if remotePlayer.state == .done {
                            print("手动播放")
                            remotePlayer.remoteSpeech(text: sseManager.botText)
                        }
                        if audioRecorder.isRecording {
                            audioRecorder.stopRecording()
                        }
                    }) {
                        Image(systemName: (remotePlayer.state == .playing) ?  "speaker.slash.fill" : "speaker.3.fill")
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
    @State private var currentIndex: Int = 0

    var body: some View {
        HStack(spacing: 15) {
            ForEach(0..<6, id: \.self) { index in
                Circle()
                    .fill(Color.white)
                    .frame(width: 20, height: 20)
                    .opacity(currentIndex == index ? 1 : 0.5)
            }
        }
        .onAppear {
            withAnimation(Animation.easeInOut(duration: 0.5).repeatForever(autoreverses: false)) {
                self.currentIndex = (self.currentIndex + 1) % 6
            }
        }
    }
}


