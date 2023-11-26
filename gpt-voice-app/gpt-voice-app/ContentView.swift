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
    @State private var showAlert = false
    @State private var cancelledLength = 0

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
                Text(humanText).foregroundColor(.white).padding()
                Text(sseManager.botText).foregroundColor(.white).padding()
                
                switch viewState {
                    
                case .microphone: // 麦克风界面 （静止状态 / 录音状态）

                    if audioRecorder.isRecording {
                        RecordingView()
                    }
                    
                    Spacer()
                    
                    HStack {
                        
                        Spacer()
                        
                        Button(action: { // 麦克风按钮（静止状态），停止并发送按钮（录音状态）
                            if audioRecorder.isRecording {
                                print("停止录音")
                                audioRecorder.stopRecording()
                                viewState = .playable
                                cancelledLength = 0
                                remotePlayer.thinkAndReply(sseManager: sseManager, userId: getUserId(), text: humanText)
                            } else {
                                print("开始录音")
                                audioRecorder.startRecording()
                                audioRecorder.transcription = ""
                                viewState = .microphone
                            }
                        }) {
                            Image(systemName: audioRecorder.isRecording ? "paperplane.fill" : "mic.fill")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 50, height: 50)
                                .foregroundColor(.white)
                                .padding()
                        }
                        
                        if audioRecorder.isRecording {
                            
                            Spacer()
                            
                            Button(action: { // 重录按钮（录音状态）
                                showAlert = true
                            }) {
                                ZStack {
                                    // 麦克风图标
                                    Image(systemName: "mic.fill")
                                        .font(.system(size: 50))
                                        .foregroundColor(.blue)
                                    // 循环/重载箭头图标
                                    Image(systemName: "arrow.counterclockwise")
                                        .font(.system(size: 20))
                                        .foregroundColor(.green)
                                        .offset(x: 20, y: 20) // 根据需要调整位置
                                }
                            }
                            .alert(isPresented: $showAlert) {
                                Alert(
                                    title: Text("确认"),
                                    message: Text("您是否要重新说一次？"),
                                    primaryButton: .destructive(Text("确认")) {
                                        // 处理确认操作
                                        cancelledLength = audioRecorder.transcription.count
                                        audioRecorder.transcription = ""
                                        print("重录操作已确认")
                                    },
                                    secondaryButton: .cancel(Text("取消")) {
                                        // 处理取消操作
                                        print("重录操作已取消")
                                    }
                                )
                            }
                        }
                        Spacer()
                    }
                    
                case .playable: // 播放界面 （静止状态/思考状态/播放状态）
                    Spacer()
                    if remotePlayer.state == .thinking {
                        ThinkingView()
                    }
                    else {
                        if remotePlayer.state == .playing {
                            PlayingView()
                        }
                    }
                    if (remotePlayer.state == .thinking) || (remotePlayer.state == .playing) {
                        Spacer()
                        Button(action: { // 停止按钮（思考或播放状态）
                            print("停止播放")
                            remotePlayer.stop()
                        }) {
                            Image(systemName: "square.fill")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 30, height: 30)
                                .foregroundColor(.white)
                                .padding()
                        }
                    }
                }
                Spacer()
                HStack {
                }
            }
        }
        .onAppear {
            audioRecorder.requestAuthorization()
        }
        .onChange(of: audioRecorder.transcription) { newhumanText in
            if newhumanText.count - self.cancelledLength > 0 {
                print("人类说:" + newhumanText.suffix(newhumanText.count - self.cancelledLength))
                self.humanText = "You: " + String(newhumanText.suffix(newhumanText.count - cancelledLength))
            }
            else {
                self.humanText = ""
            }
        }
        .onChange(of: remotePlayer.state) { newState in
            if newState == PlayerState.done {
                self.viewState = .microphone
            }
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
