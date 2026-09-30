#!/usr/bin/env swift
// Terminal use: invoked via `swift what-coreaudio-tap.swift` — TCC is attributed to
// the terminal app (Terminal.app, iTerm2, …) which already has Screen Recording.
//
// Electron use: compiled into WhatCoreAudioTap.app and launched via `open -n` so
// LaunchServices starts it in its own audit session under launchd, making
// com.what.coreaudio-tap the TCC responsible process independently of Electron.
// Use --socket-path <path> so PCM flows over a Unix socket rather than stdout.
import Foundation
import ScreenCaptureKit
import CoreMedia
import Darwin

// MARK: - Arg parsing

struct Config {
    var sampleRate: Int = 16000
    var channels: Int = 1
    var frameMs: Int = 30
    var testTone: Bool = false
    var socketPath: String? = nil
    // When true: don't exit on 10s no-client timeout or on all-clients-disconnect.
    // Use with a LaunchAgent so the tap stays alive between Electron sessions.
    var persistent: Bool = false
}

func parseArgs() -> Config {
    var cfg = Config()
    var i = 1
    while i < CommandLine.arguments.count {
        let arg = CommandLine.arguments[i]
        switch arg {
        case "--sample-rate":
            i += 1
            if i < CommandLine.arguments.count { cfg.sampleRate = Int(CommandLine.arguments[i]) ?? cfg.sampleRate }
        case "--channels":
            i += 1
            if i < CommandLine.arguments.count { cfg.channels = Int(CommandLine.arguments[i]) ?? cfg.channels }
        case "--frame-ms":
            i += 1
            if i < CommandLine.arguments.count { cfg.frameMs = Int(CommandLine.arguments[i]) ?? cfg.frameMs }
        case "--test-tone":
            cfg.testTone = true
        case "--socket-path":
            i += 1
            if i < CommandLine.arguments.count { cfg.socketPath = CommandLine.arguments[i] }
        case "--persistent":
            cfg.persistent = true
        default:
            fputs("unknown argument: \(arg)\n", stderr)
        }
        i += 1
    }
    return cfg
}

// MARK: - Unix socket server

final class SocketServer {
    private let serverFD: Int32
    private var clientFDs: [Int32] = []
    private let lock = NSLock()
    private var everConnected = false
    private let persistent: Bool

