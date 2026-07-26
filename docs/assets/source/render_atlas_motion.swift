#!/usr/bin/env swift

import AVFoundation
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum MotionError: Error {
    case badArguments
    case cannotLoadImage(String)
    case cannotCreateDestination
    case cannotCreatePixelBuffer
    case cannotCreateContext
    case writerFailure(String)
}

func loadImage(_ path: String) throws -> CGImage {
    let url = URL(fileURLWithPath: path) as CFURL
    guard
        let source = CGImageSourceCreateWithURL(url, nil),
        let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        throw MotionError.cannotLoadImage(path)
    }
    return image
}

func writeGif(paths: [String], destination: String) throws {
    guard
        let output = CGImageDestinationCreateWithURL(
            URL(fileURLWithPath: destination) as CFURL,
            UTType.gif.identifier as CFString,
            paths.count,
            nil
        )
    else {
        throw MotionError.cannotCreateDestination
    }
    CGImageDestinationSetProperties(
        output,
        [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]] as CFDictionary
    )
    for path in paths {
        let image = try loadImage(path)
        let properties = [
            kCGImagePropertyGIFDictionary: [
                kCGImagePropertyGIFDelayTime: 1.35,
                kCGImagePropertyGIFUnclampedDelayTime: 1.35,
            ]
        ] as CFDictionary
        CGImageDestinationAddImage(output, image, properties)
    }
    guard CGImageDestinationFinalize(output) else {
        throw MotionError.cannotCreateDestination
    }
}

func pixelBuffer(from image: CGImage, width: Int, height: Int) throws -> CVPixelBuffer {
    var buffer: CVPixelBuffer?
    let attributes: [CFString: Any] = [
        kCVPixelBufferCGImageCompatibilityKey: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey: true,
    ]
    let status = CVPixelBufferCreate(
        kCFAllocatorDefault,
        width,
        height,
        kCVPixelFormatType_32ARGB,
        attributes as CFDictionary,
        &buffer
    )
    guard status == kCVReturnSuccess, let buffer else {
        throw MotionError.cannotCreatePixelBuffer
    }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard
        let context = CGContext(
            data: CVPixelBufferGetBaseAddress(buffer),
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue
        )
    else {
        throw MotionError.cannotCreateContext
    }
    context.setFillColor(CGColor(red: 7 / 255, green: 10 / 255, blue: 16 / 255, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.interpolationQuality = .high
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return buffer
}

func writeVideo(paths: [String], destination: String) throws {
    let width = 1600
    let height = 900
    let fps: Int32 = 30
    let framesPerSlide = Int(fps) * 5
    let url = URL(fileURLWithPath: destination)
    try? FileManager.default.removeItem(at: url)
    let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
    let settings: [String: Any] = [
        AVVideoCodecKey: AVVideoCodecType.h264,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [
            AVVideoAverageBitRateKey: 4_000_000,
            AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        ],
    ]
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: input,
        sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
            kCVPixelBufferWidthKey as String: width,
            kCVPixelBufferHeightKey as String: height,
        ]
    )
    guard writer.canAdd(input) else {
        throw MotionError.writerFailure("cannot add video input")
    }
    writer.add(input)
    guard writer.startWriting() else {
        throw MotionError.writerFailure(writer.error?.localizedDescription ?? "start failed")
    }
    writer.startSession(atSourceTime: .zero)

    var frameNumber: Int64 = 0
    for path in paths {
        let image = try loadImage(path)
        let buffer = try pixelBuffer(from: image, width: width, height: height)
        for _ in 0..<framesPerSlide {
            while !input.isReadyForMoreMediaData {
                Thread.sleep(forTimeInterval: 0.002)
            }
            let time = CMTime(value: frameNumber, timescale: fps)
            guard adaptor.append(buffer, withPresentationTime: time) else {
                throw MotionError.writerFailure(writer.error?.localizedDescription ?? "append failed")
            }
            frameNumber += 1
        }
    }
    input.markAsFinished()
    let semaphore = DispatchSemaphore(value: 0)
    writer.finishWriting { semaphore.signal() }
    semaphore.wait()
    guard writer.status == .completed else {
        throw MotionError.writerFailure(writer.error?.localizedDescription ?? "finish failed")
    }
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard arguments.count >= 3 else {
    throw MotionError.badArguments
}

switch arguments[0] {
case "gif":
    try writeGif(paths: Array(arguments.dropFirst(2)), destination: arguments[1])
case "video":
    try writeVideo(paths: Array(arguments.dropFirst(2)), destination: arguments[1])
default:
    throw MotionError.badArguments
}
