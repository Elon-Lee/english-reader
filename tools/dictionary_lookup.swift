import Foundation
import CoreServices

for word in CommandLine.arguments.dropFirst() {
    let text = word as CFString
    let range = CFRange(location: 0, length: CFStringGetLength(text))
    if let value = DCSCopyTextDefinition(nil, text, range)?.takeRetainedValue() {
        print("WORD\t\(word)")
        print(value as String)
        print("END")
    } else {
        print("WORD\t\(word)\nEND")
    }
}