    init?(path: String, persistent: Bool = false) {
        self.persistent = persistent
        Darwin.unlink(path)

        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let pathBytes = path.utf8CString
        withUnsafeMutableBytes(of: &addr.sun_path) { dest in
            pathBytes.withUnsafeBytes { src in
                _ = Darwin.memcpy(dest.baseAddress!, src.baseAddress!, min(dest.count, src.count))
            }
        }

        let bound: Int32 = withUnsafePointer(to: &addr) { p in
            p.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                Darwin.bind(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard bound == 0, Darwin.listen(fd, 5) == 0 else {
            Darwin.close(fd); return nil
        }
        self.serverFD = fd

        // Accept incoming connections in background
        DispatchQueue.global(qos: .background).async { [weak self] in self?.acceptLoop() }

        // In non-persistent mode: exit if no client connects within 10 s
        if !persistent {
            DispatchQueue.global().asyncAfter(deadline: .now() + 10) { [weak self] in
                guard let self else { return }
                self.lock.lock()
                let connected = self.everConnected
                self.lock.unlock()
                if !connected {
                    fputs("[tap] no socket client after 10s, exiting\n", stderr)
                    exit(1)
                }
            }
        }
    }

    func writeToClients(_ ptr: UnsafeRawPointer, _ count: Int) {
        lock.lock()
        let clients = clientFDs
        lock.unlock()
        guard !clients.isEmpty else { return }

        var dead: [Int32] = []
        for fd in clients {
            var remaining = count
            var offset = 0
            while remaining > 0 {
                let n = Darwin.write(fd, ptr.advanced(by: offset), remaining)
                if n <= 0 { dead.append(fd); break }
                offset += n; remaining -= n
            }
        }
        if !dead.isEmpty {
            lock.lock()
            for fd in dead { Darwin.close(fd) }
            clientFDs.removeAll { dead.contains($0) }
            let empty = clientFDs.isEmpty
            lock.unlock()
            if empty {
                if !persistent {
                    fputs("[tap] all clients disconnected, exiting\n", stderr)
                    exit(0)
                } else {
                    fputs("[tap] all clients disconnected, waiting for next connection\n", stderr)
                }
            }
        }
    }

    private func acceptLoop() {
        while true {
            let cfd = Darwin.accept(serverFD, nil, nil)
            guard cfd >= 0 else { break }
            lock.lock()
            clientFDs.append(cfd)
            everConnected = true
            lock.unlock()
            fputs("[tap] socket client connected\n", stderr)
        }
    }
}

// Global socket server — set before capture starts
var gSocketServer: SocketServer? = nil

// Write PCM to socket clients or stdout
@inline(__always)
func writePCM(_ ptr: UnsafeRawPointer, _ count: Int) {
    if let srv = gSocketServer {
        srv.writeToClients(ptr, count)
    } else {
        _ = Darwin.write(STDOUT_FILENO, ptr, count)
    }
}

// MARK: - Tone generator (no audio permissions needed)

func runTestTone(sampleRate: Int, channels: Int, frameMs: Int) {
    signal(SIGPIPE, SIG_IGN)
    let freq = 440.0
    let frameSize = sampleRate * frameMs / 1000
    let bufferSize = frameSize * channels
    var buffer = [Int16](repeating: 0, count: bufferSize)
    var phase = 0.0
    let phaseInc = 2.0 * Double.pi * freq / Double(sampleRate)
    let amplitude: Double = 16384.0
    while true {
        for f in 0..<frameSize {
            let sample = Int16(amplitude * sin(phase))
            for ch in 0..<channels { buffer[f * channels + ch] = sample }
            phase += phaseInc
            if phase > 2.0 * Double.pi { phase -= 2.0 * Double.pi }
        }
        buffer.withUnsafeBytes { ptr in writePCM(ptr.baseAddress!, ptr.count) }
    }
}

// MARK: - SCStream audio capture

@available(macOS 13.0, *)
final class AudioCapture: NSObject, SCStreamDelegate, SCStreamOutput {
    private let outRate: Int
    private let outChannels: Int

    private var inRate: Double = 0
    private var phase: Double = 0.0

    private let writeBuf: UnsafeMutablePointer<Int16>
    private let writeBufCap: Int

    // ABL backing sized for up to 2 channels: UInt32(4) + 2×AudioBuffer(12) = 28 bytes
    private var ablBacking: (UInt32, AudioBuffer, AudioBuffer) =
        (0, AudioBuffer(mNumberChannels: 0, mDataByteSize: 0, mData: nil),
            AudioBuffer(mNumberChannels: 0, mDataByteSize: 0, mData: nil))

    init(sampleRate: Int, channels: Int) {
        self.outRate = sampleRate
        self.outChannels = channels
        self.writeBufCap = sampleRate + 256
        self.writeBuf = UnsafeMutablePointer<Int16>.allocate(capacity: writeBufCap)
    }
    deinit { writeBuf.deallocate() }

    func stream(_ s: SCStream, didOutputSampleBuffer buf: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }

        if inRate == 0, let fmt = CMSampleBufferGetFormatDescription(buf),
           let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt) {
            inRate = asbd.pointee.mSampleRate
        }
        let actualInRate = inRate > 0 ? inRate : Double(outRate)

        var blockBuf: CMBlockBuffer?
        let ablStatus: OSStatus = withUnsafeMutablePointer(to: &ablBacking) { p in
            CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
                buf, bufferListSizeNeededOut: nil,
                bufferListOut: UnsafeMutableRawPointer(p).assumingMemoryBound(to: AudioBufferList.self),
                bufferListSize: MemoryLayout.size(ofValue: ablBacking),
                blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
                flags: 0, blockBufferOut: &blockBuf)
        }
        guard ablStatus == noErr, let dataPtr = ablBacking.1.mData else { return }
        defer { blockBuf = nil }

        let numBytes = Int(ablBacking.1.mDataByteSize)
        guard numBytes >= 4 else { return }

