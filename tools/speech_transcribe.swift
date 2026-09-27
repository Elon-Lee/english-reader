import Foundation
import Speech

struct Word: Codable {
    let text: String
    let start: Double
    let duration: Double
    let confidence: Float
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count >= 3 else {
    fail("Usage: speech_transcribe <audio-file> <output.json>")
}

let audioURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let semaphore = DispatchSemaphore(value: 0)
var exitCode: Int32 = 0

SFSpeechRecognizer.requestAuthorization { status in
    guard status == .authorized else {
        FileHandle.standardError.write(Data("Speech recognition permission status: \(status.rawValue)\n".utf8))
        exitCode = 2
        semaphore.signal()
        return
    }

    guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")), recognizer.isAvailable else {
        FileHandle.standardError.write(Data("English speech recognizer is unavailable\n".utf8))
        exitCode = 3
        semaphore.signal()
        return
    }

    let request = SFSpeechURLRecognitionRequest(url: audioURL)
    request.shouldReportPartialResults = false
    request.addsPunctuation = true
    if #available(macOS 10.15, *), recognizer.supportsOnDeviceRecognition {
        request.requiresOnDeviceRecognition = true
    }

    recognizer.recognitionTask(with: request) { result, error in
        if let error = error {
            FileHandle.standardError.write(Data("Recognition error: \(error.localizedDescription)\n".utf8))
            exitCode = 4
            semaphore.signal()
            return
        }
        guard let result = result, result.isFinal else { return }
        let words = result.bestTranscription.segments.map {
            Word(text: $0.substring, start: $0.timestamp, duration: $0.duration, confidence: $0.confidence)
        }
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(words).write(to: outputURL)
            FileHandle.standardError.write(Data("Recognized \(words.count) words\n".utf8))
        } catch {
            FileHandle.standardError.write(Data("Cannot save transcription: \(error)\n".utf8))
            exitCode = 5
        }
        semaphore.signal()
    }
}

_ = semaphore.wait(timeout: .now() + 600)
exit(exitCode)
