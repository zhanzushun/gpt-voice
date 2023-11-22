//
//  SSEClient.swift
//  gpt-voice-app
//
//  Created by Zushun Zhan on 11/21/23.
//

import Foundation


class SSEClient: ObservableObject {
    @Published var receivedText: String = ""

    func connectToServer(prompt: String) {
        self.receivedText = "hello: " + prompt

//        guard let url = URL(string: "http://localhost/sse-endpoint") else { return }
//
//        let task = URLSession.shared.dataTask(with: url) { data, response, error in
//            guard let data = data, error == nil else { return }
//            // 假设服务器返回的是纯文本数据
//            if let text = String(data: data, encoding: .utf8) {
//                DispatchQueue.main.async {
//                    self.receivedText = text
//                }
//            }
//        }
//        task.resume()
    }
}