        let floats = dataPtr.assumingMemoryBound(to: Float.self)
        let numFrames = numBytes / 4
        let ratio = actualInRate / Double(outRate)

        if ratio > 0.999 && ratio < 1.001 {
            let frames = min(numFrames, writeBufCap / outChannels)
            for i in 0..<frames {
                let pcm = Int16(max(-32768.0, min(32767.0, floats[i] * 32767.0)))
                for ch in 0..<outChannels { writeBuf[i * outChannels + ch] = pcm }
            }
            writePCM(writeBuf, frames * outChannels * 2)
            return
        }

        var outCount = 0
        while phase < Double(numFrames) && outCount < writeBufCap {
            let idx = Int(phase)
            let frac = Float(phase - Double(idx))
            let nextIdx = min(idx + 1, numFrames - 1)
            let sample = (1.0 - frac) * floats[idx] + frac * floats[nextIdx]
            let pcm = Int16(max(-32768.0, min(32767.0, sample * 32767.0)))
            for _ in 0..<outChannels { writeBuf[outCount] = pcm; outCount += 1 }
            phase += ratio
        }
        phase -= Double(numFrames)
        if outCount > 0 { writePCM(writeBuf, outCount * 2) }
    }

    func stream(_ s: SCStream, didStopWithError e: Error) {
        fputs("[tap] stream stopped: \(e)\n", stderr)
        exit(1)
    }
}

@available(macOS 13.0, *)
func runCapture(sampleRate: Int, channels: Int, frameMs: Int) {
    signal(SIGPIPE, SIG_IGN)

    let capturer = AudioCapture(sampleRate: sampleRate, channels: channels)
    var liveStream: AnyObject? = nil

    Task { @MainActor in
        do {
            let content = try await SCShareableContent.current
            guard let disp = content.displays.first else {
                fputs("[tap] no displays available\n", stderr); exit(2)
            }

            let cfg = SCStreamConfiguration()
            cfg.capturesAudio = true
            cfg.excludesCurrentProcessAudio = false
            cfg.width = 2
            cfg.height = 2
            cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
            cfg.showsCursor = false

            let filter = SCContentFilter(display: disp, excludingApplications: [], exceptingWindows: [])
            let stream = SCStream(filter: filter, configuration: cfg, delegate: capturer)
            let audioQ = DispatchQueue(label: "com.what.audio", qos: .userInteractive)
            let videoQ = DispatchQueue(label: "com.what.video-discard", qos: .background)
            try stream.addStreamOutput(capturer, type: .screen, sampleHandlerQueue: videoQ)
            try stream.addStreamOutput(capturer, type: .audio, sampleHandlerQueue: audioQ)
            try await stream.startCapture()
            liveStream = stream
            fputs("[tap] SCStream running — sampleRate=\(sampleRate) channels=\(channels)\n", stderr)

        } catch {
            let desc = error.localizedDescription
            if desc.contains("declined") || desc.contains("TCC") || (error as NSError).code == -3801 {
                fputs("Operation not permitted: grant Screen Recording to WhatCoreAudioTap in\n" +
                      "System Settings → Privacy & Security → Screen & System Audio Recording.\n", stderr)
                exit(1)
            }
            fputs("[tap] error: \(error)\n", stderr)
            exit(2)
        }
    }

    RunLoop.main.run()
    _ = liveStream
}

// MARK: - Entry point

let config = parseArgs()

if let sp = config.socketPath {
    guard let srv = SocketServer(path: sp, persistent: config.persistent) else {
        fputs("[tap] failed to create socket at \(sp)\n", stderr)
        exit(1)
    }
    gSocketServer = srv
    fputs("[tap] listening on \(sp)\(config.persistent ? " (persistent)" : "")\n", stderr)
}

if config.testTone {
    runTestTone(sampleRate: config.sampleRate, channels: config.channels, frameMs: config.frameMs)
} else if #available(macOS 13.0, *) {
    runCapture(sampleRate: config.sampleRate, channels: config.channels, frameMs: config.frameMs)
} else {
    fputs("error: macOS 13.0 or later required for SCStream audio capture.\n", stderr)
    exit(3)
}
