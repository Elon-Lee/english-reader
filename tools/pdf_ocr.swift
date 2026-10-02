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

func processPage(_ page: PDFPage, index: Int, total: Int, requestedScale: Double) -> OCRPage? {
    let scales = [requestedScale, min(requestedScale, 1.3), min(requestedScale, 1.0), min(requestedScale, 0.8)].reduce(into: [Double]()) { values, value in
        if value > 0, !values.contains(where: { abs($0 - value) < 0.001 }) { values.append(value) }
    }
    var fallback: OCRPage?
    for attemptScale in scales {
        do {
            let result: OCRPage? = try autoreleasepool {
                let bounds = page.bounds(for: .cropBox)
                let pixelWidth = max(1, Int(bounds.width * attemptScale))
                let pixelHeight = max(1, Int(bounds.height * attemptScale))
                guard let context = CGContext(
                    data: nil,
                    width: pixelWidth,
                    height: pixelHeight,
                    bitsPerComponent: 8,
                    bytesPerRow: 0,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                ) else { throw NSError(domain: "ShiyueOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot create image context"]) }

                context.setFillColor(NSColor.white.cgColor)
                context.fill(CGRect(x: 0, y: 0, width: pixelWidth, height: pixelHeight))
                context.saveGState()
                context.scaleBy(x: attemptScale, y: attemptScale)
                page.draw(with: .cropBox, to: context)
                context.restoreGState()
                guard let image = context.makeImage() else { throw NSError(domain: "ShiyueOCR", code: 2, userInfo: [NSLocalizedDescriptionKey: "Cannot render page"]) }
                let bitmap = NSBitmapImageRep(cgImage: image)
                guard let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.84]) else {
                    throw NSError(domain: "ShiyueOCR", code: 3, userInfo: [NSLocalizedDescriptionKey: "Cannot encode page"])
                }
                let imageName = String(format: "page-%03d.jpg", index + 1)
                try jpeg.write(to: imageDirectory.appendingPathComponent(imageName))
                fallback = OCRPage(page: index + 1, width: pixelWidth, height: pixelHeight, image: imageName, lines: [])

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
                    return OCRLine(text: candidate.string, x: box.minX, y: box.minY, width: box.width, height: box.height, confidence: candidate.confidence)
                }
                return OCRPage(page: index + 1, width: pixelWidth, height: pixelHeight, image: imageName, lines: lines)
            }
            if let result {
                let scaleText = String(format: "%.1f", attemptScale)
                FileHandle.standardError.write(Data("OCR page \(index + 1)/\(total): \(result.lines.count) lines · scale \(scaleText)\n".utf8))
                return result
            }
        } catch {
            let scaleText = String(format: "%.1f", attemptScale)
            FileHandle.standardError.write(Data("OCR page \(index + 1)/\(total) retry at scale \(scaleText): \(error.localizedDescription)\n".utf8))
        }
    }
    if let fallback {
        FileHandle.standardError.write(Data("OCR page \(index + 1)/\(total): rendered without text after all retries\n".utf8))
    }
    return fallback
}

for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { continue }
    if let result = processPage(page, index: index, total: document.pageCount, requestedScale: scale) { pages.append(result) }
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
try encoder.encode(pages).write(to: outputURL)
