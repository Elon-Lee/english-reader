import AppKit

let args = CommandLine.arguments
guard args.count == 5,
      let source = NSImage(contentsOfFile: args[1]) else {
    fatalError("Usage: render_promo_frame.swift input title subtitle output")
}

let size = NSSize(width: 1080, height: 1920)
let canvas = NSImage(size: size)
canvas.lockFocus()
NSColor(calibratedRed: 0.961, green: 0.949, blue: 0.918, alpha: 1).setFill()
NSRect(origin: .zero, size: size).fill()

let sourceSize = source.size
let scale = min(960 / sourceSize.width, 1160 / sourceSize.height)
let drawSize = NSSize(width: sourceSize.width * scale, height: sourceSize.height * scale)
let imageRect = NSRect(x: (1080 - drawSize.width) / 2, y: 380 + (1160 - drawSize.height) / 2,
                       width: drawSize.width, height: drawSize.height)
source.draw(in: imageRect)

func drawCentered(_ text: String, y: CGFloat, size: CGFloat, color: NSColor, weight: NSFont.Weight) {
    let font = NSFont.systemFont(ofSize: size, weight: weight)
    let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color]
    let rendered = NSAttributedString(string: text, attributes: attrs)
    rendered.draw(at: NSPoint(x: (1080 - rendered.size().width) / 2, y: y))
}

drawCentered(args[2], y: 1680, size: 58,
             color: NSColor(calibratedRed: 0.09, green: 0.25, blue: 0.20, alpha: 1), weight: .bold)
drawCentered(args[3], y: 1588, size: 29,
             color: NSColor(calibratedRed: 0.32, green: 0.44, blue: 0.39, alpha: 1), weight: .regular)
drawCentered("拾页  SHIYE ENGLISH WORKSPACE", y: 68, size: 28,
             color: NSColor(calibratedRed: 0.09, green: 0.25, blue: 0.20, alpha: 1), weight: .semibold)
canvas.unlockFocus()

guard let tiff = canvas.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Could not encode frame")
}
try png.write(to: URL(fileURLWithPath: args[4]))
