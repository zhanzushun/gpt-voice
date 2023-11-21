import SwiftUI

struct ContentView: View {
    @State private var showRecording = false
    @State private var showPlaying = false

    var body: some View {
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all) // 黑色背景

            VStack {
                Spacer()

                // 根据状态显示录音界面或播放界面
                if showRecording {
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
                        // 切换录音界面的显示状态
                        self.showRecording.toggle()
                        // 确保播放界面不会同时显示
                        if showPlaying { showPlaying = false }
                    }) {
                        Image(systemName: "mic.fill")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 50, height: 50)
                            .foregroundColor(.white)
                            .padding()
                    }

                    Spacer()

                    // 音量按钮
                    Button(action: {
                        // 切换播放界面的显示状态
                        self.showPlaying.toggle()
                        // 确保录音界面不会同时显示
                        if showRecording { showRecording = false }
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


