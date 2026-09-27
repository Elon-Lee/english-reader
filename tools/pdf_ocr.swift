import Foundation
import PDFKit
import Vision
import AppKit

struct OCRLine: Codable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let confidence: Float
}

struct OCRPage: Codable {
    let page: Int
    let width: Int
    let height: Int
    let image: String
    let lines: [OCRLine]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count >= 4 else {
    fail("Usage: pdf_ocr <input.pdf> <output.json> <image-directory> [scale]")
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let imageDirectory = URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true)
let scale = CommandLine.arguments.count > 4 ? (Double(CommandLine.arguments[4]) ?? 2.0) : 2.0

guard let document = PDFDocument(url: inputURL) else { fail("Cannot open PDF: \(inputURL.path)") }
try FileManager.default.createDirectory(at: imageDirectory, withIntermediateDirectories: true)

var pages: [OCRPage] = []

for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { continue }
    let bounds = page.bounds(for: .cropBox)
    let pixelWidth = max(1, Int(bounds.width * scale))
    let pixelHeight = max(1, Int(bounds.height * scale))

    guard let context = CGContext(
        data: nil,
        width: pixelWidth,
        height: pixelHeight,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { fail("Cannot create image context for page \(index + 1)") }

    context.setFillColor(NSColor.white.cgColor)
    context.fill(CGRect(x: 0, y: 0, width: pixelWidth, height: pixelHeight))
    context.saveGState()
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .cropBox, to: context)
    context.restoreGState()

    guard let image = context.makeImage() else { fail("Cannot render page \(index + 1)") }
    let bitmap = NSBitmapImageRep(cgImage: image)
    guard let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.84]) else {
        fail("Cannot encode page \(index + 1)")
    }
    let imageName = String(format: "page-%03d.jpg", index + 1)
    try jpeg.write(to: imageDirectory.appendingPathComponent(imageName))

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US", "zh-Hans"]
    request.usesLanguageCorrection = true
    request.minimumTextHeight = 0.009
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])

    let observations = (request.results ?? []).sorted {
        let rowDelta = abs($0.boundingBox.midY - $1.boundingBox.midY)
        if rowDelta < 0.012 { return $0.boundingBox.minX < $1.boundingBox.minX }
        return $0.boundingBox.midY > $1.boundingBox.midY
    }

    let lines = observations.compactMap { observation -> OCRLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return OCRLine(
            text: candidate.string,
            x: box.minX,
            y: box.minY,
            width: box.width,
            height: box.height,
            confidence: candidate.confidence
        )
    }
    pages.append(OCRPage(page: index + 1, width: pixelWidth, height: pixelHeight, image: imageName, lines: lines))
    FileHandle.standardError.write(Data("OCR page \(index + 1)/\(document.pageCount): \(lines.count) lines\n".utf8))
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
try encoder.encode(pages).write(to: outputURL)
