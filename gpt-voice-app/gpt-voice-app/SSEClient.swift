import Foundation
import LDSwiftEventSource

class MyEventHandler: EventHandler {
    var onDoneReceived: (() -> Void)?
    var onTextReceived: ((String) -> Void)?

    func onOpened() {
        print("SSE打开了")
    }
    func onClosed() {
        print("SSE关闭了")
    }
    func onMessage(eventType: String, messageEvent: MessageEvent) {
        print("Received message: \(messageEvent.data)")
        if messageEvent.data == "done" {
            onDoneReceived?()
            print("SSE完成了")
        }
        else {
            print("SSE收到了:\(messageEvent.data)")
            onTextReceived?(messageEvent.data)
        }
    }
    func onComment(comment: String) {
        print("SSE COMMENT是什么: \(comment)")
    }
    func onError(error: Error) {
        print("SSE 出错了: \(error.localizedDescription)")
    }
}


class SSEManager: ObservableObject {
    @Published var botText: String = ""
    private var eventSource: EventSource?

    func connectToSSE(messageId: String) {
        let urlString = "\(AppConfig.apiBaseUrl)/sse/\(messageId)"
        guard let url = URL(string: urlString) else { return }
        let eventHandler = MyEventHandler()
        eventHandler.onDoneReceived = { [weak self] in
            self?.eventSource?.stop()
        }
        eventHandler.onTextReceived = { [weak self] text in
            DispatchQueue.main.async {
                self?.botText += " " + text
            }
        }
        let config = EventSource.Config(handler: eventHandler, url: url)
        eventSource = EventSource(config: config)
        eventSource?.start()
    }
}

