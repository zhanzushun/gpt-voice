import SwiftUI
import AVFoundation
import Speech

struct ContentView: View {
    @StateObject private var audioRecorder = AudioRecorder()
    @State private var humanText = ""
    @State private var botText = ""
    @State private var player: AVPlayer?
    @State private var showPlaying = false

    init() {
        configureAudioSession()
    }
    
    private func configureAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playback)
            try audioSession.setActive(true)
            print("完成语音功能初始化")
        } catch {
            print("Failed to set audio session category: \(error)")
        }
    }
    
    func playSpeech() {
        guard let url = URL(string: "http://38.102.232.213:5012/speech") else { return }
        let playerItem = AVPlayerItem(url: url)
        NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: playerItem,
            queue: .main
        ) { _ in
            self.botText = "这是好事儿啊"
            self.showPlaying.toggle()
        }
        player = AVPlayer(playerItem: playerItem)
        player?.play()
    }
    
    var body: some View {
        
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all) // 黑色背景

            VStack {
                
                Text(humanText)
                    .foregroundColor(.white)
                    .padding()

                // 显示从服务器接收到的文本
                Text(botText)
                    .foregroundColor(.white)
                    .padding()


                Spacer()

                // 根据状态显示录音界面或播放界面
                if audioRecorder.isRecording {
                    RecordingView()
                }
                if showPlaying {
                    PlayingView()
                }

                Spacer()

                HStack {
                    Spacer()

                    // 麦克风按钮
                    Button(action: {
                        if audioRecorder.isRecording {
                            print("停止录音被调用")
                            audioRecorder.stopRecording()
                            audioRecorder.sendTextToServer(text: self.humanText)
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
                    
                    Spacer()

                    // 音量按钮
                    Button(action: {
                        self.showPlaying.toggle()
                        // 确保录音界面不会同时显示
                        if audioRecorder.isRecording {
                            audioRecorder.stopRecording()
                        }
                    }) {
                        Image(systemName: "speaker.3.fill")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 50, height: 50)
                            .foregroundColor(.white)
                            .padding()
                    }

                    Spacer()
                }
            }
        }
        .onAppear {
            audioRecorder.requestAuthorization()
        }
        .onChange(of: showPlaying) { newShowPlaying in
            if newShowPlaying {
                playSpeech()
            }
            else {
            }
        }
        .onChange(of: audioRecorder.transcription) { newhumanText in
            print("stt:" + newhumanText)
            self.humanText = newhumanText
        }
        .onChange(of: audioRecorder.sseClient.receivedText) { newText in
            print("从服务端返回: " + newText)
            self.botText = newText
            self.showPlaying = true
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


